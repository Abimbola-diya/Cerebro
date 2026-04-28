from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from cerebro.api.app import create_app


class _FakePlanner:
    def generate_plan(self, **_: object) -> dict[str, object]:
        return {
            "query": "test query",
            "entity_name": "Test Entity",
            "entity_id": "entity-1",
            "research_plan": {
                "regulatory": {"status": "ACTIVE", "priority": "HIGH", "sub_queries": ["q1"]},
                "financial": {"status": "SKIP", "priority": "LOW", "sub_queries": []},
                "market": {"status": "SKIP", "priority": "LOW", "sub_queries": []},
                "expert": {"status": "SKIP", "priority": "LOW", "sub_queries": []},
                "news": {"status": "SKIP", "priority": "LOW", "sub_queries": []},
                "international": {"status": "SKIP", "priority": "LOW", "sub_queries": []},
                "associations": {"status": "SKIP", "priority": "LOW", "sub_queries": []},
            },
        }


class _FakeWorkingState:
    request_id = "req-test-123"

    def __init__(self) -> None:
        self.files = {
            "working/evidence_pack.json": "{}",
            "working/filtered_evidence_pack.json": "{}",
            "working/synthesis_output.json": "{}",
        }


class _FakeOrchestrator:
    async def run(self, _plan: dict[str, object]) -> dict[str, object]:
        return {
            "request_id": "req-test-123",
            "working_files": ["working/regulatory_results.json"],
            "results": {
                "regulatory": {
                    "dimension": "regulatory",
                    "status": "COMPLETED",
                    "documents": [
                        {
                            "content": "Mocked regulatory finding 1",
                            "relevance_score": 0.8,
                            "source_id": 0,
                        },
                        {
                            "content": "Mocked regulatory finding 2",
                            "relevance_score": 0.79,
                            "source_id": 1,
                        },
                        {
                            "content": "Mocked regulatory finding 3",
                            "relevance_score": 0.78,
                            "source_id": 2,
                        },
                        {
                            "content": "Mocked regulatory finding 4",
                            "relevance_score": 0.77,
                            "source_id": 3,
                        },
                        {
                            "content": "Mocked regulatory finding 5",
                            "relevance_score": 0.76,
                            "source_id": 4,
                        }
                    ],
                    "retrieval_gaps": [],
                    "errors": [],
                }
            },
            "summary": {"result_count": 1},
            "working_state": _FakeWorkingState(),
        }


class _FakeSynthesizer:
    async def synthesize(self, **_: object) -> dict[str, object]:
        return {
            "request_id": "req-test-123",
            "query": "test query",
            "entity_name": "Test Entity",
            "synthesis_output": {
                "status": "COMPLETE",
                "brief": "Analysis text with citation [0].",
                "executive_summary": "Executive summary with citation [0].",
                "one_paragraph_summary": "Summary paragraph [0].",
                "key_findings": [
                    {
                        "finding": "Mocked regulatory finding",
                        "source_ids": [0],
                        "confidence": "MEDIUM",
                        "dimensions_involved": ["regulatory"],
                        "significance": "Test significance",
                    }
                ],
                "key_data_points": [],
                "timeline": [],
                "key_tensions": [],
                "risk_register": [],
                "forward_indicators": [],
                "confidence_assessment": {
                    "overall": "MEDIUM",
                    "rationale": "Limited evidence",
                },
                "claims": [
                    {
                        "text": "Mocked regulatory finding",
                        "source_ids": [0],
                        "source_urls": ["https://example.com"],
                        "sources": [{"id": 0, "url": "https://example.com", "title": "Test", "provider": "tavily", "date": ""}],
                        "confidence_score": 0.72,
                        "confidence_label": "MEDIUM",
                        "basis": "Single source",
                    }
                ],
                "contradiction_notes": [],
                "suggested_follow_ups": ["What are the latest regulatory updates?"],
                "related_entities": [{"name": "NUPRC", "type": "regulator", "relevance": "Primary regulator", "mention_count": 1}],
                "methodology_note": "This analysis draws on 1 source across 1 dimension.",
                "rendered_report": "## Executive Summary\n\nMocked report.",
                "source_appendix": [
                    {"id": 0, "url": "https://example.com", "provider": "tavily", "title": "Test", "date": "", "credibility_tier": "core", "credibility_rank": 4}
                ],
            },
            "evidence_summary": {
                "total_documents_retrieved": 5,
                "documents_used_in_synthesis": 3,
                "unique_sources": 1,
                "active_dimensions": ["regulatory"],
                "gaps": [],
            },
        }


class SynthesizeEndpointTests(unittest.TestCase):
    def test_synthesize_endpoint_returns_full_pipeline_contract(self) -> None:
        app = create_app()
        client = TestClient(app)

        with (
            patch("cerebro.api.app.ResearchPlanner", return_value=_FakePlanner()),
            patch("cerebro.api.app.ResearchOrchestrator", return_value=_FakeOrchestrator()),
            patch("cerebro.api.app.ResearchSynthesizer", return_value=_FakeSynthesizer()),
        ):
            response = client.post(
                "/api/research/synthesize",
                json={
                    "query": "test query",
                    "entity_id": "entity-1",
                    "entity_name": "Test Entity",
                    "thinking_mode": False,
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()

        # Top-level contract fields
        self.assertIn("request_id", payload)
        self.assertIn("query", payload)
        self.assertIn("entity_name", payload)
        self.assertIn("rendered_report", payload)

        # Structured report
        self.assertIn("report", payload)
        report = payload["report"]
        self.assertIn("executive_summary", report)
        self.assertIn("detailed_analysis", report)
        self.assertIn("key_findings", report)
        self.assertIn("key_data_points", report)
        self.assertIn("timeline", report)
        self.assertIn("risk_assessment", report)
        self.assertIn("confidence", report)
        self.assertIn("contradictions", report)

        # Citation infrastructure
        self.assertIn("sources", payload)
        self.assertIn("claims", payload)
        self.assertIsInstance(payload["claims"], list)
        if payload["claims"]:
            claim = payload["claims"][0]
            self.assertIn("source_ids", claim)
            self.assertIn("sources", claim)

        # Methodology
        self.assertIn("methodology", payload)
        methodology = payload["methodology"]
        self.assertIn("dimensions_searched", methodology)
        self.assertIn("dimensions_active", methodology)
        self.assertIn("documents_retrieved", methodology)

        # Follow-ups and related entities
        self.assertIn("suggested_follow_ups", payload)
        self.assertIn("related_entities", payload)

        # Diagnostics
        self.assertIn("diagnostics", payload)
        self.assertIn("evidence_quality", payload["diagnostics"])

        # Backward compatibility
        self.assertIn("plan", payload)
        self.assertIn("agent_results", payload)
        self.assertIn("synthesis", payload)


if __name__ == "__main__":
    unittest.main()

