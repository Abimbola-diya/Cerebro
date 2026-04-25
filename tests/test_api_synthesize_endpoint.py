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
                "status": "COMPLETED",
                "synthesis": "Mock synthesized output",
                "claims": [
                    {
                        "text": "Mocked regulatory finding",
                        "source_ids": [0],
                        "confidence_score": 0.72,
                        "confidence_label": "MEDIUM",
                    }
                ],
                "overall_confidence_score": 0.72,
                "overall_confidence_label": "MEDIUM",
                "unresolved_gaps": [],
                "contradiction_notes": [],
            },
            "evidence_summary": {
                "total_sources": 1,
                "total_evidence_items": 1,
                "active_dimensions": ["regulatory"],
                "retrieval_gaps": [],
                "errors": [],
                "conflict_flags": [],
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
        self.assertIn("request_id", payload)
        self.assertIn("plan", payload)
        self.assertIn("agent_results", payload)
        self.assertIn("synthesis", payload)
        self.assertIn("working_files", payload)

        synthesis = payload["synthesis"]
        self.assertIn("synthesis_output", synthesis)
        self.assertIn("evidence_summary", synthesis)
        self.assertIn("overall_confidence_score", synthesis["synthesis_output"])


if __name__ == "__main__":
    unittest.main()
