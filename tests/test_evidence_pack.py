from __future__ import annotations

import unittest

from cerebro.research.agents.adapter import ResearchWorkingState
from cerebro.research.agents.evidence_pack import EvidencePackBuilder


class EvidencePackBuilderTests(unittest.TestCase):
    def test_build_deduplicates_sources_and_sorts_evidence(self) -> None:
        builder = EvidencePackBuilder()
        plan = {"query": "query", "entity_name": "entity"}
        working_state = ResearchWorkingState(request_id="req-1")
        agent_results = {
            "regulatory": {
                "dimension": "regulatory",
                "documents": [
                    {
                        "content": "First document",
                        "relevance_score": 0.6,
                        "provider": "tavily",
                        "url": "https://example.com/a",
                    },
                    {
                        "content": "Second document",
                        "relevance_score": 0.9,
                        "provider": "tavily",
                        "url": "https://example.com/a",
                    },
                ],
                "retrieval_gaps": ["Need official filing"],
                "errors": [],
            }
        }

        pack = builder.build(plan=plan, working_state=working_state, agent_results=agent_results)
        payload = pack.to_dict()

        self.assertEqual(payload["query"], "query")
        self.assertEqual(len(payload["sources"]), 1)
        self.assertEqual(payload["evidence"][0]["relevance_score"], 0.9)
        self.assertEqual(payload["evidence"][1]["relevance_score"], 0.6)
        self.assertEqual(payload["gaps"], ["Need official filing"])


if __name__ == "__main__":
    unittest.main()
