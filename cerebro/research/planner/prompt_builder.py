"""Planner prompt builder with injected source-bank digest."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cerebro.research.sources.registry import SourceRegistry


PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"
PLANNER_PROMPT_FILE = PROMPTS_DIR / "00_research_planner.md"


def build_system_prompt(source_registry: SourceRegistry) -> str:
    # Keep digest compact to avoid provider request-size errors while preserving coverage.
    source_digest = source_registry.for_planner_prompt(
        include_extended=False,
        max_per_dimension=4,
    )
    exact_output_shape = """
{
    "query": "...",
    "entity_id": "...",
    "entity_name": "...",
    "entity_classification": "...",
    "query_intent": "...",
    "thinking": "...",
    "research_plan": {
        "dimension_1_regulatory": {
            "status": "ACTIVE or SKIP",
            "priority": "CRITICAL/HIGH/MEDIUM/LOW",
            "sub_queries": [
                {
                    "query": "...",
                    "target_sources": ["source-id"],
                    "what_to_find": "..."
                }
            ],
            "skip_reason": "...",
            "skip_fallback_policy": "light_fallback_1_to_2_queries"
        },
        "dimension_2_financial_institutions": { "...": "..." },
        "dimension_3_market_listing": { "...": "..." },
        "dimension_4_expert_opinion": { "...": "..." },
        "dimension_5_news": { "...": "..." },
        "dimension_6_international_orgs": { "...": "..." },
        "dimension_7_industry_associations": { "...": "..." }
    },
    "execution_order": ["dimension_1_regulatory", "..."],
    "anticipated_gaps": ["..."],
    "context_notes": "..."
}
""".strip()

    template = _read_planner_template()
    return (
        template
        .replace("{{EXACT_OUTPUT_SHAPE}}", exact_output_shape)
        .replace("{{SOURCE_DIGEST}}", source_digest)
    )


def build_user_prompt(
    query: str,
    *,
    entity_id: str | None = None,
    entity_name: str | None = None,
    entity_context: dict[str, Any] | None = None,
) -> str:
    sections = [f"RESEARCH QUERY: {query}"]
    if entity_id:
        sections.append(f"ENTITY ID: {entity_id}")
    if entity_name:
        sections.append(f"ENTITY NAME: {entity_name}")
    if entity_context:
        sections.append("ENTITY CONTEXT:\n" + json.dumps(entity_context, indent=2, default=str))

    sections.append(
        "Return only strict JSON. For target_sources, use source IDs from source bank digest."
    )
    return "\n\n".join(sections)


def _read_planner_template() -> str:
    try:
        return PLANNER_PROMPT_FILE.read_text(encoding="utf-8").strip()
    except FileNotFoundError as exc:
        raise RuntimeError(f"Missing planner prompt file at {PLANNER_PROMPT_FILE}") from exc
