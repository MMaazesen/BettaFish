"""Audit/replay sidecar persistence; runtime code passes bundles directly."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Union

from .models import ProvenanceBundle


PathLike = Union[str, Path]


def sidecar_path(report_path: PathLike) -> Path:
    return Path(report_path).with_suffix(".provenance.json")


def save_sidecar(bundle: ProvenanceBundle, report_path: PathLike) -> Path:
    target = sidecar_path(report_path)
    target.write_text(json.dumps(bundle.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def load_sidecar(path_or_report: PathLike) -> ProvenanceBundle:
    path = Path(path_or_report)
    target = path if path.name.endswith(".provenance.json") else sidecar_path(path)
    if not target.exists():
        return ProvenanceBundle()
    return ProvenanceBundle.from_dict(json.loads(target.read_text(encoding="utf-8")))
