"""News agent briefing loader."""

from __future__ import annotations

from pathlib import Path

from cerebro.research.agents.base_agent import BaseResearchAgent


class NewsResearchAgent(BaseResearchAgent):
    def __init__(self, prompts_dir: Path, schemas_dir: Path) -> None:
        super().__init__(prompts_dir=prompts_dir, schemas_dir=schemas_dir)
