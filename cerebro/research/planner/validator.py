"""Planner output validation and normalization."""

from __future__ import annotations

from typing import Any

from cerebro.research.contracts.enums import ALL_DIMENSIONS, DimensionKey, DimensionStatus, Priority
from cerebro.research.contracts.planner_contracts import ensure_dimensions_present, ensure_required_top_level
from cerebro.research.errors import PlannerValidationError
from cerebro.research.sources.registry import SourceRegistry


def _word_count(text: str) -> int:
    return len([token for token in text.replace("\n", " ").split(" ") if token.strip()])


class PlannerValidator:
    """Strict schema and policy validator for planner outputs."""

    def __init__(
        self,
        source_registry: SourceRegistry,
        *,
        min_thinking_words: int = 180,
        max_thinking_words: int = 500,
    ) -> None:
        self._registry = source_registry
        self._min_thinking_words = min_thinking_words
        self._max_thinking_words = max_thinking_words

    def validate_and_normalize(
        self,
        payload: dict[str, Any],
        *,
        provider: str | None = None,
    ) -> tuple[dict[str, Any], list[str]]:
        payload = _normalize_payload(payload, provider=provider)

        issues = []
        issues.extend(ensure_required_top_level(payload))
        issues.extend(ensure_dimensions_present(payload))
        if issues:
            msg = "; ".join(f"{i.field}: {i.message}" for i in issues)
            raise PlannerValidationError(msg)

        thinking = payload.get("thinking")
        if not isinstance(thinking, str):
            raise PlannerValidationError("thinking must be a string")
        if not thinking.strip():
            raise PlannerValidationError("thinking must not be empty")

        # Some providers emit concise streamed thinking; accept any non-empty length.
        if provider not in {"cerebras", "nvidia"}:
            words = _word_count(thinking)
            if words < self._min_thinking_words or words > self._max_thinking_words:
                raise PlannerValidationError(
                    f"thinking length must be between {self._min_thinking_words} and {self._max_thinking_words} words; got {words}"
                )

        substitutions: list[str] = []
        research_plan = payload["research_plan"]

        for dim in ALL_DIMENSIONS:
            block = research_plan.get(dim.value)
            if not isinstance(block, dict):
                raise PlannerValidationError(f"{dim.value} must be an object")

            status = block.get("status")
            if status not in {DimensionStatus.ACTIVE.value, DimensionStatus.SKIP.value}:
                raise PlannerValidationError(f"{dim.value}.status must be ACTIVE or SKIP")

            priority = block.get("priority")
            if priority not in {Priority.CRITICAL.value, Priority.HIGH.value, Priority.MEDIUM.value, Priority.LOW.value}:
                raise PlannerValidationError(f"{dim.value}.priority must be CRITICAL/HIGH/MEDIUM/LOW")

            sub_queries = block.get("sub_queries")
            if not isinstance(sub_queries, list):
                raise PlannerValidationError(f"{dim.value}.sub_queries must be an array")

            if provider in {"nvidia", "cerebras"} and len(sub_queries) == 0 and status == DimensionStatus.ACTIVE.value:
                block["status"] = DimensionStatus.SKIP.value
                block["skip_reason"] = block.get("skip_reason") or "Auto-normalized: missing sub_queries"
                status = block["status"]

            if status == DimensionStatus.ACTIVE.value and len(sub_queries) == 0:
                raise PlannerValidationError(f"{dim.value} is ACTIVE but has no sub_queries")

            fallback_sources = self._registry.by_dimension(_to_dimension(dim))
            fallback_source_id = fallback_sources[0].id if fallback_sources else None

            for index, item in enumerate(sub_queries):
                if not isinstance(item, dict):
                    raise PlannerValidationError(f"{dim.value}.sub_queries[{index}] must be object")

                if provider in {"nvidia", "cerebras"}:
                    if not item.get("query") and isinstance(item.get("what_to_find"), str):
                        item["query"] = item["what_to_find"]
                    if not item.get("what_to_find") and isinstance(item.get("query"), str):
                        item["what_to_find"] = f"Evidence for: {item['query']}"
                    if (not item.get("target_sources") or not isinstance(item.get("target_sources"), list)) and fallback_source_id:
                        item["target_sources"] = [fallback_source_id]

                if not item.get("query"):
                    raise PlannerValidationError(f"{dim.value}.sub_queries[{index}].query required")
                if not item.get("what_to_find"):
                    raise PlannerValidationError(f"{dim.value}.sub_queries[{index}].what_to_find required")
                target_sources = item.get("target_sources")
                if not isinstance(target_sources, list) or len(target_sources) == 0:
                    raise PlannerValidationError(
                        f"{dim.value}.sub_queries[{index}].target_sources must be non-empty array"
                    )

                normalized: list[str] = []
                for source_id in target_sources:
                    if not isinstance(source_id, str):
                        raise PlannerValidationError(
                            f"{dim.value}.sub_queries[{index}].target_sources entries must be strings"
                        )
                    resolved, substituted = self._registry.resolve_or_substitute(
                        source_id,
                        dimension=_to_dimension(dim),
                    )
                    normalized.append(resolved.id)
                    if substituted:
                        substitutions.append(
                            f"{dim.value}.sub_queries[{index}]: substituted {source_id} -> {resolved.id}"
                        )
                item["target_sources"] = normalized

            if "skip_fallback_policy" not in block:
                block["skip_fallback_policy"] = "light_fallback_1_to_2_queries"

        return payload, substitutions


def _to_dimension(dimension: DimensionKey) -> DimensionKey:
    return dimension


def _normalize_payload(payload: dict[str, Any], *, provider: str | None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return payload

    normalized = dict(payload)

    # Normalize thinking field: some providers (esp. Nemotron) may return as list/dict
    if "thinking" in normalized:
        thinking = normalized["thinking"]
        if isinstance(thinking, list):
            # Join list elements with space
            normalized["thinking"] = " ".join(str(item) for item in thinking)
        elif isinstance(thinking, dict):
            # Convert dict to JSON string representation
            try:
                import json
                normalized["thinking"] = json.dumps(thinking, default=str)
            except Exception:
                normalized["thinking"] = str(thinking)
        elif not isinstance(thinking, str):
            # Fallback: convert any other type to string
            normalized["thinking"] = str(thinking)

    if provider in {"nvidia", "cerebras"}:
        if "execution_order" not in normalized:
            normalized["execution_order"] = [dim.value for dim in ALL_DIMENSIONS]
        if "anticipated_gaps" not in normalized:
            normalized["anticipated_gaps"] = [
                "Auto-filled: provider did not provide anticipated_gaps explicitly."
            ]
        if "context_notes" not in normalized:
            normalized["context_notes"] = "Auto-filled by validator."

    plan = normalized.get("research_plan")
    if not isinstance(plan, dict):
        return normalized

    plan_copy: dict[str, Any] = dict(plan)

    if provider in {"nvidia", "cerebras"}:
        for dim in ALL_DIMENSIONS:
            if dim.value not in plan_copy:
                raise PlannerValidationError(
                    f"research_plan missing required block {dim.value}; model likely emitted malformed legacy structure"
                )

        if "dimensions" in plan_copy:
            raise PlannerValidationError(
                "research_plan contains unsupported legacy dimensions array; use research_plan.dimension_X blocks"
            )

    for key, block in plan_copy.items():
        if not isinstance(block, dict):
            continue

        status = block.get("status")
        if isinstance(status, str):
            status_upper = status.strip().upper()
            status_map = {
                "ACTIVE": "ACTIVE",
                "ACT": "ACTIVE",
                "ENABLED": "ACTIVE",
                "SKIP": "SKIP",
                "SKIPPED": "SKIP",
                "INACTIVE": "SKIP",
                "OMIT": "SKIP",
            }
            block["status"] = status_map.get(status_upper, status_upper)

        priority = block.get("priority")
        if isinstance(priority, str):
            priority_upper = priority.strip().upper()
            priority_map = {
                "CRITICAL": "CRITICAL",
                "VERY_HIGH": "CRITICAL",
                "HIGH": "HIGH",
                "MEDIUM": "MEDIUM",
                "MED": "MEDIUM",
                "MODERATE": "MEDIUM",
                "LOW": "LOW",
            }
            block["priority"] = priority_map.get(priority_upper, priority_upper)

        if provider in {"nvidia", "cerebras"} and "priority" not in block:
            block["priority"] = "MEDIUM"

        if provider in {"nvidia", "cerebras"} and not isinstance(block.get("sub_queries"), list):
            block["sub_queries"] = []

        plan_copy[key] = block

    normalized["research_plan"] = plan_copy
    return normalized
