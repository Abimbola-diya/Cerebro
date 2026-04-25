from __future__ import annotations

import unittest

from cerebro.research.agents.synthesis import ResearchSynthesizer


class SynthesisNormalizationTests(unittest.TestCase):
    def test_normalize_synthesis_output_adds_confidence_and_claims(self) -> None:
        synthesizer = ResearchSynthesizer()
        filtered_pack = {
            "query": "Acme compliance risk",
            "sources": [{"id": 0, "url": "https://example.com/source"}],
            "evidence": [
                {
                    "content": "Acme received a warning notice.",
                    "relevance_score": 0.85,
                    "source_id": 0,
                }
            ],
            "gaps": ["Need latest filing"],
            "conflict_flags": ["Source A conflicts with Source B on timeline"],
        }
        output = {
            "status": "partial",
            "synthesis": "Acme appears exposed to medium compliance risk.",
            "claims": [
                {
                    "text": "Acme received a warning notice.",
                    "source_ids": [0],
                }
            ],
        }

        normalized = synthesizer._normalize_synthesis_output(output=output, filtered_pack=filtered_pack)

        self.assertEqual(normalized["status"], "PARTIAL")
        self.assertEqual(normalized["overall_confidence_label"], "HIGH")
        self.assertEqual(len(normalized["claims"]), 1)
        self.assertIn("confidence_score", normalized["claims"][0])
        self.assertIn("confidence_label", normalized["claims"][0])
        self.assertIn("Source A conflicts with Source B on timeline", normalized["contradiction_notes"])


if __name__ == "__main__":
    unittest.main()
