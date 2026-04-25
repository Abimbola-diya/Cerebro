"""Source registry access and substitution logic."""

from __future__ import annotations

from collections import defaultdict

from cerebro.research.contracts.enums import DimensionKey, NigeriaRelevance, SourceTier, SourceType
from cerebro.research.errors import SourceRegistryError

from .bank import ALL_SOURCE_BANK, source_bank_stats
from .models import SourceRecord


_RELEVANCE_ORDER = {
    NigeriaRelevance.DIRECT: 4,
    NigeriaRelevance.STRONG: 3,
    NigeriaRelevance.MODERATE: 2,
    NigeriaRelevance.LOW: 1,
}


class SourceRegistry:
    """Holds the classified source bank and supports source substitution."""

    def __init__(self, records: list[SourceRecord] | None = None) -> None:
        dataset = records or ALL_SOURCE_BANK
        self._records = dataset
        self._by_id = {record.id: record for record in dataset}
        self._by_dimension: dict[DimensionKey, list[SourceRecord]] = defaultdict(list)

        for record in dataset:
            self._by_dimension[record.dimension].append(record)

    def stats(self) -> dict[str, int]:
        return source_bank_stats()

    def all(self) -> list[SourceRecord]:
        return list(self._records)

    def by_id(self, source_id: str) -> SourceRecord | None:
        return self._by_id.get(source_id)

    def by_dimension(self, dimension: DimensionKey) -> list[SourceRecord]:
        return list(self._by_dimension.get(dimension, []))

    def resolve_or_substitute(
        self,
        source_id: str,
        *,
        dimension: DimensionKey,
        source_type_hint: SourceType | None = None,
    ) -> tuple[SourceRecord, bool]:
        """Resolve source ID, or substitute from same dimension/category if missing.

        Returns (source_record, substituted_flag).
        """
        match = self.by_id(source_id)
        if match:
            return match, False

        candidates = self._by_dimension.get(dimension, [])
        if not candidates:
            raise SourceRegistryError(
                f"Cannot substitute source '{source_id}' because dimension '{dimension.value}' has no sources"
            )

        typed = candidates
        if source_type_hint is not None:
            typed = [item for item in candidates if item.source_type == source_type_hint] or candidates

        typed = sorted(
            typed,
            key=lambda item: (
                item.tier != SourceTier.CORE,
                -item.credibility_rank,
                -_RELEVANCE_ORDER[item.nigeria_relevance],
                item.id,
            ),
        )
        return typed[0], True

    def for_planner_prompt(
        self,
        *,
        include_extended: bool = True,
        max_per_dimension: int | None = None,
    ) -> str:
        """Return a compact source-bank digest to inject into planner prompt."""
        lines: list[str] = []
        for dimension in DimensionKey:
            lines.append(f"\n{dimension.value} sources:")
            pool = self.by_dimension(dimension)
            if not include_extended:
                pool = [item for item in pool if item.tier == SourceTier.CORE]
            pool = sorted(
                pool,
                key=lambda item: (
                    item.tier != SourceTier.CORE,
                    -item.credibility_rank,
                    -_RELEVANCE_ORDER[item.nigeria_relevance],
                    item.id,
                ),
            )
            if max_per_dimension is not None:
                pool = pool[:max_per_dimension]
            for item in pool:
                lines.append(f"  {item.as_prompt_line()}")
        return "\n".join(lines)


registry = SourceRegistry()
