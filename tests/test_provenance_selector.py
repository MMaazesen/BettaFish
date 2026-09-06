import unittest

from common.provenance.models import EvidenceRecord, ProvenanceBundle, SourceRecord
from common.provenance.selector import EvidenceSelector


class EvidenceSelectorTests(unittest.TestCase):
    def test_selects_only_top_k_relevant_evidence(self):
        bundle = ProvenanceBundle(
            sources=[SourceRecord(source_id=f"s{i}", title=f"source {i}") for i in range(4)],
            evidence=[
                EvidenceRecord(evidence_id="climate-1", source_id="s0", snippet="climate policy and carbon market"),
                EvidenceRecord(evidence_id="sports-1", source_id="s1", snippet="football league score"),
                EvidenceRecord(evidence_id="climate-2", source_id="s2", snippet="carbon emissions policy update"),
                EvidenceRecord(evidence_id="music-1", source_id="s3", snippet="concert ticket sales"),
            ],
        )

        selected = EvidenceSelector(top_k=2).select(bundle, chapter_topic="climate carbon policy")

        self.assertEqual(len(selected.evidence), 2)
        self.assertEqual({item.evidence_id for item in selected.evidence}, {"climate-1", "climate-2"})
        self.assertLess(len(selected.evidence), len(bundle.evidence))
        self.assertTrue(all(item.meta.get("selection_reason") for item in selected.evidence))


if __name__ == "__main__":
    unittest.main()
