"""Engagement graph E1–E16 plus authenticity."""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from datetime import datetime

from ..util import clamp, linreg_slope, median, percentile, safe_div
from .provenance import Metric, weakest

GENERIC_SHORT = 0.8


def _parse_day(s: str) -> datetime | None:
    if not s:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(s[:19].replace("Z", ""), fmt.replace("T%H:%M:%SZ", "T%H:%M:%S") if "T" in fmt else fmt)
        except ValueError:
            continue
    return None


def compute(creator: dict, posts: list[dict], engagements: list[dict], topics: dict[str, dict],
            *, k_format: float = 20.0, consented: dict | None = None,
            impressions_source: str = "estimated") -> dict[str, Metric]:
    out: dict[str, Metric] = {}
    n = len(posts)
    followers = int(creator.get("followers") or 0)

    if n == 0:
        for name in (
            "median_reactions", "median_comments", "median_reposts",
            "eng_per_1k_followers", "comment_ratio", "comment_depth",
            "substantive_comment_share", "author_reply_rate", "top20_concentration",
            "pod_signal", "ai_comment_share", "generic_comment_share",
            "engagement_bait_rate", "ai_post_share", "median_impressions_est",
            "reach_stability", "posts_per_week", "cadence_cv", "trend_90d",
            "out_of_network_share", "authenticity",
        ):
            out[name] = Metric.missing(name, "no posts")
        return out

    reactions = [int(p.get("reactions") or 0) for p in posts]
    comments = [int(p.get("comments") or 0) for p in posts]
    reposts = [int(p.get("reposts") or 0) for p in posts]
    out["median_reactions"] = Metric.measured("median_reactions", median(reactions), f"median of {n} posts")
    out["median_comments"] = Metric.measured("median_comments", median(comments), f"median of {n} posts")
    out["median_reposts"] = Metric.measured("median_reposts", median(reposts), f"median of {n} posts")

    per_1k = []
    for p in posts:
        total = int(p.get("reactions") or 0) + int(p.get("comments") or 0) + int(p.get("reposts") or 0)
        if followers:
            per_1k.append(total / followers * 1000)
    if per_1k:
        out["eng_per_1k_followers"] = Metric.measured(
            "eng_per_1k_followers", median(per_1k), f"median over {n} posts, F={followers}"
        )
    else:
        out["eng_per_1k_followers"] = Metric.missing("eng_per_1k_followers", "need follower count")

    ratios = []
    for r, c in zip(reactions, comments):
        if r > 0:
            ratios.append(c / r)
    out["comment_ratio"] = (
        Metric.measured("comment_ratio", median(ratios), f"{len(ratios)} posts with reactions")
        if ratios else Metric.missing("comment_ratio", "no posts with reactions")
    )

    bait_n = sum(1 for p in posts if (topics.get(p["id"]) or {}).get("bait"))
    out["engagement_bait_rate"] = Metric.measured(
        "engagement_bait_rate", bait_n / n, f"{bait_n} of {n} posts flagged bait"
    )
    ai_n = sum(1 for p in posts if float((topics.get(p["id"]) or {}).get("ai_likelihood") or 0) >= 0.6)
    out["ai_post_share"] = Metric.measured("ai_post_share", ai_n / n, f"{ai_n} of {n} posts ai-likely")

    weng = [int(p.get("reactions") or 0) + 3 * int(p.get("comments") or 0) + 4 * int(p.get("reposts") or 0) for p in posts]
    med_w = median(weng) or 0.0
    p90 = percentile(weng, 90) or med_w or 1.0
    out["reach_stability"] = Metric.measured(
        "reach_stability", (med_w / p90) if p90 else 0.0, f"median {med_w} / p90 {p90}"
    )

    dates = [_parse_day(p.get("posted_at") or "") for p in posts]
    dated = [d for d in dates if d]
    if len(dated) >= 2:
        span_days = max((max(dated) - min(dated)).days, 1)
        ppw = len(dated) / (span_days / 7)
        gaps = sorted((dated[i] - dated[i - 1]).days for i in range(1, len(sorted(dated))))
        mu = sum(gaps) / len(gaps) if gaps else 0
        var = sum((g - mu) ** 2 for g in gaps) / len(gaps) if gaps else 0
        cv = (math.sqrt(var) / mu) if mu else 0.0
        out["posts_per_week"] = Metric.measured("posts_per_week", ppw, f"{len(dated)} dated posts over {span_days} days")
        out["cadence_cv"] = Metric.measured("cadence_cv", cv, f"cv of {len(gaps)} gaps")
    else:
        out["posts_per_week"] = Metric.estimated("posts_per_week", n / 12.0, f"{n} posts, dates missing; assumed 12-week window")
        out["cadence_cv"] = Metric.missing("cadence_cv", "need dated posts")

    if len(weng) >= 3:
        xs = list(range(len(weng)))
        slope = linreg_slope(xs, [float(v) for v in weng])
        med = med_w or 1.0
        out["trend_90d"] = Metric.measured("trend_90d", (slope or 0.0) / med, f"slope {slope} / median {med}")
    else:
        out["trend_90d"] = Metric.missing("trend_90d", "need ≥3 posts")

    actuals = [int(p["impressions"]) for p in posts if p.get("impressions") not in (None, "")]
    if consented and consented.get("impressions") is not None:
        out["median_impressions_est"] = Metric.consented(
            "median_impressions_est", float(consented["impressions"]),
            "creator-supplied or pilot impressions",
        )
    elif actuals:
        out["median_impressions_est"] = Metric.consented(
            "median_impressions_est", median([float(a) for a in actuals]),
            f"median of {len(actuals)} posts with impressions",
        )
    else:
        est = k_format * med_w
        src = "calibrated" if impressions_source == "calibrated" else "estimated"
        # calibrated is not in RANK; treat as measured for confidence, keep label in basis
        out["median_impressions_est"] = Metric(
            "median_impressions_est",
            est,
            "measured" if src == "calibrated" else "estimated",
            f"k={k_format} × median weighted engagement {med_w} ({src})",
        )

    if consented and consented.get("out_of_network_share") is not None:
        out["out_of_network_share"] = Metric.consented(
            "out_of_network_share", float(consented["out_of_network_share"]),
            "June 2026 analytics export",
        )
    else:
        out["out_of_network_share"] = Metric.missing("out_of_network_share", "consented only")

    # Engager-dependent authenticity inputs
    if not engagements:
        for name in (
            "comment_depth", "substantive_comment_share", "author_reply_rate",
            "top20_concentration", "pod_signal", "ai_comment_share",
            "generic_comment_share",
        ):
            out[name] = Metric.missing(name, "no engager rows")
        out["authenticity"] = _authenticity(out)
        return out

    comments_e = [g for g in engagements if g.get("type") == "comment"]
    words = [int(g.get("word_count") or 0) for g in comments_e]
    out["comment_depth"] = (
        Metric.measured("comment_depth", median([float(w) for w in words]), f"{len(words)} top-level comments")
        if words else Metric.missing("comment_depth", "no comments")
    )
    if comments_e:
        subst = sum(1 for g in comments_e if int(g.get("word_count") or 0) >= 15 and not g.get("generic"))
        out["substantive_comment_share"] = Metric.measured(
            "substantive_comment_share", subst / len(comments_e), f"{subst} of {len(comments_e)}"
        )
        ai_c = sum(1 for g in comments_e if g.get("ai_flag"))
        gen_c = sum(1 for g in comments_e if g.get("generic"))
        out["ai_comment_share"] = Metric.measured("ai_comment_share", ai_c / len(comments_e), f"{ai_c} of {len(comments_e)}")
        out["generic_comment_share"] = Metric.measured(
            "generic_comment_share", gen_c / len(comments_e), f"{gen_c} of {len(comments_e)}"
        )
    else:
        out["substantive_comment_share"] = Metric.missing("substantive_comment_share", "no comments")
        out["ai_comment_share"] = Metric.missing("ai_comment_share", "no comments")
        out["generic_comment_share"] = Metric.missing("generic_comment_share", "no comments")

    author_replies = sum(1 for g in engagements if g.get("type") == "author_reply")
    top_level = max(len(comments_e), 1)
    if comments_e:
        out["author_reply_rate"] = Metric.measured(
            "author_reply_rate", author_replies / top_level, f"{author_replies} replies / {len(comments_e)} comments"
        )
    else:
        out["author_reply_rate"] = Metric.missing("author_reply_rate", "no comments")

    weights = defaultdict(float)
    total_w = 0.0
    for g in engagements:
        w = 1.0 if g.get("type") == "reaction" else 2.0
        if g.get("type") == "comment" and int(g.get("word_count") or 0) >= 15 and not g.get("generic"):
            w = 3.0
        weights[g["engager_hash"]] += w
        total_w += w
    top20 = sum(v for _, v in sorted(weights.items(), key=lambda kv: -kv[1])[:20])
    out["top20_concentration"] = Metric.measured(
        "top20_concentration", (top20 / total_w) if total_w else 0.0,
        f"top 20 of {len(weights)} engagers / Σw={total_w:.0f}",
    )

    out["pod_signal"] = _pod_signal(posts, engagements)
    out["authenticity"] = _authenticity(out)
    return out


def _pod_signal(posts: list[dict], engagements: list[dict]) -> Metric:
    if not engagements:
        return Metric.missing("pod_signal", "no engager rows")
    by_person = defaultdict(set)
    for g in engagements:
        by_person[g["engager_hash"]].add(g["post_id"])
    n_posts = len({p["id"] for p in posts}) or 1
    cutoff = max(3, math.ceil(0.5 * n_posts))
    recurring = {h for h, ps in by_person.items() if len(ps) >= cutoff}
    if not recurring:
        return Metric.measured("pod_signal", 0.0, "no recurring set (≥50% of posts)")

    comments = [g for g in engagements if g.get("type") == "comment" and g["engager_hash"] in recurring]
    has_latency = any(g.get("latency_sec") is not None for g in comments)
    pod_core = set()
    if has_latency:
        lat_by = defaultdict(list)
        for g in comments:
            if g.get("latency_sec") is not None:
                lat_by[g["engager_hash"]].append(int(g["latency_sec"]))
        for h, lats in lat_by.items():
            if median([float(x) for x in lats]) is not None and median([float(x) for x in lats]) <= 1800:
                pod_core.add(h)
    else:
        for h in recurring:
            theirs = [g for g in comments if g["engager_hash"] == h]
            if not theirs:
                continue
            generic = sum(1 for g in theirs if g.get("generic") or int(g.get("word_count") or 0) < 8)
            if generic / len(theirs) >= GENERIC_SHORT:
                pod_core.add(h)

    by_post = defaultdict(set)
    for g in engagements:
        if g["engager_hash"] in pod_core:
            by_post[g["post_id"]].add(g["engager_hash"])
    recurrence = sum(1 for p in posts if len(by_post.get(p["id"], ())) >= 5) / max(len(posts), 1)

    burst = None
    burst_n = 0
    all_comments = [g for g in engagements if g.get("type") == "comment"]
    if all_comments and any(g.get("latency_sec") is not None for g in all_comments):
        fast = [g for g in all_comments if g.get("latency_sec") is not None and int(g["latency_sec"]) <= 900]
        burst = len(fast) / len(all_comments)
        burst_n = len(fast)

    # Reciprocity needs the creator's own comment activity — usually absent.
    parts = {"recurrence": (0.5, recurrence, f"{recurrence:.2f} posts with ≥5 pod-core")}
    if burst is not None:
        parts["burst"] = (0.3, burst, f"{burst_n} comments ≤15 min")
    wsum = sum(w for w, _, _ in parts.values())
    score = sum(w * v for w, v, _ in parts.values()) / wsum if wsum else 0.0
    basis = "; ".join(b for _, _, b in parts.values()) + f"; weights renormalised over {list(parts)}"
    return Metric.measured("pod_signal", score, basis)


def _val(metrics: dict, name: str, default: float = 0.0) -> float:
    m = metrics.get(name)
    if m and m.present:
        try:
            return float(m.value)
        except (TypeError, ValueError):
            return default
    return default


def _authenticity(metrics: dict[str, Metric]) -> Metric:
    pod = _val(metrics, "pod_signal")
    ai_c = _val(metrics, "ai_comment_share")
    gen = _val(metrics, "generic_comment_share")
    conc = _val(metrics, "top20_concentration")
    bait = _val(metrics, "engagement_bait_rate")
    depth = metrics.get("comment_depth")
    reply = metrics.get("author_reply_rate")
    score = (
        100
        - 45 * pod
        - 25 * ai_c
        - 10 * max(0.0, gen - 0.4) / 0.6
        - 15 * min(conc / 0.6, 1.0)
        - 15 * bait
    )
    if depth and depth.present and float(depth.value) >= 20:
        score += 5
    if reply and reply.present and float(reply.value) >= 0.5:
        score += 5
    score = clamp(score, 0.0, 100.0)
    sources = [metrics[k].source for k in (
        "pod_signal", "ai_comment_share", "generic_comment_share",
        "top20_concentration", "engagement_bait_rate",
    ) if k in metrics and metrics[k].present]
    if not sources:
        # authenticity from bait alone (posts, no engagers)
        if metrics.get("engagement_bait_rate") and metrics["engagement_bait_rate"].present:
            return Metric("authenticity", score, "estimated",
                          f"posts-only; bait={bait:.2f}. engager terms missing")
        return Metric.missing("authenticity", "need posts or engagers")
    return Metric("authenticity", score, weakest(*sources),
                  f"100-45·pod {pod:.2f}-25·ai {ai_c:.2f}-… bait {bait:.2f}")
