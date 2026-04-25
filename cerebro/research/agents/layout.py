"""Shared file layout for Cerebro research agent orchestration."""

from __future__ import annotations

from pathlib import Path

from cerebro.research.contracts.enums import DimensionKey


PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"
SCHEMAS_DIR = Path(__file__).resolve().parents[1] / "schemas"
ORCHESTRATOR_PROMPT_FILE = "00_orchestrator.md"
EVIDENCE_FILTER_PROMPT_FILE = "08_pre_synthesis_filter.md"
SYNTHESIS_PROMPT_FILE = "09_synthesis_output.md"
PLAN_SCHEMA_FILE = "plan_schema.json"
AGENT_OUTPUT_SCHEMA_FILE = "agent_output_schema.json"
EVIDENCE_PACK_SCHEMA_FILE = "evidence_pack_schema.json"

DIMENSION_PROMPT_FILES: dict[DimensionKey, str] = {
    DimensionKey.REGULATORY: "01_regulatory_agent.md",
    DimensionKey.FINANCIAL: "02_financial_agent.md",
    DimensionKey.MARKET: "03_market_listing_agent.md",
    DimensionKey.EXPERT: "04_expert_opinion_agent.md",
    DimensionKey.NEWS: "05_news_agent.md",
    DimensionKey.INTERNATIONAL: "06_international_agent.md",
    DimensionKey.ASSOCIATIONS: "07_associations_agent.md",
}

DIMENSION_RESULT_FILES: dict[DimensionKey, str] = {
    DimensionKey.REGULATORY: "regulatory_results.json",
    DimensionKey.FINANCIAL: "financial_results.json",
    DimensionKey.MARKET: "market_results.json",
    DimensionKey.EXPERT: "expert_results.json",
    DimensionKey.NEWS: "news_results.json",
    DimensionKey.INTERNATIONAL: "international_results.json",
    DimensionKey.ASSOCIATIONS: "associations_results.json",
}
