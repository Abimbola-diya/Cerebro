from __future__ import annotations

import unittest

from cerebro.research.agents.synthesis import ResearchSynthesizer


class SynthesisNormalizationTests(unittest.TestCase):
    def test_normalize_synthesis_output_adds_confidence_and_claims(self) -> None:
        synthesizer = ResearchSynthesizer()
        source_index = [
            {"id": 0, "url": "https://example.com/source", "title": "Test Source", "provider": "tavily", "date": ""},
        ]
        output = {
            "status": "partial",
            "brief": "Acme appears exposed to medium compliance risk [0].",
            "executive_summary": "Executive summary [0].",
            "one_paragraph_summary": "Summary [0].",
            "claims": [
                {
                    "text": "Acme received a warning notice.",
                    "source_ids": [0],
                    "confidence_score": 0.85,
                    "confidence_label": "HIGH",
                }
            ],
            "key_findings": [],
            "key_data_points": [],
            "timeline": [],
            "key_tensions": [],
            "risk_register": [],
            "forward_indicators": [],
            "confidence_assessment": {"overall": "MEDIUM", "rationale": "Limited evidence"},
            "contradiction_notes": [],
            "suggested_follow_ups": ["Follow up question?"],
            "related_entities": [],
            "methodology_note": "Test methodology.",
        }

        normalized = synthesizer._normalize_synthesis_output(output=output, source_index=source_index)

        self.assertEqual(normalized["status"], "PARTIAL")
        self.assertEqual(len(normalized["claims"]), 1)
        self.assertIn("confidence_score", normalized["claims"][0])
        self.assertIn("confidence_label", normalized["claims"][0])
        # Inline citations should be preserved
        self.assertIn("[0]", normalized["brief"])
        self.assertIn("[0]", normalized["executive_summary"])
        # New fields should be present
        self.assertIn("rendered_report", normalized)
        self.assertIn("suggested_follow_ups", normalized)
        self.assertIn("related_entities", normalized)
        self.assertIn("methodology_note", normalized)
        self.assertIn("source_appendix", normalized)
        # Source appendix should have credibility data
        if normalized["source_appendix"]:
            self.assertIn("credibility_tier", normalized["source_appendix"][0])
        # Claims should have resolved sources
        claim = normalized["claims"][0]
        self.assertIn("sources", claim)
        self.assertIn("source_urls", claim)

    def test_normalize_strips_invalid_citations(self) -> None:
        synthesizer = ResearchSynthesizer()
        source_index = [
            {"id": 0, "url": "https://example.com", "title": "Test", "provider": "tavily", "date": ""},
        ]
        output = {
            "status": "COMPLETE",
            "brief": "Valid citation [0] and invalid citation [99] and dimension [dimension_1_regulatory].",
            "claims": [],
        }

        normalized = synthesizer._normalize_synthesis_output(output=output, source_index=source_index)

        # Valid citation preserved, invalid stripped, dimension reference stripped
        self.assertIn("[0]", normalized["brief"])
        self.assertNotIn("[99]", normalized["brief"])
        self.assertNotIn("dimension_1", normalized["brief"])

    def test_rendered_report_contains_sections(self) -> None:
        synthesizer = ResearchSynthesizer()
        source_index = [
            {"id": 0, "url": "https://example.com", "title": "Test Source", "provider": "tavily", "date": "2026-03-15", "source_tier": "core", "credibility_rank": 5},
        ]
        output = {
            "status": "COMPLETE",
            "brief": "Analysis text [0].",
            "executive_summary": "Executive summary [0].",
            "one_paragraph_summary": "Summary.",
            "key_findings": [{"finding": "Test finding", "source_ids": [0], "confidence": "HIGH", "dimensions_involved": [], "significance": "Important"}],
            "key_data_points": [{"metric": "Revenue", "value": "$1B", "period": "FY2025", "source_ids": [0]}],
            "risk_register": [{"risk": "Regulatory risk", "mechanism": "New law", "severity": "HIGH", "likelihood": "MEDIUM", "source_ids": [0], "evidence_strength": "2 dims", "mitigating_factors": "Legal team"}],
            "forward_indicators": [{"indicator": "License renewal", "why_it_matters": "Critical", "timeframe": "Q3 2026", "source_ids": [0]}],
            "claims": [],
            "key_tensions": [],
            "timeline": [],
            "confidence_assessment": {"overall": "MEDIUM"},
            "contradiction_notes": [],
            "suggested_follow_ups": ["What next?"],
            "related_entities": [],
            "methodology_note": "Test methodology.",
        }

        normalized = synthesizer._normalize_synthesis_output(output=output, source_index=source_index)
        report = normalized["rendered_report"]

        self.assertIn("## Executive Summary", report)
        self.assertIn("## Detailed Analysis", report)
        self.assertIn("## Key Findings", report)
        self.assertIn("## Key Data Points", report)
        self.assertIn("## Risk Assessment", report)
        self.assertIn("## Forward Indicators", report)
        self.assertIn("## References", report)
        self.assertIn("## Suggested Follow-up Questions", report)
        self.assertIn("https://example.com", report)


if __name__ == "__main__":
    unittest.main()
