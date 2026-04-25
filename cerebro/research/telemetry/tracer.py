"""Minimal structured telemetry for planner execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class PlannerTrace:
    request_id: str
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    selected_models: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    substitutions: list[str] = field(default_factory=list)
    finished_at: str | None = None

    def mark_model(self, model_name: str) -> None:
        self.selected_models.append(model_name)

    def mark_failure(self, message: str) -> None:
        self.failures.append(message)

    def mark_substitution(self, message: str) -> None:
        self.substitutions.append(message)

    def finish(self) -> None:
        self.finished_at = datetime.now(timezone.utc).isoformat()
