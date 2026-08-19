"""Social graph S1–S14."""

from __future__ import annotations

from collections import defaultdict

from .. import icp as icpmod
from ..util import safe_div
from .provenance import Metric

WEIGHT = {"reaction": 1.0, "comment": 2.0}


def _w(row: dict) -> float:
    kind = row.get("type") or "reaction"
    base = WEIGHT.get(kind, 1.0)
    if kind == "comment" and int(row.get("word_count") or 0) >= 15 and not row.get("generic"):
        return 3.0
    return base


def compute(creator: dict, engagements: list[dict], enrichment: dict[str, dict],
            *, icp_cfg: dict, abm: set[str], consented: dict | None = None) -> dict[str, Metric]:
    out: dict[str, Metric] = {}
    followers = int(creator.get("followers") or 0)
    connections = int(creator.get("connections") or 0)
    if followers:
        out["followers"] = Metric.measured("followers", followers, f"profile followers={followers}")
    else:
        out["followers"] = Metric.missing("followers", "no follower count on the profile row")

    if followers and connections:
        ratio = followers / max(connections, 1)
        out["follower_connection_ratio"] = Metric.measured(
            "follower_connection_ratio", ratio,
            f"{followers} followers / {connections} connections",
        )
    else:
        out["follower_connection_ratio"] = Metric.missing(
            "follower_connection_ratio", "need both followers and connections"
        )

    if not engagements:
        for name in (
            "unique_engagers", "repeat_engager_share", "seed_pool",
            "icp_share_engagers", "icp_share_seed_pool", "director_plus_share",
            "enterprise_share", "marketing_function_share", "geo_fit_share",
            "target_account_hits",
        ):
            out[name] = Metric.missing(name, "no engager rows")
        if consented and consented.get("icp_share") is not None:
            out["icp_share_engagers"] = Metric.consented(
                "icp_share_engagers", float(consented["icp_share"]),
                "creator-supplied audience analytics",
            )
        return out

    by_person: dict[str, list] = defaultdict(list)
    for g in engagements:
        by_person[g["engager_hash"]].append(g)
    unique = len(by_person)
    posts_touched = {g["post_id"] for g in engagements}
    n_posts = max(len(posts_touched), 1)
    repeat = sum(1 for rows in by_person.values() if len({r["post_id"] for r in rows}) >= 2)
    seed_cut = max(3, int(0.25 * n_posts))
    seed = {h for h, rows in by_person.items() if len({r["post_id"] for r in rows}) >= seed_cut}

    out["unique_engagers"] = Metric.measured("unique_engagers", unique, f"{unique} distinct hashes across {n_posts} posts")
    out["repeat_engager_share"] = Metric.measured(
        "repeat_engager_share", repeat / unique if unique else 0.0,
        f"{repeat} of {unique} on ≥2 posts",
    )
    out["seed_pool"] = Metric.measured("seed_pool", len(seed), f"engagers on ≥{seed_cut} of {n_posts} posts")

    def weighted_share(pred) -> tuple[float | None, str]:
        num = den = 0.0
        used = 0
        for g in engagements:
            enr = enrichment.get(g["engager_hash"]) or {}
            w = _w(g)
            den += w
            if pred(enr):
                num += w
                used += 1
        if den == 0:
            return None, "no weighted engagements"
        return num / den, f"{used} matching / {len(engagements)} rows, weighted"

    icp_share, icp_basis = weighted_share(lambda e: icpmod.is_icp(e, icp_cfg))
    if consented and consented.get("icp_share") is not None:
        out["icp_share_engagers"] = Metric.consented(
            "icp_share_engagers", float(consented["icp_share"]),
            f"consented audience analytics (engager-based was {icp_share})",
        )
        out["icp_share_engagers_public"] = Metric.measured("icp_share_engagers_public", icp_share, icp_basis)
    elif icp_share is not None:
        src = "measured" if enrichment else "estimated"
        out["icp_share_engagers"] = Metric("icp_share_engagers", icp_share, src, icp_basis)
    else:
        out["icp_share_engagers"] = Metric.missing("icp_share_engagers", icp_basis)

    seed_rows = [g for g in engagements if g["engager_hash"] in seed]
    if seed_rows:
        num = den = 0.0
        for g in seed_rows:
            w = _w(g)
            den += w
            if icpmod.is_icp(enrichment.get(g["engager_hash"]) or {}, icp_cfg):
                num += w
        out["icp_share_seed_pool"] = Metric.measured(
            "icp_share_seed_pool", num / den if den else 0.0,
            f"{len(seed)} seed-pool hashes",
        )
    else:
        out["icp_share_seed_pool"] = Metric.missing("icp_share_seed_pool", "seed pool empty")

    d_share, d_basis = weighted_share(lambda e: icpmod.is_director_plus(e, icp_cfg))
    out["director_plus_share"] = (
        Metric.measured("director_plus_share", d_share, d_basis)
        if d_share is not None else Metric.missing("director_plus_share", d_basis)
    )

    def enterprise(e):
        try:
            return int(e.get("company_size") or 0) >= int(icp_cfg.get("enterprise_min") or 1000)
        except (TypeError, ValueError):
            return False

    e_share, e_basis = weighted_share(enterprise)
    src = "measured" if any((enrichment.get(g["engager_hash"]) or {}).get("company_size") for g in engagements) else "estimated"
    out["enterprise_share"] = (
        Metric("enterprise_share", e_share, src, e_basis)
        if e_share is not None else Metric.missing("enterprise_share", e_basis)
    )

    m_share, m_basis = weighted_share(lambda e: icpmod.is_marketing(e, icp_cfg))
    out["marketing_function_share"] = (
        Metric.measured("marketing_function_share", m_share, m_basis)
        if m_share is not None else Metric.missing("marketing_function_share", m_basis)
    )

    g_share, g_basis = weighted_share(lambda e: icpmod.geo_fit(e, icp_cfg))
    out["geo_fit_share"] = (
        Metric.measured("geo_fit_share", g_share, g_basis)
        if g_share is not None else Metric.missing("geo_fit_share", g_basis)
    )

    companies = set()
    abm_l = {a.lower() for a in abm}
    for e in enrichment.values():
        co = (e.get("company") or "").strip().lower()
        if co and co in abm_l:
            companies.add(co)
    if abm:
        out["target_account_hits"] = Metric.measured(
            "target_account_hits", len(companies), f"{len(companies)} of {len(abm)} ABM names among engagers"
        )
    else:
        out["target_account_hits"] = Metric.missing("target_account_hits", "no ABM list loaded")

    return out


def icp_impressions(imp: Metric | None, share: Metric | None) -> Metric:
    if not imp or not imp.present:
        return Metric.missing("est_icp_impressions_per_post", "no impressions estimate")
    if not share or not share.present:
        return Metric.assumed(
            "est_icp_impressions_per_post",
            float(imp.value) * 0.25,
            f"{imp.value} × assumed icp_share 0.25; {imp.source}",
        )
    from .provenance import weakest
    return Metric(
        "est_icp_impressions_per_post",
        float(imp.value) * float(share.value),
        weakest(imp.source, share.source),
        f"{imp.value} × icp_share {share.value} ({imp.source} × {share.source})",
    )
