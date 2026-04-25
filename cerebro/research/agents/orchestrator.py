"""LangChain-ready orchestrator scaffold for Cerebro research agents."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from cerebro.research.agents.adapter import ResearchAdapter, ResearchWorkingState
from cerebro.research.agents.runtime import ResearchAgentRuntime
from cerebro.research.contracts.enums import ALL_DIMENSIONS
from cerebro.research.errors import PlannerError


@dataclass(frozen=True)
class AgentRunSummary:
    request_id: str
    active_dimensions: list[str]
    working_files: list[str]
    status: str


class ResearchOrchestrator:
    """Prepare and run the research agent pipeline using the in-memory working filesystem."""

    def __init__(self, adapter: ResearchAdapter | None = None) -> None:
        self._adapter = adapter or ResearchAdapter()
        self._runtime = ResearchAgentRuntime(self._adapter)

    def prepare(self, plan: dict[str, Any]) -> tuple[ResearchWorkingState, AgentRunSummary]:
        if not isinstance(plan, dict):
            raise PlannerError("plan must be a JSON object")

        working_state = self._adapter.prepare(plan)
        active_dimensions = self._active_dimensions(plan)

        working_state.write_file(
            "orchestrator_summary.json",
            json.dumps(
                {
                    "request_id": working_state.request_id,
                    "active_dimensions": active_dimensions,
                    "working_file_count": len(working_state.files),
                    "status": "prepared",
                },
                ensure_ascii=False,
                indent=2,
                default=str,
            ),
        )

        summary = AgentRunSummary(
            request_id=working_state.request_id,
            active_dimensions=active_dimensions,
            working_files=sorted(working_state.files.keys()),
            status="prepared",
        )
        return working_state, summary

    async def run(self, plan: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(plan, dict):
            raise PlannerError("plan must be a JSON object")
        return await self._runtime.run(plan)

    def _active_dimensions(self, plan: dict[str, Any]) -> list[str]:
        research_plan = plan.get("research_plan")
        if not isinstance(research_plan, dict):
            return []

        active_dimensions: list[str] = []
        for dimension in ALL_DIMENSIONS:
            block = research_plan.get(dimension.value)
            if isinstance(block, dict) and str(block.get("status", "")).upper() == "ACTIVE":
                active_dimensions.append(dimension.value)
        return active_dimensions
