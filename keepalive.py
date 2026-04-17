"""Background keep-alive worker for free-tier hosting environments.

This service periodically pings the public backend health endpoint so
platform idling policies are less likely to suspend the service.
"""

from __future__ import annotations

import logging
import os
import random
import threading
import time
from typing import Optional

import requests

logger = logging.getLogger(__name__)


class KeepAliveService:
    """Periodically hit a health endpoint to reduce idle shutdowns."""

    def __init__(self) -> None:
        self.enabled = self._env_bool("KEEPALIVE_ENABLED", False)
        self.target_url = (
            os.getenv("KEEPALIVE_TARGET_URL")
            or os.getenv("RENDER_EXTERNAL_URL")
            or ""
        ).strip()
        self.path = os.getenv("KEEPALIVE_PATH", "/health").strip() or "/health"
        self.interval_seconds = max(60, int(os.getenv("KEEPALIVE_INTERVAL_SECONDS", "540")))
        self.timeout_seconds = max(3, int(os.getenv("KEEPALIVE_TIMEOUT_SECONDS", "15")))
        self.startup_delay_seconds = max(0, int(os.getenv("KEEPALIVE_STARTUP_DELAY_SECONDS", "30")))
        self.jitter_seconds = max(0, int(os.getenv("KEEPALIVE_JITTER_SECONDS", "20")))

        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._ping_url = self._build_ping_url()

    @staticmethod
    def _env_bool(name: str, default: bool) -> bool:
        value = os.getenv(name)
        if value is None:
            return default
        return value.strip().lower() in {"1", "true", "yes", "on"}

    def _build_ping_url(self) -> str:
        if not self.target_url:
            return ""

        base = self.target_url.rstrip("/")
        path = self.path if self.path.startswith("/") else f"/{self.path}"
        return f"{base}{path}"

    def start(self) -> None:
        if not self.enabled:
            logger.info("Keepalive disabled")
            return

        if not self._ping_url:
            logger.warning(
                "Keepalive enabled but no target URL is configured. "
                "Set KEEPALIVE_TARGET_URL or RENDER_EXTERNAL_URL."
            )
            return

        if self._thread and self._thread.is_alive():
            return

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, name="cerebro-keepalive", daemon=True)
        self._thread.start()
        logger.info(
            "Keepalive started: url=%s interval=%ss timeout=%ss",
            self._ping_url,
            self.interval_seconds,
            self.timeout_seconds,
        )

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        logger.info("Keepalive stopped")

    def _run_loop(self) -> None:
        if self.startup_delay_seconds > 0:
            if self._stop_event.wait(self.startup_delay_seconds):
                return

        while not self._stop_event.is_set():
            self._ping_once()

            sleep_seconds = self.interval_seconds
            if self.jitter_seconds > 0:
                sleep_seconds += random.randint(0, self.jitter_seconds)

            if self._stop_event.wait(sleep_seconds):
                return

    def _ping_once(self) -> None:
        if not self._ping_url:
            return

        started = time.time()
        try:
            response = requests.get(
                self._ping_url,
                timeout=self.timeout_seconds,
                headers={"User-Agent": "CerebroKeepAlive/1.0"},
            )
            elapsed_ms = int((time.time() - started) * 1000)

            if response.status_code >= 400:
                logger.warning(
                    "Keepalive ping returned status=%s in %sms for %s",
                    response.status_code,
                    elapsed_ms,
                    self._ping_url,
                )
            else:
                logger.debug(
                    "Keepalive ping OK status=%s in %sms for %s",
                    response.status_code,
                    elapsed_ms,
                    self._ping_url,
                )
        except Exception as exc:
            logger.warning("Keepalive ping failed for %s: %s", self._ping_url, exc)


keepalive_service = KeepAliveService()
