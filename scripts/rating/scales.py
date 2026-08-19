"""Anchored 0–100 normalisation. Anchors live in config/scales.json."""

from __future__ import annotations

import json
import math
from pathlib import Path

from .features.provenance import Metric
from .util import clamp


def package_scales() -> Path:
    return Path(__file__).resolve().parents[2] / "config" / "scales.json"


def load(path: str | None = None) -> dict:
    p = Path(path).expanduser() if path else package_scales()
    data = json.loads(p.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not str(k).startswith("_")}


def scale_value(value: float | None, spec: dict) -> float | None:
    if value is None:
        return None
    lo = float(spec.get("lo", 0))
    hi = float(spec.get("hi", 1))
    if spec.get("log"):
        value = math.log10(max(value, 1e-9))
        lo = math.log10(max(lo, 1e-9))
        hi = math.log10(max(hi, 1e-8))
    if hi == lo:
        return 50.0
    return clamp(100.0 * (value - lo) / (hi - lo), 0.0, 100.0)


def apply(metrics: dict[str, Metric], anchors: dict | None = None) -> dict[str, Metric]:
    anchors = anchors if anchors is not None else load()
    for name, m in metrics.items():
        spec = anchors.get(name)
        if not spec or not m.present:
            continue
        try:
            m.scaled = scale_value(float(m.value), spec)
        except (TypeError, ValueError):
            m.scaled = None
    return metrics
