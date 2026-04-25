## Plan: Standalone Research Tool MVP

Build the Cerebro Research Tool as a fresh standalone backend in the current repository, optimized for Saturday demo speed while preserving architecture needed for scale. The approach is to lock contracts first, then implement the 4-stage pipeline in dependency order (Registry + Planner -> Executor + Chroma -> Synthesis + Formatter), then harden with targeted tests and demo runbooks.

**Steps**
1. Phase 1: Scope lock and contracts.
2. Define canonical request/response contracts for the research entrypoint and final report, including strict planner JSON schema, citation requirements, confidence levels, skipped-dimension rationale, and gap-flag behavior.
3. Define shared data contracts used across stages: ResearchPlan, DimensionTask, RetrievedDocument metadata, SynthesisInput, SynthesisOutput, and SourceReference mapping.
4. Create the new standalone package structure under the backend root for research pipeline modules and runtime wiring. This is a fresh build path and does not depend on recovering previous graph QA backend code.
5. Phase 2: Source registry and planning core (critical path).
6. Implement the Source Registry as the single source of truth for dimensions 4, 6, and 7, including source IDs, crawl paths, source type, credibility score, update frequency, and search operators.
7. Implement model selection and rotation policy for planning calls (weighted priority, least-recently-used tie-breaker, token budget exclusion, failure streak exclusion, and immediate fallback chain).
8. Implement the Research Planner with strict output validation and retry-on-malformed JSON, including mandatory 200-400 word thinking field, entity classification, intent classification, per-dimension ACTIVE or SKIP status, and execution order.
9. Add planner-focused tests with fixture prompts covering at least: listed entity, non-listed entity, policy query, controversy query, and broad sector query.
10. Phase 3: Parallel research execution and temporary document store.
11. Implement temporary per-query Chroma lifecycle (initialize fresh, write documents with required metadata, read for synthesis, then wipe) with cleanup in both success and failure paths.
12. Implement executor orchestration that runs only ACTIVE dimensions concurrently; dimensions 4, 6, and 7 must resolve planner source IDs through the registry, while dimensions 1, 2, 3, and 5 use planner-guided web search.
13. Enforce dimension-specific rules in executor: strict 12-month date filtering for news, source deduplication, relevance scoring, and deterministic metadata capture for each retrieved artifact.
14. Add fault isolation: per-dimension retries, timeout budgets, partial-failure recording, and continuation to synthesis with explicit gap notes when one or more dimensions fail.
15. Phase 4: Synthesis and analyst-grade formatting.
16. Implement synthesis stage with Gemini 2.0 Flash that consumes all Chroma documents only after all executor tasks complete; no partial streaming into synthesis.
17. Implement report formatter that enforces analyst structure: reasoning before findings, confidence labels on findings, explicit skipped-dimension notes, conflict comparison section, synthesis section, and source appendix with stable reference codes.
18. Add citation integrity checks so every claim maps to at least one source URL and uncited claims are either removed or flagged as low-confidence gaps.
19. Phase 5: API orchestration, integration, and demo hardening.
20. Implement top-level orchestration endpoint and runtime flow control (Stage 1 -> Stage 2 parallel -> Stage 3 read -> Stage 4 synthesis -> cleanup) with request IDs and trace logs for demo diagnostics.
21. Add frontend-ready contract artifacts: stable JSON responses, error envelope schema, and example payloads for success, partial evidence, and failure conditions.
22. Build an MVP verification suite and demo runbook with representative Nigerian petroleum queries spanning all 7 dimensions and edge cases (insufficient evidence, conflicting expert views, non-listed entities).
23. Run pre-demo reliability checks under free-tier constraints (rate limits, token quotas, provider fallbacks), then freeze the release candidate for investor demo usage.


**Applied Refinements (April 21, 2026)**
1. Step 0 is mandatory: planner reasoning happens before any retrieval, producing explicit ACTIVE or SKIP decisions for all 7 dimensions to prevent wasted calls.
2. Steps 1-7 are asynchronous and parallel by default; sequential execution is explicitly disallowed for MVP runtime.
3. Chroma is the required temporary document store with strict metadata per record: source_url, source_type, dimension, date_retrieved, relevance_score, and agent_that_found_it.
4. Expert-opinion retrieval is source-constrained using registry allowlists and source-type filters; blogs, personal posts, and low-credibility outlets are excluded.
5. Firecrawl targeting includes a Nigerian primary-domain set for reliability in this use case: NUPRC, NEITI, SEC Nigeria, CBN, NNPC Group, PPPRA, Nairametrics, and Businessday.
6. Planner model policy for MVP is fixed: GitHub model pool remains primary, with DeepSeek R1 via Groq as fallback and reasoning assist.
7. MVP operating mode is fixed to live mode: full retrieval on every query, with optional fallback path retained only for quota emergencies.
8. Next-phase retrieval rule: planner-provided sources are seed anchors, not hard limits; execution should discover and include additional related links relevant to the query.

**Relevant files**
- /home/abimbola/Desktop/Cerebro/cerebro_backend/non_code_files/BACKEND_STATUS.md — Treat as historical context only; currently inconsistent with the live workspace file inventory.
- /home/abimbola/Desktop/Cerebro/cerebro_backend/non_code_files/FRONTEND_INTEGRATION.md — Reuse endpoint response style for frontend contract planning.
- /home/abimbola/Desktop/Cerebro/cerebro_backend/non_code_files/entity-35-39_2020_marginal_spvs.cypher — Explicitly out of scope for this standalone research-tool phase.
- /home/abimbola/Desktop/Cerebro/cerebro_backend — Root where the new standalone research tool module tree will be created.

**Verification**
1. File-inventory gate: confirm required pipeline modules now exist under backend root and map 1:1 to planner, source registry, executor, document store, synthesizer, formatter, and entrypoint.
2. Contract gate: validate planner output against strict JSON schema and reject malformed outputs with retry behavior tests.
3. Execution gate: run integration tests confirming ACTIVE dimensions execute in parallel, SKIP dimensions do not execute, and dimension 4/6/7 source IDs resolve from registry only.
4. Store gate: verify Chroma is query-scoped and cleared after report generation for both success and exception paths.
5. Synthesis gate: assert every final finding includes confidence and at least one source URL; verify skipped dimensions and data gaps are explicitly rendered.
8. Latency gate: run side-by-side benchmark proving parallel execution materially outperforms sequential baseline for representative prompts under demo conditions.

6. Frontend gate: validate endpoint examples against expected client contract for normal, partial, and failure responses.
7. Demo gate: run a scripted smoke suite (5-10 real investor-style prompts) and capture timing, source counts, and fallback behavior.

**Decisions**
- Confirmed choice: build the standalone research tool structure fresh in current workspace; do not depend on restoring prior backend code.
- Priority set: optimize for fastest demo path while still enforcing clean architecture, reliability checks, and frontend contract readiness.
- Planner policy locked: GitHub model rotation pool is primary for planning, with DeepSeek R1 via Groq as fallback/reasoning assist.
- Execution policy locked: dimension research runs in parallel (async) for ACTIVE dimensions; sequential mode is excluded.
- Operating mode locked: live retrieval on every user query for the investor demo.
- In scope: the 4-stage research pipeline only.
- Out of scope: graph database modeling, non-research analytics routes, and persistent cross-query document memory.

**Further Considerations**
1. Demo resilience recommendation: prepare two fallback modes.
Option A: full live retrieval + synthesis (primary).
Option B: cached fixture retrieval + live synthesis (fallback when free-tier quotas are hit).
2. Evidence quality recommendation: define minimum source thresholds per active dimension (for example 2-3 independent sources) before assigning HIGH confidence.
3. Observability recommendation: capture per-dimension timings and source hit counts in a lightweight trace object for investor demo transparency and debugging.
4. Discovery expansion recommendation: add executor-side related-link expansion so web search is not restricted to only planner-listed links.