"""Firecrawl scrape tool wrapper."""

from __future__ import annotations

import os
from typing import Any

import httpx

from cerebro.research.errors import PlannerError


class FirecrawlTool:
    def __init__(self, *, timeout_seconds: float = 60.0) -> None:
        self._timeout_seconds = timeout_seconds
        self._client = httpx.AsyncClient(timeout=self._timeout_seconds)

    async def scrape(self, *, url: str, **payload: Any) -> dict[str, Any]:
        api_key = os.environ.get("FIRECRAWL_API_KEY", "").strip()
        if not api_key:
            raise PlannerError("FIRECRAWL_API_KEY is not configured")

        cleaned_payload = self._normalize_payload(payload, mode="scrape")
        body = {"url": url, **cleaned_payload}
        endpoint = os.environ.get("FIRECRAWL_SCRAPE_ENDPOINT", "https://api.firecrawl.dev/v1/scrape")
        response = await self._client.post(
            endpoint,
            json=body,
            headers={"Authorization": f"Bearer {api_key}"},
        )
        if response.status_code >= 400:
            raise PlannerError(
                "Firecrawl request failed "
                f"status={response.status_code} body={response.text[:1200]} request={body}"
            )
        payload = response.json()
        if isinstance(payload, dict):
            payload.setdefault("_debug", {})
            payload["_debug"].update({"request": body, "provider": "firecrawl", "endpoint": endpoint})
        return payload

    async def search(self, *, query: str, limit: int = 5, **payload: Any) -> dict[str, Any]:
        api_key = os.environ.get("FIRECRAWL_API_KEY", "").strip()
        if not api_key:
            raise PlannerError("FIRECRAWL_API_KEY is not configured")

        endpoint = os.environ.get("FIRECRAWL_SEARCH_ENDPOINT", "https://api.firecrawl.dev/v1/search")
        cleaned_payload = self._normalize_payload(payload, mode="search")
        body = {"query": query, "limit": limit, **cleaned_payload}
        response = await self._client.post(
            endpoint,
            json=body,
            headers={"Authorization": f"Bearer {api_key}"},
        )
        if response.status_code >= 400:
            raise PlannerError(
                "Firecrawl search failed "
                f"status={response.status_code} body={response.text[:1200]} request={body}"
            )
        result = response.json()
        if isinstance(result, dict):
            result.setdefault("_debug", {})
            result["_debug"].update({"request": body, "provider": "firecrawl", "endpoint": endpoint})
        return result

    async def interact(self, *, url: str, prompt: str, **payload: Any) -> dict[str, Any]:
        api_key = os.environ.get("FIRECRAWL_API_KEY", "").strip()
        if not api_key:
            raise PlannerError("FIRECRAWL_API_KEY is not configured")

        endpoint = os.environ.get("FIRECRAWL_INTERACT_ENDPOINT", "https://api.firecrawl.dev/v1/interact")
        cleaned_payload = self._normalize_payload(payload, mode="interact")
        body = {"url": url, "prompt": prompt, **cleaned_payload}
        response = await self._client.post(
            endpoint,
            json=body,
            headers={"Authorization": f"Bearer {api_key}"},
        )
        if response.status_code >= 400:
            raise PlannerError(
                "Firecrawl interact failed "
                f"status={response.status_code} body={response.text[:1200]} request={body}"
            )
        result = response.json()
        if isinstance(result, dict):
            result.setdefault("_debug", {})
            result["_debug"].update({"request": body, "provider": "firecrawl", "endpoint": endpoint})
        return result

    def _normalize_payload(self, payload: dict[str, Any], *, mode: str) -> dict[str, Any]:
        normalized: dict[str, Any] = {}

        # Some model tool-calls pass a nested "payload" key; flatten it.
        nested = payload.get("payload")
        if isinstance(nested, dict):
            for key, value in nested.items():
                if value is not None:
                    normalized[key] = value

        for key, value in payload.items():
            if key == "payload" or value is None:
                continue
            normalized[key] = value

        # Firecrawl rejects unknown keys, so keep only known-safe fields per endpoint.
        allowed_by_mode: dict[str, set[str]] = {
            "search": {
                "limit",
                "lang",
                "country",
                "location",
                "timeout",
                "scrapeOptions",
                "formats",
            },
            "scrape": {
                "formats",
                "onlyMainContent",
                "waitFor",
                "mobile",
                "timeout",
                "headers",
                "actions",
            },
            "interact": {
                "actions",
                "timeout",
                "mobile",
                "headers",
                "waitFor",
            },
        }
        allowed = allowed_by_mode.get(mode, set())
        if not allowed:
            return normalized

        return {key: value for key, value in normalized.items() if key in allowed}