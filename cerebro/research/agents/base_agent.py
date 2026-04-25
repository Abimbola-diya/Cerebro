"""Shared agent scaffolding for future LangChain integration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from cerebro.research.errors import PlannerError


@dataclass(frozen=True)
class AgentBriefing:
    dimension: str
    prompt_path: str
    prompt_text: str
    schema_text: str


class BaseResearchAgent:
    """Load the markdown briefing and schema for one dimension.

    This is intentionally tool-free for now. LangChain tool wiring will sit
    on top of this loader in the next slice.
    """

    def __init__(self, *, prompts_dir: Path, schemas_dir: Path) -> None:
        self._prompts_dir = prompts_dir
        self._schemas_dir = schemas_dir

    def load_briefing(self, *, dimension: str, prompt_filename: str, schema_filename: str) -> AgentBriefing:
        prompt_path = self._prompts_dir / prompt_filename
        schema_path = self._schemas_dir / schema_filename

        if not prompt_path.exists():
            raise PlannerError(f"Missing prompt briefing: {prompt_path}")
        if not schema_path.exists():
            raise PlannerError(f"Missing schema file: {schema_path}")

        return AgentBriefing(
            dimension=dimension,
            prompt_path=str(prompt_path),
            prompt_text=prompt_path.read_text(encoding="utf-8"),
            schema_text=schema_path.read_text(encoding="utf-8"),
        )
