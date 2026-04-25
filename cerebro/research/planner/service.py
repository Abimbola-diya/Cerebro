"""Planner orchestration service for Step 0."""

from __future__ import annotations

import json
import logging
import os
import random
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

from cerebro.research.errors import ModelSelectionError, PlannerError, PlannerValidationError
from cerebro.research.sources.registry import SourceRegistry, registry
from cerebro.research.telemetry.tracer import PlannerTrace

from .model_catalog import DEFAULT_PLANNER_MODELS, PlannerModel
from .prompt_builder import build_system_prompt, build_user_prompt
from .selector import ModelSelector
from .thinking_stream import ThinkingStreamExtractor
from .validator import PlannerValidator


logger = logging.getLogger(__name__)


class ResearchPlanner:
    """Generate robust seven-dimension research plans with model fallback."""

    def __init__(
        self,
        *,
        source_registry: SourceRegistry | None = None,
        models: list[PlannerModel] | None = None,
    ) -> None:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise PlannerError("openai package is required for ResearchPlanner") from exc

        self._source_registry = source_registry or registry
        self._validator = PlannerValidator(self._source_registry)
        self._stream_timeout_seconds = _load_stream_timeout_seconds()
        self._planner_timeout_seconds = _load_planner_timeout_seconds()
        self._planner_min_attempts = _load_planner_min_attempts()
        self._stream_excluded_model_ids = _load_stream_excluded_model_ids()
        self._openrouter_reasoning_effort = _load_openrouter_reasoning_effort()
        self._openrouter_reasoning_max_tokens = _load_openrouter_reasoning_max_tokens()
        self._nvidia_temperature = _load_float_env("NVIDIA_TEMPERATURE", default=0.55, minimum=0.0, maximum=1.0)
        self._nvidia_top_p = _load_float_env("NVIDIA_TOP_P", default=1.0, minimum=0.0, maximum=1.0)
        self._nvidia_random_seed = _load_bool_env("NVIDIA_RANDOM_SEED", default=True)
        self._nvidia_fixed_seed = _load_int_env("NVIDIA_FIXED_SEED", default=0, minimum=0)
        self._nvidia_thinking_enabled = _load_bool_env("NVIDIA_THINKING_ENABLED", default=False)
        self._nvidia_thinking_models = _load_csv_env(
            "NVIDIA_THINKING_MODELS",
            default=(
                "nvidia/llama-3.3-nemotron-super-49b-v1,"
                "nvidia/nemotron-3-super-120b-a12b"
            ),
        )
        self._nvidia_reasoning_budget = _load_int_env("NVIDIA_REASONING_BUDGET", default=16384, minimum=0)

        github_token = os.environ.get("GITHUB_TOKEN")
        openrouter_key = os.environ.get("OPENROUTER_API_KEY")
        cerebras_key = os.environ.get("CEREBRAS_API_KEY")
        deepseek_key = os.environ.get("DEEPSEEK_API_KEY")
        nvidia_key = os.environ.get("NVIDIA_API_KEY")
        gemini_key = os.environ.get("GEMINI_API_KEY")
        groq_key = os.environ.get("GROQ_API_KEY")

        logger.info(
            "Planner provider env presence: github=%s openrouter=%s cerebras=%s deepseek=%s nvidia=%s gemini=%s groq=%s",
            bool(github_token),
            bool(openrouter_key),
            bool(cerebras_key),
            bool(deepseek_key),
            bool(nvidia_key),
            bool(gemini_key),
            bool(groq_key),
        )

        if openrouter_key:
            logger.info("OPENROUTER_API_KEY detected: %s", _mask_secret(openrouter_key))
        if cerebras_key:
            logger.info("CEREBRAS_API_KEY detected: %s", _mask_secret(cerebras_key))
        if deepseek_key:
            logger.info("DEEPSEEK_API_KEY detected: %s", _mask_secret(deepseek_key))
        if nvidia_key:
            logger.info("NVIDIA_API_KEY detected: %s", _mask_secret(nvidia_key))

        self._clients: dict[str, Any] = {}

        if github_token:
            self._clients["github"] = OpenAI(
                base_url=os.environ.get("GITHUB_MODELS_BASE_URL", "https://models.github.ai/inference"),
                api_key=github_token,
            )

        if openrouter_key:
            openrouter_headers: dict[str, str] = {}
            referer = os.environ.get("OPENROUTER_HTTP_REFERER", "").strip()
            app_title = os.environ.get("OPENROUTER_APP_TITLE", "").strip()
            if referer:
                openrouter_headers["HTTP-Referer"] = referer
            if app_title:
                openrouter_headers["X-OpenRouter-Title"] = app_title

            kwargs: dict[str, Any] = {
                "base_url": os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
                "api_key": openrouter_key,
            }
            if openrouter_headers:
                kwargs["default_headers"] = openrouter_headers

            self._clients["openrouter"] = OpenAI(**kwargs)

        if cerebras_key:
            self._clients["cerebras"] = OpenAI(
                base_url=os.environ.get("CEREBRAS_BASE_URL", "https://api.cerebras.ai/v1"),
                api_key=cerebras_key,
            )

        if deepseek_key:
            self._clients["deepseek"] = OpenAI(
                base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
                api_key=deepseek_key,
            )

        if nvidia_key:
            self._clients["nvidia"] = OpenAI(
                base_url=os.environ.get("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1"),
                api_key=nvidia_key,
            )

        if gemini_key:
            self._clients["gemini"] = OpenAI(
                base_url=os.environ.get(
                    "GEMINI_BASE_URL",
                    "https://generativelanguage.googleapis.com/v1beta/openai",
                ),
                api_key=gemini_key,
            )

        if groq_key:
            self._clients["groq"] = OpenAI(
                base_url=os.environ.get("GROQ_BASE_URL", "https://api.groq.com/openai/v1"),
                api_key=groq_key,
            )

        if not self._clients:
            raise PlannerError(
                "No planner provider configured. Set at least one of: "
                "OPENROUTER_API_KEY, CEREBRAS_API_KEY, DEEPSEEK_API_KEY, NVIDIA_API_KEY, GEMINI_API_KEY, GITHUB_TOKEN, GROQ_API_KEY"
            )

        all_models = models or DEFAULT_PLANNER_MODELS
        self._models = [model for model in all_models if model.provider in self._clients]
        if not self._models:
            raise PlannerError(
                "No planner models available for configured providers. "
                f"Configured providers: {', '.join(sorted(self._clients.keys()))}"
            )
        self._selector = ModelSelector(self._models)
        logger.info(
            "Planner configured providers=%s models=%s",
            sorted(self._clients.keys()),
            [m.id for m in self._models],
        )

    def generate_plan(
        self,
        *,
        query: str,
        entity_id: str | None = None,
        entity_name: str | None = None,
        entity_context: dict[str, Any] | None = None,
        max_attempts: int | None = None,
        thinking_mode: bool | None = None,
        stream_thinking: bool = False,
        on_stream_token: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        request_id = str(uuid.uuid4())
        trace = PlannerTrace(request_id)
        system_prompt = build_system_prompt(self._source_registry)
        user_prompt = build_user_prompt(
            query,
            entity_id=entity_id,
            entity_name=entity_name,
            entity_context=entity_context,
        )

        attempted_ids: set[str] = set()
        failure_messages: list[str] = []
        if max_attempts is not None:
            requested_attempts = max_attempts
            attempts_budget = min(max(requested_attempts, 1), len(self._models))
        else:
            requested_attempts = len(self._models)
            attempts_budget = min(max(self._planner_min_attempts, 1), len(self._models))
        started_at = time.monotonic()
        stream_excluded = self._stream_excluded_model_ids if stream_thinking else set()
        blocked_providers: set[str] = set()

        logger.info(
            "Planner attempts: requested=%s effective=%s model_pool=%s",
            requested_attempts,
            attempts_budget,
            len(self._models),
        )

        for attempt in range(1, attempts_budget + 1):
            if (time.monotonic() - started_at) > self._planner_timeout_seconds:
                failure_messages.append(
                    f"Planner exceeded timeout budget ({self._planner_timeout_seconds}s)"
                )
                break

            try:
                excluded_ids = attempted_ids | stream_excluded
                if blocked_providers:
                    excluded_ids = excluded_ids | {
                        item.id for item in self._models if item.provider in blocked_providers
                    }
                model = self._selector.select_next(exclude_ids=excluded_ids)
            except ModelSelectionError:
                failure_messages.append("No eligible planner models remain")
                break

            attempted_ids.add(model.id)
            trace.mark_model(model.id)
            logger.info(
                "Planner attempt %s/%s using provider=%s model=%s",
                attempt,
                attempts_budget,
                model.provider,
                model.id,
            )

            try:
                response = self._run_model(
                    model=model,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    thinking_mode=thinking_mode,
                    stream_thinking=stream_thinking,
                    on_stream_token=on_stream_token,
                )

                raw = response["content"]
                payload = json.loads(raw)
                payload, substitutions = self._validator.validate_and_normalize(
                    payload,
                    provider=model.provider,
                )

                for substitution in substitutions:
                    trace.mark_substitution(substitution)

                self._selector.record_usage(model.id, response["tokens_used"])
                trace.finish()

                payload["_meta"] = {
                    "request_id": request_id,
                    "model_used": model.display_name,
                    "model_id": model.id,
                    "provider": model.provider,
                    "tokens_used": response["tokens_used"],
                    "attempt_number": attempt,
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "validation_status": "pass",
                    "substitutions": substitutions,
                    "trace": {
                        "selected_models": trace.selected_models,
                        "failures": trace.failures,
                        "finished_at": trace.finished_at,
                    },
                }
                return payload

            except (json.JSONDecodeError, PlannerValidationError) as exc:
                msg = f"{model.id} validation failure: {exc}"
                logger.warning("Planner validation failure on provider=%s model=%s: %s", model.provider, model.id, exc)
                self._selector.record_failure(model.id)
                trace.mark_failure(msg)
                failure_messages.append(msg)
                continue
            except Exception as exc:  # pragma: no cover - network/provider path
                msg = f"{model.id} execution failure: {exc}"
                logger.exception("Planner execution failure on provider=%s model=%s", model.provider, model.id)
                if _should_block_provider_for_request(exc):
                    blocked_providers.add(model.provider)
                    logger.warning(
                        "Provider blocked for this request due to terminal/rate-limit error: provider=%s model=%s",
                        model.provider,
                        model.id,
                    )
                self._selector.record_failure(model.id)
                trace.mark_failure(msg)
                failure_messages.append(msg)
                continue

        trace.finish()
        raise PlannerError(
            "Planner failed after max attempts. "
            + " | ".join(failure_messages)
        )

    def rotation_status(self) -> dict[str, dict[str, int | float | None]]:
        return self._selector.status()

    def source_bank_status(self) -> dict[str, int]:
        return self._source_registry.stats()

    def _run_model(
        self,
        *,
        model: PlannerModel,
        system_prompt: str,
        user_prompt: str,
        thinking_mode: bool | None,
        stream_thinking: bool,
        on_stream_token: Callable[[str], None] | None,
    ) -> dict[str, Any]:
        client = self._clients.get(model.provider)
        if client is None:
            raise PlannerError(
                f"Model provider '{model.provider}' is not configured in this environment"
            )

        openrouter_extra_body = self._openrouter_extra_body(model)
        nvidia_kwargs = self._nvidia_request_kwargs(
            model,
            stream_thinking=stream_thinking,
            thinking_mode=thinking_mode,
        )

        if stream_thinking:
            if model.provider == "nvidia":
                stream = client.chat.completions.create(
                    model=model.id,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    max_tokens=self._max_tokens(model),
                    response_format={"type": "json_object"},
                    stream=True,
                    **nvidia_kwargs,
                )
            elif model.provider == "github" and model.id.startswith("openai/gpt-5"):
                stream = client.chat.completions.create(
                    model=model.id,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    max_completion_tokens=self._max_completion_tokens(model),
                    response_format={"type": "json_object"},
                    stream=True,
                )
            elif openrouter_extra_body is not None:
                stream = client.chat.completions.create(
                    model=model.id,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.2,
                    max_tokens=self._max_tokens(model),
                    response_format={"type": "json_object"},
                    stream=True,
                    extra_body=openrouter_extra_body,
                )
            else:
                stream = client.chat.completions.create(
                    model=model.id,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.2,
                    max_tokens=self._max_tokens(model),
                    response_format={"type": "json_object"},
                    stream=True,
                )

            content_parts: list[str] = []
            extractor = ThinkingStreamExtractor()
            stream_started = time.monotonic()
            for chunk in stream:
                if (time.monotonic() - stream_started) > self._stream_timeout_seconds:
                    raise PlannerError(
                        f"Stream timed out for {model.id} after {self._stream_timeout_seconds}s"
                    )

                if not chunk.choices:
                    continue

                delta = getattr(chunk.choices[0], "delta", None)
                reasoning_piece = getattr(delta, "reasoning_content", None)
                piece = getattr(delta, "content", None)

                # NVIDIA reasoning models may emit thinking text in reasoning_content.
                # Stream it to clients, but do not append to content_parts because final payload
                # must remain valid JSON from delta.content fragments only.
                if on_stream_token and reasoning_piece:
                    if not isinstance(reasoning_piece, str):
                        reasoning_piece = str(reasoning_piece)
                    on_stream_token(reasoning_piece)

                if not piece:
                    continue

                # Some providers may return non-string fragments; normalize to string.
                if not isinstance(piece, str):
                    piece = str(piece)

                content_parts.append(piece)

                if on_stream_token:
                    thinking_delta = extractor.feed(piece)
                    if thinking_delta:
                        on_stream_token(thinking_delta)

            full_content = "".join(content_parts)
            tokens_used = _estimate_tokens(full_content)

            # Fallback: if extractor found nothing, emit thinking once from parsed JSON.
            if on_stream_token and extractor.emitted_chars == 0:
                try:
                    payload = json.loads(full_content)
                    thinking = payload.get("thinking")
                    if isinstance(thinking, str) and thinking.strip():
                        on_stream_token(thinking)
                except Exception:
                    pass

            return {
                "content": full_content,
                "tokens_used": tokens_used,
            }

        if model.provider == "nvidia":
            response = client.chat.completions.create(
                model=model.id,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=self._max_tokens(model),
                response_format={"type": "json_object"},
                **nvidia_kwargs,
            )
        elif model.provider == "github" and model.id.startswith("openai/gpt-5"):
            response = client.chat.completions.create(
                model=model.id,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_completion_tokens=self._max_completion_tokens(model),
                response_format={"type": "json_object"},
            )
        elif openrouter_extra_body is not None:
            response = client.chat.completions.create(
                model=model.id,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.2,
                max_tokens=self._max_tokens(model),
                response_format={"type": "json_object"},
                extra_body=openrouter_extra_body,
            )
        else:
            response = client.chat.completions.create(
                model=model.id,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.2,
                max_tokens=self._max_tokens(model),
                response_format={"type": "json_object"},
            )

        content = response.choices[0].message.content
        usage = getattr(response, "usage", None)
        tokens_used = 0
        if usage is not None:
            total_tokens = getattr(usage, "total_tokens", 0) or 0
            prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
            completion_tokens = getattr(usage, "completion_tokens", 0) or 0
            tokens_used = total_tokens or (prompt_tokens + completion_tokens)
        if not tokens_used:
            tokens_used = _estimate_tokens(content)

        return {
            "content": content,
            "tokens_used": tokens_used,
        }

    def _openrouter_extra_body(self, model: PlannerModel) -> dict[str, Any] | None:
        if model.provider != "openrouter":
            return None

        reasoning: dict[str, Any] = {}
        if self._openrouter_reasoning_effort:
            reasoning["effort"] = self._openrouter_reasoning_effort
        elif self._openrouter_reasoning_max_tokens > 0:
            reasoning["max_tokens"] = self._openrouter_reasoning_max_tokens

        if not reasoning:
            return None

        return {"reasoning": reasoning}

    def _max_tokens(self, model: PlannerModel) -> int:
        if model.provider == "nvidia":
            raw = os.environ.get("NVIDIA_MAX_TOKENS", "2200")
            try:
                value = int(raw)
            except ValueError:
                value = 2200
            return max(value, 256)

        if model.provider == "openrouter":
            raw = os.environ.get("OPENROUTER_MAX_TOKENS", "1200")
            try:
                value = int(raw)
            except ValueError:
                value = 1200
            return max(value, 128)

        raw = os.environ.get("PLANNER_MAX_TOKENS", "3200")
        try:
            value = int(raw)
        except ValueError:
            value = 3200
        return max(value, 256)

    def _max_completion_tokens(self, model: PlannerModel) -> int:
        if model.provider == "github" and model.id.startswith("openai/gpt-5"):
            raw = os.environ.get("GITHUB_GPT5_MAX_COMPLETION_TOKENS", "2200")
            try:
                value = int(raw)
            except ValueError:
                value = 2200
            return max(value, 256)

        return self._max_tokens(model)

    def _nvidia_request_kwargs(
        self,
        model: PlannerModel,
        *,
        stream_thinking: bool,
        thinking_mode: bool | None,
    ) -> dict[str, Any]:
        if model.provider != "nvidia":
            return {}

        kwargs: dict[str, Any] = {
            "temperature": self._nvidia_temperature,
        }
        if self._nvidia_top_p < 1.0:
            kwargs["top_p"] = self._nvidia_top_p

        if self._nvidia_random_seed:
            kwargs["seed"] = random.randint(1, 2_147_483_647)
        elif self._nvidia_fixed_seed > 0:
            kwargs["seed"] = self._nvidia_fixed_seed

        target_models = self._nvidia_thinking_models
        if thinking_mode is None:
            enable_reasoning = stream_thinking and self._nvidia_thinking_enabled and model.id in target_models
        else:
            enable_reasoning = thinking_mode and model.id in target_models

        if enable_reasoning:
            kwargs["extra_body"] = {
                "chat_template_kwargs": {"enable_thinking": True},
                "reasoning_budget": self._nvidia_reasoning_budget,
            }

        return kwargs


def _load_stream_timeout_seconds() -> int:
    raw = os.environ.get("PLANNER_STREAM_TIMEOUT_SECONDS", "45")
    try:
        value = int(raw)
    except ValueError:
        return 45
    return max(value, 15)


def _load_planner_timeout_seconds() -> int:
    raw = os.environ.get("PLANNER_TIMEOUT_SECONDS", "120")
    try:
        value = int(raw)
    except ValueError:
        return 120
    return max(value, 30)


def _load_planner_min_attempts() -> int:
    raw = os.environ.get("PLANNER_MIN_ATTEMPTS", "8")
    try:
        value = int(raw)
    except ValueError:
        return 8
    return max(value, 1)


def _load_stream_excluded_model_ids() -> set[str]:
    raw = os.environ.get("PLANNER_STREAM_EXCLUDE_MODELS", "openai/gpt-5")
    return {item.strip() for item in raw.split(",") if item.strip()}


def _load_openrouter_reasoning_effort() -> str | None:
    raw = os.environ.get("OPENROUTER_REASONING_EFFORT", "high").strip().lower()
    if not raw:
        return None
    if raw in {"low", "medium", "high"}:
        return raw
    return None


def _load_openrouter_reasoning_max_tokens() -> int:
    raw = os.environ.get("OPENROUTER_REASONING_MAX_TOKENS", "1024")
    try:
        value = int(raw)
    except ValueError:
        return 1024
    return max(value, 0)


def _load_float_env(name: str, *, default: float, minimum: float, maximum: float) -> float:
    raw = os.environ.get(name, str(default))
    try:
        value = float(raw)
    except ValueError:
        return default
    return min(max(value, minimum), maximum)


def _load_int_env(name: str, *, default: int, minimum: int) -> int:
    raw = os.environ.get(name, str(default))
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(value, minimum)


def _load_bool_env(name: str, *, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _load_csv_env(name: str, *, default: str) -> set[str]:
    raw = os.environ.get(name, default)
    return {item.strip() for item in raw.split(",") if item.strip()}


def _estimate_tokens(text: str) -> int:
    if not text:
        return 0
    words = [token for token in text.replace("\n", " ").split(" ") if token.strip()]
    estimated = int(round(len(words) * 1.3))
    return max(estimated, 1)


def _mask_secret(value: str) -> str:
    if len(value) <= 10:
        return "***"
    return f"{value[:6]}...{value[-4:]}"


def _should_block_provider_for_request(exc: Exception) -> bool:
    message = str(exc).lower()
    terminal_markers = (
        "too many requests",
        "rate limit",
        "resource_exhausted",
        "quota exceeded",
        "queue_exceeded",
        "insufficient credits",
        "invalid api key",
        "authentication",
        "error code: 429",
        "error code: 402",
        "error code: 401",
        "error code: 403",
    )
    return any(marker in message for marker in terminal_markers)
