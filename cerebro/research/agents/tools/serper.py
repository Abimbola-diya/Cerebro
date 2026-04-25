"""Serper search tool wrapper."""

from __future__ import annotations

import os
from typing import Any

import httpx

from cerebro.research.errors import PlannerError


class SerperTool:
    def __init__(self, *, timeout_seconds: float = 45.0) -> None:
        self._timeout_seconds = timeout_seconds
        self._client = httpx.AsyncClient(timeout=self._timeout_seconds)

    async def search(self, *, query: str, gl: str = "ng", hl: str = "en") -> dict[str, Any]:
        api_key = os.environ.get("SERPER_API_KEY", "").strip()
        if not api_key:
            raise PlannerError("SERPER_API_KEY is not configured")

        body = {"q": query, "num": 10, "gl": gl, "hl": hl}
        response = await self._client.post(
            "https://google.serper.dev/search",
            json=body,
            headers={"X-API-KEY": api_key},
        )
        if response.status_code >= 400:
            raise PlannerError(
                "Serper request failed "
                f"status={response.status_code} body={response.text[:1200]} request={body}"
            )
        payload = response.json()
        if isinstance(payload, dict):
            payload.setdefault("_debug", {})
            payload["_debug"].update({"request": body, "provider": "serper"})
        return payload