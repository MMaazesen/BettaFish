"""Evidence admission and claim-level gates. Never promote generated text to evidence."""

from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass
from typing import Any, Iterable, List, Mapping, Sequence, Tuple
from urllib.parse import urlparse

from .models import ClaimRecord, EvidenceRecord, ProvenanceBundle, SourceRecord
from .normalizer import stable_id


FACT_TYPES = {"fact", "metric"}
FORECAST_TYPES = {"prediction", "recommendation"}
VALID_STATUSES = {"supported", "weak", "unsupported", "predicted"}
EMPTY_MESSAGE = "本段未检索到可追溯证据。"
_RAW_TYPES = {"web", "social", "news", "text", "search_result", "ocr", "video", "comment", "multimodal", "db_row", "db_agg"}


def is_valid_evidence(record: EvidenceRecord, source: SourceRecord | None = None) -> bool:
    if not source or not record.evidence_id or not record.snippet.strip():
        return False
    if source.source_id != record.source_id:
        return False
    if "forum" in record.agent.lower() or "forum" in source.agent.lower():
        return False
    evidence_type = record.evidence_type.lower()
    if evidence_type not in _RAW_TYPES or source.source_type.lower() not in _RAW_TYPES | {"database"}:
        return False
    if evidence_type in {"db_row", "db_agg"} or record.agent == "insight_engine":
        if evidence_type not in {"db_row", "db_agg"}:
            return False
        scope = record.scope
        required = {"query_time", "table", "filters", "time_window", "sample_size", "aggregation_method", "row_ids"}
        if not required.issubset(scope):
            return False
        if not all(scope.get(key) for key in ("query_time", "table", "time_window", "aggregation_method", "row_ids")):
            return False
        if not isinstance(scope["filters"], Mapping) or not isinstance(scope["time_window"], Mapping):
            return False
        if not isinstance(scope["row_ids"], list) or any(item in (None, "") for item in scope["row_ids"]):
            return False
        try:
            if int(scope["sample_size"]) <= 0:
                return False
        except (TypeError, ValueError, OverflowError):
            return False
        if evidence_type == "db_row" and scope.get("primary_key", scope.get("record_id")) in (None, ""):
            return False
        if evidence_type == "db_agg" and not scope.get("metric"):
            return False
        return True
    try:
        parsed = urlparse(source.url)
        has_url = parsed.scheme.lower() in {"https", "http"} and bool(parsed.netloc)
    except ValueError:
        has_url = False
    # A locator alone must identify a platform record, not an arbitrary label.
    has_record = bool(source.platform and (source.locator.get("post_id") or source.locator.get("comment_id")))
    return bool(has_url or has_record)


def filter_valid_evidence(bundle: ProvenanceBundle) -> ProvenanceBundle:
    result = copy.deepcopy(bundle)
    source_index = {item.source_id: item for item in result.sources}
    result.evidence = [item for item in result.evidence if is_valid_evidence(item, source_index.get(item.source_id))]
    source_ids = {item.source_id for item in result.evidence}
    result.sources = [item for item in result.sources if item.source_id in source_ids]
    result.claims, _ = gate_claims(result.claims, result)
    return result


@dataclass
class ClaimGateResult:
    claim: ClaimRecord
    allowed: bool
    reason: str = ""


def _numbers(text: str) -> set[str]:
    return set(re.findall(r"(?<![A-Za-z])\d+(?:\.\d+)?", text.replace(",", "")))


def gate_claim(claim: ClaimRecord | Mapping[str, Any], available_evidence_ids: Iterable[str] | ProvenanceBundle) -> ClaimGateResult:
    record = copy.deepcopy(claim) if isinstance(claim, ClaimRecord) else ClaimRecord.from_dict(claim)
    bundle = available_evidence_ids if isinstance(available_evidence_ids, ProvenanceBundle) else None
    evidence_index = {item.evidence_id: item for item in bundle.evidence} if bundle else {}
    available = set(evidence_index) if bundle else set(available_evidence_ids)
    aliases = bundle.meta.get("evidence_aliases", {}) if bundle else {}
    refs = [aliases.get(item, item) for item in record.evidence_ids]
    record.evidence_ids = list(dict.fromkeys(item for item in refs if item in available))
    record.claim_type = (record.claim_type or "fact").lower()
    if not record.text.strip():
        return ClaimGateResult(record, False, "claim 缺少正文")
    if not record.claim_id:
        record.claim_id = stable_id("claim", record.claim_type, record.text, record.evidence_ids)
    if bundle and record.evidence_ids:
        evidence = [evidence_index[item] for item in record.evidence_ids]
        for key in ("subject", "time_range", "platform", "condition"):
            values = [item.scope.get(key) for item in evidence if item.scope.get(key)]
            if values and all(value == values[0] for value in values):
                record.scope.setdefault(key, copy.deepcopy(values[0]))
        if record.claim_type in FACT_TYPES:
            # Retrieval dates and other metadata do not substantiate factual numbers.
            support_text = " ".join(item.snippet + " " + json.dumps(item.normalized_value, ensure_ascii=False) for item in evidence)
            if not _numbers(record.text).issubset(_numbers(support_text)):
                record.evidence_ids = []

    if record.claim_type in FACT_TYPES:
        allowed = bool(record.evidence_ids)
        record.status = record.support_level = "supported" if allowed else "unsupported"
        return ClaimGateResult(record, allowed, "事实或指标必须绑定有效证据，数字必须出现在证据中")
    if record.claim_type == "inference":
        count = len(record.evidence_ids)
        record.status = record.support_level = "supported" if count >= 2 else "weak" if count else "unsupported"
        return ClaimGateResult(record, bool(count), "推断少于两条证据时降级为弱支持")
    if record.claim_type in FORECAST_TYPES:
        record.status = record.support_level = "predicted"
        record.meta["display_label"] = "预测" if record.claim_type == "prediction" else "建议"
        return ClaimGateResult(record, True, "预测或建议必须单独显示")
    record.status = record.support_level = "unsupported"
    return ClaimGateResult(record, False, "未知 claim 类型")


def gate_claims(claims: Sequence[ClaimRecord | Mapping[str, Any]] | None, available_evidence_ids: Iterable[str] | ProvenanceBundle) -> Tuple[List[ClaimRecord], List[ClaimGateResult]]:
    accepted, rejected = [], []
    available = available_evidence_ids if isinstance(available_evidence_ids, ProvenanceBundle) else set(available_evidence_ids)
    for claim in claims or []:
        if not isinstance(claim, (ClaimRecord, Mapping)):
            continue
        result = gate_claim(claim, available)
        (accepted if result.allowed else rejected).append(result.claim if result.allowed else result)
    return accepted, rejected


def _claim_paragraph(claims: List[ClaimRecord], empty_message: str = EMPTY_MESSAGE) -> dict:
    cursor, parts = 0, []
    for claim in claims:
        if parts:
            cursor += 1
        claim.text_span = {"start": cursor, "end": cursor + len(claim.text)}
        cursor += len(claim.text)
        parts.append(claim.text)
    statuses = {item.status for item in claims}
    return {
        "type": "paragraph",
        "inlines": [{"text": " ".join(parts) if parts else empty_message}],
        "claims": [item.to_dict() for item in claims],
        "citation_refs": list(dict.fromkeys(ref for item in claims for ref in item.evidence_ids)),
        "support_status": "predicted" if "predicted" in statuses else "weak" if "weak" in statuses else "supported" if claims else "unsupported",
    }


def sanitize_claim_block(block: Mapping[str, Any], available_evidence_ids: Iterable[str] | ProvenanceBundle, *, empty_message: str = EMPTY_MESSAGE) -> dict:
    """Rebuild from allowed claims so unclaimed text cannot hitchhike on a citation."""
    accepted, _ = gate_claims(block.get("claims"), available_evidence_ids)
    return _claim_paragraph(accepted, empty_message)


def sanitize_blocks(blocks: Any, evidence: Iterable[str] | ProvenanceBundle) -> list[dict]:
    """Gate nested content and split forecasts from facts, preserving accepted claims."""
    if not isinstance(blocks, list):
        return []
    result = []
    for block in blocks:
        if not isinstance(block, Mapping):
            continue
        kind = block.get("type")
        if kind in {"heading", "hr", "pageBreak"} and not block.get("claims"):
            result.append(copy.deepcopy(dict(block)))
            continue
        accepted, _ = gate_claims(block.get("claims"), evidence)
        groups: dict[str, list[ClaimRecord]] = {}
        for claim in accepted:
            group = claim.claim_type if claim.claim_type in FORECAST_TYPES else claim.status
            groups.setdefault(group, []).append(claim)
        own = [_claim_paragraph(items) for items in groups.values()]
        children = sanitize_blocks(block.get("blocks"), evidence)
        for item in block.get("items", []) or []:
            if isinstance(item, list):
                children.extend(sanitize_blocks(item, evidence))
        for row in block.get("rows", []) or []:
            if not isinstance(row, Mapping):
                continue
            for cell in row.get("cells", []) or []:
                if isinstance(cell, Mapping):
                    children.extend(sanitize_blocks(cell.get("blocks"), evidence))
        valid_children = [child for child in children if child.get("claims") or child.get("type") == "heading"]
        # Unsupported leaf blocks carry no user-visible information.  Dropping
        # them here keeps the IR free of repeated "no evidence" placeholders;
        # headings are preserved above so chapter structure and anchors remain
        # stable even when a subsection has no admissible claims.
        if own or valid_children:
            result.extend(own + valid_children)
    return result
