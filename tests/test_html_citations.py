import unittest

from common.provenance.citation_service import CitationService
from common.provenance.models import EvidenceRecord, ProvenanceBundle, SourceRecord
from ReportEngine.core.stitcher import DocumentComposer
from ReportEngine.renderers.html_renderer import HTMLRenderer


class HtmlCitationTests(unittest.TestCase):
    def test_paragraph_renders_clickable_hover_citation(self):
        bundle = ProvenanceBundle(
            sources=[
                SourceRecord(
                    source_id="s1",
                    title="Official release",
                    url="https://example.com/original",
                    platform="example.com",
                    publish_time="2026-09-01",
                )
            ],
            evidence=[
                EvidenceRecord(
                    evidence_id="e1",
                    source_id="s1",
                    snippet="The reported value was 42.",
                    meta={"selection_reason": "直接匹配章节主题"},
                )
            ],
        )
        renderer = HTMLRenderer()
        renderer.citation_service = CitationService(bundle)
        html = renderer._render_paragraph(
            {
                "type": "paragraph",
                "inlines": [{"text": "The value was 42."}],
                "claims": [
                    {
                        "claim_id": "c1",
                        "text": "The value was 42.",
                        "claim_type": "metric",
                        "evidence_ids": ["e1"],
                        "support_status": "supported",
                    }
                ],
                "citation_refs": ["e1"],
                "support_status": "supported",
            }
        )
        self.assertIn('class="citation-ref"', html)
        self.assertIn('href="https://example.com/original"', html)
        self.assertIn("Official release", html)
        self.assertIn("The reported value was 42.", html)
        self.assertIn("直接匹配章节主题", html)

    def test_composed_document_carries_a_claim_through_to_clickable_html(self):
        bundle = ProvenanceBundle(
            sources=[
                SourceRecord(
                    source_id="official-source",
                    source_type="news",
                    title="Official announcement",
                    url="https://example.com/announcement",
                    platform="example.com",
                    publish_time="2026-09-01",
                )
            ],
            evidence=[
                EvidenceRecord(
                    evidence_id="official-evidence",
                    source_id="official-source",
                    agent="query_engine",
                    evidence_type="news",
                    snippet="The official announcement reports 42 completed cases.",
                    meta={"selection_reason": "官方公告直接给出该指标"},
                )
            ],
        )
        chapter = {
            "chapterId": "S1",
            "title": "Findings",
            "order": 10,
            "blocks": [
                {"type": "heading", "level": 2, "text": "Findings", "anchor": "findings"},
                {
                    "type": "paragraph",
                    "inlines": [{"text": "The official announcement reports 42 completed cases."}],
                    "claims": [
                        {
                            "claim_id": "completed-cases",
                            "text": "The official announcement reports 42 completed cases.",
                            "claim_type": "metric",
                            "evidence_ids": ["official-evidence"],
                        }
                    ],
                },
            ],
        }

        document = DocumentComposer().build_document("report-1", {}, [chapter], bundle)
        html = HTMLRenderer().render(document)

        self.assertIn("official-evidence", document["provenanceIndex"]["evidence"])
        self.assertIn("completed-cases", document["claimIndex"])
        self.assertTrue(document["provenanceEnforced"])
        self.assertIn('href="https://example.com/announcement"', html)
        self.assertIn('class="citation-ref"', html)
        self.assertIn("引用理由：官方公告直接给出该指标", html)


if __name__ == "__main__":
    unittest.main()
