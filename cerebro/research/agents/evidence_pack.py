"""Evidence pack builder for research synthesis."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .adapter import ResearchWorkingState


@dataclass(frozen=True)
class SourceMetadata:
    """Deduplicated source reference."""

    url: str
    provider: str
    title: str | None = None
    date: str | None = None


@dataclass(frozen=True)
class EvidenceItem:
    """Single piece of evidence with source attribution."""

    dimension: str
    content: str
    relevance_score: float
    source_id: int
    tool: str | None = None


@dataclass(frozen=True)
class EvidencePack:
    """Aggregated, deduplicated evidence across all dimensions."""

    request_id: str
    query: str
    entity_name: str
    active_dimensions: list[str]
    sources: list[SourceMetadata]
    evidence: list[EvidenceItem]
    retrieval_gaps: list[str]
    errors: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "query": self.query,
            "entity_name": self.entity_name,
            "active_dimensions": self.active_dimensions,
            "sources": [
                {
                    "id": idx,
                    "url": src.url,
                    "provider": src.provider,
                    "title": src.title,
                    "date": src.date,
                }
                for idx, src in enumerate(self.sources)
            ],
            "evidence": [
                {
                    "dimension": ev.dimension,
                    "content": ev.content,
                    "relevance_score": ev.relevance_score,
                    "source_id": ev.source_id,
                    "tool": ev.tool,
                }
                for ev in self.evidence
            ],
            "gaps": self.retrieval_gaps,
            "retrieval_gaps": self.retrieval_gaps,
            "conflict_flags": [],
            "errors": self.errors,
        }


class EvidencePackBuilder:
    """Build evidence pack from dimension agent results."""

    def __init__(self) -> None:
        self._source_cache: dict[str, int] = {}
        self._sources: list[SourceMetadata] = []

    def build(
        self,
        *,
        plan: dict[str, Any],
        working_state: ResearchWorkingState,
        agent_results: dict[str, dict[str, Any]],
    ) -> EvidencePack:
        """Build evidence pack from plan, working state, and agent results."""
        query = plan.get("query", "")
        entity_name = plan.get("entity_name", "")
        request_id = working_state.request_id

        active_dimensions: list[str] = []
        evidence: list[EvidenceItem] = []
        gaps: list[str] = []
        errors: list[str] = []

        # Process each dimension's results
        for dimension_key, result in agent_results.items():
            if not isinstance(result, dict):
                errors.append(f"Invalid result for {dimension_key}: {result}")
                continue

            dimension = result.get("dimension", dimension_key)
            active_dimensions.append(dimension)

            # Extract documents as evidence
            for doc in result.get("documents", []):
                if not isinstance(doc, dict):
                    continue
                content = doc.get("content", "").strip()
                if not content:
                    continue

                relevance = float(doc.get("relevance_score", 0.5))
                tool = doc.get("tool") or doc.get("provider")
                source_url = doc.get("source") or doc.get("url") or ""

                # Deduplicate source
                source_id = self._register_source(
                    url=source_url,
                    provider=tool or "unknown",
                    title=doc.get("title"),
                    date=doc.get("date"),
                )

                evidence.append(
                    EvidenceItem(
                        dimension=dimension,
                        content=content,
                        relevance_score=relevance,
                        source_id=source_id,
                        tool=tool,
                    )
                )

            # Collect gaps and errors
            gaps.extend(result.get("retrieval_gaps", []))
            errors.extend(result.get("errors", []))

        # Sort evidence by relevance (descending)
        evidence = sorted(evidence, key=lambda e: e.relevance_score, reverse=True)

        return EvidencePack(
            request_id=request_id,
            query=query,
            entity_name=entity_name,
            active_dimensions=active_dimensions,
            sources=self._sources,
            evidence=evidence,
            retrieval_gaps=gaps,
            errors=errors,
        )

    def _register_source(
        self,
        *,
        url: str,
        provider: str,
        title: str | None = None,
        date: str | None = None,
    ) -> int:
        """Register a source and return its deduplicated ID."""
        key = (url, provider)
        key_str = f"{url}|{provider}"

        if key_str in self._source_cache:
            return self._source_cache[key_str]

        source_id = len(self._sources)
        self._source_cache[key_str] = source_id
        self._sources.append(
            SourceMetadata(url=url, provider=provider, title=title, date=date)
        )
        return source_id
