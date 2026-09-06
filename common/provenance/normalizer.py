"""Provenance normalization, stable identifiers, and typed deduplication."""

from __future__ import annotations

import hashlib
import json
import re
import copy
from dataclasses import replace
from typing import Any, Dict, Iterable, Mapping, Tuple
from urllib.parse import urlparse, urlunparse

from .models import ClaimRecord, EvidenceRecord, ProvenanceBundle, SourceRecord, utc_now_iso


def stable_id(prefix: str, *parts: Any) -> str:
    payload = json.dumps(parts, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))
    return f"{prefix}_{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:20]}"


def content_hash(content: Any) -> str:
    normalized = re.sub(r"\s+", " ", str(content or "")).strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def normalize_url(url: str) -> str:
    value = str(url or "").strip()
    if not value:
        return ""
    try:
        parsed = urlparse(value)
        return urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path.rstrip("/"), "", parsed.query, ""))
    except ValueError:
        return value


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))


def _lookup(record: EvidenceRecord, source: SourceRecord | None, key: str, default: Any = "") -> Any:
    for mapping in (record.scope, record.meta, source.locator if source else {}, source.meta if source else {}):
        if key in mapping and mapping[key] not in (None, "", [], {}):
            return mapping[key]
    return default


def evidence_dedupe_key(record: EvidenceRecord, source: SourceRecord | None = None) -> Tuple[str, ...]:
    """Return a source-type-specific identity key for one evidence record."""
    evidence_type = (record.evidence_type or "").lower()
    source_type = (source.source_type if source else "").lower()
    kind = evidence_type or source_type

    if kind == "db_row":
        return (
            "db_row",
            str(_lookup(record, source, "table")),
            _canonical(_lookup(record, source, "primary_key", _lookup(record, source, "record_id"))),
        )
    if kind == "db_agg":
        return (
            "db_agg",
            str(_lookup(record, source, "table")),
            str(_lookup(record, source, "metric")),
            _canonical(_lookup(record, source, "filters", {})),
            _canonical(_lookup(record, source, "time_window", {})),
            str(_lookup(record, source, "aggregation_method")),
        )
    if kind in {"video", "comment"} or source_type in {"video", "comment"}:
        post_id = _lookup(record, source, "post_id")
        comment_id = _lookup(record, source, "comment_id")
        timestamp = _lookup(record, source, "timestamp")
        if not post_id and not comment_id:
            return (kind, normalize_url(source.url if source else ""), str(timestamp), content_hash(record.snippet))
        return (
            "video_comment",
            source.platform.lower() if source else "",
            str(post_id), str(comment_id), str(timestamp),
        )
    if kind in {"web", "social", "text", "search_result", "ocr", "multimodal", "image_metadata"} or source_type in {"web", "social", "news"}:
        url = normalize_url(source.url if source else str(record.meta.get("url", "")))
        locator = source.locator if source else record.meta.get("locator", {})
        digest = str(record.meta.get("content_hash") or content_hash(record.snippet))
        return ("web_social", url, _canonical(locator), digest)

    return ("generic", record.source_id, evidence_type, content_hash(record.snippet), _canonical(record.scope))


def source_dedupe_key(source: SourceRecord) -> Tuple[str, ...]:
    url = normalize_url(source.url)
    if url:
        return (source.source_type.lower(), url, _canonical(source.locator))
    return (
        source.source_type.lower(),
        source.platform.lower(),
        source.title.strip().lower(),
        _canonical(source.locator),
    )


def dedupe_bundle(bundle: ProvenanceBundle) -> ProvenanceBundle:
    bundle = copy.deepcopy(bundle)
    source_by_key: Dict[Tuple[str, ...], SourceRecord] = {}
    source_aliases: Dict[str, str] = {}
    for source in bundle.sources:
        key = source_dedupe_key(source)
        kept = source_by_key.get(key)
        if kept is None:
            source_by_key[key] = source
            source_aliases[source.source_id] = source.source_id
        else:
            source_aliases[source.source_id] = kept.source_id

    sources = list(source_by_key.values())
    source_index = {item.source_id: item for item in sources}
    evidence_by_key: Dict[Tuple[str, ...], EvidenceRecord] = {}
    evidence_aliases: Dict[str, str] = {}
    for item in bundle.evidence:
        canonical_source_id = source_aliases.get(item.source_id, item.source_id)
        normalized = item if canonical_source_id == item.source_id else replace(item, source_id=canonical_source_id)
        key = evidence_dedupe_key(normalized, source_index.get(canonical_source_id))
        kept = evidence_by_key.get(key)
        if kept is None:
            evidence_by_key[key] = normalized
            evidence_aliases[item.evidence_id] = normalized.evidence_id
        else:
            evidence_aliases[item.evidence_id] = kept.evidence_id

    evidence = list(evidence_by_key.values())
    claims = []
    seen_claims = set()
    for claim in bundle.claims:
        claim.evidence_ids = list(dict.fromkeys(evidence_aliases.get(item, item) for item in claim.evidence_ids))
        key = (claim.claim_type, claim.text.strip().lower(), tuple(claim.evidence_ids))
        if key not in seen_claims:
            claims.append(claim)
            seen_claims.add(key)

    aliases = dict(bundle.meta.get("evidence_aliases") or {})
    aliases = {key: evidence_aliases.get(value, value) for key, value in aliases.items()}
    aliases.update({key: value for key, value in evidence_aliases.items() if key != value})
    return ProvenanceBundle(
        bundle_id=bundle.bundle_id,
        agent=bundle.agent,
        sources=sources,
        evidence=evidence,
        claims=claims,
        created_at=bundle.created_at,
        version=bundle.version,
        meta={**bundle.meta, "evidence_aliases": aliases},
    )


def merge_bundles(bundles: Iterable[ProvenanceBundle | Mapping[str, Any] | None]) -> ProvenanceBundle:
    merged = ProvenanceBundle(agent="report_engine", bundle_id=stable_id("bundle", "report_engine", utc_now_iso()))
    agents = []
    for value in bundles:
        if not value:
            continue
        bundle = value if isinstance(value, ProvenanceBundle) else ProvenanceBundle.from_dict(value)
        if bundle.agent:
            agents.append(bundle.agent)
        merged.meta.setdefault("evidence_aliases", {}).update(bundle.meta.get("evidence_aliases") or {})
        merged.add_records(bundle.sources, bundle.evidence, bundle.claims)
    merged.meta["agents"] = list(dict.fromkeys(agents))
    return dedupe_bundle(merged)


def records_from_search_result(
    agent: str,
    result: Mapping[str, Any],
    *,
    query: str = "",
    paragraph_title: str = "",
    source_type: str = "web",
    evidence_type: str = "web",
    retrieved_time: str = "",
) -> Tuple[SourceRecord, EvidenceRecord]:
    """Normalize one existing engine result without changing its legacy output."""
    snippet = str(result.get("raw_content") or result.get("content") or result.get("title_or_content") or "")
    url = str(result.get("url") or "")
    title = str(result.get("title") or result.get("title_or_content") or "")
    platform = str(result.get("platform") or result.get("domain") or (urlparse(url).netloc if url else ""))
    publish_time = result.get("publish_time") or result.get("published_date") or result.get("published_at") or ""
    locator = dict(result.get("locator") or {})
    for key in ("post_id", "comment_id", "timestamp", "table", "primary_key", "record_id"):
        if result.get(key) not in (None, ""):
            locator[key] = result[key]

    source_id = stable_id("src", agent, source_type, normalize_url(url), locator, title)
    source = SourceRecord(
        source_id=source_id,
        agent=agent,
        source_type=source_type,
        title=title,
        url=url,
        platform=platform,
        author=str(result.get("author") or result.get("author_nickname") or ""),
        publish_time=str(publish_time),
        retrieved_time=retrieved_time or str(result.get("retrieved_time") or utc_now_iso()),
        locator=locator,
        meta={
            "domain": str(result.get("domain") or (urlparse(url).netloc if url else "")),
            "search_tool": str(result.get("search_tool") or ""),
        },
    )
    scope = dict(result.get("scope") or {})
    if query:
        scope.setdefault("query", query)
    if paragraph_title:
        scope.setdefault("subject", paragraph_title)
    evidence = EvidenceRecord(
        evidence_id=stable_id("ev", source_id, evidence_type, locator, content_hash(snippet)),
        source_id=source_id,
        agent=agent,
        evidence_type=evidence_type,
        snippet=snippet,
        normalized_value=result.get("normalized_value"),
        scope=scope,
        meta={"content_hash": content_hash(snippet)},
    )
    return source, evidence


def add_search_results_to_bundle(
    bundle: ProvenanceBundle,
    *,
    agent: str,
    results: Iterable[Mapping[str, Any]],
    query: str,
    paragraph_title: str,
    source_type: str = "web",
    evidence_type: str = "web",
) -> ProvenanceBundle:
    """Add raw tool results and source-backed candidate claims to a bundle."""
    for result in results:
        item_source_type = str(result.get("source_type") or source_type)
        item_evidence_type = str(result.get("evidence_type") or evidence_type)
        source, evidence = records_from_search_result(
            agent,
            result,
            query=query,
            paragraph_title=paragraph_title,
            source_type=item_source_type,
            evidence_type=item_evidence_type,
        )
        if not evidence.snippet.strip():
            continue
        claim_text = str(result.get("claim_text") or evidence.snippet).strip()
        claim = ClaimRecord(
            claim_id=stable_id("claim", agent, claim_text, evidence.evidence_id),
            text=claim_text,
            claim_type=str(result.get("claim_type") or "fact"),
            evidence_ids=[evidence.evidence_id],
            support_level="supported",
            status="supported",
            scope=dict(evidence.scope),
            meta={"candidate": True, "derived_from": "raw_tool_result"},
        )
        bundle.add_records([source], [evidence], [claim])
    return dedupe_bundle(bundle)
