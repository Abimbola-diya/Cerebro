"""In-memory adapter layer that prepares plan files and agent briefing files."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cerebro.research.contracts.enums import ALL_DIMENSIONS
from cerebro.research.errors import PlannerError

from .layout import AGENT_OUTPUT_SCHEMA_FILE, DIMENSION_PROMPT_FILES, DIMENSION_RESULT_FILES, EVIDENCE_FILTER_PROMPT_FILE, EVIDENCE_PACK_SCHEMA_FILE, ORCHESTRATOR_PROMPT_FILE, PLAN_SCHEMA_FILE, PROMPTS_DIR, SCHEMAS_DIR, SYNTHESIS_PROMPT_FILE


@dataclass
class ResearchWorkingState:
    """In-memory filesystem for a single research request."""

    request_id: str
    files: dict[str, str] = field(default_factory=dict)
    log: list[dict[str, Any]] = field(default_factory=list)

    def write_file(self, path: str, content: str) -> None:
        self.files[path] = content

    def read_file(self, path: str) -> str:
        if path not in self.files:
            raise PlannerError(f"Working file not found: {path}")
        return self.files[path]


class ResearchAdapter:
    """Load the planner output, active prompt files, and working-file stubs."""

    def __init__(self, *, prompts_dir: Path | None = None, schemas_dir: Path | None = None) -> None:
        self._prompts_dir = prompts_dir or PROMPTS_DIR
        self._schemas_dir = schemas_dir or SCHEMAS_DIR

    def prepare(self, plan: dict[str, Any], request_id: str | None = None) -> ResearchWorkingState:
        if not isinstance(plan, dict):
            raise PlannerError("plan must be a JSON object")

        working_state = ResearchWorkingState(request_id=request_id or str(uuid.uuid4()))
        working_state.write_file(f"prompts/{ORCHESTRATOR_PROMPT_FILE}", self._read_prompt(ORCHESTRATOR_PROMPT_FILE))
        working_state.write_file(f"prompts/{EVIDENCE_FILTER_PROMPT_FILE}", self._read_prompt(EVIDENCE_FILTER_PROMPT_FILE))
        working_state.write_file(f"prompts/{SYNTHESIS_PROMPT_FILE}", self._read_prompt(SYNTHESIS_PROMPT_FILE))
        working_state.write_file("plan.json", json.dumps(plan, ensure_ascii=False, indent=2, default=str))
        working_state.write_file(f"schemas/{PLAN_SCHEMA_FILE}", self._read_schema(PLAN_SCHEMA_FILE))
        working_state.write_file(f"schemas/{AGENT_OUTPUT_SCHEMA_FILE}", self._read_schema(AGENT_OUTPUT_SCHEMA_FILE))
        working_state.write_file(f"schemas/{EVIDENCE_PACK_SCHEMA_FILE}", self._read_schema(EVIDENCE_PACK_SCHEMA_FILE))

        research_plan = plan.get("research_plan")
        if not isinstance(research_plan, dict):
            raise PlannerError("plan is missing research_plan")

        active_dimensions: list[str] = []
        for dimension in ALL_DIMENSIONS:
            block = research_plan.get(dimension.value)
            status = str(block.get("status") if isinstance(block, dict) else "SKIP").upper()
            prompt_file = DIMENSION_PROMPT_FILES[dimension]

            if status == "ACTIVE":
                active_dimensions.append(dimension.value)
                working_state.write_file(
                    f"prompts/{prompt_file}",
                    self._read_prompt(prompt_file),
                )
                working_state.write_file(
                    f"working/{DIMENSION_RESULT_FILES[dimension]}",
                    json.dumps(
                        {
                            "dimension": dimension.value,
                            "status": "PENDING",
                            "prompt_file": prompt_file,
                            "sub_queries": block.get("sub_queries", []) if isinstance(block, dict) else [],
                        },
                        ensure_ascii=False,
                        indent=2,
                        default=str,
                    ),
                )
            else:
                working_state.write_file(
                    f"working/{DIMENSION_RESULT_FILES[dimension]}",
                    json.dumps(
                        {
                            "dimension": dimension.value,
                            "status": "SKIPPED",
                            "reason": block.get("skip_reason") if isinstance(block, dict) else None,
                        },
                        ensure_ascii=False,
                        indent=2,
                        default=str,
                    ),
                )

        working_state.write_file(
            "orchestrator_log.json",
            json.dumps(
                {
                    "request_id": working_state.request_id,
                    "active_dimensions": active_dimensions,
                    "files_written": sorted(working_state.files.keys()),
                },
                ensure_ascii=False,
                indent=2,
                default=str,
            ),
        )

        working_state.log.append(
            {
                "request_id": working_state.request_id,
                "active_dimensions": active_dimensions,
                "status": "prepared",
            }
        )
        return working_state

    def _read_prompt(self, filename: str) -> str:
        path = self._prompts_dir / filename
        if not path.exists():
            raise PlannerError(f"Prompt file missing: {path}")
        return path.read_text(encoding="utf-8")

    def _read_schema(self, filename: str) -> str:
        path = self._schemas_dir / filename
        if not path.exists():
            raise PlannerError(f"Schema file missing: {path}")
        return path.read_text(encoding="utf-8")