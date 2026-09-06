"""Bounded, per-run in-memory transport between Streamlit workers and Flask."""

from __future__ import annotations

import copy
import json
import os
import threading
import uuid
from collections import OrderedDict
from urllib.request import Request, urlopen

from .models import ProvenanceBundle
from .normalizer import merge_bundles
from .validators import filter_valid_evidence


ENGINE_ORDER = ("query", "media", "insight")


class RuntimeProvenanceStore:
    def __init__(self, max_runs: int = 32):
        self.max_runs = max_runs
        self._runs = OrderedDict()
        self._lock = threading.RLock()

    def begin(self, query: str, engines=ENGINE_ORDER) -> str:
        expected = [engine for engine in ENGINE_ORDER if engine in engines]
        if not query.strip() or not expected:
            raise ValueError("查询和参与引擎不能为空")
        run_id = uuid.uuid4().hex
        with self._lock:
            self._runs[run_id] = {"query": query, "expected": expected, "engines": {}}
            while len(self._runs) > self.max_runs:
                self._runs.popitem(last=False)
        return run_id

    def publish(self, run_id: str, engine: str, query: str, report: str, bundle, complete: bool = True):
        with self._lock:
            run = self._runs.get(run_id)
            if not run or query != run["query"] or engine not in run["expected"]:
                raise ValueError("运行任务不存在，或查询/引擎不匹配")
            provenance = ProvenanceBundle.from_dict(bundle.to_dict() if isinstance(bundle, ProvenanceBundle) else bundle)
            if provenance.agent != f"{engine}_engine":
                raise ValueError("bundle 与发布引擎不匹配")
            provenance.meta.update({"run_id": run_id, "query": query})
            # Empty evidence is an explicit result, never a request to reload old sidecars.
            run["engines"][engine] = {
                "report": str(report), "bundle": filter_valid_evidence(provenance), "complete": bool(complete),
            }

    def status(self, run_id: str) -> dict:
        with self._lock:
            run = self._runs.get(run_id)
            if not run:
                return {"ready": False, "missing_files": ["runtime task expired or unknown"], "latest_files": {}}
            missing = [engine for engine in run["expected"] if not run["engines"].get(engine, {}).get("complete")]
            return {"ready": not missing, "missing_files": missing, "latest_files": {}, "transport": "runtime"}

    def inputs(self, run_id: str, query: str) -> dict:
        with self._lock:
            if not self.status(run_id)["ready"]:
                raise ValueError("本轮 Agent 尚未全部提交运行态结果")
            run = self._runs[run_id]
            if query != run["query"]:
                raise ValueError("报告查询与本轮任务不匹配")
            entries = run["engines"]
            return {
                "reports": [entries.get(engine, {}).get("report", "") for engine in ENGINE_ORDER],
                "provenance_bundle": merge_bundles([copy.deepcopy(item["bundle"]) for item in entries.values()]),
                "forum_logs": "",
            }


runtime_store = RuntimeProvenanceStore()


def publish_runtime_result(run_id: str, engine: str, query: str, report: str, bundle: ProvenanceBundle):
    """Publish through the parent's loopback endpoint; standalone CLI has no endpoint."""
    endpoint = os.environ.get("BETTAFISH_PROVENANCE_ENDPOINT", "")
    if not run_id or not endpoint:
        return
    payload = json.dumps({"run_id": run_id, "engine": engine, "query": query, "report": report, "bundle": bundle.to_dict()}, ensure_ascii=False).encode("utf-8")
    request = Request(endpoint, data=payload, headers={
        "Content-Type": "application/json",
        "X-Provenance-Token": os.environ.get("BETTAFISH_PROVENANCE_TOKEN", ""),
    }, method="POST")
    with urlopen(request, timeout=15) as response:
        if response.status != 200:
            raise RuntimeError("运行态证据提交失败")
