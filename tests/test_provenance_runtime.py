import unittest

from common.provenance.models import EvidenceRecord, ProvenanceBundle, SourceRecord
from common.provenance.runtime import RuntimeProvenanceStore
from ReportEngine.core.stitcher import DocumentComposer


class RuntimeProvenanceTests(unittest.TestCase):
    def test_empty_engine_result_is_retained_for_the_current_run(self):
        store = RuntimeProvenanceStore()
        run_id = store.begin("test topic", ["query", "insight"])
        store.publish(
            run_id,
            "query",
            "test topic",
            "query report",
            ProvenanceBundle(agent="query_engine"),
        )
        store.publish(
            run_id,
            "insight",
            "test topic",
            "no internal evidence",
            ProvenanceBundle(agent="insight_engine"),
        )

        inputs = store.inputs(run_id, "test topic")

        self.assertEqual(inputs["reports"], ["query report", "", "no internal evidence"])
        self.assertEqual(inputs["provenance_bundle"].evidence, [])

    def test_document_composer_rejects_external_evidence_without_a_source_url(self):
        bundle = ProvenanceBundle(
            agent="query_engine",
            sources=[SourceRecord(source_id="source-1", source_type="web", title="missing link")],
            evidence=[
                EvidenceRecord(
                    evidence_id="evidence-1",
                    source_id="source-1",
                    agent="query_engine",
                    evidence_type="web",
                    snippet="A claimed fact.",
                )
            ],
        )
        chapter = {
            "chapterId": "S1",
            "title": "Evidence",
            "order": 10,
            "blocks": [
                {
                    "type": "paragraph",
                    "inlines": [{"text": "A claimed fact."}],
                    "claims": [
                        {
                            "claim_id": "claim-1",
                            "text": "A claimed fact.",
                            "claim_type": "fact",
                            "evidence_ids": ["evidence-1"],
                        }
                    ],
                }
            ],
        }

        document = DocumentComposer().build_document("report-1", {}, [chapter], bundle)

        self.assertEqual(document["provenanceIndex"]["evidence"], {})
        blocks = document["chapters"][0]["blocks"]
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0]["type"], "heading")
        self.assertNotIn("本段未检索到可追溯证据", str(blocks))


if __name__ == "__main__":
    unittest.main()
