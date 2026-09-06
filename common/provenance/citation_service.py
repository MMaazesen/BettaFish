"""Resolve claim/evidence references into renderer-friendly citation details."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping

from .models import EvidenceRecord, ProvenanceBundle, SourceRecord


class CitationService:
    def __init__(self, provenance: ProvenanceBundle | Mapping[str, Any] | None = None):
        self.bundle = provenance if isinstance(provenance, ProvenanceBundle) else ProvenanceBundle.from_dict(provenance)
        self.sources: Dict[str, SourceRecord] = {item.source_id: item for item in self.bundle.sources}
        self.evidence: Dict[str, EvidenceRecord] = {item.evidence_id: item for item in self.bundle.evidence}
        self._numbers: Dict[str, int] = {}

    def evidence_ids_for_block(self, block: Mapping[str, Any]) -> List[str]:
        ids: List[str] = []
        ids.extend(str(item) for item in block.get("citation_refs", []) if item)
        for claim in block.get("claims", []) or []:
            if not isinstance(claim, Mapping):
                continue
            if claim.get("support_status") == "unsupported" or claim.get("status") == "unsupported":
                continue
            ids.extend(str(item) for item in claim.get("evidence_ids", []) if item)
        return list(dict.fromkeys(item for item in ids if item in self.evidence))

    def number_for(self, evidence_id: str) -> int:
        if evidence_id not in self._numbers:
            self._numbers[evidence_id] = len(self._numbers) + 1
        return self._numbers[evidence_id]

    def details_for_ids(self, evidence_ids: Iterable[str]) -> List[Dict[str, Any]]:
        details = []
        for evidence_id in evidence_ids:
            evidence = self.evidence.get(str(evidence_id))
            if evidence is None:
                continue
            source = self.sources.get(evidence.source_id, SourceRecord(source_id=evidence.source_id))
            details.append(
                {
                    "number": self.number_for(evidence.evidence_id),
                    "evidence_id": evidence.evidence_id,
                    "source_id": evidence.source_id,
                    "title": source.title or source.platform or evidence.evidence_id,
                    "url": source.url,
                    "platform": source.platform or source.meta.get("domain", ""),
                    "author": source.author,
                    "publish_time": source.publish_time,
                    "retrieved_time": source.retrieved_time,
                    "locator": source.locator,
                    "evidence_type": evidence.evidence_type,
                    "snippet": evidence.snippet,
                    "scope": evidence.scope,
                    "selection_reason": evidence.meta.get("selection_reason", ""),
                }
            )
        return details
