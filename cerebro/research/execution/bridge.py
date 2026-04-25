"""Bridge from Step 1 planner output to Step 2 retrieval tasks."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any
from urllib.parse import urljoin, urlparse

from cerebro.research.contracts.enums import ALL_DIMENSIONS, DimensionKey
from cerebro.research.errors import PlannerError
from cerebro.research.sources.registry import SourceRegistry, registry


@dataclass(frozen=True)
class RetrievalTask:
    task_type: str
    provider: str
    query: str | None
    source_id: str
    source_name: str
    source_url: str
    request: dict[str, Any]


@dataclass
class ExecutionBatch:
    query: str
    entity_id: str | None
    entity_name: str | None
    tasks: list[RetrievalTask] = field(default_factory=list)


class ResearchExecutionBridge:
    """Translate planner plans into search and scrape tasks."""

    def __init__(self, source_registry: SourceRegistry | None = None) -> None:
        self._registry = source_registry or registry

    def build_execution_batch(self, plan: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(plan, dict):
            raise PlannerError("Planner output must be a JSON object")

        research_plan = plan.get("research_plan")
        if not isinstance(research_plan, dict):
            raise PlannerError("Planner output is missing research_plan")

        batch = ExecutionBatch(
            query=str(plan.get("query", "")).strip(),
            entity_id=plan.get("entity_id"),
            entity_name=plan.get("entity_name"),
        )

        tasks: list[RetrievalTask] = []

        for dimension in ALL_DIMENSIONS:
            block = research_plan.get(dimension.value)
            if not isinstance(block, dict):
                continue
            if block.get("status") != "ACTIVE":
                continue

            sub_queries = block.get("sub_queries")
            if not isinstance(sub_queries, list):
                continue

            for sub_query in sub_queries:
                if not isinstance(sub_query, dict):
                    continue

                query_text = str(sub_query.get("query", "")).strip()
                what_to_find = str(sub_query.get("what_to_find", "")).strip()
                target_sources = sub_query.get("target_sources") or []
                if not isinstance(target_sources, list):
                    continue

                for source_id in target_sources:
                    if not isinstance(source_id, str):
                        continue

                    source = self._registry.by_id(source_id)
                    if source is None:
                        continue

                    strategy = self._strategy_for(dimension)

                    if strategy.search_provider is not None:
                        search_request = self._build_search_request(
                            source_id=source.id,
                            query=query_text,
                            source_name=source.name,
                            dimension=dimension,
                            source_url=source.url,
                            provider=strategy.search_provider,
                        )
                        tasks.append(search_request)

                    if strategy.scrape_crawl_paths:
                        for path in source.crawl_paths:
                            scrape_url = urljoin(source.url.rstrip("/") + "/", path.lstrip("/"))
                            tasks.append(
                                RetrievalTask(
                                    task_type="scrape",
                                    provider="firecrawl",
                                    query=query_text,
                                    source_id=source.id,
                                    source_name=source.name,
                                    source_url=scrape_url,
                                    request={
                                        "url": scrape_url,
                                        "source_id": source.id,
                                        "source_name": source.name,
                                        "source_type": source.source_type.value,
                                        "dimension": dimension.value,
                                        "what_to_find": what_to_find,
                                    },
                                )
                            )

        batch.tasks = tasks
        return {
            "query": batch.query,
            "entity_id": batch.entity_id,
            "entity_name": batch.entity_name,
            "task_count": len(tasks),
            "tasks": [asdict(task) for task in tasks],
        }

    def _build_search_request(
        self,
        *,
        source_id: str,
        source_name: str,
        source_url: str,
        dimension: DimensionKey,
        query: str,
        provider: str,
    ) -> RetrievalTask:
        source = self._registry.by_id(source_id)
        if source is None:
            raise PlannerError(f"Unknown source_id: {source_id}")

        operator = source.search_operator or f"site:{source.url.replace('https://', '').replace('http://', '').rstrip('/')}"
        search_query = f"{operator} {query}".strip()

        request = self._search_request_payload(provider=provider, query=search_query, source=source, dimension=dimension)

        return RetrievalTask(
            task_type="search",
            provider=provider,
            query=search_query,
            source_id=source_id,
            source_name=source_name,
            source_url=source_url,
            request={
                **request,
                "source_id": source_id,
                "source_name": source_name,
                "source_type": source.source_type.value,
                "dimension": dimension.value,
                "search_operator": operator,
            },
        )

    def _strategy_for(self, dimension: DimensionKey) -> "ExecutionStrategy":
        if dimension == DimensionKey.FINANCIAL:
            return ExecutionStrategy(search_provider="tavily", scrape_crawl_paths=True)
        if dimension == DimensionKey.EXPERT:
            return ExecutionStrategy(search_provider="tavily", scrape_crawl_paths=False)
        if dimension == DimensionKey.NEWS:
            return ExecutionStrategy(search_provider="tavily", scrape_crawl_paths=False)
        if dimension == DimensionKey.INTERNATIONAL:
            return ExecutionStrategy(search_provider="serper", scrape_crawl_paths=True)
        if dimension == DimensionKey.ASSOCIATIONS:
            return ExecutionStrategy(search_provider="tavily", scrape_crawl_paths=False)
        return ExecutionStrategy(search_provider="serper", scrape_crawl_paths=True)

    def _search_request_payload(self, *, provider: str, query: str, source: Any, dimension: DimensionKey) -> dict[str, Any]:
        if provider == "tavily":
            parsed_url = urlparse(str(source.url))
            include_domain = parsed_url.netloc or parsed_url.path
            topic = "news" if dimension == DimensionKey.NEWS else "general"
            return {
                "endpoint": "https://api.tavily.com/search",
                "body": {
                    "query": query,
                    "topic": topic,
                    "search_depth": "advanced",
                    "max_results": 5,
                    "include_raw_content": False,
                    "include_answer": False,
                    "include_domains": [include_domain] if include_domain else [],
                },
                "auth_env": "TAVILY_API_KEY",
            }

        return {
            "endpoint": "https://google.serper.dev/search",
            "body": {
                "q": query,
                "num": 5,
                "gl": "ng",
                "hl": "en",
            },
            "headers": {
                "X-API-KEY": "SERPER_API_KEY",
            },
        }


@dataclass(frozen=True)
class ExecutionStrategy:
    search_provider: str | None
    scrape_crawl_paths: bool