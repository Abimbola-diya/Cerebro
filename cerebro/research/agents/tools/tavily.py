"""Tavily search tool wrapper."""

from __future__ import annotations

import os
import re
from typing import Any
from urllib.parse import urlparse

import httpx

from cerebro.research.errors import PlannerError


class TavilyTool:
    def __init__(self, *, timeout_seconds: float = 45.0) -> None:
        self._timeout_seconds = timeout_seconds
        self._client = httpx.AsyncClient(timeout=self._timeout_seconds)

    async def search(self, *, query: str, topic: str = "general", include_domains: list[str] | None = None) -> dict[str, Any]:
        api_key = os.environ.get("TAVILY_API_KEY", "").strip()
        if not api_key:
            raise PlannerError("TAVILY_API_KEY is not configured")

        sanitized_query = self._sanitize_query(query)
        sanitized_topic = topic if topic in {"news", "general"} else "general"
        sanitized_domains = self._sanitize_domains(include_domains)

        body: dict[str, Any] = {
            "query": sanitized_query,
            "topic": sanitized_topic,
            "search_depth": "advanced",
            "max_results": 10,
            "include_raw_content": False,
            "include_answer": False,
        }
        if sanitized_domains:
            body["include_domains"] = sanitized_domains

        response = await self._client.post(
            "https://api.tavily.com/search",
            json=body,
            headers={"Authorization": f"Bearer {api_key}"},
        )
        if response.status_code >= 400:
            response_text = response.text[:1200]
            raise PlannerError(
                "Tavily request failed "
                f"status={response.status_code} body={response_text} request={body}"
            )

        payload = response.json()
        if isinstance(payload, dict):
            payload.setdefault("_debug", {})
            payload["_debug"].update(
                {
                    "sanitized_request": body,
                    "provider": "tavily",
                }
            )
        return payload

    def _sanitize_query(self, query: str) -> str:
        cleaned = re.sub(r"[\(\)\[\]\{\}\|\\\^~`<>\"]", " ", query)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if len(cleaned) > 400:
            cleaned = cleaned[:400].rstrip()
        return cleaned

    def _sanitize_domains(self, include_domains: list[str] | None) -> list[str] | None:
        if not include_domains:
            return None
        normalized: list[str] = []
        for value in include_domains:
            parsed = urlparse(value if "://" in value else f"https://{value}")
            netloc = parsed.netloc.strip().lower()
            if not netloc:
                continue
            if netloc.startswith("www."):
                netloc = netloc[4:]
            normalized.append(netloc)
        unique = sorted(set(normalized))
        return unique or None