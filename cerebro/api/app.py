"""FastAPI app exposing planner streaming endpoints."""

from __future__ import annotations

import asyncio
import contextlib
import json
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

        return {
            "request_id": working_state.request_id,
            "plan": plan,
            "agent_results": agent_results,
            "synthesis": synthesis_result,
            "evidence_diagnostics": threshold_check,
            "warnings": warnings,
            "retrieval_summary": retrieval_summary,
            "working_files": sorted(working_state.files.keys()),
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


def _build_retrieval_summary(agent_results: dict[str, Any]) -> dict[str, Any]:
    documents_preview: list[dict[str, Any]] = []
    per_dimension_counts: dict[str, int] = {}
    total_documents = 0

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
            if len(documents_preview) >= 12:
                break
            documents_preview.append(
                {
                    "dimension": dimension,
                    "title": item.get("title"),
                    "url": item.get("url") or item.get("source"),
                    "provider": item.get("provider") or item.get("retrieval_provider"),
                    "retrieval_method": item.get("retrieval_method"),
                    "content_snippet": str(item.get("content") or "")[:240],
                }
            )

    return {
        "total_documents": total_documents,
        "per_dimension_counts": per_dimension_counts,
        "documents_preview": documents_preview,
    }


app = create_app()
