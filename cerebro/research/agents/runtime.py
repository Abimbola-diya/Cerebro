"""LangGraph-backed research agent runtime."""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from cerebro.research.contracts.enums import ALL_DIMENSIONS, DimensionKey, SourceTier
from cerebro.research.errors import PlannerError
from cerebro.research.sources.models import SourceRecord
from cerebro.research.sources.registry import registry

from .adapter import ResearchAdapter, ResearchWorkingState
from .base_agent import BaseResearchAgent
from .langchain_tools import build_tools_for_dimension
from .layout import AGENT_OUTPUT_SCHEMA_FILE, DIMENSION_PROMPT_FILES, DIMENSION_RESULT_FILES, PROMPTS_DIR, SCHEMAS_DIR
from .tools import CrawlbaseTool, FirecrawlTool, SerperTool, TavilyTool


PRIORITY_ORDER = {
    "CRITICAL": 0,
    "HIGH": 0,
    "MEDIUM": 1,
    "LOW": 2,
}

MIN_RESULTS_PER_DIMENSION = 3
MAX_EXPANSION_ROUNDS = 2
RETRIEVAL_ROUND_CONCURRENCY = max(1, int(os.environ.get("RETRIEVAL_ROUND_CONCURRENCY", "6")))
SEARCH_RESULTS_PER_PROVIDER = max(1, int(os.environ.get("SEARCH_RESULTS_PER_PROVIDER", "10")))
ARTIFACT_MAX_DOCS = max(0, int(os.environ.get("ARTIFACT_MAX_DOCS", "0")))
AGENT_LOOP_TIMEOUT_SECONDS = max(5.0, float(os.environ.get("AGENT_LOOP_TIMEOUT_SECONDS", "25")))
SOURCE_QUERY_TIMEOUT_SECONDS = max(5.0, float(os.environ.get("SOURCE_QUERY_TIMEOUT_SECONDS", "12")))
_RETRYABLE_HTTP_STATUSES = {400, 402, 429, 500, 502, 503, 504}
_FIRECRAWL_CACHE_TTL_SECONDS = 24 * 60 * 60
PARALLELIZE_ALL_DIMENSIONS = os.environ.get("PARALLELIZE_ALL_DIMENSIONS", "true").strip().lower() in {"1", "true", "yes", "on"}
OVERALL_RUNTIME_CAP_SECONDS = max(30.0, float(os.environ.get("OVERALL_RUNTIME_CAP_SECONDS", "200")))


@dataclass(frozen=True)
class DimensionAgentResult:
    dimension: str
    status: str
    documents: list[dict[str, Any]]
    retrieval_gaps: list[str]
    errors: list[str]
    duration_seconds: float
    expansion_rounds: int = 0


class ResearchAgentRuntime:
    """Run the active dimension agents in priority groups."""

    _firecrawl_cache: dict[str, tuple[float, dict[str, Any]]] = {}

    def __init__(self, adapter: ResearchAdapter | None = None) -> None:
        self._adapter = adapter or ResearchAdapter()
        self._base_agent = BaseResearchAgent(prompts_dir=PROMPTS_DIR, schemas_dir=SCHEMAS_DIR)
        self._tavily = TavilyTool()
        self._serper = SerperTool()
        self._crawlbase = CrawlbaseTool()
        self._firecrawl = FirecrawlTool()

    async def run(self, plan: dict[str, Any], request_id: str | None = None) -> dict[str, Any]:
        run_started = time.monotonic()
        deadline = run_started + OVERALL_RUNTIME_CAP_SECONDS
        working_state = self._adapter.prepare(plan, request_id=request_id)
        active_dimensions = self._active_dimensions(plan)
        grouped_dimensions = self._group_dimensions(plan, active_dimensions)

        batch_order: list[list[DimensionKey]]
        if PARALLELIZE_ALL_DIMENSIONS:
            batch_order = [active_dimensions]
        else:
            batch_order = [grouped_dimensions.get(priority, []) for priority in ("CRITICAL", "HIGH", "MEDIUM")]

        results: dict[str, DimensionAgentResult] = {}
        for dimensions in batch_order:
            if not dimensions:
                continue

            timeout_remaining = deadline - time.monotonic()
            if timeout_remaining <= 0:
                for dimension in dimensions:
                    timeout_result = DimensionAgentResult(
                        dimension=dimension.value,
                        status="PARTIAL",
                        documents=[],
                        retrieval_gaps=[
                            f"overall runtime cap reached ({OVERALL_RUNTIME_CAP_SECONDS}s) before dimension execution"
                        ],
                        errors=[f"overall runtime cap reached ({OVERALL_RUNTIME_CAP_SECONDS}s)"],
                        duration_seconds=0.0,
                        expansion_rounds=0,
                    )
                    results[dimension.value] = timeout_result
                    self._write_dimension_result(working_state, dimension, timeout_result)
                break

            task_by_dimension: dict[DimensionKey, asyncio.Task[DimensionAgentResult]] = {
                dimension: asyncio.create_task(self._run_dimension(plan=plan, working_state=working_state, dimension=dimension))
                for dimension in dimensions
            }
            dimension_by_task = {task: dimension for dimension, task in task_by_dimension.items()}

            done, pending = await asyncio.wait(
                task_by_dimension.values(),
                timeout=timeout_remaining,
                return_when=asyncio.ALL_COMPLETED,
            )

            for task in done:
                dimension = dimension_by_task[task]
                item: DimensionAgentResult | Exception
                try:
                    item = task.result()
                except Exception as exc:  # pragma: no cover - runtime safety path
                    item = exc

                if not isinstance(item, DimensionAgentResult):
                    failure_text = str(item)
                    failure = DimensionAgentResult(
                        dimension=dimension.value,
                        status="PARTIAL",
                        documents=[],
                        retrieval_gaps=[failure_text],
                        errors=[failure_text],
                        duration_seconds=0.0,
                        expansion_rounds=0,
                    )
                    results[dimension.value] = failure
                    self._write_dimension_result(working_state, dimension, failure)
                    continue

                results[dimension.value] = item
                self._write_dimension_result(working_state, dimension, item)

            if pending:
                for task in pending:
                    task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)

                for task in pending:
                    dimension = dimension_by_task[task]
                    timeout_result = DimensionAgentResult(
                        dimension=dimension.value,
                        status="PARTIAL",
                        documents=[],
                        retrieval_gaps=[f"dimension timed out due overall runtime cap ({OVERALL_RUNTIME_CAP_SECONDS}s)"],
                        errors=[f"dimension timed out due overall runtime cap ({OVERALL_RUNTIME_CAP_SECONDS}s)"],
                        duration_seconds=0.0,
                        expansion_rounds=0,
                    )
                    results[dimension.value] = timeout_result
                    self._write_dimension_result(working_state, dimension, timeout_result)
                break

        summary = self._write_orchestrator_summary(working_state, plan, results)
        return {
            "request_id": working_state.request_id,
            "working_files": sorted(working_state.files.keys()),
            "results": {dimension: self._serialize_result(result) for dimension, result in results.items()},
            "summary": summary,
            "working_state": working_state,
        }

    async def _run_dimension(
        self,
        *,
        plan: dict[str, Any],
        working_state: ResearchWorkingState,
        dimension: DimensionKey,
    ) -> DimensionAgentResult:
        research_plan = plan.get("research_plan") or {}
        block = research_plan.get(dimension.value) if isinstance(research_plan, dict) else {}
        if not isinstance(block, dict):
            raise PlannerError(f"Missing plan block for {dimension.value}")

        prompt_filename = DIMENSION_PROMPT_FILES[dimension]
        schema_text = working_state.read_file(f"schemas/{AGENT_OUTPUT_SCHEMA_FILE}")
        prompt_text = working_state.read_file(f"prompts/{prompt_filename}")
        briefing_text = f"{prompt_text}\n\nOUTPUT SCHEMA:\n{schema_text}"

        model = self._build_model()
        tools = build_tools_for_dimension(dimension)
        agent = create_react_agent(
            model=model,
            tools=tools,
            prompt=briefing_text,
            version="v2",
            name=dimension.value,
        )

        total_start = time.monotonic()
        message_payload = self._build_dimension_payload(plan=plan, dimension=dimension, block=block, working_state=working_state)

        agent_start = time.monotonic()
        try:
            response = await asyncio.wait_for(
                agent.ainvoke({"messages": [HumanMessage(content=message_payload)]}),
                timeout=AGENT_LOOP_TIMEOUT_SECONDS,
            )
            agent_duration = round(time.monotonic() - agent_start, 3)
            print(f"[TIMING] {dimension.value} agent_loop={agent_duration}s", flush=True)

            final_text = self._extract_final_text(response)
            parsed = self._parse_agent_output(final_text, dimension)
        except asyncio.TimeoutError:
            agent_duration = round(time.monotonic() - agent_start, 3)
            print(
                f"[TIMING] {dimension.value} agent_loop_timeout={agent_duration}s limit={AGENT_LOOP_TIMEOUT_SECONDS}s",
                flush=True,
            )
            parsed = {
                "dimension": dimension.value,
                "status": "PARTIAL",
                "documents": [],
                "retrieval_gaps": [f"agent loop timed out after {AGENT_LOOP_TIMEOUT_SECONDS}s"],
                "errors": [f"agent loop timed out after {AGENT_LOOP_TIMEOUT_SECONDS}s"],
            }

        agent_documents = [doc for doc in list(parsed.get("documents") or []) if self._is_valid_document(doc)]
        agent_gaps = list(parsed.get("retrieval_gaps") or [])
        agent_errors = list(parsed.get("errors") or [])

        retrieval_start = time.monotonic()
        if len(agent_documents) >= MIN_RESULTS_PER_DIMENSION:
            recovered_documents = self._dedupe_documents(agent_documents)
            recovered_gaps = agent_gaps
            recovered_errors = agent_errors
            expansion_rounds = 0
            retrieval_duration = round(time.monotonic() - retrieval_start, 3)
            print(
                f"[TIMING] {dimension.value} retrieval_pass={retrieval_duration}s docs_found={len(recovered_documents)} mode=skipped",
                flush=True,
            )
        else:
            recovered_documents, recovered_gaps, recovered_errors, expansion_rounds = await self._resilient_dimension_retrieval(
                plan=plan,
                dimension=dimension,
                block=block,
                current_documents=agent_documents,
                current_gaps=agent_gaps,
                current_errors=agent_errors,
            )
            retrieval_duration = round(time.monotonic() - retrieval_start, 3)
            print(
                f"[TIMING] {dimension.value} retrieval_pass={retrieval_duration}s docs_found={len(recovered_documents)} mode=fallback",
                flush=True,
            )
        
        total_duration = round(time.monotonic() - total_start, 3)
        print(f"[TIMING] {dimension.value} TOTAL={total_duration}s (agent={agent_duration}s + retrieval={retrieval_duration}s)", flush=True)

        status = str(parsed.get("status") or "PARTIAL")
        if recovered_documents:
            status = "COMPLETED" if len(recovered_documents) >= MIN_RESULTS_PER_DIMENSION else "PARTIAL"
        elif status == "COMPLETED":
            status = "PARTIAL"

        recovered_gaps = list(dict.fromkeys(recovered_gaps))
        recovered_errors = list(dict.fromkeys(recovered_errors))
        parsed["duration_seconds"] = total_duration
        parsed["agent_duration_seconds"] = agent_duration
        parsed["retrieval_duration_seconds"] = retrieval_duration
        parsed["expansion_rounds"] = expansion_rounds
        return DimensionAgentResult(
            dimension=dimension.value,
            status=status,
            documents=recovered_documents,
            retrieval_gaps=recovered_gaps,
            errors=recovered_errors,
            duration_seconds=total_duration,
            expansion_rounds=expansion_rounds,
        )

    async def _resilient_dimension_retrieval(
        self,
        *,
        plan: dict[str, Any],
        dimension: DimensionKey,
        block: dict[str, Any],
        current_documents: list[dict[str, Any]],
        current_gaps: list[str],
        current_errors: list[str],
    ) -> tuple[list[dict[str, Any]], list[str], list[str], int]:
        documents = [doc for doc in current_documents if self._is_valid_document(doc)]
        gaps = list(current_gaps)
        errors = list(current_errors)

        queried_sources: set[str] = set()
        targeted_sources = self._targeted_source_ids(block)
        sub_queries = self._sub_query_texts(block)
        if not sub_queries:
            sub_queries = [str(plan.get("query") or "")]

        primary_docs, primary_gaps, primary_errors, primary_timeouts = await self._run_sources_round(
            dimension=dimension,
            source_ids=targeted_sources,
            sub_queries=sub_queries,
            queried_sources=queried_sources,
            retrieval_method="primary",
        )
        documents.extend(primary_docs)
        gaps.extend(primary_gaps)
        errors.extend(primary_errors)
        documents = self._dedupe_documents(documents)

        expansion_rounds = 0
        if primary_timeouts > 0 and self._valid_document_count(documents) == 0:
            gaps.append(
                f"Primary round timed out across {primary_timeouts} source-query jobs for {dimension.value}; skipping expansion"
            )
            return documents, gaps, errors, expansion_rounds

        if self._valid_document_count(documents) < MIN_RESULTS_PER_DIMENSION:
            core_sources = self._expansion_sources(dimension, SourceTier.CORE, queried_sources)
            if core_sources:
                expansion_rounds += 1
                core_docs, core_gaps, core_errors, _core_timeouts = await self._run_sources_round(
                    dimension=dimension,
                    source_ids=[item.id for item in core_sources[:3]],
                    sub_queries=sub_queries,
                    queried_sources=queried_sources,
                    retrieval_method="fallback_1",
                )
                documents.extend(core_docs)
                gaps.extend(core_gaps)
                errors.extend(core_errors)
                documents = self._dedupe_documents(documents)

        if expansion_rounds < MAX_EXPANSION_ROUNDS and self._valid_document_count(documents) < MIN_RESULTS_PER_DIMENSION:
            extended_sources = self._expansion_sources(dimension, SourceTier.EXTENDED, queried_sources)
            if extended_sources:
                expansion_rounds += 1
                ext_docs, ext_gaps, ext_errors, _ext_timeouts = await self._run_sources_round(
                    dimension=dimension,
                    source_ids=[item.id for item in extended_sources[:3]],
                    sub_queries=sub_queries,
                    queried_sources=queried_sources,
                    retrieval_method="fallback_2",
                )
                documents.extend(ext_docs)
                gaps.extend(ext_gaps)
                errors.extend(ext_errors)
                documents = self._dedupe_documents(documents)

        return documents, gaps, errors, expansion_rounds

    async def _run_sources_round(
        self,
        *,
        dimension: DimensionKey,
        source_ids: list[str],
        sub_queries: list[str],
        queried_sources: set[str],
        retrieval_method: str,
    ) -> tuple[list[dict[str, Any]], list[str], list[str], int]:
        documents: list[dict[str, Any]] = []
        gaps: list[str] = []
        errors: list[str] = []
        timeouts = 0
        round_start = time.monotonic()

        selected_sources: list[SourceRecord] = []
        for source_id in source_ids:
            source = registry.by_id(source_id)
            if source is None or source.id in queried_sources:
                continue
            queried_sources.add(source.id)
            selected_sources.append(source)

        jobs: list[tuple[SourceRecord, str]] = [
            (source, sub_query)
            for source in selected_sources
            for sub_query in sub_queries
        ]
        semaphore = asyncio.Semaphore(RETRIEVAL_ROUND_CONCURRENCY)

        async def _run_single_query(source: SourceRecord, sub_query: str) -> tuple[list[dict[str, Any]], list[str], list[str]]:
            query_start = time.monotonic()
            try:
                async with semaphore:
                    docs, doc_gaps, doc_errors = await asyncio.wait_for(
                        self._retrieve_for_source(
                            dimension=dimension,
                            source=source,
                            sub_query=sub_query,
                            retrieval_method=retrieval_method,
                        ),
                        timeout=SOURCE_QUERY_TIMEOUT_SECONDS,
                    )
            except asyncio.TimeoutError:
                return [], [f"query_timeout source={source.id} method={retrieval_method}"], [
                    f"query_timeout source={source.id} method={retrieval_method}"
                ]
            query_dur = round(time.monotonic() - query_start, 2)
            if docs:
                print(
                    f"  [QUERY] {dimension.value} src={source.id[:15]} method={retrieval_method} docs={len(docs)} time={query_dur}s",
                    flush=True,
                )
            return docs, doc_gaps, doc_errors

        results = await asyncio.gather(
            *(_run_single_query(source, sub_query) for source, sub_query in jobs),
            return_exceptions=True,
        )

        for (source, sub_query), result in zip(jobs, results, strict=False):
            if isinstance(result, BaseException):
                message = f"retrieval failed source={source.id} query={sub_query[:120]} error={result}"
                gaps.append(message)
                errors.append(message)
                continue
            if not isinstance(result, tuple) or len(result) != 3:
                message = f"retrieval failed source={source.id} query={sub_query[:120]} error=unexpected result"
                gaps.append(message)
                errors.append(message)
                continue
            docs, doc_gaps, doc_errors = result
            documents.extend(docs)
            gaps.extend(doc_gaps)
            errors.extend(doc_errors)
            timeouts += len([item for item in doc_errors if "query_timeout" in item])
        
        round_dur = round(time.monotonic() - round_start, 2)
        print(f"  [ROUND] {dimension.value} method={retrieval_method} total_docs={len(documents)} time={round_dur}s", flush=True)
        return documents, gaps, errors, timeouts

    async def _retrieve_for_source(
        self,
        *,
        dimension: DimensionKey,
        source: SourceRecord,
        sub_query: str,
        retrieval_method: str,
    ) -> tuple[list[dict[str, Any]], list[str], list[str]]:
        provider = self._primary_provider_for_dimension(dimension)
        docs: list[dict[str, Any]] = []
        gaps: list[str] = []
        errors: list[str] = []

        if retrieval_method == "primary":
            query_variants = self._query_variants(source=source, dimension=dimension, sub_query=sub_query)
        else:
            query_variants = [sub_query[:400]]

        for query in query_variants:
            found_docs, found_gaps, found_errors = await self._execute_search_with_fallback(
                primary_provider=provider,
                query=query,
                dimension=dimension,
                source=source,
                retrieval_method=retrieval_method,
            )
            docs.extend(found_docs)
            gaps.extend(found_gaps)
            errors.extend(found_errors)
        docs = self._rank_and_trim_documents(self._dedupe_documents(docs), SEARCH_RESULTS_PER_PROVIDER)

        if retrieval_method == "primary" and len(docs) >= 2 and len(docs) < SEARCH_RESULTS_PER_PROVIDER:
            hydrated_docs, hydrated_gaps, hydrated_errors = await self._hydrate_documents_with_firecrawl(
                source=source,
                dimension=dimension,
                query=sub_query,
                base_docs=docs,
            )
            docs.extend(hydrated_docs)
            gaps.extend(hydrated_gaps)
            errors.extend(hydrated_errors)
            docs = self._rank_and_trim_documents(self._dedupe_documents(docs), SEARCH_RESULTS_PER_PROVIDER)

        docs.extend(self._artifact_documents(docs, dimension=dimension, source=source, query=sub_query))

        # Only spend crawl path budget if direct retrieval is still sparse.
        if len(docs) < MIN_RESULTS_PER_DIMENSION and source.tier == SourceTier.CORE and source.crawl_paths:
            crawl_path = source.crawl_paths[0]
            scrape_url = self._join_source_url(source.url, crawl_path)
            scrape_docs, scrape_gaps, scrape_errors = await self._execute_firecrawl_with_fallback(
                source=source,
                scrape_url=scrape_url,
                query=sub_query,
                dimension=dimension,
                retrieval_method=retrieval_method,
            )
            docs.extend(scrape_docs)
            gaps.extend(scrape_gaps)
            errors.extend(scrape_errors)

        return self._rank_and_trim_documents(self._dedupe_documents(docs), SEARCH_RESULTS_PER_PROVIDER), gaps, errors

    async def _hydrate_documents_with_firecrawl(
        self,
        *,
        source: SourceRecord,
        dimension: DimensionKey,
        query: str,
        base_docs: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[str], list[str]]:
        hydrated: list[dict[str, Any]] = []
        gaps: list[str] = []
        errors: list[str] = []

        max_hydrate = int(os.environ.get("FIRECRAWL_HYDRATE_MAX_PER_QUERY", "1"))
        for doc in base_docs:
            if len(hydrated) >= max_hydrate:
                break
            if not isinstance(doc, dict):
                continue
            candidate_url = str(doc.get("url") or doc.get("source") or "").strip()
            if not candidate_url.startswith("http"):
                continue

            try:
                scraped = await self._crawlbase.scrape(url=candidate_url, javascript=False)
                normalized = self._normalize_firecrawl_payload(
                    scraped,
                    source,
                    dimension,
                    query,
                    "hydrate",
                    provider="crawlbase",
                )
                if normalized:
                    normalized["hydrated_from"] = candidate_url
                    hydrated.append(normalized)
                    continue
            except Exception as exc:
                errors.append(f"crawlbase normal hydrate failed for {candidate_url}: {exc}")

            try:
                js_scraped = await self._crawlbase.scrape(url=candidate_url, javascript=True)
                normalized = self._normalize_firecrawl_payload(
                    js_scraped,
                    source,
                    dimension,
                    query,
                    "hydrate_js",
                    provider="crawlbase",
                )
                if normalized:
                    normalized["hydrated_from"] = candidate_url
                    hydrated.append(normalized)
                    continue
            except Exception as exc:
                errors.append(f"crawlbase js hydrate failed for {candidate_url}: {exc}")

            gaps.append(f"hydrate failed after crawlbase normal/js for {candidate_url}")

        return hydrated, gaps, errors

    async def _execute_search_with_fallback(
        self,
        *,
        primary_provider: str,
        query: str,
        dimension: DimensionKey,
        source: SourceRecord,
        retrieval_method: str,
    ) -> tuple[list[dict[str, Any]], list[str], list[str]]:
        gaps: list[str] = []
        errors: list[str] = []

        try:
            if primary_provider == "tavily":
                payload = await self._tavily.search(
                    query=query,
                    topic="news" if dimension == DimensionKey.NEWS else "general",
                    include_domains=[source.url],
                )
                docs = self._normalize_tavily_payload(payload, source, dimension, query, retrieval_method)
                if docs:
                    return docs, gaps, errors
            else:
                payload = await self._serper.search(query=query)
                docs = self._normalize_serper_payload(payload, source, dimension, query, retrieval_method)
                if docs:
                    return docs, gaps, errors
        except Exception as exc:
            status = self._extract_status_code(str(exc))
            gaps.append(f"{primary_provider} primary failed: {exc}")
            errors.append(f"{primary_provider} primary failed: {exc}")
            if status not in _RETRYABLE_HTTP_STATUSES:
                return [], gaps, errors

            if primary_provider == "tavily":
                retry_docs, retry_errors = await self._fallback_serper(query, source, dimension, retrieval_method)
                errors.extend(retry_errors)
                return retry_docs, gaps, errors

            retry_docs, retry_errors = await self._fallback_tavily(query, source, dimension, retrieval_method)
            errors.extend(retry_errors)
            return retry_docs, gaps, errors

        return [], gaps, errors

    async def _execute_firecrawl_with_fallback(
        self,
        *,
        source: SourceRecord,
        scrape_url: str,
        query: str,
        dimension: DimensionKey,
        retrieval_method: str,
    ) -> tuple[list[dict[str, Any]], list[str], list[str]]:
        gaps: list[str] = []
        errors: list[str] = []

        # Use 24h cache to avoid burning Firecrawl credits repeatedly.
        cached = self._firecrawl_cache.get(scrape_url)
        if cached and (time.time() - cached[0]) < _FIRECRAWL_CACHE_TTL_SECONDS:
            return [cached[1]], gaps, errors

        try:
            payload = await self._crawlbase.scrape(url=scrape_url, javascript=False)
            doc = self._normalize_firecrawl_payload(
                payload,
                source,
                dimension,
                query,
                retrieval_method,
                provider="crawlbase",
            )
            if doc is not None:
                self._firecrawl_cache[scrape_url] = (time.time(), doc)
                return [doc], gaps, errors
        except Exception as exc:
            gaps.append(f"crawlbase normal failed: {exc}")
            errors.append(f"crawlbase normal failed: {exc}")

        try:
            js_payload = await self._crawlbase.scrape(url=scrape_url, javascript=True)
            js_doc = self._normalize_firecrawl_payload(
                js_payload,
                source,
                dimension,
                query,
                f"{retrieval_method}_js",
                provider="crawlbase",
            )
            if js_doc is not None:
                self._firecrawl_cache[scrape_url] = (time.time(), js_doc)
                return [js_doc], gaps, errors
        except Exception as js_exc:
            gaps.append(f"crawlbase js failed: {js_exc}")
            errors.append(f"crawlbase js failed: {js_exc}")

        fallback_query = f"{scrape_url} {query}".strip()
        if self._primary_provider_for_dimension(dimension) == "tavily":
            tav_docs, tav_errors = await self._fallback_tavily(
                query=fallback_query,
                source=source,
                dimension=dimension,
                retrieval_method="fallback_1",
            )
            errors.extend(tav_errors)
            return tav_docs, gaps, errors

        ser_docs, ser_errors = await self._fallback_serper(
            query=f"site:{self._domain(source.url)} {query}".strip(),
            source=source,
            dimension=dimension,
            retrieval_method="fallback_1",
        )
        errors.extend(ser_errors)
        return ser_docs, gaps, errors

        return [], gaps, errors

    async def _fallback_tavily(
        self,
        query: str,
        source: SourceRecord,
        dimension: DimensionKey,
        retrieval_method: str,
    ) -> tuple[list[dict[str, Any]], list[str]]:
        try:
            payload = await self._tavily.search(
                query=query,
                topic="news" if dimension == DimensionKey.NEWS else "general",
                include_domains=[source.url],
            )
            docs = self._normalize_tavily_payload(payload, source, dimension, query, retrieval_method)
            return docs, []
        except Exception as exc:
            return [], [f"tavily fallback failed: {exc}"]

    async def _fallback_serper(
        self,
        query: str,
        source: SourceRecord,
        dimension: DimensionKey,
        retrieval_method: str,
    ) -> tuple[list[dict[str, Any]], list[str]]:
        try:
            payload = await self._serper.search(query=query)
            docs = self._normalize_serper_payload(payload, source, dimension, query, retrieval_method)
            return docs, []
        except Exception as exc:
            return [], [f"serper fallback failed: {exc}"]

    def _normalize_tavily_payload(
        self,
        payload: dict[str, Any],
        source: SourceRecord,
        dimension: DimensionKey,
        query: str,
        retrieval_method: str,
    ) -> list[dict[str, Any]]:
        results = payload.get("results") if isinstance(payload, dict) else []
        if not isinstance(results, list):
            return []
        documents: list[dict[str, Any]] = []
        for item in results:
            if not isinstance(item, dict):
                continue
            content = str(item.get("content") or item.get("snippet") or "").strip()
            if not content:
                continue
            documents.append(
                {
                    "dimension": dimension.value,
                    "source_id": source.id,
                    "source": item.get("url") or source.url,
                    "url": item.get("url") or source.url,
                    "title": item.get("title"),
                    "content": content,
                    "relevance_score": float(item.get("score") or 0.6),
                    "provider": "tavily",
                    "retrieval_provider": "tavily",
                    "retrieval_method": retrieval_method,
                    "query": query,
                    "published_date": item.get("published_date"),
                    "raw": item,
                }
            )
        documents.sort(key=lambda item: float(item.get("relevance_score") or 0.0), reverse=True)
        return documents[:SEARCH_RESULTS_PER_PROVIDER]

    def _normalize_serper_payload(
        self,
        payload: dict[str, Any],
        source: SourceRecord,
        dimension: DimensionKey,
        query: str,
        retrieval_method: str,
    ) -> list[dict[str, Any]]:
        results = payload.get("organic") if isinstance(payload, dict) else []
        if not isinstance(results, list):
            return []
        documents: list[dict[str, Any]] = []
        for item in results:
            if not isinstance(item, dict):
                continue
            content = str(item.get("snippet") or "").strip()
            if not content:
                continue
            position = item.get("position")
            rank = int(position) if isinstance(position, (int, float, str)) and str(position).isdigit() else None
            relevance_score = round(1.0 / max(rank or 2, 1), 3)
            documents.append(
                {
                    "dimension": dimension.value,
                    "source_id": source.id,
                    "source": item.get("link") or source.url,
                    "url": item.get("link") or source.url,
                    "title": item.get("title"),
                    "content": content,
                    "relevance_score": relevance_score,
                    "provider": "serper",
                    "retrieval_provider": "serper",
                    "retrieval_method": retrieval_method,
                    "query": query,
                    "published_date": item.get("date"),
                    "raw": item,
                }
            )
        documents.sort(key=lambda item: float(item.get("relevance_score") or 0.0), reverse=True)
        return documents[:SEARCH_RESULTS_PER_PROVIDER]

    def _normalize_firecrawl_payload(
        self,
        payload: dict[str, Any],
        source: SourceRecord,
        dimension: DimensionKey,
        query: str,
        retrieval_method: str,
        provider: str = "firecrawl",
    ) -> dict[str, Any] | None:
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict):
            data = payload if isinstance(payload, dict) else {}
        metadata_obj = data.get("metadata")
        metadata = metadata_obj if isinstance(metadata_obj, dict) else {}
        content = str(data.get("markdown") or data.get("text") or data.get("content") or "").strip()
        if not content:
            return None
        return {
            "dimension": dimension.value,
            "source_id": source.id,
            "source": metadata.get("sourceURL") or source.url,
            "url": metadata.get("sourceURL") or source.url,
            "title": metadata.get("title") or source.name,
            "content": content,
            "relevance_score": 0.7,
            "provider": provider,
            "retrieval_provider": provider,
            "retrieval_method": retrieval_method,
            "query": query,
            "raw": data,
        }

    def _targeted_source_ids(self, block: dict[str, Any]) -> list[str]:
        source_ids: list[str] = []
        for sub_query in block.get("sub_queries", []):
            if not isinstance(sub_query, dict):
                continue
            targets = sub_query.get("target_sources")
            if not isinstance(targets, list):
                continue
            for source_id in targets:
                if isinstance(source_id, str) and source_id:
                    source_ids.append(source_id)
        return list(dict.fromkeys(source_ids))

    def _query_variants(self, *, source: SourceRecord, dimension: DimensionKey, sub_query: str) -> list[str]:
        site_query = self._build_query(source, sub_query)
        variants = [site_query]

        # Keep variant fan-out shallow to avoid query explosion.
        if dimension in {DimensionKey.EXPERT, DimensionKey.NEWS, DimensionKey.FINANCIAL, DimensionKey.REGULATORY}:
            variants.append(sub_query[:400])

        # Deduplicate while preserving order.
        deduped: list[str] = []
        seen: set[str] = set()
        for query in variants:
            normalized = query.strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            deduped.append(normalized)
        return deduped

    def _artifact_documents(
        self,
        docs: list[dict[str, Any]],
        *,
        dimension: DimensionKey,
        source: SourceRecord,
        query: str,
    ) -> list[dict[str, Any]]:
        if ARTIFACT_MAX_DOCS <= 0:
            return []
        artifacts: list[dict[str, Any]] = []
        for doc in docs[:ARTIFACT_MAX_DOCS]:
            if not isinstance(doc, dict):
                continue
            title = str(doc.get("title") or "").strip()
            url = str(doc.get("url") or doc.get("source") or "").strip()
            snippet = str(doc.get("content") or "").strip()
            if not (title or snippet):
                continue

            artifact_text = " | ".join(
                part
                for part in [
                    f"title={title}" if title else "",
                    f"url={url}" if url else "",
                    f"snippet={snippet[:300]}" if snippet else "",
                ]
                if part
            )
            artifacts.append(
                {
                    "dimension": dimension.value,
                    "source_id": source.id,
                    "source": url or source.url,
                    "url": url or source.url,
                    "title": title or f"artifact from {source.name}",
                    "content": artifact_text,
                    "relevance_score": float(doc.get("relevance_score") or 0.45),
                    "provider": str(doc.get("provider") or "artifact"),
                    "retrieval_provider": str(doc.get("retrieval_provider") or doc.get("provider") or "artifact"),
                    "retrieval_method": "artifact",
                    "artifact_type": "insight",
                    "query": query,
                }
            )
        return artifacts

    def _sub_query_texts(self, block: dict[str, Any]) -> list[str]:
        texts: list[str] = []
        for item in block.get("sub_queries", []):
            if not isinstance(item, dict):
                continue
            query = item.get("query")
            if isinstance(query, str) and query.strip():
                texts.append(query.strip())
        return texts

    def _expansion_sources(
        self,
        dimension: DimensionKey,
        tier: SourceTier,
        queried_sources: set[str],
    ) -> list[SourceRecord]:
        records = [
            item
            for item in registry.by_dimension(dimension)
            if item.tier == tier and item.id not in queried_sources
        ]
        records.sort(key=lambda item: item.credibility_rank, reverse=True)
        return records

    def _build_query(self, source: SourceRecord, sub_query: str) -> str:
        operator = source.search_operator or f"site:{self._domain(source.url)}"
        query = f"{operator} {sub_query}".strip()
        return query[:400]

    def _join_source_url(self, base_url: str, path: str) -> str:
        return f"{base_url.rstrip('/')}/{path.lstrip('/')}"

    def _domain(self, url: str) -> str:
        parsed = urlparse(url)
        return parsed.netloc or url

    def _extract_status_code(self, message: str) -> int | None:
        match = re.search(r"status=(\d{3})", message)
        if not match:
            return None
        return int(match.group(1))

    def _primary_provider_for_dimension(self, dimension: DimensionKey) -> str:
        if dimension in {DimensionKey.FINANCIAL, DimensionKey.EXPERT, DimensionKey.NEWS, DimensionKey.ASSOCIATIONS}:
            return "tavily"
        return "serper"

    def _is_valid_document(self, doc: Any) -> bool:
        if not isinstance(doc, dict):
            return False
        content = doc.get("content")
        return isinstance(content, str) and bool(content.strip())

    def _valid_document_count(self, documents: list[dict[str, Any]]) -> int:
        return len([doc for doc in documents if self._is_valid_document(doc)])

    def _dedupe_documents(self, documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
        deduped: dict[str, dict[str, Any]] = {}
        for doc in documents:
            if not self._is_valid_document(doc):
                continue
            key = str(doc.get("url") or doc.get("source") or doc.get("content"))
            deduped[key] = doc
        return list(deduped.values())

    def _rank_and_trim_documents(self, documents: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
        ranked = list(documents)
        ranked.sort(key=lambda item: float(item.get("relevance_score") or 0.0), reverse=True)
        return ranked[: max(1, limit)]

    def _build_model(self) -> ChatOpenAI:
        api_key = os.environ.get("NVIDIA_API_KEY", "").strip()
        if not api_key:
            raise PlannerError("NVIDIA_API_KEY is not configured")

        base_url = os.environ.get("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
        model_name = os.environ.get("NVIDIA_MODEL", "nvidia/llama-3.3-nemotron-super-49b-v1")
        temperature = float(os.environ.get("NVIDIA_TEMPERATURE", "0.2"))
        max_completion_tokens = int(os.environ.get("NVIDIA_MAX_TOKENS", "1800"))

        return ChatOpenAI(
            model=model_name,
            api_key=lambda: api_key,
            base_url=base_url,
            temperature=temperature,
            max_completion_tokens=max_completion_tokens,
            stream_usage=True,
        )

    def _build_dimension_payload(
        self,
        *,
        plan: dict[str, Any],
        dimension: DimensionKey,
        block: dict[str, Any],
        working_state: ResearchWorkingState,
    ) -> str:
        payload = {
            "request_id": working_state.request_id,
            "dimension": dimension.value,
            "entity_name": plan.get("entity_name"),
            "entity_id": plan.get("entity_id"),
            "query": plan.get("query"),
            "dimension_plan": block,
            "sub_queries": block.get("sub_queries", []),
            "execution_order": plan.get("execution_order", []),
            "anticipated_gaps": plan.get("anticipated_gaps", []),
            "working_files": sorted(working_state.files.keys()),
            "instruction": (
                "Use the briefing above, inspect the sub_queries, call the available tools, "
                "and return JSON matching the schema. Include documents only when content is non-empty."
            ),
        }
        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)

    def _extract_final_text(self, response: Any) -> str:
        if isinstance(response, dict):
            if "output" in response and isinstance(response["output"], str):
                return response["output"]
            messages = response.get("messages")
            if isinstance(messages, list) and messages:
                last_message = messages[-1]
                content = getattr(last_message, "content", None)
                if isinstance(content, str):
                    return content
                if isinstance(last_message, dict) and isinstance(last_message.get("content"), str):
                    return last_message["content"]
        raise PlannerError("Could not extract final agent response")

    def _parse_agent_output(self, text: str, dimension: DimensionKey) -> dict[str, Any]:
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = {
                "dimension": dimension.value,
                "status": "FAILED",
                "documents": [],
                "retrieval_gaps": ["Agent returned non-JSON output"],
                "errors": [text],
            }
        if not isinstance(parsed, dict):
            parsed = {
                "dimension": dimension.value,
                "status": "FAILED",
                "documents": [],
                "retrieval_gaps": ["Agent output was not an object"],
                "errors": [str(parsed)],
            }
        parsed.setdefault("dimension", dimension.value)
        parsed.setdefault("status", "PARTIAL")
        parsed.setdefault("documents", [])
        parsed.setdefault("retrieval_gaps", [])
        parsed.setdefault("errors", [])
        return parsed

    def _write_dimension_result(
        self,
        working_state: ResearchWorkingState,
        dimension: DimensionKey,
        result: DimensionAgentResult,
    ) -> None:
        file_name = DIMENSION_RESULT_FILES[dimension]
        working_state.write_file(
            f"working/{file_name}",
            json.dumps(
                {
                    "dimension": result.dimension,
                    "status": result.status,
                    "documents": result.documents,
                    "retrieval_gaps": result.retrieval_gaps,
                    "errors": result.errors,
                    "duration_seconds": result.duration_seconds,
                    "expansion_rounds": result.expansion_rounds,
                },
                ensure_ascii=False,
                indent=2,
                default=str,
            ),
        )

    def _write_orchestrator_summary(
        self,
        working_state: ResearchWorkingState,
        plan: dict[str, Any],
        results: dict[str, DimensionAgentResult],
    ) -> dict[str, Any]:
        active_dimensions = [dimension.value for dimension in ALL_DIMENSIONS if dimension.value in results]
        skipped_dimensions = self._skipped_dimensions(plan)
        failed_dimensions = [dimension for dimension, result in results.items() if result.status == "FAILED"]
        summary = {
            "request_id": working_state.request_id,
            "query": plan.get("query"),
            "entity_name": plan.get("entity_name"),
            "active_dimensions": active_dimensions,
            "skipped_dimensions": skipped_dimensions,
            "failed_dimensions": failed_dimensions,
            "result_count": len(results),
        }
        working_state.write_file("orchestrator_summary.json", json.dumps(summary, ensure_ascii=False, indent=2, default=str))
        working_state.write_file("ready_for_synthesis", "true")
        return summary

    def _active_dimensions(self, plan: dict[str, Any]) -> list[DimensionKey]:
        research_plan = plan.get("research_plan")
        if not isinstance(research_plan, dict):
            return []

        active_dimensions: list[DimensionKey] = []
        for dimension in ALL_DIMENSIONS:
            block = research_plan.get(dimension.value)
            if isinstance(block, dict) and str(block.get("status", "")).upper() == "ACTIVE":
                active_dimensions.append(dimension)
        return active_dimensions

    def _skipped_dimensions(self, plan: dict[str, Any]) -> list[str]:
        research_plan = plan.get("research_plan")
        if not isinstance(research_plan, dict):
            return []
        skipped = []
        for dimension in ALL_DIMENSIONS:
            block = research_plan.get(dimension.value)
            if not isinstance(block, dict):
                continue
            if str(block.get("status", "")).upper() == "SKIP":
                skipped.append(dimension.value)
        return skipped

    def _group_dimensions(
        self,
        plan: dict[str, Any],
        active_dimensions: list[DimensionKey],
    ) -> dict[str, list[DimensionKey]]:
        research_plan = plan.get("research_plan") or {}
        order = plan.get("execution_order") or []
        execution_index = {value: index for index, value in enumerate(order) if isinstance(value, str)}

        groups: dict[str, list[DimensionKey]] = {"CRITICAL": [], "HIGH": [], "MEDIUM": []}
        for dimension in active_dimensions:
            block = research_plan.get(dimension.value) if isinstance(research_plan, dict) else {}
            priority = str(block.get("priority", "MEDIUM")).upper() if isinstance(block, dict) else "MEDIUM"
            group = "CRITICAL" if priority in {"CRITICAL", "HIGH"} else "MEDIUM"
            groups.setdefault(group, []).append(dimension)

        for group_name, dimensions in groups.items():
            dimensions.sort(key=lambda dim: execution_index.get(dim.value, len(execution_index)))
        return groups

    def _serialize_result(self, result: DimensionAgentResult) -> dict[str, Any]:
        return {
            "dimension": result.dimension,
            "status": result.status,
            "documents": result.documents,
            "retrieval_gaps": result.retrieval_gaps,
            "errors": result.errors,
            "duration_seconds": result.duration_seconds,
            "expansion_rounds": result.expansion_rounds,
        }
