"""Custom exceptions for research planning modules."""

from __future__ import annotations


class PlannerError(Exception):
    """Base exception for planner failures."""


class PlannerValidationError(PlannerError):
    """Raised when planner output fails schema or policy checks."""


class ModelSelectionError(PlannerError):
    """Raised when no eligible model is available."""


class SourceRegistryError(PlannerError):
    """Raised for source registry resolution and policy failures."""
