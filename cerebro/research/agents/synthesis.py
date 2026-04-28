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


def _normalize_inline_citations(text: str, source_count: int) -> str:
    """Preserve valid [N] citations, strip legacy dimension-style references."""
    # Strip legacy dimension-style citations that the old prompt produced
    text = re.sub(r"\s*\(dimension_\w+(?:[^)]*source[_\s]id[s]?[\s:]*[\d,\s]*)?\)", "", text)
    text = re.sub(r"\s*\[dimension_\w+[^\]]*\]", "", text)
    text = re.sub(r"\s*source[_\s]id[s]?[\s:]*[\d,\s]+", "", text)

    # Validate [N] citations: keep valid ones, strip invalid ones
    def _validate_citation(match: re.Match[str]) -> str:
        try:
            n = int(match.group(1))
            if 0 <= n < source_count:
                return f"[{n}]"
        except (ValueError, TypeError):
            pass
        return ""

    text = re.sub(r"\[(\d+)\]", _validate_citation, text)
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
    executive_summary: str
    key_findings: list[dict[str, Any]]
    key_data_points: list[dict[str, Any]]
    timeline: list[dict[str, Any]]
    key_tensions: list[dict[str, Any]]
    risk_register: list[dict[str, Any]]
    forward_indicators: list[dict[str, Any]]
    confidence_assessment: dict[str, Any]
    claims: list[dict[str, Any]]
    contradiction_notes: list[dict[str, Any]]
    suggested_follow_ups: list[str]
    related_entities: list[dict[str, Any]]
    methodology_note: str
    rendered_report: str
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
        max_per_dimension: int = 8,
        content_chars: int = 800,
    ) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
        """Build a compressed, model-readable evidence bundle and source index.

        High-credibility sources (rank 4-5) get more content space to improve
        the synthesis model's ability to cite specific facts.
        """
        del evidence_pack  # Bundle is built from agent_results documents by design.

        source_index: list[dict[str, Any]] = []
        url_to_source_id: dict[str, int] = {}

        # Build a lookup from source_id string -> SourceRecord for credibility data
        from cerebro.research.sources.registry import registry as _source_registry
        _source_by_id = {rec.id: rec for rec in _source_registry.all()}

        def register_source(
            url: str, title: str, provider: str, date: str,
            source_id_str: str = "", dimension: str = "",
        ) -> int | None:
            key = url.strip() if isinstance(url, str) else ""
            if not key:
                return None
            if key in url_to_source_id:
                return url_to_source_id[key]
            sid = len(source_index)

            # Look up credibility from source bank
            source_rec = _source_by_id.get(source_id_str)
            credibility_rank = source_rec.credibility_rank if source_rec else 2
            source_tier = source_rec.tier.value if source_rec else "unknown"

            source_index.append(
                {
                    "id": sid,
                    "url": key,
                    "title": (title or "")[:120],
                    "provider": provider or "unknown",
                    "date": date or "",
                    "credibility_rank": credibility_rank,
                    "source_tier": source_tier,
                    "dimension": dimension,
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
                doc_source_id = str(doc.get("source_id") or "")

                # High-credibility sources get more content space
                source_rec = _source_by_id.get(doc_source_id)
                doc_rank = source_rec.credibility_rank if source_rec else 2
                effective_chars = 1500 if doc_rank >= 4 else content_chars

                if len(content) > effective_chars:
                    clipped = content[:effective_chars]
                    content = clipped.rsplit(" ", 1)[0] + "..."

                sid = register_source(
                    url, title, provider, date,
                    source_id_str=doc_source_id,
                    dimension=dim_key,
                )

                dim_entries.append(
                    {
                        "source_id": sid,
                        "title": title[:120],
                        "url": url,
                        "published_date": date,
                        "credibility_rank": doc_rank,
                        "dimension": dim_key,
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
        max_tokens = int(os.environ.get("NVIDIA_SYNTHESIS_MAX_TOKENS", "10000"))

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

SOURCE INDEX (use these integer IDs for inline citations [N] and in source_ids arrays):
{json.dumps(source_index, ensure_ascii=False, indent=2)}

CRITICAL CITATION INSTRUCTIONS:
- In brief, executive_summary, and one_paragraph_summary: cite every factual claim with [N] where N is the source_id from the SOURCE INDEX above
- In claims, key_findings, key_data_points, timeline, risk_register, forward_indicators, key_tensions, contradiction_notes: include source_ids arrays
- If a source has credibility_rank 4-5, it should be weighted more heavily
- Write the executive_summary in your own analytical voice
- Do not copy document text verbatim
- Identify cross-dimension patterns and corroboration
- Flag contradictions between sources in contradiction_notes
- Generate 3-5 suggested_follow_ups based on gaps and emerging themes
- Identify 3-8 related_entities mentioned frequently across the evidence
- Write a methodology_note summarising the research scope
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
        """Normalize model output to the canonical synthesis schema.

        Preserves valid inline citations [N], resolves source references in claims,
        and generates a pre-rendered Markdown report.
        """
        source_count = len(source_index)

        if not isinstance(output, dict):
            return self._empty_synthesis_output(source_index)

        status = str(output.get("status") or "PARTIAL").upper()
        if status not in {"COMPLETE", "PARTIAL", "FAILED"}:
            status = "PARTIAL"

        def to_str(value: Any, fallback: str = "") -> str:
            if isinstance(value, str) and value.strip():
                return value.strip()
            return fallback

        def to_list(value: Any) -> list[Any]:
            return value if isinstance(value, list) else []

        def normalize_source_ids(raw_ids: Any) -> list[int]:
            result: list[int] = []
            for sid in (raw_ids or []):
                if isinstance(sid, int) and 0 <= sid < source_count:
                    result.append(sid)
                elif isinstance(sid, str) and sid.isdigit() and int(sid) < source_count:
                    result.append(int(sid))
            return result

        def resolve_source_urls(sids: list[int]) -> list[str]:
            return [
                source_index[idx].get("url", "")
                for idx in sids
                if 0 <= idx < source_count
            ]

        def resolve_sources(sids: list[int]) -> list[dict[str, Any]]:
            return [
                {
                    "id": idx,
                    "url": source_index[idx].get("url", ""),
                    "title": source_index[idx].get("title", ""),
                    "provider": source_index[idx].get("provider", ""),
                    "date": source_index[idx].get("date", ""),
                }
                for idx in sids
                if 0 <= idx < source_count
            ]

        # --- Claims ---
        claims: list[dict[str, Any]] = []
        for claim in to_list(output.get("claims")):
            if not isinstance(claim, dict):
                continue
            text = to_str(claim.get("text"))
            if not text:
                continue

            normalized_sids = normalize_source_ids(claim.get("source_ids"))

            confidence_raw = claim.get("confidence_score", 0.5)
            try:
                confidence_score = float(confidence_raw)
            except (TypeError, ValueError):
                confidence_score = 0.5
            confidence_score = max(0.0, min(1.0, confidence_score))

            claims.append(
                {
                    "text": text,
                    "source_ids": normalized_sids,
                    "source_urls": resolve_source_urls(normalized_sids),
                    "sources": resolve_sources(normalized_sids),
                    "confidence_score": confidence_score,
                    "confidence_label": to_str(claim.get("confidence_label"), "MEDIUM"),
                    "basis": to_str(claim.get("basis"), ""),
                }
            )

        # --- Text fields: preserve valid inline citations ---
        brief = to_str(output.get("brief"))
        brief = _normalize_inline_citations(brief, source_count)
        brief = _clean_brief(brief)

        executive_summary = to_str(output.get("executive_summary"), brief)
        executive_summary = _normalize_inline_citations(executive_summary, source_count)
        executive_summary = _clean_brief(executive_summary)

        one_paragraph_summary = to_str(output.get("one_paragraph_summary"))
        one_paragraph_summary = _normalize_inline_citations(one_paragraph_summary, source_count)
        one_paragraph_summary = _clean_brief(one_paragraph_summary)

        # --- Structured sections with source_ids normalization ---
        key_findings = []
        for item in to_list(output.get("key_findings")):
            if not isinstance(item, dict):
                continue
            item["source_ids"] = normalize_source_ids(item.get("source_ids"))
            key_findings.append(item)

        key_data_points = []
        for item in to_list(output.get("key_data_points")):
            if not isinstance(item, dict):
                continue
            item["source_ids"] = normalize_source_ids(item.get("source_ids"))
            key_data_points.append(item)

        timeline = []
        for item in to_list(output.get("timeline")):
            if not isinstance(item, dict):
                continue
            item["source_ids"] = normalize_source_ids(item.get("source_ids"))
            timeline.append(item)

        key_tensions = []
        for item in to_list(output.get("key_tensions")):
            if not isinstance(item, dict):
                continue
            item["source_ids"] = normalize_source_ids(item.get("source_ids"))
            key_tensions.append(item)

        risk_register = []
        for item in to_list(output.get("risk_register")):
            if not isinstance(item, dict):
                continue
            item["source_ids"] = normalize_source_ids(item.get("source_ids"))
            risk_register.append(item)

        forward_indicators = []
        for item in to_list(output.get("forward_indicators")):
            if not isinstance(item, dict):
                continue
            item["source_ids"] = normalize_source_ids(item.get("source_ids"))
            forward_indicators.append(item)

        contradiction_notes = []
        for item in to_list(output.get("contradiction_notes")):
            if isinstance(item, dict):
                item["source_ids"] = normalize_source_ids(item.get("source_ids"))
                contradiction_notes.append(item)
            elif isinstance(item, str) and item.strip():
                contradiction_notes.append({"topic": item, "source_ids": []})

        confidence_assessment = output.get("confidence_assessment")
        if not isinstance(confidence_assessment, dict):
            confidence_assessment = {}

        suggested_follow_ups = [
            str(item) for item in to_list(output.get("suggested_follow_ups"))
            if isinstance(item, str) and item.strip()
        ]

        related_entities = [
            item for item in to_list(output.get("related_entities"))
            if isinstance(item, dict)
        ]

        methodology_note = to_str(output.get("methodology_note"), "")

        source_appendix = self._source_appendix(source_index)

        # --- Build rendered Markdown report ---
        rendered_report = _render_markdown_report(
            executive_summary=executive_summary,
            brief=brief,
            key_findings=key_findings,
            key_data_points=key_data_points,
            timeline=timeline,
            risk_register=risk_register,
            forward_indicators=forward_indicators,
            key_tensions=key_tensions,
            contradiction_notes=contradiction_notes,
            confidence_assessment=confidence_assessment,
            methodology_note=methodology_note,
            suggested_follow_ups=suggested_follow_ups,
            source_appendix=source_appendix,
        )

        return {
            "status": status,
            "brief": brief,
            "one_paragraph_summary": one_paragraph_summary,
            "executive_summary": executive_summary,
            "key_findings": key_findings,
            "key_data_points": key_data_points,
            "timeline": timeline,
            "key_tensions": key_tensions,
            "risk_register": risk_register,
            "forward_indicators": forward_indicators,
            "confidence_assessment": confidence_assessment,
            "claims": claims,
            "contradiction_notes": contradiction_notes,
            "suggested_follow_ups": suggested_follow_ups,
            "related_entities": related_entities,
            "methodology_note": methodology_note,
            "rendered_report": rendered_report,
            "source_appendix": source_appendix,
        }

    def _empty_synthesis_output(self, source_index: list[dict[str, Any]]) -> SynthesisOutput:
        """Return a valid but empty synthesis output for failure cases."""
        return {
            "status": "FAILED",
            "brief": "Model did not return a valid object.",
            "one_paragraph_summary": "",
            "executive_summary": "",
            "key_findings": [],
            "key_data_points": [],
            "timeline": [],
            "key_tensions": [],
            "risk_register": [],
            "forward_indicators": [],
            "confidence_assessment": {},
            "claims": [],
            "contradiction_notes": [],
            "suggested_follow_ups": [],
            "related_entities": [],
            "methodology_note": "",
            "rendered_report": "",
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
                    "credibility_tier": item.get("source_tier", "unknown"),
                    "credibility_rank": item.get("credibility_rank", 0),
                }
            )
        return appendix


def _render_markdown_report(
    *,
    executive_summary: str,
    brief: str,
    key_findings: list[dict[str, Any]],
    key_data_points: list[dict[str, Any]],
    timeline: list[dict[str, Any]],
    risk_register: list[dict[str, Any]],
    forward_indicators: list[dict[str, Any]],
    key_tensions: list[dict[str, Any]],
    contradiction_notes: list[dict[str, Any]],
    confidence_assessment: dict[str, Any],
    methodology_note: str,
    suggested_follow_ups: list[str],
    source_appendix: list[dict[str, Any]],
) -> str:
    """Render a pre-formatted Markdown research report from structured synthesis data."""
    sections: list[str] = []

    # Executive Summary
    if executive_summary:
        sections.append(f"## Executive Summary\n\n{executive_summary}")

    # Detailed Analysis
    if brief:
        sections.append(f"## Detailed Analysis\n\n{brief}")

    # Key Findings
    if key_findings:
        lines = ["## Key Findings\n"]
        for i, finding in enumerate(key_findings, 1):
            text = finding.get("finding", "")
            confidence = finding.get("confidence", "")
            sids = finding.get("source_ids", [])
            refs = " ".join(f"[{s}]" for s in sids) if sids else ""
            significance = finding.get("significance", "")
            line = f"{i}. **{confidence}** {text}"
            if refs:
                line += f" {refs}"
            if significance:
                line += f"\n   *{significance}*"
            lines.append(line)
        sections.append("\n".join(lines))

    # Key Data Points
    if key_data_points:
        lines = ["## Key Data Points\n"]
        lines.append("| Metric | Value | Period | Source |")
        lines.append("|--------|-------|--------|--------|")
        for dp in key_data_points:
            metric = dp.get("metric", "")
            value = dp.get("value", "")
            period = dp.get("period", "")
            sids = dp.get("source_ids", [])
            refs = ", ".join(f"[{s}]" for s in sids) if sids else ""
            lines.append(f"| {metric} | {value} | {period} | {refs} |")
        sections.append("\n".join(lines))

    # Timeline
    if timeline:
        lines = ["## Timeline\n"]
        for event in timeline:
            date = event.get("date", "")
            text = event.get("event", "")
            sids = event.get("source_ids", [])
            refs = " ".join(f"[{s}]" for s in sids) if sids else ""
            significance = event.get("significance", "")
            line = f"- **{date}**: {text}"
            if refs:
                line += f" {refs}"
            if significance:
                line += f"\n  *{significance}*"
            lines.append(line)
        sections.append("\n".join(lines))

    # Risk Assessment
    if risk_register:
        lines = ["## Risk Assessment\n"]
        lines.append("| Risk | Severity | Likelihood | Evidence Strength |")
        lines.append("|------|----------|------------|-------------------|")
        for risk in risk_register:
            name = risk.get("risk", "")
            severity = risk.get("severity", "")
            likelihood = risk.get("likelihood", "")
            strength = risk.get("evidence_strength", "")
            lines.append(f"| {name} | {severity} | {likelihood} | {strength} |")
        lines.append("")
        for risk in risk_register:
            name = risk.get("risk", "")
            mechanism = risk.get("mechanism", "")
            mitigating = risk.get("mitigating_factors", "")
            sids = risk.get("source_ids", [])
            refs = " ".join(f"[{s}]" for s in sids) if sids else ""
            if mechanism:
                lines.append(f"**{name}**: {mechanism} {refs}")
                if mitigating:
                    lines.append(f"*Mitigating factors*: {mitigating}")
                lines.append("")
        sections.append("\n".join(lines))

    # Key Tensions
    if key_tensions:
        lines = ["## Key Tensions & Contradictions\n"]
        for tension in key_tensions:
            name = tension.get("tension", "")
            desc = tension.get("description", "")
            outlook = tension.get("resolution_outlook", "")
            dims = tension.get("dimensions_involved", [])
            dims_str = ", ".join(dims) if dims else ""
            lines.append(f"### {name}")
            lines.append(f"{desc}")
            if dims_str:
                lines.append(f"*Dimensions*: {dims_str}")
            if outlook:
                lines.append(f"*Resolution outlook*: {outlook}")
            lines.append("")
        sections.append("\n".join(lines))

    # Forward Indicators
    if forward_indicators:
        lines = ["## Forward Indicators\n"]
        for indicator in forward_indicators:
            name = indicator.get("indicator", "")
            why = indicator.get("why_it_matters", "")
            timeframe = indicator.get("timeframe", "")
            sids = indicator.get("source_ids", [])
            refs = " ".join(f"[{s}]" for s in sids) if sids else ""
            lines.append(f"- **{name}** ({timeframe}): {why} {refs}")
        sections.append("\n".join(lines))

    # Contradiction Notes
    if contradiction_notes:
        lines = ["## Source Contradictions\n"]
        for note in contradiction_notes:
            if isinstance(note, dict):
                topic = note.get("topic", "")
                pos_a = note.get("position_a", "")
                pos_b = note.get("position_b", "")
                assessment = note.get("analyst_assessment", "")
                lines.append(f"### {topic}")
                if pos_a:
                    lines.append(f"- Position A: {pos_a}")
                if pos_b:
                    lines.append(f"- Position B: {pos_b}")
                if assessment:
                    lines.append(f"- *Analyst assessment*: {assessment}")
                lines.append("")
        sections.append("\n".join(lines))

    # Confidence Assessment
    if confidence_assessment:
        lines = ["## Confidence Assessment\n"]
        overall = confidence_assessment.get("overall", "")
        rationale = confidence_assessment.get("rationale", "")
        strongest = confidence_assessment.get("strongest_dimensions", [])
        weakest = confidence_assessment.get("weakest_dimensions", [])
        gaps = confidence_assessment.get("critical_gaps", [])
        if overall:
            lines.append(f"**Overall confidence**: {overall}")
        if rationale:
            lines.append(f"\n{rationale}")
        if strongest:
            lines.append(f"\n*Strongest dimensions*: {', '.join(strongest)}")
        if weakest:
            lines.append(f"*Weakest dimensions*: {', '.join(weakest)}")
        if gaps:
            lines.append("\n**Critical gaps**:")
            for gap in gaps:
                lines.append(f"- {gap}")
        sections.append("\n".join(lines))

    # Methodology
    if methodology_note:
        sections.append(f"## Methodology\n\n{methodology_note}")

    # Suggested Follow-ups
    if suggested_follow_ups:
        lines = ["## Suggested Follow-up Questions\n"]
        for i, q in enumerate(suggested_follow_ups, 1):
            lines.append(f"{i}. {q}")
        sections.append("\n".join(lines))

    # References
    if source_appendix:
        lines = ["## References\n"]
        for src in source_appendix:
            sid = src.get("id", "")
            title = src.get("title", "Untitled")
            url = src.get("url", "")
            provider = src.get("provider", "")
            date = src.get("date", "")
            tier = src.get("credibility_tier", "")
            date_str = f" ({date})" if date else ""
            provider_str = f" via {provider}" if provider else ""
            tier_str = f" [{tier}]" if tier and tier != "unknown" else ""
            lines.append(f"[{sid}] [{title}]({url}){date_str}{provider_str}{tier_str}")
        sections.append("\n".join(lines))

    return "\n\n---\n\n".join(sections)


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
