"""Crawlbase scrape tool wrapper."""

from __future__ import annotations

import os
import re
from typing import Any

import httpx

from cerebro.research.errors import PlannerError


class CrawlbaseTool:
    def __init__(self, *, timeout_seconds: float = 35.0) -> None:
        self._timeout_seconds = timeout_seconds
        self._client = httpx.AsyncClient(timeout=self._timeout_seconds)

    async def scrape(self, *, url: str, javascript: bool = False, **payload: Any) -> dict[str, Any]:
        token_env = "CRAWLBASE_JS_TOKEN" if javascript else "CRAWLBASE_NORMAL_TOKEN"
        token = os.environ.get(token_env, "").strip()
        if not token:
            raise PlannerError(f"{token_env} is not configured")

        endpoint = os.environ.get("CRAWLBASE_API_ENDPOINT", "https://api.crawlbase.com/")
        params: dict[str, Any] = {
            "token": token,
            "url": url,
            **self._normalize_params(payload),
        }

        response = await self._client.get(endpoint, params=params)
        if response.status_code >= 400:
            raise PlannerError(
                "Crawlbase request failed "
                f"status={response.status_code} body={response.text[:1200]} request={params}"
            )

        content_type = response.headers.get("content-type", "")
        raw_text = response.text
        if "application/json" in content_type.lower():
            parsed = response.json()
            text_content = str(parsed.get("body") or parsed.get("content") or "").strip()
        else:
            parsed = None
            text_content = self._extract_text_from_html(raw_text)

        metadata = {
            "sourceURL": url,
            "originalStatus": response.headers.get("original_status") or response.headers.get("pc_status"),
        }

        result = {
            "data": {
                "markdown": text_content,
                "content": text_content,
                "metadata": metadata,
                "raw": parsed if isinstance(parsed, dict) else raw_text[:4000],
            }
        }
        result.setdefault("_debug", {})
        result["_debug"].update(
            {
                "request": {"endpoint": endpoint, "params": {**params, "token": "***"}},
                "provider": "crawlbase",
                "javascript": javascript,
            }
        )
        return result

    def _normalize_params(self, payload: dict[str, Any]) -> dict[str, Any]:
        normalized: dict[str, Any] = {}
        for key, value in payload.items():
            if value is None:
                continue
            normalized[key] = value

        allowed = {
            "format",
            "device",
            "user_agent",
            "ajax_wait",
            "page_wait",
            "country",
        }
        return {key: value for key, value in normalized.items() if key in allowed}

    def _extract_text_from_html(self, html: str) -> str:
        without_script = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.IGNORECASE | re.DOTALL)
        without_style = re.sub(r"<style[^>]*>.*?</style>", " ", without_script, flags=re.IGNORECASE | re.DOTALL)
        text = re.sub(r"<[^>]+>", " ", without_style)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:12000]