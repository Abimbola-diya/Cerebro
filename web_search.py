"""Web search and scraping utilities for external evidence enrichment.

This module blends multiple discovery providers (Tavily, DuckDuckGo,
Wikipedia, optional Serper) and then deep-scrapes top candidates with
Firecrawl to build richer, cleaner context for answer synthesis.
"""

from __future__ import annotations

import logging
import os
import re
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import requests

logger = logging.getLogger(__name__)

try:
    from tavily import TavilyClient
except Exception:  # pragma: no cover - optional dependency
    TavilyClient = None

try:
    from duckduckgo_search import DDGS  # type: ignore[import-not-found]
except Exception:  # pragma: no cover - optional dependency
    DDGS = None


TAVILY_TIMEOUT = 30
FIRECRAWL_TIMEOUT = 20
SERPER_TIMEOUT = 20
WIKIPEDIA_TIMEOUT = 15


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int, minimum: int = 1) -> int:
    try:
        return max(minimum, int(os.getenv(name, str(default))))
    except Exception:
        return max(minimum, default)


def _clean_text(text: Any, max_chars: int = 3000) -> str:
    """Normalize noisy snippet/scrape text into paragraph-safe plain text."""
    if text is None:
        return ""

    value = str(text)
    value = re.sub(r"```[\s\S]*?```", " ", value)
    value = re.sub(r"<[^>]+>", " ", value)
    value = value.replace("\u00a0", " ")
    value = re.sub(r"\[[0-9]+\]", " ", value)
    value = re.sub(r"(?:\r\n|\r|\n)+", "\n", value)
    value = re.sub(r"[\t ]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    value = re.sub(r"\s{2,}", " ", value)
    value = value.strip(" \n")

    if len(value) > max_chars:
        value = value[:max_chars].rstrip()
    return value


def _normalize_url(url: Any) -> str:
    text = str(url or "").strip()
    if not text:
        return ""
    return text.rstrip("/")


class TavilySearcher:
    """Search for external context with Tavily."""

    def __init__(self) -> None:
        self.client: Any = None
        api_key = os.getenv("TAVILY_API_KEY")

        if not api_key:
            logger.warning("TAVILY_API_KEY not set; Tavily discovery disabled")
            return
        if TavilyClient is None:
            logger.warning("tavily-python not installed; Tavily discovery disabled")
            return

        try:
            self.client = TavilyClient(api_key=api_key)
        except Exception as exc:
            logger.warning("Failed to initialize Tavily client: %s", exc)
            self.client = None

        self.max_results_per_query = _env_int("TAVILY_MAX_RESULTS_PER_QUERY", 6)
        self.max_query_variants = _env_int("TAVILY_QUERY_VARIANTS", 2)
        self.search_depth = os.getenv("TAVILY_SEARCH_DEPTH", "advanced").strip() or "advanced"
        self.topic = os.getenv("TAVILY_TOPIC", "general").strip() or "general"
        self.include_raw_content = _env_bool("TAVILY_INCLUDE_RAW_CONTENT", True)

    @property
    def enabled(self) -> bool:
        return self.client is not None

    def _build_search_queries(self, subject: str, focus: str) -> List[str]:
        candidates = [
            f"{subject} {focus} Nigeria upstream oil and gas",
            f"{subject} {focus} latest update Nigeria petroleum sector",
            f"{subject} {focus} production reserves operations outlook",
        ]

        seen = set()
        queries: List[str] = []
        for raw in candidates:
            normalized = " ".join(raw.split()).strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            queries.append(normalized)
            if len(queries) >= self.max_query_variants:
                break

        return queries

    def _run_single_search(self, search_query: str) -> Dict[str, Any]:
        if not self.enabled:
            return {"results": [], "answer": "", "error": "tavily_disabled"}

        base_kwargs: Dict[str, Any] = {
            "include_answer": True,
            "max_results": self.max_results_per_query,
        }
        advanced_kwargs: Dict[str, Any] = {
            "search_depth": self.search_depth,
            "topic": self.topic,
        }
        if self.include_raw_content:
            advanced_kwargs["include_raw_content"] = True

        try:
            response = self.client.search(search_query, **base_kwargs, **advanced_kwargs)
        except TypeError:
            response = self.client.search(search_query, **base_kwargs)

        return response if isinstance(response, dict) else {"results": [], "answer": ""}

    def search(self, subject: str, focus: str) -> Dict[str, Any]:
        if not self.enabled:
            return {"sources": [], "ai_summary": "", "queries": [], "num_results": 0}

        queries = self._build_search_queries(subject, focus)
        summaries: List[str] = []
        unique_sources: List[Dict[str, Any]] = []
        seen = set()

        started = time.time()
        for query in queries:
            try:
                response = self._run_single_search(query)
            except Exception as exc:
                logger.warning("Tavily search failed for variant '%s': %s", query, exc)
                continue

            answer = _clean_text(response.get("answer", ""), max_chars=900)
            if answer:
                summaries.append(answer)

            for rank, item in enumerate(response.get("results", []) or [], start=1):
                url = _normalize_url(item.get("url"))
                title = _clean_text(item.get("title", ""), max_chars=300)
                dedupe_key = url.lower() if url else title.lower()
                if not dedupe_key or dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                unique_sources.append(
                    {
                        "title": title or "Untitled source",
                        "url": url,
                        "content": _clean_text(item.get("content", ""), max_chars=2000),
                        "raw_content": _clean_text(item.get("raw_content", ""), max_chars=6000),
                        "provider": "tavily",
                        "provider_rank": rank,
                        "query": query,
                    }
                )

        elapsed = time.time() - started
        logger.info("Tavily discovery completed: %d unique sources in %.2fs", len(unique_sources), elapsed)

        return {
            "sources": unique_sources,
            "ai_summary": " ".join(summaries[:3]).strip(),
            "queries": queries,
            "num_results": len(unique_sources),
        }


class SerperSearcher:
    """Optional Google-based search via serper.dev."""

    def __init__(self) -> None:
        self.api_key = os.getenv("SERPER_API_KEY", "").strip()
        self.enabled = bool(self.api_key)
        self.max_results = _env_int("SERPER_MAX_RESULTS", 6)
        self.timeout_seconds = _env_int("SERPER_TIMEOUT_SECONDS", SERPER_TIMEOUT)
        self.endpoint = "https://google.serper.dev/search"

    def search(self, query: str) -> List[Dict[str, Any]]:
        if not self.enabled:
            return []

        try:
            response = requests.post(
                self.endpoint,
                headers={
                    "X-API-KEY": self.api_key,
                    "Content-Type": "application/json",
                },
                json={"q": query, "num": self.max_results},
                timeout=self.timeout_seconds,
            )
            if response.status_code != 200:
                logger.warning("Serper returned status=%s", response.status_code)
                return []

            payload = response.json()
            organic = payload.get("organic", [])
            normalized: List[Dict[str, Any]] = []
            for rank, item in enumerate(organic, start=1):
                normalized.append(
                    {
                        "title": _clean_text(item.get("title", ""), max_chars=300),
                        "url": _normalize_url(item.get("link")),
                        "content": _clean_text(item.get("snippet", ""), max_chars=1800),
                        "provider": "serper",
                        "provider_rank": rank,
                    }
                )
            return normalized
        except Exception as exc:
            logger.warning("Serper search failed: %s", exc)
            return []


class DuckDuckGoSearcher:
    """No-key search expansion using duckduckgo-search package."""

    def __init__(self) -> None:
        self.enabled = _env_bool("DUCKDUCKGO_ENABLED", True) and DDGS is not None
        self.max_results = _env_int("DUCKDUCKGO_MAX_RESULTS", 8)
        self.timeout_seconds = _env_int("DUCKDUCKGO_TIMEOUT_SECONDS", 18)
        if DDGS is None:
            logger.warning("duckduckgo-search not installed; DuckDuckGo discovery disabled")

    def search(self, query: str) -> List[Dict[str, Any]]:
        if not self.enabled:
            return []
        if DDGS is None:
            return []

        results: List[Dict[str, Any]] = []
        try:
            with DDGS(timeout=self.timeout_seconds) as ddgs:
                raw_items = list(ddgs.text(query, max_results=self.max_results))
        except Exception as exc:
            logger.warning("DuckDuckGo search failed: %s", exc)
            return []

        for rank, item in enumerate(raw_items, start=1):
            results.append(
                {
                    "title": _clean_text(item.get("title", ""), max_chars=300),
                    "url": _normalize_url(item.get("href")),
                    "content": _clean_text(item.get("body", ""), max_chars=1800),
                    "provider": "duckduckgo",
                    "provider_rank": rank,
                }
            )
        return results


class WikipediaSearcher:
    """Lightweight no-key encyclopedic lookup."""

    def __init__(self) -> None:
        self.enabled = _env_bool("WIKIPEDIA_ENABLED", True)
        self.max_results = _env_int("WIKIPEDIA_MAX_RESULTS", 5)
        self.timeout_seconds = _env_int("WIKIPEDIA_TIMEOUT_SECONDS", WIKIPEDIA_TIMEOUT)
        self.endpoint = "https://en.wikipedia.org/w/api.php"

    def search(self, query: str) -> List[Dict[str, Any]]:
        if not self.enabled:
            return []

        try:
            response = requests.get(
                self.endpoint,
                params={
                    "action": "query",
                    "format": "json",
                    "list": "search",
                    "srsearch": query,
                    "srlimit": self.max_results,
                    "utf8": 1,
                },
                timeout=self.timeout_seconds,
            )
            if response.status_code != 200:
                return []

            payload = response.json()
            entries = payload.get("query", {}).get("search", [])
            output: List[Dict[str, Any]] = []
            for rank, item in enumerate(entries, start=1):
                title = _clean_text(item.get("title", ""), max_chars=200)
                snippet = _clean_text(item.get("snippet", ""), max_chars=1500)
                url = _normalize_url(f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}")
                output.append(
                    {
                        "title": title,
                        "url": url,
                        "content": snippet,
                        "provider": "wikipedia",
                        "provider_rank": rank,
                    }
                )
            return output
        except Exception as exc:
            logger.warning("Wikipedia search failed: %s", exc)
            return []


class FirecrawlScraper:
    """Deep scrape URLs using Firecrawl API."""

    def __init__(self) -> None:
        self.api_key = os.getenv("FIRECRAWL_API_KEY")
        self.enabled = bool(self.api_key)
        if not self.enabled:
            logger.warning("FIRECRAWL_API_KEY not set; deep scraping disabled")
        self.endpoint = "https://api.firecrawl.dev/v1/scrape"
        self.timeout_seconds = _env_int("FIRECRAWL_TIMEOUT_SECONDS", FIRECRAWL_TIMEOUT)

    def scrape_url(self, url: str) -> Dict[str, Any]:
        if not self.enabled:
            return {"url": url, "success": False, "error": "firecrawl_disabled"}

        try:
            response = requests.post(
                self.endpoint,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "url": url,
                    "formats": ["markdown", "html"],
                    "onlyMainContent": True,
                },
                timeout=self.timeout_seconds,
            )
            if response.status_code != 200:
                return {
                    "url": url,
                    "success": False,
                    "error": f"status_{response.status_code}",
                }

            data = response.json()
            return {
                "url": url,
                "markdown": _clean_text(data.get("markdown", ""), max_chars=8000),
                "html": data.get("html", ""),
                "metadata": data.get("metadata", {}),
                "success": True,
            }
        except Exception as exc:
            return {"url": url, "success": False, "error": str(exc)}


class HybridSearcher:
    """Comprehensive search orchestration across multiple providers."""

    def __init__(self) -> None:
        self.tavily = TavilySearcher()
        self.serper = SerperSearcher()
        self.duckduckgo = DuckDuckGoSearcher()
        self.wikipedia = WikipediaSearcher()
        self.firecrawl = FirecrawlScraper()

        self.max_sources_to_scrape = _env_int("WEB_SCRAPE_MAX_SOURCES", 8)
        self.max_discovered_sources = _env_int("WEB_DISCOVERED_SOURCES_LIMIT", 12)
        self.query_variants = _env_int("WEB_QUERY_VARIANTS", 3)
        self.extensive_mode = _env_bool("WEB_EXTENSIVE_MODE", True)

        blocked_domains_raw = os.getenv(
            "WEB_SCRAPE_BLOCKED_DOMAINS",
            "facebook,twitter,x.com,instagram,tiktok,linkedin",
        )
        self.blocked_domains = {
            token.strip().lower()
            for token in blocked_domains_raw.split(",")
            if token.strip()
        }

        self.provider_priority = {
            "tavily": 1,
            "serper": 2,
            "duckduckgo": 3,
            "wikipedia": 4,
            "unknown": 5,
        }

    def _should_skip_firecrawl(self, url: str) -> bool:
        normalized = (url or "").lower()
        if not normalized:
            return True
        return any(domain in normalized for domain in self.blocked_domains)

    def _build_search_queries(self, subject: str, topic: str) -> List[str]:
        base_queries = [
            f"{subject} {topic}",
            f"{subject} {topic} Nigeria upstream oil and gas",
            f"{subject} {topic} latest update 2025 2026",
            f"{subject} {topic} reserves production operations",
        ]

        seen = set()
        output: List[str] = []
        for raw in base_queries:
            normalized = " ".join(raw.split()).strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            output.append(normalized)
            if len(output) >= self.query_variants:
                break
        return output

    def _dedupe_and_rank_sources(self, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        deduped: List[Dict[str, Any]] = []
        seen = set()

        for candidate in candidates:
            url = _normalize_url(candidate.get("url"))
            title = _clean_text(candidate.get("title", ""), max_chars=300)
            key = url.lower() if url else title.lower()
            if not key or key in seen:
                continue
            seen.add(key)
            candidate["url"] = url
            candidate["title"] = title or "Untitled source"
            candidate["content"] = _clean_text(candidate.get("content", ""), max_chars=2400)
            candidate["provider"] = str(candidate.get("provider") or "unknown").lower()
            deduped.append(candidate)

        deduped.sort(
            key=lambda item: (
                self.provider_priority.get(item.get("provider", "unknown"), 9),
                int(item.get("provider_rank") or 999),
            )
        )
        return deduped[: self.max_discovered_sources]

    def _collect_discovery_sources(self, subject: str, topic: str) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        tavily_payload = self.tavily.search(subject, topic)
        candidates: List[Dict[str, Any]] = list(tavily_payload.get("sources", []))

        queries = self._build_search_queries(subject, topic)
        provider_counts: Dict[str, int] = {"tavily": len(tavily_payload.get("sources", []))}

        for query in queries:
            ddg_items = self.duckduckgo.search(query)
            if ddg_items:
                candidates.extend(ddg_items)
                provider_counts["duckduckgo"] = provider_counts.get("duckduckgo", 0) + len(ddg_items)

            wiki_items = self.wikipedia.search(query)
            if wiki_items:
                candidates.extend(wiki_items)
                provider_counts["wikipedia"] = provider_counts.get("wikipedia", 0) + len(wiki_items)

            if self.extensive_mode:
                serper_items = self.serper.search(query)
                if serper_items:
                    candidates.extend(serper_items)
                    provider_counts["serper"] = provider_counts.get("serper", 0) + len(serper_items)

        discovered = self._dedupe_and_rank_sources(candidates)
        tavily_payload["provider_counts"] = provider_counts
        return discovered, tavily_payload

    def search_and_scrape(self, company_name: str, topic: str) -> Dict[str, Any]:
        """Discover, dedupe, and deep-scrape web sources for richer evidence."""
        target = _clean_text(company_name or "", max_chars=200) or "Nigerian upstream producers"
        focus = _clean_text(topic or "overview", max_chars=80) or "overview"

        discovered_sources, tavily_results = self._collect_discovery_sources(target, focus)

        scraped_sources: List[Dict[str, Any]] = []
        for index, source in enumerate(discovered_sources[: self.max_sources_to_scrape], start=1):
            url = source.get("url", "")
            snippet = _clean_text(source.get("content", ""), max_chars=2200)
            raw_seed = _clean_text(source.get("raw_content", ""), max_chars=5000)
            snippet_values = extract_numeric_values(f"{snippet}\n{raw_seed}")

            scraped_item: Dict[str, Any] = {
                "url": url,
                "title": source.get("title", "Untitled source"),
                "provider": source.get("provider", "unknown"),
                "snippet": snippet,
                "tavily_values": snippet_values,
                "rank": index,
                "scrape_success": False,
                "scraped_values": [],
                "scraped_content": "",
            }

            if url and not self._should_skip_firecrawl(url):
                scraped = self.firecrawl.scrape_url(url)
                if scraped.get("success"):
                    markdown = _clean_text(scraped.get("markdown", ""), max_chars=5000)
                    scraped_item["scraped_content"] = markdown
                    scraped_item["scraped_values"] = extract_numeric_values(markdown)
                    scraped_item["scrape_success"] = bool(markdown)

            scraped_sources.append(scraped_item)

        return {
            "company_name": target,
            "topic": focus,
            "tavily_summary": _clean_text(tavily_results.get("ai_summary", ""), max_chars=1200),
            "tavily_results_count": int(tavily_results.get("num_results", 0)),
            "provider_counts": tavily_results.get("provider_counts", {}),
            "discovered_sources": discovered_sources,
            "scraped_sources": scraped_sources,
            "search_timestamp": datetime.now().isoformat(),
        }


def extract_numeric_values(text: str) -> List[Tuple[float, str]]:
    """Extract common quantitative metrics from unstructured web text."""
    patterns = {
        "production": r"(\d+(?:,\d{3})*(?:\.\d+)?)\s*(?:bopd|bpd|barrels?\s+per\s+day)",
        "reserves": r"(\d+(?:,\d{3})*(?:\.\d+)?)\s*(?:mmbbl|mmbbls|million\s+barrels|billion\s+barrels)",
        "equity": r"(\d+(?:\.\d+)?)\s*%",
        "revenue": r"\$\s?(\d+(?:,\d{3})*(?:\.\d+)?)\s*(?:million|billion)?",
    }

    values: List[Tuple[float, str]] = []
    haystack = text or ""
    for metric, pattern in patterns.items():
        for raw_value in re.findall(pattern, haystack, flags=re.IGNORECASE):
            value_text = str(raw_value).replace(",", "").strip()
            try:
                values.append((float(value_text), metric))
            except ValueError:
                continue
    return values


def synthesize_web_results(
    company_name: str,
    database_data: Dict[str, Any],
    web_results: Dict[str, Any],
    topic: str,
) -> Dict[str, Any]:
    """Build structured and cleaned evidence bundles for final LLM synthesis."""
    synthesis: Dict[str, Any] = {
        "company_name": company_name,
        "topic": topic,
        "sources": [],
        "data_points": [],
        "source_briefs": [],
        "synthesis": "",
    }

    if isinstance(database_data, dict) and database_data:
        for key, value in database_data.items():
            if value not in {None, "", "NOT_AVAILABLE"}:
                synthesis["data_points"].append(
                    {
                        "source": "Internal Database",
                        "metric": key,
                        "value": value,
                        "priority": 1,
                    }
                )
        synthesis["sources"].append(
            {
                "name": "Internal Database",
                "url": None,
                "type": "database",
            }
        )

    brief_seen = set()

    discovered_sources = web_results.get("discovered_sources", []) if isinstance(web_results, dict) else []
    for source in discovered_sources[:20]:
        provider = str(source.get("provider", "unknown")).lower()
        title = _clean_text(source.get("title", ""), max_chars=220)
        url = _normalize_url(source.get("url"))
        snippet = _clean_text(source.get("content", ""), max_chars=800)
        if not (title or snippet):
            continue

        synthesis["sources"].append(
            {
                "name": title or "Unknown",
                "url": url,
                "type": provider,
            }
        )

        brief_key = (url.lower() if url else title.lower()) + "|snippet"
        if brief_key not in brief_seen and snippet:
            brief_seen.add(brief_key)
            synthesis["source_briefs"].append(
                {
                    "title": title or "Unknown",
                    "url": url,
                    "provider": provider,
                    "text": snippet,
                }
            )

    scraped_sources = web_results.get("scraped_sources", []) if isinstance(web_results, dict) else []
    for scraped in scraped_sources:
        title = _clean_text(scraped.get("title", ""), max_chars=220)
        url = _normalize_url(scraped.get("url"))
        provider = str(scraped.get("provider", "unknown")).lower()

        for value, metric_type in scraped.get("tavily_values", []) or []:
            synthesis["data_points"].append(
                {
                    "source": title or provider,
                    "url": url,
                    "metric": metric_type,
                    "value": value,
                    "priority": 2,
                }
            )

        for value, metric_type in scraped.get("scraped_values", []) or []:
            synthesis["data_points"].append(
                {
                    "source": title or provider,
                    "url": url,
                    "metric": metric_type,
                    "value": value,
                    "priority": 3,
                }
            )

        deep_text = _clean_text(scraped.get("scraped_content", ""), max_chars=1500)
        if deep_text:
            synthesis["sources"].append(
                {
                    "name": title or "Unknown",
                    "url": url,
                    "type": "firecrawl",
                }
            )

            brief_key = (url.lower() if url else title.lower()) + "|scraped"
            if brief_key not in brief_seen:
                brief_seen.add(brief_key)
                synthesis["source_briefs"].append(
                    {
                        "title": title or "Unknown",
                        "url": url,
                        "provider": "firecrawl",
                        "text": deep_text,
                    }
                )

    summary_parts: List[str] = []
    tavily_summary = _clean_text(web_results.get("tavily_summary", ""), max_chars=1000)
    if tavily_summary:
        summary_parts.append(tavily_summary)

    for brief in synthesis["source_briefs"][:8]:
        summary_parts.append(f"{brief['title']}: {brief['text']}")

    synthesis["synthesis"] = _clean_text("\n\n".join(summary_parts), max_chars=10000)
    return synthesis


hybrid_searcher = HybridSearcher()
