"""Spec §10 pricing. A price always prints the assumptions that produced it."""

from __future__ import annotations

import json
from pathlib import Path

from .features.provenance import Metric, weakest
from .util import clamp

CFG_PATH = Path(__file__).resolve().parents[2] / "config" / "pricing.json"


def load(path: str | None = None) -> dict:
    p = Path(path).expanduser() if path else CFG_PATH
    return json.loads(p.read_text(encoding="utf-8"))


def follower_tier(followers: int) -> str:
    f = int(followers or 0)
    if f < 5_000:
        return "lt5k"
    if f < 20_000:
        return "5_20k"
    if f < 50_000:
        return "20_50k"
    if f < 100_000:
        return "50_100k"
    if f < 500_000:
        return "100_500k"
    if f < 1_000_000:
        return "500k_1m"
    return "gt1m"


def k_for(followers: int, cfg: dict | None = None, fitted: dict | None = None) -> float:
    cfg = cfg or load()
    tier = follower_tier(followers)
    if fitted and tier in fitted:
        return float(fitted[tier])
    return float((cfg.get("k_by_tier") or {}).get(tier, cfg.get("k_default") or 20))


def floor_for(followers: int, cfg: dict | None = None) -> float:
    cfg = cfg or load()
    return float((cfg.get("floors") or {}).get(follower_tier(followers), 150))


def _f(m: Metric | None) -> float | None:
    if m and m.present:
        try:
            return float(m.value)
        except (TypeError, ValueError):
            return None
    return None


def quality_of(metrics: dict[str, Metric]) -> tuple[float, dict, bool]:
    """Each factor bounded as in the spec. authenticity < 60 → do_not_buy."""
    auth = _f(metrics.get("authenticity"))
    fit = _f(metrics.get("brand_topic_fit"))
    senior = _f(metrics.get("director_plus_share"))
    consist = _f(metrics.get("posts_per_week"))
    trend = _f(metrics.get("trend_90d"))

    f_auth = 0.5 if auth is None else clamp(0.5 + 0.5 * (auth / 100.0), 0.5, 1.0)
    f_fit = 0.8 if fit is None else clamp(0.8 + 0.4 * fit, 0.8, 1.2)
    f_sen = 0.9 if senior is None else clamp(0.9 + 0.4 * senior, 0.9, 1.3)
    f_con = 1.0 if consist is None else clamp(0.9 + 0.025 * consist, 0.9, 1.0)
    f_tr = 1.0 if trend is None else clamp(1.0 + 0.05 * max(min(trend, 1.0), -1.0), 0.95, 1.05)
    q = f_auth * f_fit * f_sen * f_con * f_tr
    do_not = auth is not None and auth < 60
    return q, {
        "authenticity": f_auth,
        "topic_fit": f_fit,
        "seniority": f_sen,
        "consistency": f_con,
        "trend": f_tr,
    }, do_not


def w_engagement(posts: list[dict]) -> float:
    """Sheet definition: (likes + 3·shares + 1.5·comments) per post, median-ish mean."""
    if not posts:
        return 0.0
    vals = []
    for p in posts:
        vals.append(
            int(p.get("reactions") or 0)
            + 3 * int(p.get("reposts") or 0)
            + 1.5 * int(p.get("comments") or 0)
        )
    return sum(vals) / len(vals)


def legacy_price(followers: int, posts: list[dict], *, top_voice: bool = False) -> float:
    weng = w_engagement(posts)
    # Sheet uses / 10 posts; we already averaged per post, so ×10 to match.
    weng10 = weng * min(len(posts), 10) / 10 * 10 if posts else 0
    # Simpler: treat WEngagement as the 10-post sum scaled to 10.
    if posts:
        sample = posts[:10]
        weng10 = sum(
            int(p.get("reactions") or 0) + 3 * int(p.get("reposts") or 0) + 1.5 * int(p.get("comments") or 0)
            for p in sample
        ) * (10 / max(len(sample), 1))
    else:
        weng10 = 0
    tier = 1.25 if top_voice else 1.0
    return ((followers * 0.008) + (weng10 * 1.5)) * tier * 0.7


def price(
    metrics: dict[str, Metric],
    creator: dict,
    posts: list[dict],
    *,
    cfg: dict | None = None,
    fitted_k: dict | None = None,
    format_name: str = "text",
    rights: list[str] | None = None,
    authority: str = "none",
    asking: float | None = None,
) -> dict | None:
    """Return a price card, or None when there is no post history to price from."""
    if not posts and not (_f(metrics.get("median_impressions_est"))):
        return None
    cfg = cfg or load()
    followers = int(creator.get("followers") or 0)
    k = k_for(followers, cfg, fitted_k)
    weng = w_engagement(posts)

    imp_m = metrics.get("median_impressions_est")
    if imp_m and imp_m.present:
        impressions = float(imp_m.value)
        imp_src = imp_m.source
        imp_basis = imp_m.basis
    else:
        impressions = k * weng
        imp_src = "estimated"
        imp_basis = f"k({follower_tier(followers)})={k} × WEngagement {weng:.2f}"

    share_m = metrics.get("icp_share_engagers")
    default_share = float(cfg.get("default_icp_share") or 0.25)
    if share_m and share_m.present:
        icp_share = float(share_m.value)
        share_src = share_m.source
        share_note = share_m.basis
    else:
        icp_share = default_share
        share_src = "assumed"
        share_note = f"default icp_share {default_share:.0%} until measured"

    icp_impr = impressions * icp_share
    cpm = float(cfg.get("cpm_target") or 45)
    media = (icp_impr / 1000.0) * cpm
    eng_val = weng * icp_share * float(cfg.get("engagement_dollar") or 2.5)
    q, qparts, do_not = quality_of(metrics)
    dmap = cfg.get("deliverable") or {}
    deliverable = float(dmap.get(format_name) or dmap.get("text") or 1.0)
    rmap = cfg.get("rights") or {}
    for r in rights or []:
        deliverable *= float(rmap.get(r) or 1.0)
    amap = cfg.get("authority") or {}
    auth_m = float(amap.get(authority) or amap.get("none") or 1.0)
    raw = (media + eng_val) * q * deliverable * auth_m
    floor = floor_for(followers, cfg)
    fair = max(raw, floor)
    floor_driven = raw < floor
    open_p = 0.8 * fair
    walk = 1.5 * fair
    lead_cap = (
        icp_impr
        * float(cfg.get("lead_ctr") or 0.006)
        * float(cfg.get("lead_cvr") or 0.03)
        * float(cfg.get("lead_value") or 400)
        / float(cfg.get("lead_split") or 0.5)
    )
    cpm_icp = (fair / (icp_impr / 1000.0)) if icp_impr > 0 else None
    asking_cpm = (asking / (icp_impr / 1000.0)) if asking and icp_impr > 0 else None
    legacy = legacy_price(followers, posts, top_voice=authority == "top_voice")
    src = weakest(imp_src, share_src)

    assumptions = [
        f"impressions {impressions:.0f} ({imp_src}: {imp_basis})",
        f"icp_share {icp_share:.0%} ({share_src}: {share_note})",
        f"CPM_target ${cpm:.0f}",
        f"k={k} for {follower_tier(followers)} ({followers} followers)",
        f"quality {q:.2f} = auth {qparts['authenticity']:.2f} × fit {qparts['topic_fit']:.2f} "
        f"× senior {qparts['seniority']:.2f} × cadence {qparts['consistency']:.2f} × trend {qparts['trend']:.2f}",
        f"deliverable {format_name} {deliverable:.2f} · authority {authority} {auth_m:.2f}",
    ]
    if floor_driven:
        assumptions.append(f"fair set by market floor ${floor:.0f} — buying authority, not reach")
    if do_not:
        assumptions.append("authenticity < 60 — do not buy")

    return {
        "fair": fair,
        "open": open_p,
        "walk_away": walk,
        "raw": raw,
        "floor": floor,
        "floor_driven": floor_driven,
        "do_not_buy": do_not,
        "media_value": media,
        "engagement_value": eng_val,
        "quality": q,
        "quality_parts": qparts,
        "deliverable": deliverable,
        "authority": auth_m,
        "impressions_est": impressions,
        "icp_share": icp_share,
        "icp_impressions": icp_impr,
        "cpm_target": cpm,
        "cpm_icp": cpm_icp,
        "asking": asking,
        "asking_cpm_icp": asking_cpm,
        "lead_value_cap": lead_cap,
        "legacy": legacy,
        "k": k,
        "w_engagement": weng,
        "source": src,
        "assumptions": assumptions,
        "interpret": _interpret(fair, floor_driven, cpm_icp, cpm, legacy, walk, floor),
    }


def _interpret(fair, floor_driven, cpm_icp, cpm, legacy, walk, floor) -> list[str]:
    lines = []
    if floor_driven:
        lines.append("fair is set by the market floor — brand association or seeding, not reach")
    if cpm_icp is not None and cpm_icp > 2 * cpm:
        lines.append(
            f"CPM-ICP at fair (${cpm_icp:.0f}) exceeds 2× ad CPM (${cpm:.0f}) — "
            "negotiate a CPM-based deal or pass"
        )
    if legacy > walk:
        lines.append("legacy exceeds walk-away — the old formula was overpaying (large account)")
    if legacy < floor:
        lines.append("legacy is below the floor — the old formula offers less than creators accept")
    return lines


def calibrate_k(pairs: list[tuple[float, float]]) -> tuple[float, float | None]:
    """Least-squares k from (weighted_engagement, actual_impressions) pairs."""
    xs = [p[0] for p in pairs if p[0] and p[1]]
    ys = [p[1] for p in pairs if p[0] and p[1]]
    n = min(len(xs), len(ys))
    if n < 2:
        return 20.0, None
    # intercept 0: k = Σxy / Σx²
    num = sum(xs[i] * ys[i] for i in range(n))
    den = sum(xs[i] ** 2 for i in range(n))
    k = num / den if den else 20.0
    yhat = [k * xs[i] for i in range(n)]
    my = sum(ys) / n
    ss_tot = sum((ys[i] - my) ** 2 for i in range(n))
    ss_res = sum((ys[i] - yhat[i]) ** 2 for i in range(n))
    r2 = 1.0 - ss_res / ss_tot if ss_tot else 1.0
    return k, r2
