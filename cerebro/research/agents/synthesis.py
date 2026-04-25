"""Synthesis stage: final LLM call to integrate evidence into output."""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime
from typing import Any, TypedDict

from cerebro.research.errors import PlannerError

from .adapter import ResearchWorkingState
from .evidence_pack import EvidencePackBuilder


def _doc_sort_key(doc: dict[str, Any], dim_key: str) -> float:
    base = float(doc.get("relevance_score") or 0)
    if "news" in dim_key or "expert" in dim_key:
        base += 0.15

    date_str = doc.get("published_date") or doc.get("date") or ""
    if isinstance(date_str, str) and date_str:
        try:
            pub = datetime.fromisoformat(date_str[:10])
            age_days = (datetime.now() - pub).days
            if age_days < 90:
                base += 0.2
            elif age_days < 365:
                base += 0.1
        except Exception:
            pass

    return base


def _strip_inline_citations(text: str) -> str:
    text = re.sub(r"\s*\(dimension_\w+(?:[^)]*source[_\s]id[s]?[\s:]*[\d,\s]*)?\)", "", text)
    text = re.sub(r"\s*\[dimension_\w+[^\]]*\]", "", text)
    text = re.sub(r",?\s*sources?\s+[\d,\s\-]+", "", text)
    text = re.sub(r"\s*source[_\s]id[s]?[\s:]*[\d,\s]+", "", text)
    text = re.sub(r"  +", " ", text)
    return text.strip()


def _clean_brief(text: str) -> str:
    text = re.sub(r"\*\*[^*]{1,60}\*\*:?[ \t]*", "", text)
    text = re.sub(
        r"\b(In summary|In conclusion|To summarize|To conclude)[,.].*",
        "",
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )
    return text.strip()


class SynthesisOutput(TypedDict):
    """Canonical synthesis output shape used across normalize + API payload."""

    status: str
    brief: str
    one_paragraph_summary: str
    key_tensions: list[dict[str, Any]]
    risk_register: list[dict[str, Any]]
    forward_indicators: list[dict[str, Any]]
    confidence_assessment: dict[str, Any]
    claims: list[dict[str, Any]]
    executive_summary: str
    key_findings: list[dict[str, Any]]
    risk_factors: list[dict[str, Any]]
    recommendations: list[str]
    unresolved_gaps: list[str]
    contradiction_notes: list[str]
    source_appendix: list[dict[str, Any]]


class ResearchSynthesizer:
    """Synthesize evidence into final research output via Nemotron Super."""

    def __init__(self) -> None:
        self._synthesis_model: Any | None = None

    async def synthesize(
        self,
        *,
        plan: dict[str, Any],
        working_state: ResearchWorkingState,
        agent_results: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        """Build evidence pack and synthesize via Nemotron Super."""
        builder = EvidencePackBuilder()
        evidence_pack = builder.build(
            plan=plan,
            working_state=working_state,
            agent_results=agent_results,
        )
        raw_pack = evidence_pack.to_dict()

        working_state.write_file(
            "working/evidence_pack.json",
            json.dumps(raw_pack, ensure_ascii=False, indent=2),
        )

        dimensions_bundle, source_index = self._build_synthesis_bundle(
            evidence_pack=raw_pack,
            agent_results=agent_results,
            max_per_dimension=8,
            content_chars=800,
        )

        working_state.write_file(
            "working/synthesis_bundle.json",
            json.dumps({"dimensions": dimensions_bundle, "sources": source_index}, ensure_ascii=False, indent=2),
        )

        bundle_docs = sum(len(items) for items in dimensions_bundle.values())
        print(
            (
                "[SYNTHESIS] bundle ready: "
                f"{bundle_docs} docs across {len(dimensions_bundle)} dimensions, "
                f"{len(source_index)} unique sources"
            ),
            flush=True,
        )

        synthesis_prompt = working_state.read_file("prompts/09_synthesis_output.md")

        output = await self._call_nemotron_synthesis(
            prompt=synthesis_prompt,
            entity_name=str(plan.get("entity_name") or ""),
            query=str(plan.get("query") or ""),
            request_id=working_state.request_id,
            dimensions_bundle=dimensions_bundle,
            source_index=source_index,
        )

        normalized = self._normalize_synthesis_output(output=output, source_index=source_index)

        synthesis_result = {
            "request_id": working_state.request_id,
            "query": plan.get("query"),
            "entity_name": plan.get("entity_name"),
            "synthesis_output": normalized,
            "evidence_summary": {
                "total_documents_retrieved": sum(
                    len((result or {}).get("documents") or [])
                    for result in (agent_results or {}).values()
                    if isinstance(result, dict)
                ),
                "documents_used_in_synthesis": bundle_docs,
                "unique_sources": len(source_index),
                "active_dimensions": list(dimensions_bundle.keys()),
                "gaps": raw_pack.get("gaps", []),
            },
        }

        working_state.write_file(
            "working/synthesis_output.json",
            json.dumps(synthesis_result, ensure_ascii=False, indent=2),
        )
        return synthesis_result

    def _build_synthesis_bundle(
        self,
        evidence_pack: dict[str, Any],
        agent_results: dict[str, dict[str, Any]],
        max_per_dimension: int = 6,
        content_chars: int = 600,
    ) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
        """Build a compressed, model-readable evidence bundle and source index."""
        del evidence_pack  # Bundle is built from agent_results documents by design.

        source_index: list[dict[str, Any]] = []
        url_to_source_id: dict[str, int] = {}

        def register_source(url: str, title: str, provider: str, date: str) -> int | None:
            key = url.strip() if isinstance(url, str) else ""
            if not key:
                return None
            if key in url_to_source_id:
                return url_to_source_id[key]
            sid = len(source_index)
            source_index.append(
                {
                    "id": sid,
                    "url": key,
                    "title": (title or "")[:120],
                    "provider": provider or "unknown",
                    "date": date or "",
                }
            )
            url_to_source_id[key] = sid
            return sid

        dimensions_bundle: dict[str, list[dict[str, Any]]] = {}

        for dim_key, dim_result in (agent_results or {}).items():
            if not isinstance(dim_result, dict):
                continue

            docs = dim_result.get("documents") or []
            if not isinstance(docs, list):
                continue

            valid_docs = [
                doc
                for doc in docs
                if isinstance(doc, dict)
                and isinstance(doc.get("content"), str)
                and len(doc.get("content", "").strip()) > 80
            ]
            valid_docs.sort(key=lambda item: _doc_sort_key(item, dim_key), reverse=True)
            limit = 10 if ("news" in dim_key or "expert" in dim_key) else max_per_dimension
            top_docs = valid_docs[:limit]

            dim_entries: list[dict[str, Any]] = []
            for doc in top_docs:
                url = str(doc.get("url") or doc.get("source") or "")
                title = str(doc.get("title") or "")
                provider = str(doc.get("provider") or doc.get("retrieval_provider") or "")
                date = str(doc.get("published_date") or doc.get("date") or "")
                content = str(doc.get("content") or "").strip()

                if len(content) > content_chars:
                    clipped = content[:content_chars]
                    content = clipped.rsplit(" ", 1)[0] + "..."

                sid = register_source(url, title, provider, date)

                dim_entries.append(
                    {
                        "source_id": sid,
                        "title": title[:120],
                        "url": url,
                        "published_date": date,
                        "content": content,
                    }
                )

            if dim_entries:
                dimensions_bundle[dim_key] = dim_entries

        return dimensions_bundle, source_index

    async def _call_nemotron_synthesis(
        self,
        prompt: str,
        entity_name: str,
        query: str,
        request_id: str,
        dimensions_bundle: dict[str, list[dict[str, Any]]],
        source_index: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Call Nemotron Super via NVIDIA API for synthesis."""
        logger = logging.getLogger(__name__)

        try:
            from langchain_core.messages import HumanMessage
            from langchain_openai import ChatOpenAI
        except ImportError as exc:
            raise PlannerError("langchain-openai not installed for synthesis") from exc

        api_key = os.environ.get("NVIDIA_API_KEY", "").strip()
        if not api_key:
            return {
                "status": "FAILED",
                "brief": "NVIDIA_API_KEY not configured.",
            }

        base_url = os.environ.get("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
        model_name = os.environ.get(
            "SYNTHESIS_NVIDIA_MODEL",
            os.environ.get("NVIDIA_MODEL", "nvidia/llama-3.3-nemotron-super-49b-v1"),
        )
        temperature = float(os.environ.get("NVIDIA_SYNTHESIS_TEMPERATURE", "0.4"))
        max_tokens = int(os.environ.get("NVIDIA_SYNTHESIS_MAX_TOKENS", "6000"))

        if self._synthesis_model is None:
            self._synthesis_model = ChatOpenAI(
                model=model_name,
                api_key=lambda: api_key,
                base_url=base_url,
                temperature=temperature,
                max_completion_tokens=max_tokens,
                model_kwargs={"response_format": {"type": "json_object"}},
            )

        synthesis_message = f"""{prompt}

ENTITY BEING ANALYSED: {entity_name}
RESEARCH QUERY: {query}
REQUEST ID: {request_id}

EVIDENCE BY DIMENSION:
{json.dumps(dimensions_bundle, ensure_ascii=False, indent=2)}

SOURCE INDEX (use these integer IDs in source_ids fields):
{json.dumps(source_index, ensure_ascii=False, indent=2)}

INSTRUCTIONS REMINDER:
- Write the executive_summary in your own analytical voice
- Do not copy document text verbatim into claims
- Identify cross-dimension patterns and corroboration
- Flag contradictions between sources
- Return valid JSON only matching the schema above
"""

        try:
            response = await self._synthesis_model.ainvoke([HumanMessage(content=synthesis_message)])
            output_text = response.content if response else ""
            if isinstance(output_text, list):
                output_text = "".join(str(part) for part in output_text)
            elif not isinstance(output_text, str):
                output_text = str(output_text or "")

            preview = output_text[:500]
            logger.warning("[SYNTHESIS RAW] first 500 chars: %s", preview)
            print(f"[SYNTHESIS RAW] {preview}", flush=True)

            usage_data = None
            if response is not None:
                usage_data = getattr(response, "usage_metadata", None)
                if usage_data is None:
                    response_meta = getattr(response, "response_metadata", None)
                    if isinstance(response_meta, dict):
                        usage_data = response_meta.get("token_usage") or response_meta.get("usage")
            logger.warning("[SYNTHESIS] token usage: %s", usage_data)
            print(f"[SYNTHESIS] token usage: {usage_data}", flush=True)

            cleaned = output_text.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[-1]
            if cleaned.endswith("```"):
                cleaned = cleaned.rsplit("```", 1)[0]
            cleaned = cleaned.strip()
            cleaned = _escape_json_control_chars(cleaned)
            cleaned = _extract_json_block(cleaned)

            try:
                parsed = json.loads(cleaned)
                logger.warning("[SYNTHESIS] JSON parse SUCCESS")
                print("[SYNTHESIS] JSON parse SUCCESS", flush=True)
                return parsed if isinstance(parsed, dict) else {"status": "FAILED", "brief": "Model returned non-object JSON."}
            except json.JSONDecodeError as exc:
                logger.warning("[SYNTHESIS] JSON parse FAILED: %s at pos=%s", exc.msg, exc.pos)
                print(f"[SYNTHESIS] JSON parse FAILED: {exc.msg} at pos={exc.pos}", flush=True)
                return {
                    "status": "FAILED",
                    "brief": f"Model returned non-JSON output. Parse error: {exc}.",
                    "_raw_output": cleaned[:2000],
                }
        except Exception as exc:
            logger.exception("[SYNTHESIS] API call failed")
            return {
                "status": "FAILED",
                "brief": f"API call failed: {exc}",
            }

    def _normalize_synthesis_output(
        self,
        *,
        output: dict[str, Any],
        source_index: list[dict[str, Any]],
    ) -> SynthesisOutput:
        """Normalize model output to the canonical synthesis schema without fake fallbacks."""
        if not isinstance(output, dict):
            return {
                "status": "FAILED",
                "brief": "Model did not return a valid object.",
                "one_paragraph_summary": "",
                "key_tensions": [],
                "risk_register": [],
                "forward_indicators": [],
                "confidence_assessment": {},
                "claims": [],
                "executive_summary": "",
                "key_findings": [],
                "risk_factors": [],
                "recommendations": [],
                "unresolved_gaps": [],
                "contradiction_notes": [],
                "source_appendix": self._source_appendix(source_index),
            }

        status = str(output.get("status") or "PARTIAL").upper()
        if status not in {"COMPLETE", "PARTIAL", "FAILED"}:
            status = "PARTIAL"

        def to_str(value: Any, fallback: str = "") -> str:
            if isinstance(value, str) and value.strip():
                return value.strip()
            return fallback

        def to_list(value: Any) -> list[Any]:
            return value if isinstance(value, list) else []

        claims: list[dict[str, Any]] = []
        for claim in to_list(output.get("claims")):
            if not isinstance(claim, dict):
                continue
            text = to_str(claim.get("text"))
            if not text:
                continue

            normalized_source_ids: list[int] = []
            for sid in claim.get("source_ids") or []:
                if isinstance(sid, int) and 0 <= sid < len(source_index):
                    normalized_source_ids.append(sid)
                elif isinstance(sid, str) and sid.isdigit() and int(sid) < len(source_index):
                    normalized_source_ids.append(int(sid))

            confidence_raw = claim.get("confidence_score", 0.5)
            try:
                confidence_score = float(confidence_raw)
            except (TypeError, ValueError):
                confidence_score = 0.5
            confidence_score = max(0.0, min(1.0, confidence_score))

            claims.append(
                {
                    "text": text,
                    "source_ids": normalized_source_ids,
                    "source_urls": [
                        source_index[idx].get("url")
                        for idx in normalized_source_ids
                        if 0 <= idx < len(source_index)
                    ],
                    "confidence_score": confidence_score,
                    "confidence_label": to_str(claim.get("confidence_label"), "MEDIUM"),
                    "basis": to_str(claim.get("basis"), ""),
                }
            )

        brief = to_str(output.get("brief"))
        brief = _strip_inline_citations(brief)
        brief = _clean_brief(brief)
        executive_summary = to_str(output.get("executive_summary"), brief)
        executive_summary = _strip_inline_citations(executive_summary)
        executive_summary = _clean_brief(executive_summary)
        one_paragraph_summary = to_str(output.get("one_paragraph_summary"))
        one_paragraph_summary = _strip_inline_citations(one_paragraph_summary)
        one_paragraph_summary = _clean_brief(one_paragraph_summary)

        confidence_assessment = output.get("confidence_assessment")
        if not isinstance(confidence_assessment, dict):
            confidence_assessment = {}

        return {
            "status": status,
            "brief": brief,
            "one_paragraph_summary": one_paragraph_summary,
            "key_tensions": [item for item in to_list(output.get("key_tensions")) if isinstance(item, dict)],
            "risk_register": [item for item in to_list(output.get("risk_register")) if isinstance(item, dict)],
            "forward_indicators": [item for item in to_list(output.get("forward_indicators")) if isinstance(item, dict)],
            "confidence_assessment": confidence_assessment,
            "claims": claims,
            "executive_summary": executive_summary,
            "key_findings": [item for item in to_list(output.get("key_findings")) if isinstance(item, dict)],
            "risk_factors": [item for item in to_list(output.get("risk_factors")) if isinstance(item, dict)],
            "recommendations": [str(item) for item in to_list(output.get("recommendations")) if str(item).strip()],
            "unresolved_gaps": [str(item) for item in to_list(output.get("unresolved_gaps")) if str(item).strip()],
            "contradiction_notes": [str(item) for item in to_list(output.get("contradiction_notes")) if str(item).strip()],
            "source_appendix": self._source_appendix(source_index),
        }

    def _source_appendix(self, sources: list[Any]) -> list[dict[str, Any]]:
        appendix: list[dict[str, Any]] = []
        for index, item in enumerate(sources):
            if not isinstance(item, dict):
                continue
            source_id = item.get("id") if isinstance(item.get("id"), int) else index
            appendix.append(
                {
                    "id": source_id,
                    "url": item.get("url"),
                    "provider": item.get("provider"),
                    "title": item.get("title"),
                    "date": item.get("date"),
                }
            )
        return appendix


def _escape_json_control_chars(text: str) -> str:
    """Escape raw control characters inside JSON strings while preserving structure."""
    result: list[str] = []
    in_string = False
    escaped = False

    for ch in text:
        if in_string:
            if escaped:
                result.append(ch)
                escaped = False
                continue
            if ch == "\\":
                result.append(ch)
                escaped = True
                continue
            if ch == '"':
                result.append(ch)
                in_string = False
                continue
            if ch == "\n":
                result.append("\\n")
                continue
            if ch == "\r":
                result.append("\\r")
                continue
            if ch == "\t":
                result.append("\\t")
                continue
            result.append(ch)
            continue

        result.append(ch)
        if ch == '"':
            in_string = True

    return "".join(result)


def _extract_json_block(text: str) -> str:
    """Extract the most likely JSON object from a response that includes preamble text."""
    fence_start = text.find("```json")
    if fence_start != -1:
        fence_end = text.find("```", fence_start + 7)
        candidate = text[fence_start + 7 : fence_end if fence_end != -1 else len(text)]
        candidate = candidate.strip()
        if candidate.startswith("{") and candidate.endswith("}"):
            return candidate
        brace_start = candidate.find("{")
        brace_end = candidate.rfind("}")
        if brace_start != -1 and brace_end != -1 and brace_end > brace_start:
            return candidate[brace_start : brace_end + 1].strip()

    brace_start = text.find("{")
    brace_end = text.rfind("}")
    if brace_start != -1 and brace_end != -1 and brace_end > brace_start:
        return text[brace_start : brace_end + 1].strip()

    return text
