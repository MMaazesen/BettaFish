import unittest

from common.provenance.models import EvidenceRecord, ProvenanceBundle, SourceRecord
from common.provenance.normalizer import dedupe_bundle


class ProvenanceDedupeTests(unittest.TestCase):
    def _deduped_count(self, evidence_type, locator=None, scope=None, snippet="same"):
        locator = locator or {}
        scope = scope or {}
        bundle = ProvenanceBundle(
            sources=[
                SourceRecord(source_id="s1", source_type="web", url="https://example.com/item", locator=locator),
                SourceRecord(source_id="s2", source_type="web", url="https://example.com/item/", locator=locator),
            ],
            evidence=[
                EvidenceRecord(evidence_id="e1", source_id="s1", evidence_type=evidence_type, snippet=snippet, scope=scope),
                EvidenceRecord(evidence_id="e2", source_id="s2", evidence_type=evidence_type, snippet=snippet, scope=scope),
            ],
        )
        return len(dedupe_bundle(bundle).evidence)

    def test_web_uses_url_locator_and_content_hash(self):
        self.assertEqual(self._deduped_count("web", locator={"page": 2}), 1)

    def test_video_comment_uses_post_comment_timestamp(self):
        scope = {"post_id": "p1", "comment_id": "c1", "timestamp": "00:42"}
        self.assertEqual(self._deduped_count("comment", scope=scope), 1)

    def test_db_row_uses_table_and_primary_key(self):
        self.assertEqual(self._deduped_count("db_row", scope={"table": "posts", "primary_key": 7}), 1)

    def test_db_agg_uses_full_query_signature(self):
        scope = {
            "table": "posts",
            "metric": "count",
            "filters": {"platform": "weibo"},
            "time_window": {"start": "2026-01-01", "end": "2026-01-31"},
            "aggregation_method": "count",
        }
        self.assertEqual(self._deduped_count("db_agg", scope=scope), 1)


if __name__ == "__main__":
    unittest.main()
