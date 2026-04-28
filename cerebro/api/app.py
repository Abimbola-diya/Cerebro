"""FastAPI app exposing planner streaming endpoints."""

from __future__ import annotations

import asyncio
import contextlib
import json
import time
from datetime import datetime
from typing import Any

from fastapi import FastAPI
from fastapi import HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from cerebro.research import ChromaDimensionStore, ResearchAdapter, ResearchExecutionBridge, ResearchOrchestrator, ResearchPlanner, RetrievalExecutor
from cerebro.research.agents.synthesis import ResearchSynthesizer


class PlannerStreamRequest(BaseModel):
    query: str = Field(min_length=1)
    entity_id: str | None = None
    entity_name: str | None = None
    entity_context: dict[str, Any] | None = None
    max_attempts: int | None = Field(default=None, ge=1, le=20)
    thinking_mode: bool | None = Field(
        default=None,
        description="Override model reasoning mode. true=on, false=off, null=use server default.",
    )


def create_app() -> FastAPI:
    app = FastAPI(title="Cerebro Planner API", version="0.1.0")

    # MVP default: allow frontend integration from any origin.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/planner/plan")
    async def get_plan(request: PlannerStreamRequest) -> dict[str, Any]:
        """Non-streaming endpoint to get the full plan as JSON.
        Useful for testing and inspecting sub-queries without streaming overhead."""
        planner = ResearchPlanner()
        effective_thinking_mode = request.thinking_mode if request.thinking_mode is not None else False
        plan = planner.generate_plan(
            query=request.query,
            entity_id=request.entity_id,
            entity_name=request.entity_name,
            entity_context=request.entity_context,
            max_attempts=request.max_attempts,
            thinking_mode=effective_thinking_mode,
            stream_thinking=False,
        )
        return {"plan": plan}

    @app.post("/api/planner/stream")
    async def stream_planner(request: PlannerStreamRequest) -> StreamingResponse:
        planner = ResearchPlanner()
        queue: asyncio.Queue[tuple[str, dict[str, Any]]] = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def on_token(token: str) -> None:
            loop.call_soon_threadsafe(
                queue.put_nowait,
                ("thinking_delta", {"delta": token}),
            )

        def run_plan() -> dict[str, Any]:
            effective_thinking_mode = request.thinking_mode if request.thinking_mode is not None else True
            return planner.generate_plan(
                query=request.query,
                entity_id=request.entity_id,
                entity_name=request.entity_name,
                entity_context=request.entity_context,
                max_attempts=request.max_attempts,
                thinking_mode=effective_thinking_mode,
                stream_thinking=True,
                on_stream_token=on_token,
            )

        async def event_stream():
            task = asyncio.create_task(asyncio.to_thread(run_plan))
            pending_thinking = ""

            def flush_pending() -> str | None:
                nonlocal pending_thinking
                if not pending_thinking:
                    return None
                delta = pending_thinking
                pending_thinking = ""
                return _sse("thinking_delta", {"delta": delta})

            try:
                yield _sse("start", {"status": "started"})

                while True:
                    if task.done() and queue.empty():
                        break

                    try:
                        event_type, payload = await asyncio.wait_for(queue.get(), timeout=0.2)

                        if event_type == "thinking_delta":
                            pending_thinking += payload.get("delta", "")
                            if (
                                len(pending_thinking) < 140
                                and not pending_thinking.endswith((".", "?", "!", ":", ";", "\n"))
                            ):
                                continue

                            chunk = flush_pending()
                            if chunk is not None:
                                yield chunk
                            continue

                        chunk = flush_pending()
                        if chunk is not None:
                            yield chunk

                        yield _sse(event_type, payload)
                    except asyncio.TimeoutError:
                        continue

                chunk = flush_pending()
                if chunk is not None:
                    yield chunk

                plan = await task
                yield _sse("plan", {"plan": plan})
                yield _sse("done", {"status": "ok"})

            except Exception as exc:  # pragma: no cover - streaming runtime branch
                yield _sse("error", {"message": str(exc)})
                yield _sse("done", {"status": "error"})
            finally:
                if not task.done():
                    task.cancel()
                with contextlib.suppress(Exception):
                    await task

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @app.post("/api/research/bridge")
    async def research_bridge(request: PlannerStreamRequest) -> dict[str, Any]:
        """Run Step 1 planning and connect it to Step 2 retrieval task generation."""
        planner = ResearchPlanner()
        bridge = ResearchExecutionBridge()
        effective_thinking_mode = request.thinking_mode if request.thinking_mode is not None else False

        plan = planner.generate_plan(
            query=request.query,
            entity_id=request.entity_id,
            entity_name=request.entity_name,
            entity_context=request.entity_context,
            max_attempts=request.max_attempts,
            thinking_mode=effective_thinking_mode,
            stream_thinking=False,
        )
        execution_batch = bridge.build_execution_batch(plan)
        return {
            "plan": plan,
            "execution_batch": execution_batch,
        }

    @app.post("/api/research/prepare")
    async def research_prepare(request: PlannerStreamRequest) -> dict[str, Any]:
        """Prepare in-memory working files and prompt loads for active dimensions."""
        planner = ResearchPlanner()
        adapter = ResearchAdapter()
        effective_thinking_mode = request.thinking_mode if request.thinking_mode is not None else False

        plan = planner.generate_plan(
            query=request.query,
            entity_id=request.entity_id,
            entity_name=request.entity_name,
            entity_context=request.entity_context,
            max_attempts=request.max_attempts,
            thinking_mode=effective_thinking_mode,
            stream_thinking=False,
        )
        working_state = adapter.prepare(plan)
        return {
            "request_id": working_state.request_id,
            "plan": plan,
            "files": sorted(working_state.files.keys()),
            "log": working_state.log,
        }

    @app.post("/api/research/orchestrate")
    async def research_orchestrate(request: PlannerStreamRequest) -> dict[str, Any]:
        """Prepare the in-memory working state using the orchestrator adapter."""
        planner = ResearchPlanner()
        orchestrator = ResearchOrchestrator()
        effective_thinking_mode = request.thinking_mode if request.thinking_mode is not None else False

        plan = planner.generate_plan(
            query=request.query,
            entity_id=request.entity_id,
            entity_name=request.entity_name,
            entity_context=request.entity_context,
            max_attempts=request.max_attempts,
            thinking_mode=effective_thinking_mode,
            stream_thinking=False,
        )
        working_state, summary = orchestrator.prepare(plan)
        return {
            "request_id": working_state.request_id,
            "summary": {
                "request_id": summary.request_id,
                "active_dimensions": summary.active_dimensions,
                "working_files": summary.working_files,
                "status": summary.status,
            },
            "files": sorted(working_state.files.keys()),
        }

    @app.post("/api/research/agents/run")
    async def research_agents_run(request: PlannerStreamRequest) -> dict[str, Any]:
        """Run the LangGraph-backed agent layer over the prepared working state."""
        planner = ResearchPlanner()
        orchestrator = ResearchOrchestrator()
        effective_thinking_mode = request.thinking_mode if request.thinking_mode is not None else False

        plan = planner.generate_plan(
            query=request.query,
            entity_id=request.entity_id,
            entity_name=request.entity_name,
            entity_context=request.entity_context,
            max_attempts=request.max_attempts,
            thinking_mode=effective_thinking_mode,
            stream_thinking=False,
        )
        result = await orchestrator.run(plan)
        working_state = result.pop("working_state")
        return {
            "request_id": result["request_id"],
            "working_files": result["working_files"],
            "results": result["results"],
            "summary": result["summary"],
            "files": sorted(working_state.files.keys()),
        }
    @app.post("/api/research/run")
    async def research_run(request: PlannerStreamRequest) -> dict[str, Any]:
        """Run Step 1 planning, build Step 2 tasks, then execute provider retrieval."""
        planner = ResearchPlanner()
        bridge = ResearchExecutionBridge()
        executor = RetrievalExecutor()
        vector_store = ChromaDimensionStore(ttl_seconds=3600)
        effective_thinking_mode = request.thinking_mode if request.thinking_mode is not None else False

        plan = planner.generate_plan(
            query=request.query,
            entity_id=request.entity_id,
            entity_name=request.entity_name,
            entity_context=request.entity_context,
            max_attempts=request.max_attempts,
            thinking_mode=effective_thinking_mode,
            stream_thinking=False,
        )
        execution_batch = bridge.build_execution_batch(plan)
        execution_result = await executor.run(execution_batch)
        storage_result = vector_store.ingest(
            documents=execution_result.get("documents", []),
            query_id=plan.get("_meta", {}).get("request_id", "unknown"),
        )
        return {
            "plan": plan,
            "execution_batch": execution_batch,
            "execution_result": execution_result,
            "storage_result": storage_result,
        }

    @app.post("/api/research/synthesize")
    async def research_synthesize(request: PlannerStreamRequest) -> dict[str, Any]:
        """Run full pipeline: planner → agents → evidence pack → synthesis."""
        planner = ResearchPlanner()
        orchestrator = ResearchOrchestrator()
        synthesizer = ResearchSynthesizer()
        effective_thinking_mode = request.thinking_mode if request.thinking_mode is not None else False

        # Step 0: Plan
        plan = planner.generate_plan(
            query=request.query,
            entity_id=request.entity_id,
            entity_name=request.entity_name,
            entity_context=request.entity_context,
            max_attempts=request.max_attempts,
            thinking_mode=effective_thinking_mode,
            stream_thinking=False,
        )

        # Steps 1-8: Run agents
        result = await orchestrator.run(plan)
        working_state = result["working_state"]
        agent_results = result["results"]

        threshold_check = _evaluate_evidence_thresholds(plan=plan, agent_results=agent_results)
        warnings: list[str] = []
        if not threshold_check["ok"]:
            warnings.append(
                "Retrieval evidence is below minimum threshold; synthesized output is based on available partial evidence."
            )

        # Step 9: Synthesize
        synthesis_result = await synthesizer.synthesize(
            plan=plan,
            working_state=working_state,
            agent_results=agent_results,
        )

        retrieval_summary = _build_retrieval_summary(agent_results=agent_results)
        evidence_quality = _compute_evidence_quality_score(
            agent_results=agent_results, plan=plan,
        )

        # Extract synthesis output for clean API contract
        synth_output = synthesis_result.get("synthesis_output", {})
        evidence_summary = synthesis_result.get("evidence_summary", {})

        return {
            "request_id": working_state.request_id,
            "query": request.query,
            "entity_name": request.entity_name or plan.get("entity_name", ""),

            # Pre-rendered for immediate display
            "rendered_report": synth_output.get("rendered_report", ""),

            # Structured report data for frontend rendering
            "report": {
                "status": synth_output.get("status", "PARTIAL"),
                "executive_summary": synth_output.get("executive_summary", ""),
                "detailed_analysis": synth_output.get("brief", ""),
                "one_paragraph_summary": synth_output.get("one_paragraph_summary", ""),
                "key_findings": synth_output.get("key_findings", []),
                "key_data_points": synth_output.get("key_data_points", []),
                "timeline": synth_output.get("timeline", []),
                "risk_assessment": synth_output.get("risk_register", []),
                "forward_indicators": synth_output.get("forward_indicators", []),
                "key_tensions": synth_output.get("key_tensions", []),
                "confidence": {
                    **(synth_output.get("confidence_assessment") or {}),
                    "evidence_quality_score": evidence_quality.get("composite_score", 0.0),
                },
                "contradictions": synth_output.get("contradiction_notes", []),
                "methodology_note": synth_output.get("methodology_note", ""),
            },

            # Citation infrastructure
            "sources": synth_output.get("source_appendix", []),

            # Claims with full source resolution
            "claims": synth_output.get("claims", []),

            # Research methodology transparency
            "methodology": {
                "dimensions_searched": len(plan.get("research_plan", {})),
                "dimensions_active": len(evidence_summary.get("active_dimensions", [])),
                "total_sources_consulted": evidence_summary.get("unique_sources", 0),
                "documents_retrieved": evidence_summary.get("total_documents_retrieved", 0),
                "documents_used_in_synthesis": evidence_summary.get("documents_used_in_synthesis", 0),
                "unique_domains": retrieval_summary.get("unique_domains", 0),
                "search_providers": retrieval_summary.get("providers_used", []),
            },

            # Actionable next steps
            "suggested_follow_ups": synth_output.get("suggested_follow_ups", []),

            # Related entities discovered during research
            "related_entities": synth_output.get("related_entities", []),

            # Diagnostics
            "diagnostics": {
                "evidence_thresholds": threshold_check,
                "evidence_quality": evidence_quality,
                "warnings": warnings,
                "retrieval_summary": retrieval_summary,
                "working_files": sorted(working_state.files.keys()),
            },

            # Keep raw data for backward compatibility
            "plan": plan,
            "agent_results": agent_results,
            "synthesis": synthesis_result,
        }

    return app


def _sse(event: str, payload: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _evaluate_evidence_thresholds(plan: dict[str, Any], agent_results: dict[str, Any]) -> dict[str, Any]:
    research_plan = plan.get("research_plan") if isinstance(plan, dict) else {}
    if not isinstance(research_plan, dict):
        research_plan = {}

    total_documents = 0
    priority_documents = 0
    per_dimension: dict[str, Any] = {}

    for dimension, result in agent_results.items():
        if not isinstance(result, dict):
            continue
        docs = result.get("documents")
        if not isinstance(docs, list):
            docs = []
        valid_docs = [item for item in docs if isinstance(item, dict) and str(item.get("content") or "").strip()]
        count = len(valid_docs)
        total_documents += count

        block = research_plan.get(dimension)
        priority = str(block.get("priority") if isinstance(block, dict) else "").upper()
        if priority in {"CRITICAL", "HIGH"}:
            priority_documents += count

        per_dimension[dimension] = {
            "document_count": count,
            "priority": priority or "UNKNOWN",
            "status": result.get("status"),
            "retrieval_gaps": result.get("retrieval_gaps", []),
            "errors": result.get("errors", []),
        }

    return {
        "ok": total_documents >= 5 and priority_documents >= 2,
        "total_documents": total_documents,
        "priority_documents": priority_documents,
        "per_dimension": per_dimension,
    }


def _compute_evidence_quality_score(
    agent_results: dict[str, Any], plan: dict[str, Any],
) -> dict[str, Any]:
    """Compute a composite evidence quality score (0-1.0) from multiple factors."""
    all_docs: list[dict[str, Any]] = []
    domains: set[str] = set()
    providers: set[str] = set()
    recent_count = 0
    high_credibility_count = 0
    dimensions_with_docs = 0

    for _dim, result in (agent_results or {}).items():
        if not isinstance(result, dict):
            continue
        docs = result.get("documents") or []
        if not isinstance(docs, list):
            continue
        valid = [d for d in docs if isinstance(d, dict) and str(d.get("content", "")).strip()]
        if valid:
            dimensions_with_docs += 1
        all_docs.extend(valid)

        for doc in valid:
            url = str(doc.get("url") or doc.get("source") or "")
            if url:
                try:
                    from urllib.parse import urlparse
                    domain = urlparse(url).netloc
                    if domain:
                        domains.add(domain)
                except Exception:
                    pass

            provider = str(doc.get("provider") or doc.get("retrieval_provider") or "")
            if provider:
                providers.add(provider)

            # Check recency (< 90 days)
            date_str = str(doc.get("published_date") or doc.get("date") or "")
            if date_str:
                try:
                    pub = datetime.fromisoformat(date_str[:10])
                    if (datetime.now() - pub).days < 90:
                        recent_count += 1
                except Exception:
                    pass

    total = len(all_docs) or 1

    # Factor 1: Source diversity (unique domains / total docs, capped at 1.0)
    diversity_score = min(1.0, len(domains) / max(total * 0.5, 1))

    # Factor 2: Recency (% of docs from last 90 days)
    recency_score = recent_count / total

    # Factor 3: Cross-dimension coverage (dimensions with docs / total dimensions)
    total_dims = len(plan.get("research_plan", {})) or 7
    coverage_score = dimensions_with_docs / total_dims

    # Factor 4: Volume adequacy (smooth curve, 20+ docs = 1.0)
    volume_score = min(1.0, total / 20)

    # Composite: weighted average
    composite = (
        diversity_score * 0.25
        + recency_score * 0.25
        + coverage_score * 0.30
        + volume_score * 0.20
    )

    return {
        "composite_score": round(composite, 3),
        "source_diversity": {"unique_domains": len(domains), "score": round(diversity_score, 3)},
        "recency": {"recent_docs": recent_count, "total_docs": total, "score": round(recency_score, 3)},
        "dimension_coverage": {"active": dimensions_with_docs, "total": total_dims, "score": round(coverage_score, 3)},
        "volume": {"total_docs": total, "score": round(volume_score, 3)},
    }


def _build_retrieval_summary(agent_results: dict[str, Any]) -> dict[str, Any]:
    documents_preview: list[dict[str, Any]] = []
    per_dimension_counts: dict[str, int] = {}
    total_documents = 0
    all_domains: set[str] = set()
    all_providers: set[str] = set()

    for dimension, result in agent_results.items():
        if not isinstance(result, dict):
            continue
        docs = result.get("documents")
        if not isinstance(docs, list):
            per_dimension_counts[dimension] = 0
            continue

        valid_docs = [item for item in docs if isinstance(item, dict) and str(item.get("content") or "").strip()]
        per_dimension_counts[dimension] = len(valid_docs)
        total_documents += len(valid_docs)

        for item in valid_docs:
            # Track domains and providers
            url = str(item.get("url") or item.get("source") or "")
            if url:
                try:
                    from urllib.parse import urlparse
                    domain = urlparse(url).netloc
                    if domain:
                        all_domains.add(domain)
                except Exception:
                    pass
            provider = str(item.get("provider") or item.get("retrieval_provider") or "")
            if provider:
                all_providers.add(provider)

            if len(documents_preview) >= 12:
                continue
            documents_preview.append(
                {
                    "dimension": dimension,
                    "title": item.get("title"),
                    "url": url,
                    "provider": provider,
                    "retrieval_method": item.get("retrieval_method"),
                    "content_snippet": str(item.get("content") or "")[:240],
                }
            )

    return {
        "total_documents": total_documents,
        "unique_domains": len(all_domains),
        "providers_used": sorted(all_providers),
        "per_dimension_counts": per_dimension_counts,
        "documents_preview": documents_preview,
    }


app = create_app()
