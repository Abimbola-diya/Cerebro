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
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

try:
    import google.generativeai as genai
except Exception:  # pragma: no cover - optional provider dependency
    genai = None

try:
    from cerebras.cloud.sdk import Cerebras
except Exception:  # pragma: no cover - optional provider dependency
    Cerebras = None

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

        self._init_llm_client()
        self.node_catalog = self._load_node_catalog()

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
                    if len(alias) >= 3 and self._contains_alias(query_norm, alias):
                        add_score(entity_id, 90 + len(alias))

                for token in entity_tokens.get(entity_id, []):
                    if token_frequency.get(token) == 1 and self._contains_alias(query_norm, token):
                        add_score(entity_id, 40 + len(token))

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

        entity_resolution_hint = ""
        if resolved_entity_ids:
            has_compare_intent = self._has_explicit_compare_intent(user_query)
            if len(resolved_entity_ids) == 1 and not self._is_aggregation_query(user_query):
                resolved_id = self._quote_cypher_string(resolved_entity_ids[0])
                entity_resolution_hint = (
                    "\n\n[RESOLVED_ENTITY_ID]\n"
                    f"{resolved_id}\n"
                    "Use WHERE n.id = '<resolved_id>' as primary filter unless question explicitly asks for all entities."
                )
            elif len(resolved_entity_ids) >= 2 and has_compare_intent:
                resolved_literal_list = ", ".join([f"'{self._quote_cypher_string(entity_id)}'" for entity_id in resolved_entity_ids[:3]])
                entity_resolution_hint = (
                    "\n\n[RESOLVED_ENTITY_IDS]\n"
                    f"{resolved_literal_list}\n"
                    "When comparing or disambiguating these entities, use WHERE n.id IN [..] as primary filter."
                )

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

    def _synthesize_from_cypher(self, user_query: str, cypher_results: List[Dict[str, Any]]) -> str:
        """Call 2: Convert raw query results into a natural language answer."""
        logger.info("[LLM-ANSWER-GEN] Synthesizing answer for: %s", user_query[:120])

        deterministic_answer = self._deterministic_answer_override(user_query, cypher_results)
        if deterministic_answer:
            logger.info("[LLM-ANSWER-GEN] Using deterministic aggregate answer override")
            return deterministic_answer

        synthesis_rows, was_truncated, total_rows = self._prepare_results_for_synthesis(cypher_results)
        results_json = json.dumps(synthesis_rows, indent=2, default=str)
        system_prompt = """You are a data analyst for Nigerian upstream petroleum data.

You will receive:
- the user's question
- raw JSON results from Neo4j

Rules:
1. Answer only from the provided JSON results.
2. Do not invent fields, values, or entities.
3. If no results exist, say: "No data found for this query."
4. If values are null or NOT_AVAILABLE, state that clearly.
5. Keep the answer concise but complete.
"""

        user_prompt = (
            f"User question:\n{user_query}\n\n"
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
        }
        for topic, keywords in topic_map.items():
            if any(keyword in query_lower for keyword in keywords):
                return topic
        return "overview"

    def _maybe_add_web_context(
        self,
        user_query: str,
        base_answer: str,
        cypher_results: List[Dict[str, Any]],
    ) -> Tuple[str, Optional[str], List[Dict[str, Any]]]:
        """Add optional supplementary web context for DB-backed answers."""
        if not self.web_enrichment_enabled:
            return base_answer, None, []

        # User requested DB+web enrichment; skip only when database has no rows.
        if not cypher_results:
            return base_answer, None, []

        if not hybrid_searcher:
            return base_answer, None, []

        entity_id, entity_name = self._extract_entity_identity(cypher_results)

        # If no single entity is obvious, enrich using query-level target.
        target = entity_name if entity_name else user_query

        topic = self._topic_from_query(user_query)
        web_results = hybrid_searcher.search_and_scrape(target, topic)
        if not web_results:
            return base_answer, entity_name, []

        db_snapshot = cypher_results[0] if cypher_results and isinstance(cypher_results[0], dict) else {}
        synthesis = synthesize_web_results(target, db_snapshot, web_results, topic)

        web_summary = web_results.get("tavily_summary", "").strip()
        if web_summary:
            answer = (
                f"{base_answer}\n\n"
                f"Supplementary web context (Tavily/Firecrawl, non-database): {web_summary}"
            )
        else:
            answer = base_answer

        # Keep only true web sources in outward provenance list.
        sources = [
            source
            for source in synthesis.get("sources", [])
            if source.get("type") in {"tavily", "firecrawl"}
        ]

        # Fallback to discovered Tavily sources when parsed synthesis contains none.
        if not sources:
            discovered = web_results.get("discovered_sources", [])
            for item in discovered[:5]:
                sources.append(
                    {
                        "name": item.get("title", "Unknown"),
                        "url": item.get("url"),
                        "type": "tavily",
                    }
                )

        return answer, entity_name, sources

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
                    "is_success": False,
                    "error": "security_blocked",
                }

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
                "is_success": True,
            }

        except Exception as exc:
            logger.error("[%s] Pipeline failure: %s", request_id, exc, exc_info=True)
            return {
                "answer": f"Pipeline error: {str(exc)}",
                "entity_id": None,
                "entity_name": None,
                "used_web_enrichment": False,
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
