"""
LLM-first question pipeline for Neo4j.

Core flow per question:
1) LLM call: natural language -> Cypher
2) Execute Cypher against Neo4j (read-only)
3) LLM call: raw Cypher results -> natural language answer

Web search is optional and only used as supplementary context for single-entity queries.
"""

import json
import logging
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

try:
    import google.generativeai as genai  # type: ignore[import-not-found]
except Exception:  # pragma: no cover - optional provider dependency
    genai = None

try:
    from cerebras.cloud.sdk import Cerebras
except Exception:  # pragma: no cover - optional provider dependency
    Cerebras = None

try:
    from langchain_community.graphs import Neo4jGraph
except Exception:  # pragma: no cover - optional dependency
    Neo4jGraph = None

try:
    from langchain_openai import ChatOpenAI
except Exception:  # pragma: no cover - optional dependency
    ChatOpenAI = None

from database import db
from web_search import hybrid_searcher, synthesize_web_results

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Curated aliases for common user wording that does not always map directly to
# the canonical short_name field.
MANUAL_ENTITY_ALIASES: Dict[str, str] = {
    "shell": "shell-spdc",
    "spdc": "shell-spdc",
    "shell nigeria": "shell-spdc",
    "snepco": "snepco-shell-deepwater",
    "shell deepwater": "snepco-shell-deepwater",
    "bonga": "snepco-shell-deepwater",
    "total": "totalenergies-ep-nigeria",
    "totalenergies": "totalenergies-ep-nigeria",
    "chevron": "chevron-nigeria-limited",
    "cnl": "chevron-nigeria-limited",
    "mobil": "eepnl-exxonmobil-deepwater",
    "exxonmobil": "eepnl-exxonmobil-deepwater",
    "esso": "eepnl-exxonmobil-deepwater",
    "nnpc": "nnpc-limited",
    "nnpc limited": "nnpc-limited",
    "nepl": "nepl-nnpc-ep",
    "nnpc e&p": "nepl-nnpc-ep",
    "agip": "oando-png-formerly-naoc",
    "naoc": "oando-png-formerly-naoc",
    "oando": "oando-petroleum-natural-gas",
    "seplat": "seplat-energy",
    "heirs": "heirs-energies",
    "aiteo": "aiteo-eastern-ep",
    "first e&p": "first-ep",
    "shoreline": "shoreline-energy",
    "neconde": "neconde-energy",
    "eroton": "eroton-ep",
    "star deep water": "star-deep-water-chevron",
    "agbami": "star-deep-water-chevron",
    "famfa": "famfa-oil",
    "cnooc": "cnooc-nigeria",
    "sapetro": "sapetro-south-atlantic",
    "nae": "nae-eni-deepwater",
    "seepco": "seepco-sterling",
    "sterling oil": "seepco-sterling",
    "elcrest": "elcrest-ep",
    "nd western": "nd-western",
    "chappal": "chappal-energies",
    "waltersmith": "waltersmith-petroman",
    "aradel": "aradel-holdings",
    "amni": "amni-international",
    "pan ocean": "pan-ocean-nigeria",
    "belema": "belema-oil",
    "midwestern": "midwestern-oil-gas",
    "green energy": "green-energy-international",
    "suntrust": "suntrust-oil",
    "newcross": "newcross-ep",
    "oriental energy": "oriental-energy",
    "platform petroleum": "platform-petroleum",
}

ENTITY_TOKEN_STOPWORDS = {
    "company",
    "limited",
    "ltd",
    "plc",
    "producer",
    "producers",
    "operator",
    "operators",
    "upstream",
    "aggregate",
    "oil",
    "gas",
    "nigeria",
    "nigerian",
    "exploration",
    "production",
    "petroleum",
    "energy",
    "resources",
    "development",
    "international",
    "services",
}


class LLMPipeline:
    def __init__(self):
        self.provider = ""
        self.model = ""
        self.last_provider_used: Optional[str] = None
        self.available_providers: List[str] = []
        self.web_enrichment_enabled = (
            os.getenv("WEB_ENRICHMENT_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}
        )
        self.web_sources_for_synthesis = int(os.getenv("WEB_SOURCES_FOR_SYNTHESIS", "12"))
        self.web_source_max_chars = int(os.getenv("WEB_SOURCE_MAX_CHARS", "2200"))
        self.web_answer_max_chars = int(os.getenv("WEB_ANSWER_MAX_CHARS", "14000"))
        self.web_priority_mode = os.getenv("WEB_PRIORITY_MODE", "balanced").strip().lower()
        self.web_multi_model_enabled = (
            os.getenv("WEB_MULTI_MODEL_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}
        )
        self.web_source_summary_provider = os.getenv("WEB_SOURCE_SUMMARY_PROVIDER", "auto").strip().lower()
        self.web_final_synthesis_provider = os.getenv("WEB_FINAL_SYNTHESIS_PROVIDER", "auto").strip().lower()

        self.cerebras_api_key: Optional[str] = None
        self.cerebras_client: Any = None
        self.cerebras_endpoint: str = os.getenv(
            "CEREBRAS_ENDPOINT", "https://api.cerebras.ai/v1/chat/completions"
        )
        self.cerebras_model: str = os.getenv("CEREBRAS_MODEL", "llama3.1-8b")
        self.cerebras_max_completion_tokens = int(os.getenv("CEREBRAS_MAX_COMPLETION_TOKENS", "1024"))
        self.cerebras_temperature = float(os.getenv("CEREBRAS_TEMPERATURE", "0.2"))
        self.cerebras_top_p = float(os.getenv("CEREBRAS_TOP_P", "1"))

        self.openrouter_api_key: Optional[str] = None
        self.openrouter_endpoint: str = os.getenv(
            "OPENROUTER_ENDPOINT", "https://openrouter.ai/api/v1/chat/completions"
        )
        self.openrouter_model: str = os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.1-70b-instruct")
        self.openrouter_max_tokens = int(os.getenv("OPENROUTER_MAX_TOKENS", "1024"))
        self.openrouter_temperature = float(os.getenv("OPENROUTER_TEMPERATURE", "0.1"))
        self.openrouter_site_url = os.getenv("OPENROUTER_SITE_URL", "").strip()
        self.openrouter_site_name = os.getenv("OPENROUTER_SITE_NAME", "Cerebro Backend").strip()
        self.synthesis_max_rows = int(os.getenv("SYNTHESIS_MAX_ROWS", "40"))
        self.synthesis_max_json_chars = int(os.getenv("SYNTHESIS_MAX_JSON_CHARS", "12000"))

        self.groq_api_key: Optional[str] = None
        self.groq_endpoint: Optional[str] = None
        self.groq_model: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

        self.gemini_client: Any = None
        self.gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        self.groq_schema_max_chars = int(os.getenv("GROQ_SCHEMA_MAX_CHARS", "7000"))
        self.groq_schema_rag_max_sections = int(os.getenv("GROQ_SCHEMA_RAG_MAX_SECTIONS", "6"))
        self.groq_schema_rag_max_chars = int(os.getenv("GROQ_SCHEMA_RAG_MAX_CHARS", "4500"))
        self.schema_rag_default_max_sections = int(os.getenv("SCHEMA_RAG_DEFAULT_MAX_SECTIONS", "10"))
        self.schema_rag_default_max_chars = int(os.getenv("SCHEMA_RAG_DEFAULT_MAX_CHARS", "14000"))
        compact_schema_providers_raw = os.getenv("LLM_COMPACT_SCHEMA_PROVIDERS", "groq")
        self.compact_schema_providers = {
            provider.strip().lower()
            for provider in compact_schema_providers_raw.split(",")
            if provider.strip()
        }
        self.runtime_schema_introspection_enabled = (
            os.getenv("RUNTIME_SCHEMA_INTROSPECTION_ENABLED", "true").strip().lower()
            in {"1", "true", "yes", "on"}
        )
        self.runtime_schema_context: str = ""
        self.entity_resolution_enabled = (
            os.getenv("ENTITY_RESOLUTION_ENABLED", "true").strip().lower()
            in {"1", "true", "yes", "on"}
        )
        self.entity_resolution_max_ids = int(os.getenv("ENTITY_RESOLUTION_MAX_IDS", "5"))
        self.entity_resolution_min_score = int(os.getenv("ENTITY_RESOLUTION_MIN_SCORE", "100"))
        self.entity_resolution_alias_fuzzy_threshold = float(
            os.getenv("ENTITY_RESOLUTION_ALIAS_FUZZY_THRESHOLD", "0.80")
        )
        self.entity_resolution_dynamic_fuzzy_threshold = float(
            os.getenv("ENTITY_RESOLUTION_DYNAMIC_FUZZY_THRESHOLD", "0.84")
        )
        self.entity_resolution_token_fuzzy_threshold = float(
            os.getenv("ENTITY_RESOLUTION_TOKEN_FUZZY_THRESHOLD", "0.82")
        )

        self.langchain_cypher_shadow_enabled = (
            os.getenv("LANGCHAIN_CYPHER_SHADOW_ENABLED", "true").strip().lower()
            in {"1", "true", "yes", "on"}
        )
        self.langchain_cypher_provider = os.getenv("LANGCHAIN_CYPHER_PROVIDER", "openrouter").strip().lower()
        self.langchain_openrouter_model = os.getenv("LANGCHAIN_OPENROUTER_MODEL", self.openrouter_model)
        self.langchain_openrouter_base_url = os.getenv(
            "LANGCHAIN_OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"
        ).strip()
        self.langchain_openrouter_temperature = float(os.getenv("LANGCHAIN_OPENROUTER_TEMPERATURE", "0.0"))
        self.langchain_openrouter_max_tokens = int(os.getenv("LANGCHAIN_OPENROUTER_MAX_TOKENS", "1200"))
        self.langchain_timeout_seconds = float(os.getenv("LANGCHAIN_TIMEOUT_SECONDS", "35"))
        self.langchain_schema_max_chars = int(os.getenv("LANGCHAIN_SCHEMA_MAX_CHARS", "18000"))
        self.langchain_schema_refresh_seconds = int(os.getenv("LANGCHAIN_SCHEMA_REFRESH_SECONDS", "900"))
        self.langchain_init_retry_seconds = int(os.getenv("LANGCHAIN_INIT_RETRY_SECONDS", "120"))

        self.langchain_shadow_ready = False
        self.langchain_shadow_last_error: Optional[str] = None
        self.langchain_schema_source = "uninitialized"
        self._langchain_chat_model: Any = None
        self._langchain_graph: Any = None
        self._langchain_schema_cache: str = ""
        self._langchain_schema_cache_ts: float = 0.0
        self._langchain_init_last_attempt_ts: float = 0.0

        self._init_llm_client()
        self.node_catalog = self._load_node_catalog()
        self._init_langchain_shadow_components()

    def _init_llm_client(self) -> None:
        """Initialize providers and pick a preferred primary provider."""
        preferred_provider = os.getenv("LLM_PRIMARY_PROVIDER", "cerebras").strip().lower()

        cerebras_api_key = os.getenv("CEREBRAS_API_KEY")
        cerebras_model = os.getenv("CEREBRAS_MODEL", "llama3.1-8b")

        openrouter_api_key = os.getenv("OPENROUTER_API_KEY")
        openrouter_model = os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.1-70b-instruct")

        groq_api_key = os.getenv("GROQ_API_KEY")
        groq_model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        groq_endpoint = os.getenv("GROQ_ENDPOINT", "https://api.groq.com/openai/v1/chat/completions")

        google_api_key = os.getenv("GOOGLE_API_KEY")
        gemini_model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

        if cerebras_api_key:
            self.cerebras_api_key = cerebras_api_key
            self.cerebras_model = cerebras_model
            if Cerebras is not None:
                self.cerebras_client = Cerebras(api_key=self.cerebras_api_key)
                logger.info("LLM provider available: Cerebras (model=%s, sdk=true)", self.cerebras_model)
            else:
                logger.warning(
                    "cerebras-cloud-sdk not installed; Cerebras will use REST fallback endpoint"
                )
                logger.info("LLM provider available: Cerebras (model=%s, sdk=false)", self.cerebras_model)
            self.available_providers.append("cerebras")

        if openrouter_api_key:
            self.openrouter_api_key = openrouter_api_key
            self.openrouter_model = openrouter_model
            self.available_providers.append("openrouter")
            logger.info("LLM provider available: OpenRouter (model=%s)", self.openrouter_model)

        if groq_api_key:
            self.groq_api_key = groq_api_key
            self.groq_endpoint = groq_endpoint
            self.groq_model = groq_model
            self.available_providers.append("groq")
            logger.info("LLM provider available: Groq (model=%s)", self.groq_model)

        if google_api_key:
            if genai is None:
                logger.warning("google-generativeai package not available; skipping Gemini provider")
            else:
                self.gemini_model = gemini_model
                genai.configure(api_key=google_api_key)
                self.gemini_client = genai.GenerativeModel(self.gemini_model)
                self.available_providers.append("gemini")
                logger.info("LLM provider available: Gemini (model=%s)", self.gemini_model)

        if not self.available_providers:
            raise ValueError(
                "No LLM credentials configured. Set one of: CEREBRAS_API_KEY, "
                "OPENROUTER_API_KEY, GROQ_API_KEY, GOOGLE_API_KEY."
            )

        self.provider = preferred_provider if preferred_provider in self.available_providers else self.available_providers[0]

        if self.provider == "cerebras":
            self.model = self.cerebras_model
        elif self.provider == "openrouter":
            self.model = self.openrouter_model
        elif self.provider == "groq":
            self.model = self.groq_model
        elif self.provider == "gemini":
            self.model = self.gemini_model
        else:
            self.model = "unknown"

        logger.info(
            "Primary LLM provider set to %s (model=%s); fallbacks=%s",
            self.provider,
            self.model,
            [p for p in self.available_providers if p != self.provider],
        )
        logger.info("Web enrichment enabled: %s", self.web_enrichment_enabled)

    def _load_node_catalog(self) -> str:
        """Load full schema context from disk for Cypher generation."""
        env_path = os.getenv("SCHEMA_CONTEXT_PATH")
        default_path = Path(__file__).resolve().parent / "SCHEMA_CONTEXT_FOR_LLM.md"
        schema_path = Path(env_path) if env_path else default_path

        try:
            schema_text = schema_path.read_text(encoding="utf-8").strip()
            if not schema_text:
                raise ValueError("Schema context file is empty")
            logger.info("Loaded schema context from %s (%d chars)", schema_path, len(schema_text))
            return schema_text
        except Exception as exc:
            logger.warning("Failed to load schema context from %s: %s", schema_path, exc)
            return self._get_fallback_schema()

    def _get_runtime_schema_context(self) -> str:
        """Get dynamic schema summary from Neo4j when connection is available."""
        if not self.runtime_schema_introspection_enabled:
            return ""

        if not getattr(db, "driver", None):
            return self.runtime_schema_context

        try:
            runtime_schema = db.get_schema_summary()
            if runtime_schema:
                self.runtime_schema_context = runtime_schema
            return self.runtime_schema_context
        except Exception as exc:
            logger.debug("Runtime schema context unavailable: %s", exc)
            return self.runtime_schema_context

    def _active_schema_catalog(self) -> str:
        """Combine static schema file context with runtime database introspection."""
        runtime_schema = self._get_runtime_schema_context()
        if not runtime_schema:
            return self.node_catalog
        return f"{self.node_catalog}\n\n{runtime_schema}"

    def _init_langchain_shadow_components(self) -> None:
        """Initialize LangChain shadow-mode components (schema-aware Cypher generation only)."""
        self._langchain_init_last_attempt_ts = time.time()
        self.langchain_shadow_ready = False
        self.langchain_shadow_last_error = None
        self.langchain_schema_source = "uninitialized"

        if not self.langchain_cypher_shadow_enabled:
            logger.info("LangChain shadow mode disabled")
            return

        if self.langchain_cypher_provider != "openrouter":
            self.langchain_shadow_last_error = (
                f"Unsupported LANGCHAIN_CYPHER_PROVIDER={self.langchain_cypher_provider}; only openrouter is configured"
            )
            logger.warning(self.langchain_shadow_last_error)
            return

        if ChatOpenAI is None or Neo4jGraph is None:
            self.langchain_shadow_last_error = (
                "LangChain dependencies unavailable. Install langchain, langchain-community, and langchain-openai"
            )
            logger.warning(self.langchain_shadow_last_error)
            return

        if not self.openrouter_api_key:
            self.langchain_shadow_last_error = "OPENROUTER_API_KEY is required for LangChain shadow mode"
            logger.warning(self.langchain_shadow_last_error)
            return

        neo4j_uri = os.getenv("NEO4J_URI", "").strip()
        neo4j_username = os.getenv("NEO4J_USERNAME", "").strip()
        neo4j_password = os.getenv("NEO4J_PASSWORD", "").strip()
        neo4j_database = os.getenv("NEO4J_DATABASE", "neo4j").strip()

        if not neo4j_uri or not neo4j_username or not neo4j_password:
            self.langchain_shadow_last_error = (
                "NEO4J_URI/NEO4J_USERNAME/NEO4J_PASSWORD are required for LangChain schema introspection"
            )
            logger.warning(self.langchain_shadow_last_error)
            return

        headers: Dict[str, str] = {}
        if self.openrouter_site_url:
            headers["HTTP-Referer"] = self.openrouter_site_url
        if self.openrouter_site_name:
            headers["X-Title"] = self.openrouter_site_name

        try:
            chat_kwargs: Dict[str, Any] = {
                "model": self.langchain_openrouter_model,
                "api_key": self.openrouter_api_key,
                "base_url": self.langchain_openrouter_base_url,
                "temperature": self.langchain_openrouter_temperature,
                "max_tokens": self.langchain_openrouter_max_tokens,
                "timeout": self.langchain_timeout_seconds,
            }
            if headers:
                chat_kwargs["default_headers"] = headers

            self._langchain_chat_model = ChatOpenAI(**chat_kwargs)

            try:
                self._langchain_graph = Neo4jGraph(
                    url=neo4j_uri,
                    username=neo4j_username,
                    password=neo4j_password,
                    database=neo4j_database,
                )
                self.langchain_schema_source = "neo4jgraph"
            except Exception as graph_exc:
                self._langchain_graph = None
                self.langchain_schema_source = "active_schema_fallback"
                self.langchain_shadow_last_error = (
                    "LangChain Neo4jGraph unavailable; using active schema fallback: "
                    f"{graph_exc}"
                )
                logger.warning(self.langchain_shadow_last_error)

            self._refresh_langchain_schema_cache(force=True)

            self.langchain_shadow_ready = True
            logger.info(
                "LangChain shadow mode ready (provider=%s, model=%s, schema_source=%s)",
                self.langchain_cypher_provider,
                self.langchain_openrouter_model,
                self.langchain_schema_source,
            )
        except Exception as exc:
            self.langchain_shadow_last_error = f"LangChain shadow initialization failed: {exc}"
            self._langchain_graph = None
            self._langchain_chat_model = None
            self.langchain_shadow_ready = False
            logger.warning(self.langchain_shadow_last_error)

    def _refresh_langchain_schema_cache(self, force: bool = False) -> str:
        """Refresh schema snapshot loaded by LangChain Neo4j graph helper."""
        now = time.time()
        if (
            not force
            and self._langchain_schema_cache
            and (now - self._langchain_schema_cache_ts) < self.langchain_schema_refresh_seconds
        ):
            return self._langchain_schema_cache

        schema_text = ""
        try:
            if self._langchain_graph:
                refresh_schema = getattr(self._langchain_graph, "refresh_schema", None)
                if callable(refresh_schema):
                    refresh_schema()

                schema_text = str(getattr(self._langchain_graph, "get_schema", "") or "").strip()
                if not schema_text:
                    structured_schema = getattr(self._langchain_graph, "get_structured_schema", None)
                    if structured_schema:
                        schema_text = json.dumps(structured_schema, indent=2, default=str)

            if not schema_text:
                schema_text = self._active_schema_catalog()
                self.langchain_schema_source = "active_schema_fallback"

            if self.langchain_schema_max_chars > 0 and len(schema_text) > self.langchain_schema_max_chars:
                schema_text = schema_text[: self.langchain_schema_max_chars].rstrip()

            self._langchain_schema_cache = schema_text
            self._langchain_schema_cache_ts = now
            return schema_text
        except Exception as exc:
            self.langchain_shadow_last_error = f"LangChain schema refresh failed: {exc}"
            logger.warning(self.langchain_shadow_last_error)
            if self._langchain_schema_cache:
                return self._langchain_schema_cache

            fallback_schema = self._active_schema_catalog()
            if self.langchain_schema_max_chars > 0 and len(fallback_schema) > self.langchain_schema_max_chars:
                fallback_schema = fallback_schema[: self.langchain_schema_max_chars].rstrip()
            self.langchain_schema_source = "active_schema_fallback"
            self._langchain_schema_cache = fallback_schema
            self._langchain_schema_cache_ts = now
            return fallback_schema

    @staticmethod
    def _extract_message_text(message_content: Any) -> str:
        """Convert provider-specific message payloads to plain text."""
        if isinstance(message_content, str):
            return message_content
        if isinstance(message_content, list):
            parts: List[str] = []
            for item in message_content:
                if isinstance(item, dict):
                    text = item.get("text")
                    if text:
                        parts.append(str(text))
                elif item is not None:
                    parts.append(str(item))
            return "".join(parts)
        if message_content is None:
            return ""
        return str(message_content)

    @staticmethod
    def _check_read_only_cypher(cypher_query: str) -> Tuple[bool, Optional[str]]:
        """Validate generated query against backend read-only policy."""
        try:
            db._validate_read_only_cypher(cypher_query)
            return True, None
        except Exception as exc:
            return False, str(exc)

    @staticmethod
    def _get_fallback_schema() -> str:
        """Minimal fallback schema if full file is unavailable."""
        return (
            "Database contains UpstreamProducer nodes with properties including id, name, short_name, "
            "current_production_bopd, proven_reserves_mmbbls, nnpc_equity_percentage, oml_blocks_held, "
            "opl_blocks_held, operational_area, and operational_status."
        )

    @staticmethod
    def _get_compact_schema() -> str:
        """Compact schema context for token-limited providers."""
        return """SCHEMA: Nigerian Upstream Petroleum Graph

PRIMARY LABEL FOCUS:
- UpstreamProducer (major entity group)
- Additional labels can exist (for example ClassNode, concession/infrastructure categories).
- Use retrieved schema excerpts as source of truth for labels beyond UpstreamProducer.

KEY PROPERTIES:
- id (string): unique slug
- name (string): legal company name
- short_name (string): abbreviated name
- current_production_bopd (number): current production rate
- proven_reserves_mmbbls (number): proven reserves in million barrels
- nnpc_equity_percentage (number): NNPC stake percentage
- operational_status (string): active/inactive/transitioned
- operational_area (string): core operating area
- oml_blocks_held (list[string])
- opl_blocks_held (list[string])
- parent_company (string)
- sub_type (string): IOC, NOC, IndigenousOperator, MarginalFieldOperator

CYPHER PATTERNS:
- Count producers:
  MATCH (n:UpstreamProducer)
  RETURN count(n) AS total_upstream_producers

- Company lookup:
  MATCH (n:UpstreamProducer)
  WHERE toLower(n.name) CONTAINS toLower("shell") OR toLower(coalesce(n.short_name, "")) CONTAINS toLower("shell")
  RETURN n
  LIMIT 25

- Production ranking:
  MATCH (n:UpstreamProducer)
  WHERE n.current_production_bopd IS NOT NULL
  RETURN n.name AS name, n.current_production_bopd AS current_production_bopd
  ORDER BY n.current_production_bopd DESC
  LIMIT 10

READ-ONLY CLAUSES ONLY:
MATCH, OPTIONAL MATCH, WHERE, WITH, RETURN, ORDER BY, LIMIT, COUNT, COLLECT, DISTINCT, UNWIND
"""

    @staticmethod
    def _extract_query_keywords(user_query: str) -> List[str]:
        """Extract lightweight keywords used to retrieve relevant schema sections."""
        stop_words = {
            "a", "an", "and", "are", "as", "at", "be", "by", "for", "from",
            "how", "in", "is", "it", "me", "of", "on", "or", "our", "show",
            "tell", "that", "the", "to", "we", "what", "which", "who", "with",
            "about", "have", "has", "do", "does", "nigeria",
        }
        tokens = re.findall(r"[a-zA-Z0-9_]+", user_query.lower())
        seen = set()
        keywords: List[str] = []

        for token in tokens:
            if len(token) < 3 or token in stop_words:
                continue
            if token not in seen:
                seen.add(token)
                keywords.append(token)

        return keywords

    @staticmethod
    def _split_schema_sections(schema_text: str) -> List[str]:
        """Split schema text into retrievable sections (markdown heading-aware)."""
        if not schema_text.strip():
            return []

        lines = schema_text.splitlines()
        sections: List[str] = []
        current: List[str] = []

        for line in lines:
            if line.lstrip().startswith("#"):
                if current:
                    sections.append("\n".join(current).strip())
                current = [line]
            else:
                current.append(line)

        if current:
            sections.append("\n".join(current).strip())

        if len(sections) <= 1:
            return [block.strip() for block in schema_text.split("\n\n") if block.strip()]

        return [section for section in sections if section]

    def _retrieve_relevant_schema_sections(
        self,
        user_query: str,
        max_sections: Optional[int] = None,
        max_chars: Optional[int] = None,
        schema_catalog: Optional[str] = None,
    ) -> List[str]:
        """Retrieve highest-signal schema sections for the current user query."""
        keywords = self._extract_query_keywords(user_query)
        if not keywords:
            return []

        max_sections = max_sections or self.schema_rag_default_max_sections
        max_chars = max_chars or self.schema_rag_default_max_chars

        schema_text = schema_catalog if schema_catalog is not None else self.node_catalog
        sections = self._split_schema_sections(schema_text)
        if not sections:
            return []

        scored_sections = []
        for section in sections:
            section_lower = section.lower()
            score = 0

            for keyword in keywords:
                if keyword in section_lower:
                    score += 2

            if "upstreamproducer" in section_lower or "upstream producer" in section_lower:
                score += 1

            if score > 0:
                scored_sections.append((score, len(section), section))

        scored_sections.sort(key=lambda item: (-item[0], item[1]))

        selected: List[str] = []
        used_chars = 0
        for _, _, section in scored_sections:
            if len(selected) >= max_sections:
                break

            snippet = section
            if len(snippet) > 1400:
                snippet = snippet[:1400].rstrip() + "\n..."

            if used_chars + len(snippet) > max_chars:
                continue

            selected.append(snippet)
            used_chars += len(snippet)

        logger.info(
            "Schema-RAG selected %d sections (keywords=%s, chars=%d)",
            len(selected),
            ",".join(keywords[:8]) if keywords else "none",
            used_chars,
        )
        return selected

    @staticmethod
    def _normalize_lookup_text(value: str) -> str:
        """Normalize free text for resilient entity alias matching."""
        return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()

    @staticmethod
    def _contains_alias(query_norm: str, alias_norm: str) -> bool:
        """Word-boundary-like containment on normalized text."""
        if not query_norm or not alias_norm:
            return False
        return f" {alias_norm} " in f" {query_norm} "

    @staticmethod
    def _levenshtein_distance(left: str, right: str) -> int:
        """Compute edit distance for typo-tolerant entity matching."""
        if left == right:
            return 0
        if not left:
            return len(right)
        if not right:
            return len(left)

        # Use the shorter string for the DP row to keep memory bounded.
        if len(left) < len(right):
            left, right = right, left

        previous_row = list(range(len(right) + 1))
        for left_idx, left_char in enumerate(left, start=1):
            current_row = [left_idx]
            for right_idx, right_char in enumerate(right, start=1):
                insert_cost = current_row[right_idx - 1] + 1
                delete_cost = previous_row[right_idx] + 1
                replace_cost = previous_row[right_idx - 1] + (0 if left_char == right_char else 1)
                current_row.append(min(insert_cost, delete_cost, replace_cost))
            previous_row = current_row

        return previous_row[-1]

    @classmethod
    def _normalized_edit_similarity(cls, left: str, right: str) -> float:
        """Return 0..1 similarity based on normalized edit distance."""
        left_norm = cls._normalize_lookup_text(left)
        right_norm = cls._normalize_lookup_text(right)
        if not left_norm or not right_norm:
            return 0.0

        max_len = max(len(left_norm), len(right_norm))
        if max_len == 0:
            return 0.0

        distance = cls._levenshtein_distance(left_norm, right_norm)
        return max(0.0, 1.0 - (distance / max_len))

    @classmethod
    def _best_phrase_similarity(cls, query_norm: str, phrase_norm: str) -> float:
        """Find best fuzzy score between a phrase and any same-length query n-gram."""
        query = cls._normalize_lookup_text(query_norm)
        phrase = cls._normalize_lookup_text(phrase_norm)
        if not query or not phrase:
            return 0.0

        query_tokens = query.split()
        phrase_tokens = phrase.split()
        if not query_tokens or not phrase_tokens:
            return 0.0

        if len(query_tokens) < len(phrase_tokens):
            return cls._normalized_edit_similarity(query, phrase)

        window_size = len(phrase_tokens)
        best = 0.0
        for index in range(len(query_tokens) - window_size + 1):
            candidate = " ".join(query_tokens[index : index + window_size])
            score = cls._normalized_edit_similarity(candidate, phrase)
            if score > best:
                best = score
            if best >= 0.99:
                return best

        return max(best, cls._normalized_edit_similarity(query, phrase))

    @staticmethod
    def _quote_cypher_string(value: str) -> str:
        """Escape a Python string for safe embedding in single-quoted Cypher literals."""
        return (value or "").replace("\\", "\\\\").replace("'", "\\'")

    @staticmethod
    def _has_explicit_compare_intent(user_query: str) -> bool:
        """Detect direct multi-entity comparison/disambiguation intent."""
        q = f" {(user_query or '').lower()} "
        compare_markers = [" compare ", " vs ", " versus ", " between ", " difference", " separately "]
        return any(marker in q for marker in compare_markers)

    def _resolve_entity_ids_from_query(self, user_query: str) -> List[str]:
        """Resolve likely entity IDs from user query using aliases and live DB metadata."""
        if not self.entity_resolution_enabled:
            return []

        query_norm = self._normalize_lookup_text(user_query)
        if not query_norm:
            return []
        query_tokens = query_norm.split()

        scores: Dict[str, int] = {}

        def add_score(entity_id: Optional[str], score: int) -> None:
            if not entity_id:
                return
            scores[entity_id] = scores.get(entity_id, 0) + score

        # 1) High-confidence manual aliases.
        for alias, entity_id in MANUAL_ENTITY_ALIASES.items():
            alias_norm = self._normalize_lookup_text(alias)
            if self._contains_alias(query_norm, alias_norm):
                add_score(entity_id, 200 + len(alias_norm))
                continue

            if len(alias_norm) >= 4:
                fuzzy_score = self._best_phrase_similarity(query_norm, alias_norm)
                if fuzzy_score >= self.entity_resolution_alias_fuzzy_threshold:
                    add_score(entity_id, int(130 * fuzzy_score) + len(alias_norm))

        # 2) Dynamic aliases from live entities to reduce hardcoded drift.
        entities: List[Dict[str, Any]] = []
        if getattr(db, "driver", None):
            try:
                entities = db.query_all_entities("UpstreamProducer")
            except Exception as exc:
                logger.debug("Entity resolution lookup skipped: %s", exc)

        if entities:
            token_frequency: Dict[str, int] = {}
            entity_tokens: Dict[str, List[str]] = {}

            for entity in entities:
                entity_id = entity.get("id")
                if not isinstance(entity_id, str):
                    continue

                token_candidates: List[str] = []
                for source in [entity.get("name", ""), entity.get("short_name", "")]:
                    for token in self._normalize_lookup_text(str(source)).split():
                        if len(token) < 4 or token in ENTITY_TOKEN_STOPWORDS:
                            continue
                        token_candidates.append(token)

                deduped_tokens = sorted(set(token_candidates))
                entity_tokens[entity_id] = deduped_tokens
                for token in deduped_tokens:
                    token_frequency[token] = token_frequency.get(token, 0) + 1

            for entity in entities:
                entity_id = entity.get("id")
                if not isinstance(entity_id, str):
                    continue

                alias_variants = {
                    self._normalize_lookup_text(entity_id.replace("-", " ")),
                    self._normalize_lookup_text(str(entity.get("name", ""))),
                    self._normalize_lookup_text(str(entity.get("short_name", ""))),
                }

                for alias in alias_variants:
                    if len(alias) < 3:
                        continue

                    if self._contains_alias(query_norm, alias):
                        add_score(entity_id, 90 + len(alias))
                        continue

                    if len(alias) >= 5:
                        fuzzy_score = self._best_phrase_similarity(query_norm, alias)
                        if fuzzy_score >= self.entity_resolution_dynamic_fuzzy_threshold:
                            add_score(entity_id, int(90 * fuzzy_score) + len(alias))

                for token in entity_tokens.get(entity_id, []):
                    if token_frequency.get(token) != 1:
                        continue

                    if self._contains_alias(query_norm, token):
                        add_score(entity_id, 40 + len(token))
                        continue

                    if len(token) >= 5:
                        best_token_score = max(
                            (
                                self._normalized_edit_similarity(query_token, token)
                                for query_token in query_tokens
                                if abs(len(query_token) - len(token)) <= 2
                            ),
                            default=0.0,
                        )
                        if best_token_score >= self.entity_resolution_token_fuzzy_threshold:
                            add_score(entity_id, int(35 * best_token_score) + len(token))

        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        if not ranked:
            return []

        top_score = ranked[0][1]
        score_floor = max(self.entity_resolution_min_score, int(top_score * 0.55))
        resolved_ids = [
            entity_id
            for entity_id, score in ranked
            if score >= score_floor
        ][: self.entity_resolution_max_ids]

        if resolved_ids:
            logger.info(
                "[ENTITY-RESOLUTION] Query resolved to entity IDs: %s (top_score=%d, floor=%d)",
                resolved_ids,
                top_score,
                score_floor,
            )

        return resolved_ids

    def _deterministic_entity_resolution_override(
        self,
        user_query: str,
        resolved_entity_ids: Optional[List[str]] = None,
    ) -> Optional[str]:
        """Use deterministic entity-scoped queries when intent and resolved IDs are high confidence."""
        resolved_ids = resolved_entity_ids if resolved_entity_ids is not None else self._resolve_entity_ids_from_query(user_query)
        if not resolved_ids:
            return None

        has_multi_entity_intent = self._has_explicit_compare_intent(user_query)

        if len(resolved_ids) == 1 and not self._is_aggregation_query(user_query):
            entity_id = self._quote_cypher_string(resolved_ids[0])
            return (
                "MATCH (n:UpstreamProducer)\n"
                f"WHERE n.id = '{entity_id}'\n"
                "RETURN n AS entity\n"
                "LIMIT 1"
            )

        if len(resolved_ids) >= 2 and has_multi_entity_intent:
            id_literals = ", ".join([f"'{self._quote_cypher_string(entity_id)}'" for entity_id in resolved_ids[:3]])
            return (
                "MATCH (n:UpstreamProducer)\n"
                f"WHERE n.id IN [{id_literals}]\n"
                "RETURN n AS entity\n"
                "ORDER BY n.name ASC\n"
                "LIMIT 25"
            )

        return None

    def _build_entity_resolution_hint(self, user_query: str, resolved_entity_ids: List[str]) -> str:
        """Build optional resolved-id hint block for Cypher generation prompts."""
        if not resolved_entity_ids:
            return ""

        has_compare_intent = self._has_explicit_compare_intent(user_query)
        if len(resolved_entity_ids) == 1 and not self._is_aggregation_query(user_query):
            resolved_id = self._quote_cypher_string(resolved_entity_ids[0])
            return (
                "\n\n[RESOLVED_ENTITY_ID]\n"
                f"{resolved_id}\n"
                "Use WHERE n.id = '<resolved_id>' as primary filter unless question explicitly asks for all entities."
            )

        if len(resolved_entity_ids) >= 2 and has_compare_intent:
            resolved_literal_list = ", ".join(
                [f"'{self._quote_cypher_string(entity_id)}'" for entity_id in resolved_entity_ids[:3]]
            )
            return (
                "\n\n[RESOLVED_ENTITY_IDS]\n"
                f"{resolved_literal_list}\n"
                "When comparing or disambiguating these entities, use WHERE n.id IN [..] as primary filter."
            )

        return ""

    def _run_langchain_cypher_shadow(self, user_query: str) -> Dict[str, Any]:
        """Generate Cypher in shadow mode using LangChain + live Neo4j schema."""
        if not self.langchain_cypher_shadow_enabled:
            return {
                "enabled": False,
                "status": "disabled",
            }

        if not self.langchain_shadow_ready:
            now = time.time()
            if (now - self._langchain_init_last_attempt_ts) >= self.langchain_init_retry_seconds:
                self._init_langchain_shadow_components()

        if not self.langchain_shadow_ready or self._langchain_chat_model is None:
            return {
                "enabled": True,
                "status": "unavailable",
                "error": self.langchain_shadow_last_error,
            }

        started = time.time()

        try:
            schema_context = self._refresh_langchain_schema_cache()
            if not schema_context:
                raise ValueError("LangChain schema cache is empty")

            resolved_entity_ids = self._resolve_entity_ids_from_query(user_query)
            entity_resolution_hint = self._build_entity_resolution_hint(user_query, resolved_entity_ids)

            system_prompt = self._build_cypher_system_prompt(schema_context)
            user_prompt = (
                "Generate a Cypher query for this question:\n"
                f"{user_query}"
                f"{entity_resolution_hint}\n\n"
                "Return only Cypher."
            )

            model_response = self._langchain_chat_model.invoke(
                [
                    ("system", system_prompt),
                    ("human", user_prompt),
                ]
            )

            response_text = self._extract_message_text(getattr(model_response, "content", model_response))
            cypher_query = self._normalize_cypher_for_neo4j(self._extract_cypher(response_text))
            read_only_cypher, safety_error = self._check_read_only_cypher(cypher_query)

            execution_success = False
            execution_error: Optional[str] = None
            data_rows = 0
            if read_only_cypher:
                try:
                    shadow_results = db.execute_raw_cypher(cypher_query)
                    data_rows = len(shadow_results) if isinstance(shadow_results, list) else 0
                    execution_success = True
                except Exception as exec_exc:
                    execution_error = str(exec_exc)

            return {
                "enabled": True,
                "status": "ok",
                "provider": "langchain-openrouter",
                "model": self.langchain_openrouter_model,
                "schema_source": self.langchain_schema_source,
                "schema_chars": len(schema_context),
                "duration_ms": int((time.time() - started) * 1000),
                "read_only_cypher": read_only_cypher,
                "safety_error": safety_error,
                "execution_success": execution_success,
                "execution_error": execution_error,
                "data_rows": data_rows,
                "cypher_query": cypher_query,
            }
        except Exception as exc:
            return {
                "enabled": True,
                "status": "error",
                "provider": "langchain-openrouter",
                "model": self.langchain_openrouter_model,
                "schema_source": self.langchain_schema_source,
                "duration_ms": int((time.time() - started) * 1000),
                "error": str(exc),
            }

    def _build_groq_schema_context(self, user_query: str, schema_catalog: Optional[str] = None) -> str:
        """Build a size-safe schema context for Groq: compact schema + retrieved excerpts."""
        compact_schema = self._get_compact_schema()
        retrieved_sections = self._retrieve_relevant_schema_sections(
            user_query,
            max_sections=self.groq_schema_rag_max_sections,
            max_chars=self.groq_schema_rag_max_chars,
            schema_catalog=schema_catalog,
        )

        if not retrieved_sections:
            return compact_schema

        retrieved_text = "\n\n".join(retrieved_sections)

        context = (
            f"{compact_schema}\n\n"
            "RELEVANT SCHEMA EXCERPTS (retrieved for this question):\n"
            f"{retrieved_text}"
        )

        if len(context) > self.groq_schema_max_chars:
            context = context[: self.groq_schema_max_chars].rstrip()

        return context

    def _build_general_schema_context(self, user_query: str, schema_catalog: Optional[str] = None) -> str:
        """Build query-focused schema context for providers that can support larger prompts."""
        schema_text = schema_catalog if schema_catalog is not None else self.node_catalog
        retrieved_sections = self._retrieve_relevant_schema_sections(
            user_query,
            max_sections=self.schema_rag_default_max_sections,
            max_chars=self.schema_rag_default_max_chars,
            schema_catalog=schema_text,
        )

        if not retrieved_sections:
            context = schema_text
        else:
            context = "RELEVANT SCHEMA EXCERPTS (retrieved for this question):\n" + "\n\n".join(
                retrieved_sections
            )

        if len(context) > self.schema_rag_default_max_chars:
            context = context[: self.schema_rag_default_max_chars].rstrip()

        return context

    def _schema_context_for_query(self, user_query: str) -> str:
        """Select schema context size based on provider/token constraints."""
        active_schema_catalog = self._active_schema_catalog()

        if self.provider in self.compact_schema_providers:
            schema_context = self._build_groq_schema_context(
                user_query,
                schema_catalog=active_schema_catalog,
            )
            logger.info(
                "Using compact schema context for provider=%s (%d chars, full schema=%d chars)",
                self.provider,
                len(schema_context),
                len(active_schema_catalog),
            )
            return schema_context

        schema_context = self._build_general_schema_context(
            user_query,
            schema_catalog=active_schema_catalog,
        )
        logger.info(
            "Using query-focused schema context for provider=%s (%d chars, full schema=%d chars)",
            self.provider,
            len(schema_context),
            len(active_schema_catalog),
        )
        return schema_context

    @staticmethod
    def _build_cypher_system_prompt(schema_context: str) -> str:
        """Build system prompt for Cypher generation using one schema context block."""
        return f"""You are a Cypher query generator for a Neo4j database containing the Nigerian upstream petroleum industry.

Complete schema context:
{schema_context}

Rules:
1. Output ONLY one valid Cypher query. No markdown. No explanation.
2. Query must be read-only.
3. Use only read clauses: MATCH, OPTIONAL MATCH, WHERE, WITH, RETURN, ORDER BY, LIMIT, COUNT, COLLECT, DISTINCT, UNWIND.
4. Never use write clauses: CREATE, DELETE, MERGE, SET, REMOVE, DROP, ALTER, CALL.
5. For broad result sets, include LIMIT 100 unless the query is an aggregate count.
6. For count questions (e.g., "how many", "count", "number of"), return a COUNT alias.
7. For list-length metrics, always use null-safe expressions like size(coalesce(n.some_list, [])).
8. For entity-centric questions, include stable aliases when possible: n.id AS entity_id, n.name AS entity_name.
9. Avoid returning only NOT_AVAILABLE/null metric fields; prefer robust derived metrics from available properties.
10. Use Neo4j built-ins only (toFloat, toInteger); never use APOC helper functions.
11. For AVG/SUM on mixed-type numeric fields, convert safely with CASE + regex before aggregation.
12. Avoid UNION unless absolutely necessary.
13. For user-specified entity names, use case-insensitive matching: toLower(n.name) CONTAINS toLower("...") OR toLower(coalesce(n.short_name, "")) CONTAINS toLower("...").
14. Use labels and properties exactly as they appear in schema context; do not invent new labels/properties.
15. If user prompt includes RESOLVED_ENTITY_ID or RESOLVED_ENTITY_IDS, you MUST prioritize n.id equality/IN filters over name matching.
16. Do not invent relationship types. Only use relationships that appear in schema context.
17. operational_area is often a list. For deepwater/offshore filters, use list-safe predicates like: any(area IN coalesce(n.operational_area, []) WHERE toLower(toString(area)) CONTAINS 'deepwater').
"""

    @staticmethod
    def _is_fallback_eligible_error(error_text: str) -> bool:
        """Whether provider failure should trigger fallback provider attempt."""
        text = error_text.lower()
        retryable_markers = [
            "429",
            "rate limit",
            "rate_limit",
            "quota",
            "limit reached",
            "503",
            "502",
            "timeout",
            "temporarily unavailable",
            "service unavailable",
            "resource exhausted",
            "too many requests",
        ]
        return any(marker in text for marker in retryable_markers)

    @staticmethod
    def _extract_chat_completion_content(payload: Dict[str, Any], provider_name: str) -> str:
        """Extract text content from OpenAI-style chat completion payloads."""
        choices = payload.get("choices", [])
        if not choices:
            raise ValueError(f"{provider_name} returned no choices")

        content = choices[0].get("message", {}).get("content", "")
        if not content:
            raise ValueError(f"{provider_name} returned empty content")

        return str(content).strip()

    def _call_with_provider(self, provider: str, system_prompt: str, user_prompt: str) -> str:
        """Perform one provider-specific call."""
        if provider == "cerebras":
            if not self.cerebras_api_key:
                raise ValueError("Cerebras client is not initialized")

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]

            if self.cerebras_client is not None:
                completion = self.cerebras_client.chat.completions.create(
                    messages=messages,
                    model=self.cerebras_model,
                    max_completion_tokens=self.cerebras_max_completion_tokens,
                    temperature=self.cerebras_temperature,
                    top_p=self.cerebras_top_p,
                    stream=False,
                )
                choices = getattr(completion, "choices", None)
                if not choices:
                    raise ValueError("Cerebras returned no choices")

                message = getattr(choices[0], "message", None)
                content = getattr(message, "content", "") if message else ""
                if isinstance(content, list):
                    content = "".join(
                        item.get("text", "") if isinstance(item, dict) else str(item)
                        for item in content
                    )
                if not content:
                    raise ValueError("Cerebras returned empty content")

                self.last_provider_used = "cerebras"
                return str(content).strip()

            response = requests.post(
                self.cerebras_endpoint,
                headers={
                    "Authorization": f"Bearer {self.cerebras_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.cerebras_model,
                    "messages": messages,
                    "max_completion_tokens": self.cerebras_max_completion_tokens,
                    "temperature": self.cerebras_temperature,
                    "top_p": self.cerebras_top_p,
                    "stream": False,
                },
                timeout=60,
            )

            if response.status_code != 200:
                raise ValueError(f"Cerebras API error ({response.status_code}): {response.text}")

            payload = response.json()
            content = self._extract_chat_completion_content(payload, "Cerebras")
            self.last_provider_used = "cerebras"
            return content

        if provider == "openrouter":
            if not self.openrouter_api_key:
                raise ValueError("OpenRouter client is not initialized")

            headers = {
                "Authorization": f"Bearer {self.openrouter_api_key}",
                "Content-Type": "application/json",
            }
            if self.openrouter_site_url:
                headers["HTTP-Referer"] = self.openrouter_site_url
            if self.openrouter_site_name:
                headers["X-Title"] = self.openrouter_site_name

            response = requests.post(
                self.openrouter_endpoint,
                headers=headers,
                json={
                    "model": self.openrouter_model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "max_tokens": self.openrouter_max_tokens,
                    "temperature": self.openrouter_temperature,
                },
                timeout=60,
            )

            if response.status_code != 200:
                raise ValueError(f"OpenRouter API error ({response.status_code}): {response.text}")

            payload = response.json()
            content = self._extract_chat_completion_content(payload, "OpenRouter")
            self.last_provider_used = "openrouter"
            return content

        if provider == "groq":
            if not self.groq_api_key or not self.groq_endpoint:
                raise ValueError("Groq client is not initialized")

            response = requests.post(
                self.groq_endpoint,
                headers={
                    "Authorization": f"Bearer {self.groq_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.groq_model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": 0.1,
                },
                timeout=60,
            )

            if response.status_code != 200:
                raise ValueError(f"Groq API error ({response.status_code}): {response.text}")

            payload = response.json()
            content = self._extract_chat_completion_content(payload, "Groq")
            self.last_provider_used = "groq"
            return content

        if provider == "gemini":
            if self.gemini_client is None:
                raise ValueError("Gemini client is not initialized")

            combined_prompt = f"{system_prompt}\n\n{user_prompt}"
            response = self.gemini_client.generate_content(combined_prompt)
            text = getattr(response, "text", "")
            if not text:
                raise ValueError("Gemini returned empty response")

            self.last_provider_used = "gemini"
            return text.strip()

        raise ValueError(f"Unsupported provider: {provider}")

    def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        """Provider-aware call wrapper with automatic fallback."""
        if not self.available_providers:
            raise ValueError("No LLM providers are initialized")

        provider_order = [self.provider] + [p for p in self.available_providers if p != self.provider]
        errors: List[str] = []

        for idx, provider in enumerate(provider_order):
            try:
                return self._call_with_provider(provider, system_prompt, user_prompt)
            except Exception as exc:
                error_text = str(exc)
                errors.append(f"{provider}: {error_text}")

                has_fallback = idx < len(provider_order) - 1
                if has_fallback:
                    if self._is_fallback_eligible_error(error_text):
                        logger.warning(
                            "LLM provider %s failed with retryable error; attempting fallback provider.",
                            provider,
                        )
                    else:
                        logger.warning(
                            "LLM provider %s failed; attempting fallback provider.",
                            provider,
                        )
                    continue

                break

        raise ValueError("All LLM providers failed: " + " | ".join(errors))

    def _provider_order_with_preference(self, preferred_provider: Optional[str]) -> List[str]:
        """Build provider order with an optional preferred provider first."""
        if not self.available_providers:
            return []

        if not preferred_provider or preferred_provider in {"", "auto", "default"}:
            return [self.provider] + [p for p in self.available_providers if p != self.provider]

        preferred = preferred_provider.strip().lower()
        ordered: List[str] = []
        if preferred in self.available_providers:
            ordered.append(preferred)

        for provider in [self.provider] + self.available_providers:
            if provider not in ordered:
                ordered.append(provider)
        return ordered

    def _call_llm_with_preference(
        self,
        system_prompt: str,
        user_prompt: str,
        preferred_provider: Optional[str] = None,
    ) -> str:
        """Call LLM using an optional preferred provider, then fallback providers."""
        provider_order = self._provider_order_with_preference(preferred_provider)
        if not provider_order:
            raise ValueError("No LLM providers are initialized")

        errors: List[str] = []
        for idx, provider in enumerate(provider_order):
            try:
                return self._call_with_provider(provider, system_prompt, user_prompt)
            except Exception as exc:
                error_text = str(exc)
                errors.append(f"{provider}: {error_text}")

                has_fallback = idx < len(provider_order) - 1
                if has_fallback:
                    if self._is_fallback_eligible_error(error_text):
                        logger.warning(
                            "Preferred provider %s failed with retryable error; attempting fallback provider.",
                            provider,
                        )
                    else:
                        logger.warning(
                            "Preferred provider %s failed; attempting fallback provider.",
                            provider,
                        )
                    continue
                break

        raise ValueError("All preferred/fallback LLM providers failed: " + " | ".join(errors))

    @staticmethod
    def _extract_cypher(llm_output: str) -> str:
        """Extract raw Cypher text from model output."""
        text = (llm_output or "").strip()
        if not text:
            raise ValueError("LLM did not return a Cypher query")

        start_patterns = (
            "MATCH",
            "OPTIONAL MATCH",
            "WITH",
            "UNWIND",
            "RETURN",
        )

        # Prefer fenced code blocks to avoid trailing conversational text.
        code_blocks = re.findall(
            r"```(?:\s*cypher|\s*cql)?\s*([\s\S]*?)```",
            text,
            flags=re.IGNORECASE,
        )
        candidates = code_blocks + [text]

        trailer_pattern = re.compile(
            r"^(here|enjoy|note|explanation|output|result|i hope|this query|let me|code snippet)\b",
            flags=re.IGNORECASE,
        )

        for candidate in candidates:
            block_text = candidate.strip()
            if block_text.lower().startswith("cypher"):
                block_text = block_text[6:].strip()

            lines = [line.strip() for line in block_text.splitlines() if line.strip()]
            if not lines:
                continue

            start_idx = None
            for idx, line in enumerate(lines):
                upper_line = line.upper()
                if any(upper_line.startswith(pattern) for pattern in start_patterns):
                    start_idx = idx
                    break

            if start_idx is None:
                continue

            cypher_lines: List[str] = []
            for line in lines[start_idx:]:
                if line.startswith("```"):
                    break
                if trailer_pattern.match(line):
                    break
                cypher_lines.append(line)

            query = "\n".join(cypher_lines).strip().rstrip(";")
            if query:
                return query

        raise ValueError("Failed to parse Cypher from LLM output")

    @staticmethod
    def _deterministic_cypher_override(user_query: str) -> Optional[str]:
        """Return a deterministic Cypher query for known brittle intents."""
        q = user_query.lower()

        count_patterns = [
            "how many upstream producers do we have in nigeria",
            "count all upstream producers",
            "number of upstream producers",
            "how many upstream producers",
        ]
        if any(pattern in q for pattern in count_patterns):
            return "MATCH (n:UpstreamProducer) RETURN count(n) AS total_upstream_producers"

        if "average" in q and "current production" in q:
            return """
MATCH (n:UpstreamProducer)
WITH CASE
    WHEN n.current_production_bopd IS NULL THEN NULL
    WHEN toString(n.current_production_bopd) =~ '^[0-9]+(\\.[0-9]+)?$' THEN toFloat(toString(n.current_production_bopd))
    ELSE NULL
END AS production_bopd
WHERE production_bopd IS NOT NULL
RETURN avg(production_bopd) AS average_current_production_bopd
""".strip()

        if "summary" in q and "shell" in q and "chevron" in q:
            return """
MATCH (n:UpstreamProducer)
WHERE toLower(n.name) CONTAINS 'shell' OR toLower(n.name) CONTAINS 'chevron'
RETURN
    n.id AS entity_id,
    n.name AS entity_name,
    n.current_production_bopd AS current_production_bopd,
    n.proven_reserves_mmbbls AS proven_reserves_mmbbls,
    n.operational_status AS operational_status,
    n.sub_type AS sub_type
ORDER BY entity_name ASC
LIMIT 10
""".strip()

        oil_field_patterns = [
            "highest number of oil fields",
            "most oil fields",
            "highest number of fields",
            "largest number of fields",
            "producer has the highest number of oil fields",
        ]

        if any(pattern in q for pattern in oil_field_patterns):
            return """
MATCH (n:UpstreamProducer)
WITH
    n,
    size(coalesce(n.oml_blocks_held, [])) AS oml_block_count,
    size(coalesce(n.opl_blocks_held, [])) AS opl_block_count,
    CASE
        WHEN n.marginal_field_count IS NULL THEN 0
        WHEN toString(n.marginal_field_count) =~ '^[0-9]+$' THEN toInteger(n.marginal_field_count)
        ELSE 0
    END AS marginal_field_count
WITH
    n,
    oml_block_count,
    opl_block_count,
    marginal_field_count,
    (oml_block_count + opl_block_count + marginal_field_count) AS total_field_proxy_count
RETURN
    n.name AS name,
    total_field_proxy_count,
    oml_block_count,
    opl_block_count,
    marginal_field_count
ORDER BY total_field_proxy_count DESC, name ASC
LIMIT 1
""".strip()

        if (
            ("largeindigenous" in q or "large indigenous" in q)
            and "security risk" in q
            and ("top" in q or "rank" in q)
            and "production" in q
        ):
            return """
MATCH (n:UpstreamProducer)
WHERE n.sub_type = 'LargeIndigenous'
  AND toLower(coalesce(n.security_risk_level, '')) = 'high'
WITH
    n,
    CASE
        WHEN toString(n.current_production_bopd) =~ '^[0-9]+(\\.[0-9]+)?$' THEN toFloat(toString(n.current_production_bopd))
        ELSE NULL
    END AS current_production_bopd,
    CASE
        WHEN toString(n.nnpc_equity_percentage) =~ '^[0-9]+(\\.[0-9]+)?$' THEN toFloat(toString(n.nnpc_equity_percentage))
        ELSE NULL
    END AS nnpc_equity_percentage,
    size(coalesce(n.oml_blocks_held, [])) + size(coalesce(n.opl_blocks_held, [])) AS total_block_footprint
WHERE current_production_bopd IS NOT NULL
RETURN
    n.id AS entity_id,
    n.name AS entity_name,
    n.security_risk_level AS security_risk_level,
    current_production_bopd,
    nnpc_equity_percentage,
    total_block_footprint
ORDER BY current_production_bopd DESC, total_block_footprint DESC, entity_name ASC
LIMIT 3
""".strip()

        if "deepwater" in q and ("operational_area" in q or "parent company" in q):
            return """
MATCH (n:UpstreamProducer)
WHERE any(area IN coalesce(n.operational_area, []) WHERE toLower(toString(area)) CONTAINS 'deepwater')
WITH
    n,
    CASE
        WHEN toString(n.current_production_bopd) =~ '^[0-9]+(\\.[0-9]+)?$' THEN toFloat(toString(n.current_production_bopd))
        ELSE NULL
    END AS current_production_bopd
RETURN
    n.id AS entity_id,
    n.name AS entity_name,
    n.parent_company AS parent_company,
    current_production_bopd
ORDER BY current_production_bopd DESC, entity_name ASC
LIMIT 100
""".strip()

        if (
            "marginal field" in q
            and ("how many" in q or "count" in q)
            and ("active" in q or "near production" in q)
        ):
            return """
MATCH (n:UpstreamProducer)
WHERE (
    'MarginalFieldOperator' IN labels(n)
    OR n.is_marginal_field_operator = true
    OR n.marginal_field_round IS NOT NULL
)
AND toLower(coalesce(n.operational_status, '')) IN ['active', 'near production']
AND CASE
    WHEN toString(n.current_production_bopd) =~ '^[0-9]+(\\.[0-9]+)?$' THEN toFloat(toString(n.current_production_bopd))
    ELSE 0
END > 0
RETURN COUNT(n) AS active_marginal_field_operators
""".strip()

        return None

    @staticmethod
    def _normalize_cypher_for_neo4j(cypher_query: str) -> str:
        """Normalize common non-Neo4j function variants emitted by LLMs."""
        normalized = cypher_query
        normalized = re.sub(r"\bTO_FLOAT\s*\(", "toFloat(", normalized, flags=re.IGNORECASE)
        normalized = re.sub(r"\bTO_INTEGER\s*\(", "toInteger(", normalized, flags=re.IGNORECASE)
        normalized = re.sub(r"\bAPOC\.NUMBER\.TOFLOAT\s*\(", "toFloat(", normalized, flags=re.IGNORECASE)
        normalized = re.sub(r"\bAPOC\.NUMBER\.TOINTEGER\s*\(", "toInteger(", normalized, flags=re.IGNORECASE)
        return normalized

    @staticmethod
    def _is_missing_value(value: Any) -> bool:
        """Treat common empty placeholders as missing values."""
        if value is None:
            return True
        if isinstance(value, str):
            normalized = value.strip().upper()
            return normalized in {"", "NOT_AVAILABLE", "N/A", "NULL", "NONE", "UNKNOWN"}
        if isinstance(value, (list, dict)):
            return len(value) == 0
        return False

    @staticmethod
    def _coerce_numeric_value(value: Any) -> Optional[float]:
        """Convert scalar strings/numbers to float when possible."""
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            normalized = value.replace(",", "").strip()
            if re.fullmatch(r"-?[0-9]+(\.[0-9]+)?", normalized):
                return float(normalized)
        return None

    def _deterministic_answer_override(self, user_query: str, cypher_results: List[Dict[str, Any]]) -> Optional[str]:
        """Provide stable answers for simple aggregate count questions."""
        if not cypher_results or not isinstance(cypher_results[0], dict):
            return None

        q = user_query.lower()
        is_count_intent = any(token in q for token in ["how many", "count", "number of"])
        if not is_count_intent:
            return None

        first_row = cypher_results[0]
        if len(first_row) != 1:
            return None

        metric_name, metric_value = next(iter(first_row.items()))
        numeric_value = self._coerce_numeric_value(metric_value)
        if numeric_value is None:
            return None

        if numeric_value.is_integer():
            value_text = str(int(numeric_value))
        else:
            value_text = f"{numeric_value:.2f}".rstrip("0").rstrip(".")

        metric_label = metric_name.replace("_", " ")
        return f"{metric_label}: {value_text}."

    def _extract_entity_identity(self, results: List[Dict[str, Any]]) -> Tuple[Optional[str], Optional[str]]:
        """Extract best-effort (entity_id, entity_name) from query results."""
        if not results or not isinstance(results[0], dict):
            return None, None

        first_row = results[0]
        entity_id: Optional[str] = None
        entity_name: Optional[str] = None

        # Direct aliases from Cypher RETURN are highest confidence.
        direct_id_keys = ["entity_id", "id", "producer_id", "n.id"]
        direct_name_keys = ["entity_name", "name", "producer_name", "n.name"]

        for key in direct_id_keys:
            val = first_row.get(key)
            if isinstance(val, str) and val.strip():
                entity_id = val.strip()
                break

        for key in direct_name_keys:
            val = first_row.get(key)
            if isinstance(val, str) and val.strip():
                entity_name = val.strip()
                break

        # Inspect nested dictionaries (e.g., RETURN n where n is serialized node dict).
        nested_objects: List[Dict[str, Any]] = [v for v in first_row.values() if isinstance(v, dict)]
        for obj in nested_objects:
            if not entity_name:
                val = obj.get("name")
                if isinstance(val, str) and val.strip():
                    entity_name = val.strip()
            if not entity_id:
                val = obj.get("id")
                if isinstance(val, str) and val.strip():
                    entity_id = val.strip()

        # Inspect oddly-named scalar columns that still contain id/name semantics.
        for key, val in first_row.items():
            key_lower = key.lower()
            if not entity_name and "name" in key_lower and isinstance(val, str) and val.strip():
                entity_name = val.strip()
            if not entity_id and key_lower.endswith("id") and isinstance(val, str) and val.strip():
                entity_id = val.strip()

        # If we have a name but not id, resolve id from canonical entity search.
        if entity_name and not entity_id:
            try:
                candidates = db.search_entities_by_keyword(entity_name, "UpstreamProducer")
                exact = next(
                    (
                        c for c in candidates
                        if str(c.get("name", "")).strip().lower() == entity_name.lower()
                        or str(c.get("short_name", "")).strip().lower() == entity_name.lower()
                    ),
                    None,
                )
                if exact and isinstance(exact.get("id"), str):
                    entity_id = exact["id"]
            except Exception as exc:
                logger.debug("Entity id resolution by name failed: %s", exc)

        return entity_id, entity_name

    def _should_repair_cypher(self, user_query: str, cypher_results: List[Dict[str, Any]]) -> bool:
        """Heuristic gate for automatic second-pass Cypher repair."""
        if not cypher_results:
            return True

        q = user_query.lower()
        metric_intent = any(
            term in q
            for term in [
                "how many", "count", "number of", "highest", "lowest", "most",
                "least", "top", "bottom", "rank", "ranking", "compare",
            ]
        )
        asset_intent = any(term in q for term in ["oml", "opl", "field", "fields", "block", "blocks"])

        if not (metric_intent or asset_intent):
            return False

        non_name_values: List[Any] = []
        for row in cypher_results[:10]:
            if not isinstance(row, dict):
                continue
            for key, value in row.items():
                if "name" in key.lower():
                    continue
                non_name_values.append(value)

        if not non_name_values:
            return True

        has_non_missing = any(not self._is_missing_value(value) for value in non_name_values)
        return not has_non_missing

    def _repair_cypher_query(
        self,
        user_query: str,
        failed_query: str,
        cypher_results: List[Dict[str, Any]],
    ) -> str:
        """Ask LLM to repair a weak query using observed result quality feedback."""
        preview_rows = cypher_results[:5] if isinstance(cypher_results, list) else []
        preview_json = json.dumps(preview_rows, indent=2, default=str)

        system_prompt = """You are a Cypher query repair expert.

Given a user question, an initial Cypher query, and weak/empty results, repair the query.

Rules:
1. Output ONLY one valid read-only Cypher query.
2. Keep original intent exactly.
3. Use null-safe list counting with size(coalesce(..., [])).
4. Prefer robust aliases: entity_id, entity_name, and metric-specific aliases.
5. Avoid queries that return mostly null/NOT_AVAILABLE metric columns.
6. Use LIMIT 100 for non-aggregate results.
"""

        user_prompt = (
            f"User question:\n{user_query}\n\n"
            f"Initial query:\n{failed_query}\n\n"
            f"Initial results (weak):\n{preview_json}\n\n"
            "Repair the query now. Return only Cypher."
        )

        repaired_output = self._call_llm(system_prompt, user_prompt)
        return self._extract_cypher(repaired_output)

    def _repair_cypher_query_on_error(
        self,
        user_query: str,
        failed_query: str,
        execution_error: str,
    ) -> str:
        """Repair Cypher when execution fails validation/runtime checks."""
        system_prompt = """You are a Cypher query repair expert.

Given a user question, a failed Cypher query, and the execution error,
produce one corrected read-only Cypher query.

Rules:
1. Output ONLY one valid read-only Cypher query.
2. Keep the original intent exactly.
3. For list-length metrics, use size(coalesce(..., [])).
4. Include LIMIT 100 for non-aggregate queries.
5. Prefer aliases: entity_id, entity_name, plus metric aliases.
6. Never use write clauses.
7. Do NOT use APOC functions.
8. Use Neo4j built-ins: toFloat(), toInteger() (never TO_FLOAT or TO_INTEGER).
9. Avoid UNION unless absolutely required by the question.
10. Use the UpstreamProducer label for producer questions.
"""

        user_prompt = (
            f"User question:\n{user_query}\n\n"
            f"Failed query:\n{failed_query}\n\n"
            f"Execution error:\n{execution_error}\n\n"
            "Repair the query now. Return only Cypher."
        )

        repaired_output = self._call_llm(system_prompt, user_prompt)
        return self._extract_cypher(repaired_output)

    def _text_to_cypher(self, user_query: str) -> str:
        """Call 1: Convert natural language question into read-only Cypher."""
        logger.info("[LLM-CYPHER-GEN] Generating Cypher for: %s", user_query[:120])

        deterministic_query = self._deterministic_cypher_override(user_query)
        if deterministic_query:
            logger.info("[LLM-CYPHER-GEN] Using deterministic override for query intent")
            logger.info("[LLM-CYPHER-GEN] Generated: %s", deterministic_query[:200])
            return deterministic_query

        resolved_entity_ids = self._resolve_entity_ids_from_query(user_query)
        deterministic_entity_query = self._deterministic_entity_resolution_override(
            user_query,
            resolved_entity_ids,
        )
        if deterministic_entity_query:
            logger.info("[LLM-CYPHER-GEN] Using deterministic entity-resolution override")
            logger.info("[LLM-CYPHER-GEN] Generated: %s", deterministic_entity_query[:200])
            return deterministic_entity_query

        schema_context = self._schema_context_for_query(user_query)
        system_prompt = self._build_cypher_system_prompt(schema_context)

        entity_resolution_hint = self._build_entity_resolution_hint(user_query, resolved_entity_ids)

        user_prompt = (
            "Generate a Cypher query for this question:\n"
            f"{user_query}"
            f"{entity_resolution_hint}\n\n"
            "Return only Cypher."
        )

        try:
            llm_output = self._call_llm(system_prompt, user_prompt)
        except ValueError as exc:
            error_text = str(exc)
            is_size_error = (
                "Request too large" in error_text
                or "tokens per minute" in error_text
                or "rate_limit_exceeded" in error_text
            )

            if is_size_error:
                logger.warning(
                    "Provider rejected prompt size/rate; retrying Cypher generation with compact schema context"
                )
                fallback_system_prompt = self._build_cypher_system_prompt(
                    self._build_groq_schema_context(user_query)
                )
                llm_output = self._call_llm(fallback_system_prompt, user_prompt)
            else:
                raise

        cypher_query = self._extract_cypher(llm_output)
        logger.info("[LLM-CYPHER-GEN] Generated: %s", cypher_query[:200])
        return cypher_query

    @staticmethod
    def _response_depth_from_query(user_query: str) -> str:
        """Infer whether the user expects a brief, standard, or detailed response."""
        query_lower = (user_query or "").lower()

        concise_markers = ["brief", "short", "quick", "summary", "one line", "tldr"]
        detailed_markers = [
            "detailed",
            "in depth",
            "deep",
            "explain",
            "analyze",
            "critical",
            "compare",
            "breakdown",
            "walk through",
            "insight",
        ]

        if any(marker in query_lower for marker in concise_markers):
            return "concise"
        if any(marker in query_lower for marker in detailed_markers):
            return "detailed"
        return "standard"

    def _synthesize_from_cypher(self, user_query: str, cypher_results: List[Dict[str, Any]]) -> str:
        """Call 2: Convert raw query results into a natural language answer."""
        logger.info("[LLM-ANSWER-GEN] Synthesizing answer for: %s", user_query[:120])

        deterministic_answer = self._deterministic_answer_override(user_query, cypher_results)
        if deterministic_answer:
            logger.info("[LLM-ANSWER-GEN] Using deterministic aggregate answer override")
            return deterministic_answer

        synthesis_rows, was_truncated, total_rows = self._prepare_results_for_synthesis(cypher_results)
        results_json = json.dumps(synthesis_rows, indent=2, default=str)
        response_depth = self._response_depth_from_query(user_query)

        format_instructions = {
            "concise": "Use 1 short paragraph and include the key value(s) directly.",
            "standard": "Use 2-3 short paragraphs, prioritizing facts and direct interpretation.",
            "detailed": (
                "Use a detailed multi-paragraph answer with clear structure: "
                "(1) direct findings, (2) interpretation, (3) caveats if data is missing."
            ),
        }

        system_prompt = """You are a data analyst for Nigerian upstream petroleum data.

You will receive:
- the user's question
- raw JSON results from Neo4j

Rules:
1. Answer only from the provided JSON results.
2. Do not invent fields, values, or entities.
3. If no results exist, say exactly: "No data found for this query."
4. If values are null or NOT_AVAILABLE, state that clearly.
5. Keep writing clean and readable (no broken line fragments).
"""

        user_prompt = (
            f"User question:\n{user_query}\n\n"
            f"Preferred response depth: {response_depth}. "
            f"Formatting guidance: {format_instructions[response_depth]}\n\n"
            f"Database JSON results:\n{results_json}\n\n"
            "Answer in natural language."
        )

        if was_truncated:
            user_prompt += (
                f"\n\nNote: Results were truncated to {len(synthesis_rows)} of {total_rows} rows "
                "for synthesis context safety."
            )

        answer = self._call_llm(system_prompt, user_prompt)
        logger.info("[LLM-ANSWER-GEN] Generated answer (%d chars)", len(answer))
        return answer

    def _prepare_results_for_synthesis(
        self, cypher_results: List[Dict[str, Any]]
    ) -> Tuple[List[Dict[str, Any]], bool, int]:
        """Cap synthesis payload size to avoid provider context-length failures."""
        if not cypher_results:
            return [], False, 0

        total_rows = len(cypher_results)
        rows = cypher_results[: self.synthesis_max_rows]

        while rows:
            payload = json.dumps(rows, default=str)
            if len(payload) <= self.synthesis_max_json_chars:
                break
            rows = rows[:-1]

        if not rows:
            rows = [cypher_results[0]]

        was_truncated = len(rows) < total_rows
        return rows, was_truncated, total_rows

    def _text_to_cypher_pipeline(self, user_query: str) -> Dict[str, Any]:
        """Core two-call pipeline with Cypher execution between calls."""
        cypher_query = self._normalize_cypher_for_neo4j(self._text_to_cypher(user_query))
        try:
            cypher_results = db.execute_raw_cypher(cypher_query)
        except Exception as exc:
            logger.info("[LLM-CYPHER-GEN] Initial query execution failed; attempting one repair pass")
            repaired_query = self._normalize_cypher_for_neo4j(
                self._repair_cypher_query_on_error(user_query, cypher_query, str(exc))
            )
            cypher_results = db.execute_raw_cypher(repaired_query)
            cypher_query = repaired_query

        if self._should_repair_cypher(user_query, cypher_results):
            logger.info("[LLM-CYPHER-GEN] Initial query results weak; attempting one repair pass")
            try:
                repaired_query = self._normalize_cypher_for_neo4j(
                    self._repair_cypher_query(user_query, cypher_query, cypher_results)
                )
                if repaired_query.strip().lower() != cypher_query.strip().lower():
                    repaired_results = db.execute_raw_cypher(repaired_query)
                    if not self._should_repair_cypher(user_query, repaired_results):
                        logger.info("[LLM-CYPHER-GEN] Repair pass improved query quality")
                        cypher_query = repaired_query
                        cypher_results = repaired_results
                    else:
                        logger.info("[LLM-CYPHER-GEN] Repair pass did not improve quality; keeping initial query")
            except Exception as exc:
                logger.warning("[LLM-CYPHER-GEN] Query repair pass failed: %s", exc)

        answer = self._synthesize_from_cypher(user_query, cypher_results)

        return {
            "cypher_query": cypher_query,
            "cypher_results": cypher_results,
            "answer": answer,
        }

    @staticmethod
    def _extract_entity_name(results: List[Dict[str, Any]]) -> Optional[str]:
        """Try to extract a single-entity name from the first result row."""
        if not results or not isinstance(results[0], dict):
            return None

        first_row = results[0]

        name_value = first_row.get("name")
        if isinstance(name_value, str) and name_value.strip():
            return name_value.strip()

        for value in first_row.values():
            if isinstance(value, dict):
                nested_name = value.get("name")
                if isinstance(nested_name, str) and nested_name.strip():
                    return nested_name.strip()
                nested_props = value.get("properties")
                if isinstance(nested_props, dict):
                    prop_name = nested_props.get("name")
                    if isinstance(prop_name, str) and prop_name.strip():
                        return prop_name.strip()

        return None

    @staticmethod
    def _topic_from_query(user_query: str) -> str:
        query_lower = user_query.lower()
        topic_map = {
            "production": ["production", "bopd", "barrels", "output"],
            "reserves": ["reserves", "reserve"],
            "equity": ["equity", "stake", "ownership"],
            "blocks": ["block", "oml", "opl", "field"],
            "operations": ["operational", "status", "disruption"],
            "finance": ["revenue", "income", "profit", "cost", "investment"],
            "policy": ["policy", "regulation", "compliance", "licensing"],
        }
        for topic, keywords in topic_map.items():
            if any(keyword in query_lower for keyword in keywords):
                return topic
        return "overview"

    @staticmethod
    def _clean_answer_text(answer: str) -> str:
        """Normalize whitespace so returned prose is paragraph-friendly."""
        cleaned = re.sub(r"[\t ]+", " ", str(answer or "")).strip()
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        cleaned = re.sub(r"\s+\n", "\n", cleaned)
        return cleaned

    @staticmethod
    def _db_answer_has_signal(base_answer: str, cypher_results: List[Dict[str, Any]]) -> bool:
        """Determine whether DB path returned meaningful evidence."""
        if cypher_results:
            return True

        text = (base_answer or "").strip().lower()
        if not text:
            return False

        no_signal_markers = [
            "no data found for this query",
            "i could not retrieve this answer",
            "pipeline error",
            "unable to process query",
            "took too long",
        ]
        return not any(marker in text for marker in no_signal_markers)

    def _condense_web_source_briefs(
        self,
        user_query: str,
        source_briefs: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Condense verbose web evidence, optionally using a cheaper helper model."""
        if not source_briefs:
            return []

        limited = source_briefs[: self.web_sources_for_synthesis]
        normalized: List[Dict[str, Any]] = []
        for brief in limited:
            normalized.append(
                {
                    "title": str(brief.get("title", "Unknown")).strip(),
                    "url": brief.get("url"),
                    "provider": str(brief.get("provider", "unknown")).strip(),
                    "text": str(brief.get("text", "")).strip()[: self.web_source_max_chars],
                }
            )

        total_chars = sum(len(item.get("text", "")) for item in normalized)
        if total_chars <= self.web_answer_max_chars:
            return normalized

        if not self.web_multi_model_enabled:
            return normalized

        condensed: List[Dict[str, Any]] = []
        for brief in normalized[:6]:
            source_text = brief.get("text", "")
            if not source_text:
                continue

            system_prompt = """You are an evidence condenser.

Summarize one web source into a compact evidence note.
Rules:
1. Keep only factual claims present in source text.
2. Preserve important numbers, dates, and entities.
3. Use at most 4 short bullet points.
4. Do not add new claims.
"""
            user_prompt = (
                f"User question:\n{user_query}\n\n"
                f"Source title: {brief.get('title')}\n"
                f"Provider: {brief.get('provider')}\n"
                f"URL: {brief.get('url')}\n\n"
                f"Source text:\n{source_text}\n\n"
                "Return compact bullet evidence now."
            )

            try:
                reduced = self._call_llm_with_preference(
                    system_prompt,
                    user_prompt,
                    preferred_provider=self.web_source_summary_provider,
                )
                brief["text"] = str(reduced).strip()[: max(400, self.web_source_max_chars // 2)]
            except Exception as exc:
                logger.warning("Web source condensation failed for '%s': %s", brief.get("title"), exc)
                brief["text"] = source_text[: max(400, self.web_source_max_chars // 2)]

            condensed.append(brief)

        return condensed or normalized

    def _synthesize_web_augmented_answer(
        self,
        user_query: str,
        base_answer: str,
        cypher_results: List[Dict[str, Any]],
        synthesis: Dict[str, Any],
        web_results: Dict[str, Any],
    ) -> str:
        """Create a final answer that blends DB and web evidence analytically."""
        db_has_signal = self._db_answer_has_signal(base_answer, cypher_results)
        response_depth = self._response_depth_from_query(user_query)

        source_briefs = self._condense_web_source_briefs(
            user_query,
            synthesis.get("source_briefs", []),
        )
        provider_counts = web_results.get("provider_counts", {}) if isinstance(web_results, dict) else {}
        data_points = synthesis.get("data_points", [])[:40]
        db_rows = cypher_results[:15]

        if self.web_priority_mode == "web_first":
            mode_instruction = (
                "Always prioritize web evidence first. Use database rows only as secondary corroboration. "
                "If sources conflict, prefer multi-source web consensus and state the discrepancy."
            )
        elif self.web_priority_mode == "db_first":
            mode_instruction = (
                "Always prioritize database rows first. Use web evidence as supplementary context only."
            )
        else:
            mode_instruction = (
                "Database has no usable rows. Prioritize web evidence and explicitly mention that database rows were unavailable."
                if not db_has_signal
                else "Database has usable rows. Use database facts as the anchor and web evidence for expansion and recency context."
            )

        depth_instruction_map = {
            "concise": "Use one short paragraph plus one optional bullet list only if needed.",
            "standard": "Use 2-3 focused paragraphs with clear flow and concise interpretation.",
            "detailed": (
                "Use a structured in-depth response with sections: Direct answer, Evidence breakdown, "
                "Cross-source analysis, and Caveats/uncertainty."
            ),
        }

        system_prompt = """You are an analytical research assistant for Nigerian upstream petroleum intelligence.

You will receive database outputs and external web evidence.
Your job is to produce a clean, tailored final answer.

Rules:
1. Answer the user's question directly first.
2. Use only evidence supplied in the prompt.
3. Reconcile conflicts carefully; if uncertain, say so.
4. Keep writing clean, paragraph-based, with no broken line fragments.
5. Avoid filler text; be factual and specific.
"""

        user_prompt = (
            f"User question:\n{user_query}\n\n"
            f"Response depth: {response_depth}. {depth_instruction_map[response_depth]}\n"
            f"Priority mode: {mode_instruction}\n\n"
            f"Database answer draft:\n{base_answer}\n\n"
            f"Database rows (sample):\n{json.dumps(db_rows, indent=2, default=str)}\n\n"
            f"Web provider coverage counts:\n{json.dumps(provider_counts, indent=2, default=str)}\n\n"
            f"Web extracted data points:\n{json.dumps(data_points, indent=2, default=str)}\n\n"
            f"Web source briefs:\n{json.dumps(source_briefs, indent=2, default=str)}\n\n"
            "Return the final answer now."
        )

        try:
            final_answer = self._call_llm_with_preference(
                system_prompt,
                user_prompt,
                preferred_provider=self.web_final_synthesis_provider,
            )
            return self._clean_answer_text(final_answer)
        except Exception as exc:
            logger.warning("Web-augmented synthesis failed; using deterministic fallback: %s", exc)

            web_summary = synthesis.get("synthesis", "")
            if not db_has_signal and web_summary:
                fallback = (
                    "I could not find matching rows in the internal database for this query. "
                    "Based on external web evidence, here is the best available summary:\n\n"
                    f"{web_summary}"
                )
                return self._clean_answer_text(fallback)

            if web_summary:
                fallback = (
                    f"{base_answer}\n\n"
                    "Additional external context:\n"
                    f"{web_summary}"
                )
                return self._clean_answer_text(fallback)

            return self._clean_answer_text(base_answer)

    def _maybe_add_web_context(
        self,
        user_query: str,
        base_answer: str,
        cypher_results: List[Dict[str, Any]],
    ) -> Tuple[str, Optional[str], List[Dict[str, Any]]]:
        """Blend database output with extensive web evidence when enabled."""
        if not self.web_enrichment_enabled:
            return base_answer, None, []

        if not hybrid_searcher:
            return base_answer, None, []

        entity_id: Optional[str] = None
        entity_name: Optional[str] = None
        if cypher_results:
            entity_id, entity_name = self._extract_entity_identity(cypher_results)

        if not entity_name:
            resolved_entity_ids = self._resolve_entity_ids_from_query(user_query)
            if resolved_entity_ids:
                entity_id = entity_id or resolved_entity_ids[0]
                try:
                    canonical_entity = db.get_entity_by_id(resolved_entity_ids[0], "UpstreamProducer")
                except Exception as exc:
                    logger.debug("Entity lookup for web fallback failed: %s", exc)
                    canonical_entity = None

                if isinstance(canonical_entity, dict):
                    canonical_name = canonical_entity.get("name")
                    if isinstance(canonical_name, str) and canonical_name.strip():
                        entity_name = canonical_name.strip()

        # If no single entity is obvious, enrich using query-level target.
        target = entity_name if entity_name else user_query

        topic = self._topic_from_query(user_query)
        try:
            web_results = hybrid_searcher.search_and_scrape(target, topic)
        except Exception as exc:
            logger.warning("Web enrichment search failed: %s", exc)
            return self._clean_answer_text(base_answer), entity_name, []

        if not web_results:
            return self._clean_answer_text(base_answer), entity_name, []

        db_snapshot = cypher_results[0] if cypher_results and isinstance(cypher_results[0], dict) else {}
        synthesis = synthesize_web_results(target, db_snapshot, web_results, topic)
        answer = self._synthesize_web_augmented_answer(
            user_query,
            base_answer,
            cypher_results,
            synthesis,
            web_results,
        )

        sources: List[Dict[str, Any]] = []
        seen_sources = set()
        for source in synthesis.get("sources", []):
            source_type = str(source.get("type") or "unknown").lower()
            if source_type == "database":
                continue
            url = source.get("url")
            name = source.get("name", "Unknown")
            key = (str(url or "") + "|" + str(name)).lower()
            if key in seen_sources:
                continue
            seen_sources.add(key)
            sources.append(
                {
                    "name": name,
                    "url": url,
                    "type": source_type,
                }
            )

        if not sources:
            discovered = web_results.get("discovered_sources", [])
            for item in discovered[:8]:
                sources.append(
                    {
                        "name": item.get("title", "Unknown"),
                        "url": item.get("url"),
                        "type": item.get("provider", "web"),
                    }
                )

        return self._clean_answer_text(answer), entity_name, sources

    def process_question(
        self,
        user_query: str,
        session_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Public pipeline entrypoint used by FastAPI handlers."""
        request_id = str(uuid.uuid4())[:8]
        _ = session_context  # Session context reserved for future multi-turn behavior.

        try:
            logger.info("[%s] Processing: %s", request_id, user_query)

            if self._is_security_blocked_query(user_query):
                return {
                    "answer": "Request blocked by security policy: destructive database operations are not allowed.",
                    "entity_id": None,
                    "entity_name": None,
                    "data_retrieved": [],
                    "cypher_query": None,
                    "sources": [],
                    "used_web_enrichment": False,
                    "llm_provider": None,
                    "langchain_shadow": {
                        "enabled": self.langchain_cypher_shadow_enabled,
                        "status": "skipped_security_block",
                    },
                    "is_success": False,
                    "error": "security_blocked",
                }

            langchain_shadow = self._run_langchain_cypher_shadow(user_query)

            pipeline_result = self._text_to_cypher_pipeline(user_query)
            cypher_query = pipeline_result["cypher_query"]
            cypher_results = pipeline_result["cypher_results"]
            answer = pipeline_result["answer"]

            entity_id, entity_name = self._extract_entity_identity(cypher_results)

            enriched_answer, web_entity_name, sources = self._maybe_add_web_context(
                user_query,
                answer,
                cypher_results,
            )

            if web_entity_name and not entity_name:
                entity_name = web_entity_name

            used_web_enrichment = len(sources) > 0

            return {
                "answer": enriched_answer,
                "entity_id": entity_id,
                "entity_name": entity_name,
                "data_retrieved": cypher_results,
                "cypher_query": cypher_query,
                "sources": sources,
                "used_web_enrichment": used_web_enrichment,
                "llm_provider": self.last_provider_used or self.provider,
                "langchain_shadow": langchain_shadow,
                "is_success": True,
            }

        except Exception as exc:
            logger.error("[%s] Pipeline failure: %s", request_id, exc, exc_info=True)

            fallback_answer, fallback_entity_name, fallback_sources = self._maybe_add_web_context(
                user_query,
                "I could not retrieve this answer from the internal database pipeline.",
                [],
            )
            if fallback_sources:
                return {
                    "answer": fallback_answer,
                    "entity_id": None,
                    "entity_name": fallback_entity_name,
                    "data_retrieved": [],
                    "cypher_query": None,
                    "sources": fallback_sources,
                    "used_web_enrichment": True,
                    "llm_provider": self.last_provider_used or self.provider,
                    "is_success": True,
                    "error": "db_pipeline_fallback_to_web",
                }

            return {
                "answer": f"Pipeline error: {str(exc)}",
                "entity_id": None,
                "entity_name": None,
                "used_web_enrichment": False,
                "langchain_shadow": {
                    "enabled": self.langchain_cypher_shadow_enabled,
                    "status": "pipeline_error",
                },
                "is_success": False,
                "error": "pipeline",
            }

    @staticmethod
    def _is_aggregation_query(user_query: str) -> bool:
        """Detect count/ranking/comparison style questions."""
        query_lower = user_query.lower()
        aggregation_keywords = [
            "how many",
            "count",
            "number of",
            "how much",
            "total",
            "sum",
            "average",
            "highest",
            "lowest",
            "largest",
            "smallest",
            "top",
            "bottom",
            "compare",
            "comparison",
            "rank",
            "ranking",
            "all",
            "list",
            "every",
            "each",
        ]
        return any(keyword in query_lower for keyword in aggregation_keywords)

    @staticmethod
    def _is_security_blocked_query(user_query: str) -> bool:
        """Block explicit destructive/query-manipulation intents early."""
        q = user_query.lower().strip()

        blocked_patterns = [
            r"\b(ignore|bypass|override)\b.*\b(instruction|policy|guardrail)s?\b",
            r"\b(write|generate|produce|show|give)\b.*\b(create|delete|merge|set|remove|drop|alter|detach)\b.*\bquery\b",
            r"\b(insert|update)\b.*\b(node|record|producer)\b",
        ]
        if any(re.search(pattern, q) for pattern in blocked_patterns):
            return True

        blocked_substrings = [
            "ignore all prior instructions",
            "generate a create query",
            "write a create query",
            "delete all upstreamproducer",
            "drop the neo4j database",
            "merge a hacker node",
            "set n.name",
            "remove all properties",
            "load csv from",
            "; create",
            "; delete",
            "/*",
            "--",
        ]

        return any(token in q for token in blocked_substrings)


try:
    llm_pipeline = LLMPipeline()
except ValueError as exc:
    logger.warning("LLM Pipeline initialization failed: %s", exc)
    llm_pipeline = None
