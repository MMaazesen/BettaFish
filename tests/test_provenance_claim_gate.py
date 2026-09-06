import unittest

from common.provenance.models import ClaimRecord, EvidenceRecord, ProvenanceBundle, SourceRecord
from common.provenance.validators import filter_valid_evidence, gate_claim, sanitize_claim_block


class ClaimGateTests(unittest.TestCase):
    def test_fact_and_metric_require_evidence(self):
        fact = gate_claim(ClaimRecord(claim_id="f", text="fact", claim_type="fact"), {"e1"})
        metric = gate_claim(ClaimRecord(claim_id="m", text="42%", claim_type="metric"), {"e1"})
        self.assertFalse(fact.allowed)
        self.assertFalse(metric.allowed)

    def test_inference_requires_two_and_prediction_is_marked(self):
        weak = gate_claim(
            ClaimRecord(claim_id="i", text="inference", claim_type="inference", evidence_ids=["e1"]),
            {"e1", "e2"},
        )
        strong = gate_claim(
            ClaimRecord(claim_id="i2", text="inference", claim_type="inference", evidence_ids=["e1", "e2"]),
            {"e1", "e2"},
        )
        prediction = gate_claim(ClaimRecord(claim_id="p", text="future", claim_type="prediction"), set())
        self.assertTrue(weak.allowed)
        self.assertEqual(weak.claim.status, "weak")
        self.assertEqual(strong.claim.status, "supported")
        self.assertEqual(prediction.claim.status, "predicted")

    def test_removes_only_unsupported_fact_from_mixed_block(self):
        block = {
            "type": "paragraph",
            "inlines": [{"text": "Supported fact. Unsupported fact."}],
            "claims": [
                {"claim_id": "ok", "text": "Supported fact.", "claim_type": "fact", "evidence_ids": ["e1"]},
                {"claim_id": "bad", "text": "Unsupported fact.", "claim_type": "fact", "evidence_ids": []},
            ],
        }
        sanitized = sanitize_claim_block(block, {"e1"})
        text = "".join(item["text"] for item in sanitized["inlines"])
        self.assertIn("Supported fact.", text)
        self.assertNotIn("Unsupported fact.", text)
        self.assertEqual(sanitized["citation_refs"], ["e1"])

    def test_empty_block_falls_back_only_after_all_claims_removed(self):
        block = {
            "type": "paragraph",
            "inlines": [{"text": "Unsupported fact."}],
            "claims": [{"claim_id": "bad", "text": "Unsupported fact.", "claim_type": "fact"}],
        }
        sanitized = sanitize_claim_block(block, set())
        self.assertEqual(sanitized["inlines"][0]["text"], "本段未检索到可追溯证据。")

    def test_insight_evidence_without_internal_lineage_is_filtered(self):
        bundle = ProvenanceBundle(
            agent="insight_engine",
            sources=[SourceRecord(source_id="db", source_type="database", locator={"table": "posts"})],
            evidence=[
                EvidenceRecord(
                    evidence_id="bad-db-row",
                    source_id="db",
                    agent="insight_engine",
                    evidence_type="db_row",
                    snippet="42 orders",
                    scope={"table": "posts", "sample_size": 1},
                )
            ],
        )
        self.assertEqual(filter_valid_evidence(bundle).evidence, [])


if __name__ == "__main__":
    unittest.main()
