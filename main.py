"""
FastAPI Backend for Cerebro AI Pipeline
Connects Neo4j database with an LLM-driven Cypher pipeline
Implements two-call architecture: NL -> Cypher -> Results -> NL
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables FIRST before any other imports
load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env")

import asyncio
import uuid
import time
import logging
import re
from typing import Optional, List, Literal
from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, validator, ConfigDict, Field
import uvicorn

from database import db
from llm import llm_pipeline
from keepalive import keepalive_service
from session import session_manager
from upstream_intelligence import generate_upstream_dashboard

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] %(asctime)s - %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Cerebro AI Pipeline",
    description="Nigerian Upstream Oil & Gas Data Query System",
    version="0.1.0"
)

# Add CORS middleware for frontend integration.
def _parse_cors_origins() -> List[str]:
    """Parse comma-separated origins from env (supports wildcard)."""
    raw = os.getenv("CORS_ALLOWED_ORIGINS", "*").strip()
    if not raw:
        return ["*"]

    origins = [origin.strip().rstrip("/") for origin in raw.split(",") if origin.strip()]
    if not origins:
        return ["*"]
    if "*" in origins:
        return ["*"]
    return origins


cors_allowed_origins = _parse_cors_origins()
cors_allow_credentials = os.getenv("CORS_ALLOW_CREDENTIALS", "false").strip().lower() == "true"

if cors_allowed_origins == ["*"] and cors_allow_credentials:
    logger.warning("CORS_ALLOW_CREDENTIALS=true ignored when CORS_ALLOWED_ORIGINS=*; forcing false")
    cors_allow_credentials = False

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_allowed_origins,
    allow_credentials=cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Connect to Neo4j on startup
@app.on_event("startup")
async def startup():
    print("🚀 Starting Cerebro Backend...")
    try:
        db.connect()
        keepalive_service.start()
        print("✅ Backend ready")
    except Exception as e:
        print(f"❌ Startup failed: {e}")

@app.on_event("shutdown")
async def shutdown():
    print("🛑 Shutting down...")
    keepalive_service.stop()
    db.close()

# --- Request/Response Models ---

class QueryRequest(BaseModel):
    """User question request with validation."""
    query: str
    session_id: Optional[str] = None
    
    @validator('query')
    def validate_query(cls, v):
        """Validate and sanitize query input."""
        if not isinstance(v, str):
            raise ValueError("Query must be a string")
        
        # Strip whitespace
        v = v.strip()
        
        # Check length
        if len(v) < 3:
            raise ValueError("Query must be at least 3 characters")
        if len(v) > 5000:
            raise ValueError("Query must not exceed 5000 characters")
        
        # Remove extreme special characters but keep natural language punctuation
        safe_query = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', v)
        
        # Warn about SQL-like patterns but don't block
        if any(keyword in safe_query.upper() for keyword in ['DROP', 'DELETE', 'INSERT', 'UPDATE']):
            logger.warning(f"Potentially dangerous keywords in query: {safe_query[:50]}")
        
        return safe_query
    
    @validator('session_id')
    def validate_session_id(cls, v):
        """Validate session ID format if provided."""
        if v and not re.match(r'^[a-f0-9\-]{36}$|^[a-f0-9]+$', v):
            logger.warning(f"Invalid session ID format: {v}")
        return v
    
    model_config = ConfigDict(str_strip_whitespace=True)

class QueryResponse(BaseModel):
    """Response with answer and metadata"""
    answer: str
    entity_id: Optional[str] = None
    entity_name: Optional[str] = None
    session_id: str
    is_success: bool

class EntityListResponse(BaseModel):
    """List of entities"""
    entities: List[dict]
    count: int

class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    database: str
    llm: str


class UpstreamLensWeights(BaseModel):
    """Lens weighting controls for dashboard emphasis."""

    finance: float = 20.0
    volume: float = 20.0
    economics: float = 20.0
    risk: float = 20.0
    geopolitics: float = 10.0
    operations: float = 10.0

    @validator("*", pre=True)
    def validate_weight(cls, value):
        weight = float(value)
        if weight < 0:
            raise ValueError("Lens weights must be non-negative")
        if weight > 1000:
            raise ValueError("Lens weights are unrealistically high")
        return weight


class UpstreamIntelligenceRequest(BaseModel):
    """Request contract for upstream dashboard synthesis route."""

    scope: str = "upstream_nigeria"
    lens_weights: UpstreamLensWeights
    focus_strength: float = 65.0
    include: List[str] = ["global", "nigeria", "cost_curves", "yield_breakdown", "nuances"]

    @validator("scope")
    def validate_scope(cls, value: str) -> str:
        clean = value.strip().lower()
        if clean not in {"upstream_nigeria", "upstream", "nigeria_upstream"}:
            raise ValueError("scope must be one of: upstream_nigeria, upstream, nigeria_upstream")
        return clean

    @validator("focus_strength")
    def validate_focus_strength(cls, value: float) -> float:
        if value < 0 or value > 100:
            raise ValueError("focus_strength must be between 0 and 100")
        return float(value)

    @validator("include")
    def validate_include(cls, value: List[str]) -> List[str]:
        allowed = {"global", "nigeria", "cost_curves", "yield_breakdown", "nuances"}
        if not value:
            return ["global", "nigeria", "cost_curves", "yield_breakdown", "nuances"]
        cleaned: List[str] = []
        for item in value:
            key = str(item).strip().lower()
            if key not in allowed:
                raise ValueError(f"Unsupported include key: {item}")
            if key not in cleaned:
                cleaned.append(key)
        return cleaned


class UpstreamTopProducer(BaseModel):
    name: str
    code: str
    value: float
    share: float


class UpstreamGlobalProductionMetric(BaseModel):
    value: float
    unit: str
    context: str
    trendText: str
    topProducers: List[UpstreamTopProducer] = Field(min_length=1)
    series: List[float] = Field(min_length=6)


class UpstreamBrentSpotPriceMetric(BaseModel):
    value: float
    unit: str
    context: str
    trendText: str
    rangeLow: float
    rangeHigh: float
    alert: str
    series: List[float] = Field(min_length=6)


class UpstreamBarrelYieldMetric(BaseModel):
    name: str
    value: float
    unit: str
    sharePct: float
    note: str


class UpstreamReservesMetric(BaseModel):
    value: float
    unit: str
    yearsOfSupply: int
    context: str
    topHolders: List[str] = Field(min_length=1)
    series: List[float] = Field(min_length=6)


class UpstreamBreakEvenMetric(BaseModel):
    region: str
    min: float
    max: float


class UpstreamNigeriaPulseMetric(BaseModel):
    productionBpd: int
    upstreamCapacityBpd: int
    refineryThroughputBpd: int
    pmsDemandBpd: int
    context: str
    bottleneck: str
    series: List[float] = Field(min_length=6)


class UpstreamNuanceMetric(BaseModel):
    title: str
    detail: str
    severity: Literal["watch", "elevated", "critical"]


class UpstreamMetrics(BaseModel):
    globalProduction: UpstreamGlobalProductionMetric
    brentSpotPrice: UpstreamBrentSpotPriceMetric
    barrelYields: List[UpstreamBarrelYieldMetric] = Field(min_length=1)
    reserves: UpstreamReservesMetric
    breakEvenByRegion: List[UpstreamBreakEvenMetric] = Field(min_length=1)
    nigeriaPulse: UpstreamNigeriaPulseMetric


class UpstreamDashboardResponse(BaseModel):
    dashboardTitle: str
    generatedAt: str
    summary: str
    dominantLens: Literal["finance", "volume", "economics", "risk", "geopolitics", "operations"]
    metrics: UpstreamMetrics
    nuances: List[UpstreamNuanceMetric] = Field(min_length=1)


class UpstreamIntelligenceResponse(BaseModel):
    dashboard: UpstreamDashboardResponse

# --- Endpoints ---

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint - verify all services are running."""
    return {
        "status": "ok",
        "database": "connected" if db.driver else "disconnected",
        "llm": "ready" if llm_pipeline else "unavailable"
    }


@app.get("/api/schema/debug")
def schema_debug():
    """Inspect active schema context used for Cypher generation."""
    if not llm_pipeline:
        raise HTTPException(
            status_code=503,
            detail="LLM pipeline unavailable. Cannot inspect schema context.",
        )

    runtime_summary = ""
    runtime_labels: List[str] = []
    if db.driver:
        try:
            runtime_summary = db.get_schema_summary()
            for line in runtime_summary.splitlines():
                if line.startswith("## Label: "):
                    runtime_labels.append(line.replace("## Label: ", "").split("(")[0].strip())
        except Exception as exc:
            logger.warning("Schema debug: runtime summary unavailable: %s", exc)

    static_schema = llm_pipeline.node_catalog or ""
    active_schema = llm_pipeline._active_schema_catalog()

    return {
        "llm_provider": llm_pipeline.provider,
        "llm_model": llm_pipeline.model,
        "database_connected": bool(db.driver),
        "runtime_schema_introspection_enabled": llm_pipeline.runtime_schema_introspection_enabled,
        "runtime_schema_chars": len(runtime_summary),
        "static_schema_chars": len(static_schema),
        "active_schema_chars": len(active_schema),
        "runtime_labels_sample": runtime_labels[:20],
        "runtime_schema_preview": runtime_summary[:2000],
        "langchain_shadow_enabled": llm_pipeline.langchain_cypher_shadow_enabled,
        "langchain_shadow_ready": llm_pipeline.langchain_shadow_ready,
        "langchain_shadow_provider": llm_pipeline.langchain_cypher_provider,
        "langchain_shadow_model": llm_pipeline.langchain_openrouter_model,
        "langchain_schema_source": llm_pipeline.langchain_schema_source,
        "langchain_shadow_last_error": llm_pipeline.langchain_shadow_last_error,
        "langchain_schema_chars": len(llm_pipeline._langchain_schema_cache or ""),
    }

@app.post("/api/ask", response_model=QueryResponse)
def ask_question(request: QueryRequest):
    """
    Main endpoint: Answer user questions about upstream producers.

    Two-call LLM pipeline:
    1. LLM generates read-only Cypher from natural language + schema context
    2. Backend executes Cypher against Neo4j
    3. LLM synthesizes final answer from raw JSON results

    Optional web enrichment is added only as supplementary context for
    single-entity questions.

    Returns: Natural language answer with entity reference
    """
    
    request_id = str(uuid.uuid4())[:8]
    start_time = time.time()
    
    try:
        # Validation already done by Pydantic
        logger.info(f"[{request_id}] Processing query: {request.query[:60]}...")
        
        if not llm_pipeline:
            logger.error(f"[{request_id}] LLM Pipeline not initialized")
            raise HTTPException(
                status_code=503,
                detail="AI system not ready. Check LLM credentials and API connectivity."
            )
        
        # Get or create session
        session_id = request.session_id or str(uuid.uuid4())
        session = session_manager.get_session(session_id)
        
        # Process question with timeout (120 seconds max)
        try:
            result = asyncio.run(
                asyncio.wait_for(
                    asyncio.to_thread(
                        llm_pipeline.process_question,
                        request.query,
                        session
                    ),
                    timeout=120
                )
            )
        except asyncio.TimeoutError:
            logger.error(f"[{request_id}] Request timeout after 120s")
            result = {
                "answer": "The system took too long to process your query. Please try a simpler question.",
                "entity_id": None,
                "entity_name": None,
                "is_success": False
            }
        
        # Validate result
        if not result:
            result = {
                "answer": "Unable to process query. Please try rephrasing your question.",
                "entity_id": None,
                "entity_name": None,
                "is_success": False
            }
        
        # Ensure answer is not empty
        if not result.get("answer") or not str(result["answer"]).strip():
            result["answer"] = "Sorry, I couldn't find relevant information about that. Could you rephrase?"
        
        # Update session
        session_manager.add_message(session_id, "user", request.query)
        session_manager.add_message(session_id, "assistant", result["answer"])
        
        if result.get("entity_id"):
            session_manager.set_current_entity(
                session_id,
                result["entity_id"],
                result.get("entity_name", "Unknown")
            )
        
        elapsed = time.time() - start_time
        logger.info(f"[{request_id}] ✅ Completed in {elapsed:.2f}s")
        
        return QueryResponse(
            answer=result["answer"],
            entity_id=result.get("entity_id"),
            entity_name=result.get("entity_name"),
            session_id=session_id,
            is_success=result.get("is_success", False)
        )
    
    except ValueError as ve:
        logger.warning(f"[{request_id}] Validation error: {str(ve)}")
        raise HTTPException(status_code=400, detail=f"Invalid input: {str(ve)}")
    
    except HTTPException:
        raise  # Re-raise HTTP exceptions
    
    except Exception as e:
        elapsed = time.time() - start_time
        logger.error(f"[{request_id}] ❌ Pipeline error after {elapsed:.2f}s: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred. Please try again or contact support."
        )


@app.post("/api/ask/debug")
def ask_question_debug(request: QueryRequest):
    """
    Debug variant of /api/ask.
    Returns full pipeline payload including generated Cypher, raw rows,
    and whether web enrichment was used.
    """

    request_id = str(uuid.uuid4())[:8]
    start_time = time.time()

    try:
        logger.info(f"[{request_id}] Debug processing query: {request.query[:60]}...")

        if not llm_pipeline:
            raise HTTPException(
                status_code=503,
                detail="AI system not ready. Check LLM credentials and API connectivity."
            )

        session_id = request.session_id or str(uuid.uuid4())
        session = session_manager.get_session(session_id)

        try:
            result = asyncio.run(
                asyncio.wait_for(
                    asyncio.to_thread(
                        llm_pipeline.process_question,
                        request.query,
                        session
                    ),
                    timeout=120
                )
            )
        except asyncio.TimeoutError:
            result = {
                "answer": "The system took too long to process your query. Please try a simpler question.",
                "entity_id": None,
                "entity_name": None,
                "is_success": False,
                "cypher_query": None,
                "data_retrieved": [],
                "sources": [],
                "used_web_enrichment": False,
            }

        if not result:
            result = {
                "answer": "Unable to process query. Please try rephrasing your question.",
                "entity_id": None,
                "entity_name": None,
                "is_success": False,
                "cypher_query": None,
                "data_retrieved": [],
                "sources": [],
                "used_web_enrichment": False,
            }

        session_manager.add_message(session_id, "user", request.query)
        session_manager.add_message(session_id, "assistant", result.get("answer", ""))

        elapsed = time.time() - start_time
        return {
            "answer": result.get("answer"),
            "entity_id": result.get("entity_id"),
            "entity_name": result.get("entity_name"),
            "session_id": session_id,
            "is_success": result.get("is_success", False),
            "cypher_query": result.get("cypher_query"),
            "data_retrieved": result.get("data_retrieved", []),
            "sources": result.get("sources", []),
            "used_web_enrichment": result.get("used_web_enrichment", False),
            "llm_provider": result.get("llm_provider"),
            "langchain_shadow": result.get("langchain_shadow"),
            "duration_seconds": round(elapsed, 3),
        }

    except HTTPException:
        raise
    except Exception as e:
        elapsed = time.time() - start_time
        logger.error(f"[{request_id}] ❌ Debug pipeline error after {elapsed:.2f}s: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred in debug pipeline."
        )


@app.post("/api/upstream/intelligence", response_model=UpstreamIntelligenceResponse)
async def upstream_intelligence_dashboard(request: UpstreamIntelligenceRequest):
    """
    Build upstream intelligence dashboard payload for the frontend contract.
    Always returns a stable dashboard shape under {"dashboard": ...}.
    """

    request_id = str(uuid.uuid4())[:8]
    start_time = time.time()
    time_budget_seconds = max(20, int(os.getenv("UPSTREAM_INTEL_TIMEOUT_SECONDS", "180")))

    try:
        dashboard = await asyncio.to_thread(
            generate_upstream_dashboard,
            scope=request.scope,
            lens_weights=request.lens_weights.model_dump(),
            focus_strength=request.focus_strength,
            include=request.include,
            llm_pipeline=llm_pipeline,
            time_budget_seconds=time_budget_seconds,
        )
    except Exception as exc:
        logger.error("[%s] Upstream dashboard failed: %s", request_id, exc, exc_info=True)
        dashboard = generate_upstream_dashboard(
            scope=request.scope,
            lens_weights=request.lens_weights.model_dump(),
            focus_strength=request.focus_strength,
            include=request.include,
            llm_pipeline=None,
            skip_research=True,
        )

    elapsed = time.time() - start_time
    logger.info("[%s] Upstream intelligence response ready in %.2fs", request_id, elapsed)
    return {"dashboard": dashboard}

@app.get("/api/entities", response_model=EntityListResponse)
async def list_entities(entity_type: str = "UpstreamProducer"):
    """
    List all entities of a given type.
    Useful for frontend autocomplete or entity selection.
    """
    
    try:
        entities = db.query_all_entities(entity_type)
        return EntityListResponse(
            entities=entities,
            count=len(entities)
        )

    except ValueError as ve:
        raise HTTPException(status_code=400, detail=f"Invalid request: {str(ve)}")
    
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list entities: {str(e)}"
        )

@app.get("/api/search")
async def search_entities(query: str, entity_type: str = "UpstreamProducer"):
    """
    Search for entities by name or keyword.
    Useful for frontend lookup and manual exploration.
    """
    
    if not query or len(query) < 2:
        raise HTTPException(status_code=400, detail="Query too short")
    
    try:
        results = db.search_entities_by_keyword(query, entity_type)
        return {
            "results": results,
            "count": len(results),
            "query": query
        }

    except ValueError as ve:
        raise HTTPException(status_code=400, detail=f"Invalid request: {str(ve)}")
    
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Search failed: {str(e)}"
        )

@app.get("/api/entity/{entity_id}")
async def get_entity_details(entity_id: str, entity_type: str = "UpstreamProducer"):
    """
    Get all details for a specific entity.
    Query B from pipeline: Discover what properties exist.
    """
    
    try:
        # Get basic info
        entity = db.get_entity_by_id(entity_id, entity_type)
        if not entity:
            raise HTTPException(status_code=404, detail="Entity not found")
        
        # Discover properties
        properties = db.discover_properties(entity_id, entity_type)
        
        return {
            "entity": entity,
            "available_properties": properties,
            "property_count": len(properties)
        }

    except ValueError as ve:
        raise HTTPException(status_code=400, detail=f"Invalid request: {str(ve)}")
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get entity details: {str(e)}"
        )

@app.get("/api/session/{session_id}")
async def get_session(session_id: str):
    """Get session history and current context."""
    
    session = session_manager.get_session(session_id) or {}
    current_entity = session_manager.get_current_entity(session_id)
    
    return {
        "session_id": session_id,
        "created_at": session.get("created_at"),
        "current_entity": current_entity,
        "visited_entities": session.get("visited_entities", []),
        "conversation_history": session.get("conversation_history", []),
        "message_count": len(session.get("conversation_history", []))
    }

@app.delete("/api/session/{session_id}")
async def clear_session(session_id: str):
    """Clear session data (for testing or logout)."""
    
    session_manager.clear_session(session_id)
    return {"status": "cleared", "session_id": session_id}

# --- Test Endpoint ---

@app.get("/api/test")
def test_pipeline():
    """
    Test the full pipeline with a sample query.
    Useful for debugging before frontend integration.
    """
    
    if not llm_pipeline:
        return {
            "status": "failed",
            "error": "LLM Pipeline not initialized. Check LLM credentials."
        }
    
    try:
        test_query = "Tell me about NNPC"
        result = llm_pipeline.process_question(test_query)
        
        return {
            "status": "success" if result.get("is_success") else "failed",
            "test_query": test_query,
            "answer": result.get("answer"),
            "entity_found": result.get("entity_name") or "None",
            "data_sample": result.get("data_retrieved", {})
        }
    
    except Exception as e:
        return {
            "status": "failed",
            "error": str(e)
        }

# --- Main ---

if __name__ == "__main__":
    port = int(os.getenv("FASTAPI_PORT", 8000))
    host = os.getenv("FASTAPI_HOST", "0.0.0.0")
    llm_provider = os.getenv("LLM_PRIMARY_PROVIDER", "cerebras").strip().lower()
    provider_models = {
        "cerebras": os.getenv("CEREBRAS_MODEL", "llama3.1-8b"),
        "openrouter": os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.1-70b-instruct"),
        "groq": os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
        "gemini": os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
    }
    llm_banner = f"{llm_provider}:{provider_models.get(llm_provider, 'not-configured')}"
    
    print(f"""
    ╔════════════════════════════════════════╗
    ║     Cerebro AI Backend Starting        ║
    ╠════════════════════════════════════════╣
    ║  FastAPI:  http://{host}:{port}/docs     ║
    ║  Database: {os.getenv('NEO4J_URI', 'Not set')}   ║
    │  LLM:      {llm_banner}           ║
    ╚════════════════════════════════════════╝
    """)
    
    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=True
    )
