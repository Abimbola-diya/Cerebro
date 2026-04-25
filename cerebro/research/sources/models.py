"""Source model definitions for the research source bank."""

from __future__ import annotations

from dataclasses import dataclass, field

from cerebro.research.contracts.enums import DimensionKey, NigeriaRelevance, SourceTier, SourceType


@dataclass(frozen=True)
class SourceRecord:
    id: str
    name: str
    url: str
    dimension: DimensionKey
    source_type: SourceType
    tier: SourceTier
    nigeria_relevance: NigeriaRelevance
    credibility_rank: int
    update_frequency: str
    crawl_paths: tuple[str, ...] = field(default_factory=tuple)
    search_operator: str | None = None
    notes: str | None = None

    def as_prompt_line(self) -> str:
        operator = self.search_operator or f"site:{self.url.replace('https://', '').replace('http://', '').rstrip('/')}"
        return (
            f"[{self.id}] {self.name} | {self.dimension.value} | "
            f"tier={self.tier.value} | rank={self.credibility_rank}/5 | op={operator}"
        )
