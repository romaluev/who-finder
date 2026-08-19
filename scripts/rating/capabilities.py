"""Capability ladder and 'what to connect next'.

Rung 0 is a thinner report, never a refusal. Doctor names the rung; every
report prints it. Connecting a backend is ranked by weight points recovered.
"""

from __future__ import annotations

from . import auth
from .features.provenance import MEASURED_OR_BETTER, Metric

RUNG_LABELS = {
    0: "nothing connected — interest graph from profile text; no price",
    1: "public video / who-finder — yt-dlp or search hits; LinkedIn still count-less",
    2: "LinkedIn posts — Bright Data last, or a posts CSV; interest graph from text",
    3: "engager source — social graph, authenticity, true overlap",
    4: "consented analytics / pilots — impressions calibrated, ICP verified",
}

# Which metrics a backend can turn from insufficient/assumed into measured.
BACKEND_METRICS = {
    "csv": {"followers", "headline_alignment", "brand_topic_fit", "topic_concentration"},
    "who_finder": {
        "followers", "headline_alignment", "brand_topic_fit", "topic_concentration",
        "median_reactions", "eng_per_1k_followers", "posts_per_week", "trend_90d",
        "median_impressions_est", "engagement_bait_rate",
    },
    "public": {
        "followers", "headline_alignment", "brand_topic_fit", "topic_concentration",
        "median_reactions", "eng_per_1k_followers", "posts_per_week", "trend_90d",
        "median_impressions_est", "engagement_bait_rate",
    },
    "clay": {
        "followers", "headline_alignment", "brand_topic_fit", "topic_concentration",
        "enterprise_share", "target_account_hits", "icp_share_seed_pool",
    },
    "scrapecreators": {
        "median_reactions", "eng_per_1k_followers", "posts_per_week", "trend_90d",
        "median_impressions_est",
    },
    "brightdata": {
        "followers", "median_reactions", "median_comments", "median_reposts",
        "eng_per_1k_followers", "posts_per_week", "cadence_cv", "trend_90d",
        "median_impressions_est", "engagement_bait_rate", "ai_post_share",
        "brand_topic_fit", "topic_concentration", "topic_entropy",
        "headline_alignment", "language_mix", "brand_safety",
    },
    "engager": {
        "unique_engagers", "repeat_engager_share", "seed_pool",
        "icp_share_engagers", "icp_share_seed_pool", "director_plus_share",
        "enterprise_share", "marketing_function_share", "geo_fit_share",
        "target_account_hits", "comment_depth", "substantive_comment_share",
        "author_reply_rate", "top20_concentration", "pod_signal",
        "ai_comment_share", "generic_comment_share", "authenticity",
        "audience_interest_alignment",
    },
    "apollo": {"enterprise_share", "target_account_hits", "icp_share_seed_pool"},
    "llm": {"brand_topic_fit", "headline_alignment", "ai_post_share", "ai_comment_share"},
    "pilots": {"median_impressions_est", "out_of_network_share", "icp_share_engagers"},
}

BACKEND_GUIDE = {
    "brightdata": "docs/connect.md#bright-data",
    "engager": "docs/connect.md#engager-source",
    "unipile": "docs/connect.md#engager-source",
    "apollo": "docs/connect.md#apollo",
    "llm": "docs/connect.md#llm",
    "scrapecreators": "docs/connect.md#scrapecreators",
    "clay": "docs/economy.md#clay",
    "public": "docs/economy.md#public",
    "pilots": "docs/connect.md#consented-analytics",
    "csv": "docs/start.md",
}

# Rung detection: highest unlocked.
RUNG_BACKENDS = {
    1: ("scrapecreators", "who_finder", "public"),
    2: ("brightdata",),
    3: ("unipile", "engager"),
    4: ("pilots",),
}


def detect_rung(caps: dict | None = None, *, has_posts: bool = False, has_engagers: bool = False,
                has_pilots: bool = False, has_video_hits: bool = False) -> int:
    caps = caps if caps is not None else auth.capabilities()
    rung = 0
    if has_video_hits or (caps.get("scrapecreators") or {}).get("available"):
        rung = max(rung, 1)
    if has_posts or (caps.get("brightdata") or {}).get("available"):
        rung = max(rung, 2)
    if has_engagers or (caps.get("unipile") or {}).get("available"):
        rung = max(rung, 3)
    if has_pilots:
        rung = max(rung, 4)
    return rung


def rung_label(n: int) -> str:
    return f"rung {n} — {RUNG_LABELS.get(n, 'unknown')}"


def weight_points(preset: dict) -> dict[str, float]:
    """Flatten a weights preset (social/engagement/interest blocks) to metric → points."""
    out: dict[str, float] = {}
    for block in preset.values():
        if isinstance(block, dict):
            for k, v in block.items():
                out[k] = out.get(k, 0) + float(v)
    return out


def confidence(metrics: dict[str, Metric], preset: dict) -> float:
    """Share of the preset's 100 weight points that came from measured or better."""
    pts = weight_points(preset)
    total = sum(pts.values()) or 1.0
    earned = 0.0
    for name, w in pts.items():
        m = metrics.get(name)
        if m and m.present and m.source in MEASURED_OR_BETTER:
            earned += w
    return earned / total


def what_to_connect(metrics: dict[str, Metric], preset: dict, caps: dict | None = None) -> list[dict]:
    """Rank missing backends by weight points they would recover."""
    caps = caps if caps is not None else auth.capabilities()
    pts = weight_points(preset)
    missing = {
        name for name, w in pts.items()
        if w and (name not in metrics or not metrics[name].present
                  or metrics[name].source not in MEASURED_OR_BETTER)
    }
    ranked = []
    already = set()
    for backend, unlocks in BACKEND_METRICS.items():
        if backend in {"csv", "who_finder", "public"}:
            continue
        info = caps.get(backend) or caps.get("unipile" if backend == "engager" else backend) or {}
        if info.get("available") and backend != "pilots":
            continue
        if backend == "apollo" and (caps.get("clay") or {}).get("available"):
            continue
        if backend == "scrapecreators" and (caps.get("public") or {}).get("ytdlp"):
            continue
        recovered = sorted(missing & unlocks)
        points = sum(pts.get(m, 0) for m in recovered)
        if points <= 0:
            continue
        key = "engager" if backend in {"unipile", "engager"} else backend
        if key in already:
            continue
        already.add(key)
        ranked.append({
            "backend": key,
            "points": points,
            "metrics": recovered,
            "guide": BACKEND_GUIDE.get(key, "docs/connect.md"),
            "line": (
                f"connecting {key} recovers {points:.0f} of 100 points "
                f"({', '.join(f'{m} {pts[m]:.0f}' for m in recovered[:4])}"
                f"{'…' if len(recovered) > 4 else ''})"
            ),
        })
    ranked.sort(key=lambda r: -r["points"])
    return ranked


def card(caps: dict | None = None, *, rung: int | None = None, next_connect: list[dict] | None = None) -> dict:
    caps = caps if caps is not None else auth.capabilities()
    if rung is None:
        rung = detect_rung(caps)
    nxt = next_connect or []
    return {
        "rung": rung,
        "label": rung_label(rung),
        "backends": caps,
        "next": nxt,
        "thin": rung < 2,
    }
