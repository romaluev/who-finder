"""Anchored scores, four presets, gates, composite, tiers, next_action."""

from __future__ import annotations

import json
from pathlib import Path

from .capabilities import confidence as conf_of, what_to_connect
from .features.provenance import MEASURED_OR_BETTER, Metric, weakest
from .scales import apply as apply_scales
from .util import clamp

PRESETS_PATH = Path(__file__).resolve().parents[2] / "config" / "weights.json"
CONFIDENCE_FLOOR = 0.35
MIN_POSTS = 8
MIN_ENGAGERS = 300
MIN_ENGAGER_POSTS = 8

TIER_CUTS = ((75, "A"), (60, "B"), (45, "C"), (0, "D"))

NEXT = {
    "A": "pilot",
    "B": "request analytics",
    "C": "watch",
    "D": "pass",
    "?": "collect more",
}


def load_presets() -> dict:
    return json.loads(PRESETS_PATH.read_text(encoding="utf-8"))


def preset_names() -> list[str]:
    return list(load_presets())


def get_preset(name: str = "awareness+leads") -> dict:
    presets = load_presets()
    if name not in presets:
        raise KeyError(f"unknown preset '{name}'. want {list(presets)}")
    return presets[name]


def flatten(preset: dict) -> dict[str, float]:
    out: dict[str, float] = {}
    for block in preset.values():
        if isinstance(block, dict):
            out.update({k: float(v) for k, v in block.items()})
    return out


def gates_of(metrics: dict[str, Metric], n_posts: int, n_engagers: int, n_engager_posts: int) -> list[dict]:
    fired = []

    def add(name: str, why: str, hard: bool = True) -> None:
        fired.append({"name": name, "why": why, "hard": hard})

    pod = metrics.get("pod_signal")
    if pod and pod.present and float(pod.value) >= 0.6:
        add("pod_signal", f"pod_signal {pod.value:.2f} ≥ 0.6")
    ai_c = metrics.get("ai_comment_share")
    if ai_c and ai_c.present and float(ai_c.value) >= 0.5:
        add("ai_comment_share", f"ai_comment_share {ai_c.value:.2f} ≥ 0.5")
    ai_p = metrics.get("ai_post_share")
    if ai_p and ai_p.present and float(ai_p.value) >= 0.6:
        add("ai_post_share", f"ai_post_share {ai_p.value:.2f} ≥ 0.6")
    safety = metrics.get("brand_safety")
    if safety and safety.present and str(safety.value) == "fail":
        add("brand_safety", "brand_safety = fail")
    if 0 < n_posts < MIN_POSTS:
        add("dormant", f"{n_posts} posts in window < {MIN_POSTS}")
    lang = metrics.get("language_mix")
    if lang and lang.present and float(lang.value) < 0.5:
        add("language_mix", f"language_mix {lang.value:.2f} < 0.5")
    if n_posts > 0 and n_engagers and n_engagers < MIN_ENGAGERS and n_engager_posts < MIN_ENGAGER_POSTS:
        add("insufficient_data", f"{n_engagers} engager rows across {n_engager_posts} posts", hard=False)
    return fired


def _block_score(metrics: dict[str, Metric], weights: dict[str, float]) -> tuple[float | None, float, str]:
    usable = []
    for name, w in weights.items():
        m = metrics.get(name)
        if m and m.present and m.scaled is not None:
            usable.append((name, w, m))
    if not usable:
        return None, 0.0, "insufficient"
    total_w = sum(w for _, w, _ in usable)
    score = sum(w * m.scaled for _, w, m in usable) / total_w
    src = weakest(*(m.source for _, _, m in usable))
    return clamp(score, 0.0, 100.0), total_w, src


def score(
    metrics: dict[str, Metric],
    *,
    preset_name: str = "awareness+leads",
    n_posts: int = 0,
    n_engagers: int = 0,
    n_engager_posts: int = 0,
    caps: dict | None = None,
) -> dict:
    apply_scales(metrics)
    preset = get_preset(preset_name)
    social, sw, ss = _block_score(metrics, preset.get("social") or {})
    engagement, ew, es = _block_score(metrics, preset.get("engagement") or {})
    interest, iw, ins = _block_score(metrics, preset.get("interest") or {})

    blocks = []
    if social is not None:
        blocks.append((social, sw, ss))
    if engagement is not None:
        blocks.append((engagement, ew, es))
    if interest is not None:
        blocks.append((interest, iw, ins))
    if blocks:
        tw = sum(w for _, w, _ in blocks)
        composite = sum(s * w for s, w, _ in blocks) / tw
        src = weakest(*(s for _, _, s in blocks))
    else:
        composite, src = None, "insufficient"

    conf = conf_of(metrics, preset)
    fired = gates_of(metrics, n_posts, n_engagers, n_engager_posts)
    hard = [g for g in fired if g["hard"]]
    insufficient = any(g["name"] == "insufficient_data" for g in fired)

    if composite is None or conf < CONFIDENCE_FLOOR or insufficient:
        tier = "?"
        next_action = "collect more" if conf < CONFIDENCE_FLOOR else "manual review"
    elif hard:
        tier = "D"
        next_action = "pass"
    else:
        tier = "D"
        for cut, label in TIER_CUTS:
            if composite >= cut:
                tier = label
                break
        next_action = NEXT[tier]

    used_points = sum(
        flatten(preset).get(name, 0)
        for name, m in metrics.items()
        if m.present and m.scaled is not None
    )

    return {
        "preset": preset_name,
        "social": social,
        "engagement": engagement,
        "interest": interest,
        "creator_score": composite,
        "confidence": conf,
        "used_points": used_points,
        "weight_points": 100,
        "tier": tier,
        "next_action": next_action,
        "gates": fired,
        "provenance": src,
        "connect_next": what_to_connect(metrics, preset, caps),
        "metrics": metrics,
    }


def decision_line(result: dict, name: str) -> str:
    tier = result.get("tier") or "?"
    nxt = result.get("next_action") or "manual review"
    score = result.get("creator_score")
    conf = result.get("confidence") or 0
    used = result.get("used_points") or 0
    if score is None:
        return f"{name}: tier {tier} — scored on {used:.0f} of 100 weight points. {nxt}."
    return (
        f"{name}: tier {tier} ({score:.0f}/100, scored on {used:.0f} of 100 weight points, "
        f"confidence {conf:.0%}) — {nxt}."
    )
