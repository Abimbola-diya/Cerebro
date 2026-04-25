"""Dataclasses and helpers for planner payload validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .enums import ALL_DIMENSIONS, DimensionKey


@dataclass
class ValidationIssue:
    field: str
    message: str


@dataclass
class PlannedSubQuery:
    query: str
    target_sources: list[str]
    what_to_find: str


@dataclass
class DimensionPlan:
    status: str
    priority: str
    sub_queries: list[PlannedSubQuery] = field(default_factory=list)
    skip_reason: str | None = None
    notes: str | None = None


@dataclass
class PlannerMeta:
    model_used: str
    model_id: str
    tokens_used: int
    generated_at: str
    attempt_number: int
    planner_version: str
    validation_status: str


def ensure_required_top_level(payload: dict[str, Any]) -> list[ValidationIssue]:
    required = (
        "query",
        "entity_id",
        "entity_name",
        "entity_classification",
        "query_intent",
        "thinking",
        "research_plan",
        "execution_order",
        "anticipated_gaps",
        "context_notes",
    )
    issues: list[ValidationIssue] = []
    for key in required:
        if key not in payload:
            issues.append(ValidationIssue(field=key, message="Missing required field"))
    return issues


def ensure_dimensions_present(payload: dict[str, Any]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    research_plan = payload.get("research_plan")
    if not isinstance(research_plan, dict):
        return [ValidationIssue(field="research_plan", message="Expected object")]

    for dim in ALL_DIMENSIONS:
        if dim.value not in research_plan:
            issues.append(
                ValidationIssue(field=f"research_plan.{dim.value}", message="Missing dimension block")
            )
    return issues


def dimension_from_key(key: str) -> DimensionKey | None:
    for dim in ALL_DIMENSIONS:
        if dim.value == key:
            return dim
    return None
