"""Unified provenance contracts used by all BettaFish engines."""

from .citation_service import CitationService
from .models import ClaimRecord, EvidenceRecord, ProvenanceBundle, SourceRecord
from .normalizer import (
    add_search_results_to_bundle,
    dedupe_bundle,
    evidence_dedupe_key,
    merge_bundles,
    records_from_search_result,
)
from .selector import EvidenceSelector
from .validators import (
    ClaimGateResult,
    filter_valid_evidence,
    gate_claim,
    gate_claims,
    is_valid_evidence,
    sanitize_claim_block,
)

__all__ = [
    "CitationService",
    "ClaimGateResult",
    "ClaimRecord",
    "EvidenceRecord",
    "EvidenceSelector",
    "ProvenanceBundle",
    "SourceRecord",
    "add_search_results_to_bundle",
    "dedupe_bundle",
    "evidence_dedupe_key",
    "filter_valid_evidence",
    "gate_claim",
    "gate_claims",
    "merge_bundles",
    "is_valid_evidence",
    "records_from_search_result",
    "sanitize_claim_block",
]
