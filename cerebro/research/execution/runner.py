"""Execute Step 2 retrieval tasks against external providers."""

from __future__ import annotations

import asyncio
import os
import re
from typing import Any
from urllib.parse import urlparse

import httpx

from cerebro.research.errors import PlannerError


class RetrievalExecutor:
    """Execute search and scrape tasks against provider APIs."""

    def __init__(self, *, timeout_seconds: float = 60.0) -> None:
        self._timeout_seconds = timeout_seconds

    async def run(self, execution_batch: dict[str, Any]) -> dict[str, Any]:
        tasks = execution_batch.get("tasks")
        if not isinstance(tasks, list):
            raise PlannerError("execution_batch.tasks must be a list")

        sem = asyncio.Semaphore(int(os.environ.get("RETRIEVAL_CONCURRENCY", "6")))

        async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
            results = await asyncio.gather(
                *(self._run_task(client, sem, task) for task in tasks if isinstance(task, dict)),
                return_exceptions=True,
            )

        documents: list[dict[str, Any]] = []
        errors: list[str] = []
        for result in results:
            if isinstance(result, Exception):
                errors.append(str(result))
                continue
            if result is None:
                continue
            documents.extend(result)

        return {
            "query": execution_batch.get("query"),
            "entity_id": execution_batch.get("entity_id"),
            "entity_name": execution_batch.get("entity_name"),
            "document_count": len(documents),
            "error_count": len(errors),
            "errors": errors,
            "documents": documents,
        }

    async def _run_task(
        self,
        client: httpx.AsyncClient,
        sem: asyncio.Semaphore,
        task: dict[str, Any],
    ) -> list[dict[str, Any]] | None:
        async with sem:
            task_type = task.get("task_type")
            provider = task.get("provider")
            request = task.get("request") or {}
            if not isinstance(request, dict):
                raise PlannerError("task.request must be an object")

            if task_type == "search":
                return await self._run_search(client, provider, task, request)
            if task_type == "scrape":
                return await self._run_scrape(client, provider, task, request)

            raise PlannerError(f"Unsupported task_type: {task_type}")

    async def _run_search(
        self,
        client: httpx.AsyncClient,
        provider: str,
        task: dict[str, Any],
        request: dict[str, Any],
        *,
        allow_fallback: bool = True,
    ) -> list[dict[str, Any]]:
        endpoint = request.get("endpoint")
        body = request.get("body") or {}
        if not isinstance(body, dict):
            raise PlannerError("search request body must be an object")

        if provider == "tavily":
            body = self._sanitize_tavily_body(body)

        headers = self._provider_headers(provider, request)
        try:
            response = await client.post(str(endpoint), json=body, headers=headers)
            if response.status_code >= 400:
                raise PlannerError(
                    f"{provider} search failed status={response.status_code} body={response.text[:1200]} request={body}"
                )
            payload = response.json()
        except Exception as exc:
            status = self._extract_status(str(exc))
            if not allow_fallback or status not in {400, 402, 429, 500, 502, 503, 504}:
                raise

            # fallback chain
            if provider == "tavily":
                fallback_payload = await self._run_fallback_search(client, "serper", task, body)
                return fallback_payload
            fallback_payload = await self._run_fallback_search(client, "tavily", task, body)
            return fallback_payload

        if provider == "tavily":
            results = payload.get("results") or []
            if not isinstance(results, list):
                results = []
            return [
                {
                    "provider": provider,
                    "task_type": "search",
                    "source_id": task.get("source_id"),
                    "source_name": task.get("source_name"),
                    "source_type": request.get("source_type"),
                    "source_url": item.get("url"),
                    "dimension": request.get("dimension"),
                    "query": task.get("query"),
                    "title": item.get("title"),
                    "content": item.get("content") or item.get("snippet"),
                    "published_date": item.get("published_date"),
                    "score": item.get("score"),
                    "raw": item,
                }
                for item in results
                if isinstance(item, dict)
            ]

        results = payload.get("organic") or payload.get("results") or []
        if not isinstance(results, list):
            results = []
        return [
            {
                "provider": provider,
                "task_type": "search",
                "source_id": task.get("source_id"),
                "source_name": task.get("source_name"),
                "source_type": request.get("source_type"),
                "source_url": item.get("link"),
                "dimension": request.get("dimension"),
                "query": task.get("query"),
                "title": item.get("title"),
                "content": item.get("snippet"),
                "date": item.get("date"),
                "position": item.get("position"),
                "raw": item,
            }
            for item in results
            if isinstance(item, dict)
        ]

    async def _run_scrape(
        self,
        client: httpx.AsyncClient,
        provider: str,
        task: dict[str, Any],
        request: dict[str, Any],
    ) -> list[dict[str, Any]]:
        endpoint = str(request.get("endpoint") or os.environ.get("FIRECRAWL_SCRAPE_ENDPOINT", "https://api.firecrawl.dev/v1/scrape"))
        body = dict(request)
        body.pop("endpoint", None)
        headers = self._provider_headers(provider, request)
        try:
            response = await client.post(endpoint, json=body, headers=headers)
            if response.status_code >= 400:
                raise PlannerError(
                    f"firecrawl scrape failed status={response.status_code} body={response.text[:1200]} request={body}"
                )
            payload = response.json()
        except Exception as exc:
            status = self._extract_status(str(exc))
            if status not in {400, 402, 429, 500, 502, 503, 504}:
                raise
            # firecrawl fallback: tavily then serper
            query = f"{task.get('source_url', '')} {task.get('query', '')}".strip()
            fallback_task = {
                "query": query,
                "request": {
                    "endpoint": "https://api.tavily.com/search",
                    "body": {
                        "query": query,
                        "topic": "general",
                        "search_depth": "advanced",
                        "max_results": 5,
                    },
                },
            }
            try:
                return await self._run_search(client, "tavily", fallback_task, fallback_task["request"])
            except Exception:
                fallback_task["request"] = {
                    "endpoint": "https://google.serper.dev/search",
                    "body": {"q": f"site:{self._domain(task.get('source_url'))} {task.get('query', '')}".strip(), "num": 5, "gl": "ng", "hl": "en"},
                }
                return await self._run_search(client, "serper", fallback_task, fallback_task["request"])

        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict):
            data = payload if isinstance(payload, dict) else {}

        return [
            {
                "provider": provider,
                "task_type": "scrape",
                "source_id": task.get("source_id"),
                "source_name": task.get("source_name"),
                "source_type": request.get("source_type"),
                "source_url": task.get("source_url"),
                "dimension": request.get("dimension"),
                "query": task.get("query"),
                "title": data.get("metadata", {}).get("title") if isinstance(data.get("metadata"), dict) else data.get("title"),
                "content": data.get("markdown") or data.get("text") or data.get("content"),
                "raw": data,
            }
        ]

    def _provider_headers(self, provider: str, request: dict[str, Any]) -> dict[str, str]:
        headers: dict[str, str] = {"Content-Type": "application/json"}

        if provider == "serper":
            api_key = os.environ.get("SERPER_API_KEY", "").strip()
            if not api_key:
                raise PlannerError("SERPER_API_KEY is not configured")
            headers["X-API-KEY"] = api_key
            return headers

        if provider == "tavily":
            api_key = os.environ.get("TAVILY_API_KEY", "").strip()
            if not api_key:
                raise PlannerError("TAVILY_API_KEY is not configured")
            headers["Authorization"] = f"Bearer {api_key}"
            return headers

        if provider == "firecrawl":
            api_key = os.environ.get("FIRECRAWL_API_KEY", "").strip()
            if not api_key:
                raise PlannerError("FIRECRAWL_API_KEY is not configured")
            headers["Authorization"] = f"Bearer {api_key}"
            return headers

        raise PlannerError(f"Unsupported provider: {provider}")

    async def _run_fallback_search(
        self,
        client: httpx.AsyncClient,
        provider: str,
        task: dict[str, Any],
        previous_body: dict[str, Any],
    ) -> list[dict[str, Any]]:
        if provider == "tavily":
            fallback_request = {
                "endpoint": "https://api.tavily.com/search",
                "body": {
                    "query": previous_body.get("query") or task.get("query") or "",
                    "topic": "general",
                    "search_depth": "advanced",
                    "max_results": 5,
                    "include_raw_content": False,
                    "include_answer": False,
                },
            }
        else:
            fallback_request = {
                "endpoint": "https://google.serper.dev/search",
                "body": {
                    "q": previous_body.get("query") or previous_body.get("q") or task.get("query") or "",
                    "num": 5,
                    "gl": "ng",
                    "hl": "en",
                },
            }
        return await self._run_search(client, provider, task, fallback_request, allow_fallback=False)
        

    def _sanitize_tavily_body(self, body: dict[str, Any]) -> dict[str, Any]:
        query = str(body.get("query") or "")
        query = re.sub(r"[\(\)\[\]\{\}\|\\\^~`<>\"]", " ", query)
        query = re.sub(r"\s+", " ", query).strip()[:400]
        topic = str(body.get("topic") or "general")
        if topic not in {"news", "general"}:
            topic = "general"

        sanitized = dict(body)
        sanitized["query"] = query
        sanitized["topic"] = topic

        include_domains = sanitized.get("include_domains")
        if isinstance(include_domains, list):
            domains = []
            for value in include_domains:
                parsed = urlparse(value if "://" in str(value) else f"https://{value}")
                if parsed.netloc:
                    domains.append(parsed.netloc)
            if domains:
                sanitized["include_domains"] = sorted(set(domains))
            else:
                sanitized.pop("include_domains", None)
        return sanitized

    def _extract_status(self, text: str) -> int | None:
        match = re.search(r"status=(\d{3})", text)
        if match:
            return int(match.group(1))
        return None

    def _domain(self, url: Any) -> str:
        parsed = urlparse(str(url or ""))
        return parsed.netloc or str(url or "")