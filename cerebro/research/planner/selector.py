"""Deterministic model selection and state management."""

from __future__ import annotations

import threading
import time

from cerebro.research.errors import ModelSelectionError

from .model_catalog import PlannerModel


class ModelSelector:
    """Select models with weighted ranking and explicit next-eligible fallback."""

    def __init__(
        self,
        models: list[PlannerModel],
        *,
        failure_cutoff: int = 3,
    ) -> None:
        self._models = models
        self._failure_cutoff = failure_cutoff
        self._lock = threading.Lock()

    def eligible_models(self, exclude_ids: set[str] | None = None) -> list[PlannerModel]:
        exclude = exclude_ids or set()
        with self._lock:
            available = [
                model
                for model in self._models
                if model.id not in exclude
                and model.tokens_used < model.token_limit_per_session
                and model.consecutive_failures < self._failure_cutoff
            ]
            if not available:
                return []
            return sorted(
                available,
                key=lambda m: (
                    -m.weight,
                    m.last_used_at if m.last_used_at is not None else 0.0,
                ),
            )

    def select_next(self, exclude_ids: set[str] | None = None) -> PlannerModel:
        eligible = self.eligible_models(exclude_ids=exclude_ids)
        if not eligible:
            raise ModelSelectionError("No eligible planner model available")
        return eligible[0]

    def record_usage(self, model_id: str, tokens_used: int) -> None:
        with self._lock:
            model = self._get(model_id)
            model.tokens_used += max(tokens_used, 0)
            model.consecutive_failures = 0
            model.last_used_at = time.time()

    def record_failure(self, model_id: str) -> None:
        with self._lock:
            model = self._get(model_id)
            model.consecutive_failures += 1
            model.last_used_at = time.time()

    def status(self) -> dict[str, dict[str, int | float | None]]:
        with self._lock:
            return {
                model.id: {
                    "tokens_used": model.tokens_used,
                    "token_limit": model.token_limit_per_session,
                    "consecutive_failures": model.consecutive_failures,
                    "last_used_at": model.last_used_at,
                    "weight": model.weight,
                }
                for model in self._models
            }

    def _get(self, model_id: str) -> PlannerModel:
        for model in self._models:
            if model.id == model_id:
                return model
        raise ModelSelectionError(f"Unknown model id: {model_id}")
