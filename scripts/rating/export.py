"""CSV handoff. Physically cannot emit engager PII."""

from __future__ import annotations

import csv
import io

from .db import engager_pii_columns

FIELDS = (
    "id", "name", "url", "handle", "platform", "headline", "followers",
    "status", "tier", "creator_score", "social", "engagement", "interest",
    "confidence", "next_action", "fair", "open", "walk_away", "cpm_icp",
    "est_icp_impressions_per_post", "icp_share", "gates", "source",
)

FORBIDDEN = engager_pii_columns() | frozenset({
    "engager_hash", "hash", "profile_url", "comment_text", "engager_headline",
})


def row_of(creator: dict, score: dict | None, price: dict | None) -> dict:
    s = score or {}
    p = price or {}
    metrics = s.get("metrics") or {}
    icp = metrics.get("est_icp_impressions_per_post") or {}
    share = metrics.get("icp_share_engagers") or {}
    gates = s.get("gates") or []
    if isinstance(gates, list):
        gate_s = ",".join(g.get("name") if isinstance(g, dict) else str(g) for g in gates)
    else:
        gate_s = str(gates)
    return {
        "id": creator.get("id"),
        "name": creator.get("name"),
        "url": creator.get("url"),
        "handle": creator.get("handle"),
        "platform": creator.get("platform"),
        "headline": creator.get("headline"),
        "followers": creator.get("followers"),
        "status": creator.get("status"),
        "tier": s.get("tier"),
        "creator_score": s.get("creator_score"),
        "social": s.get("social"),
        "engagement": s.get("engagement"),
        "interest": s.get("interest"),
        "confidence": s.get("confidence"),
        "next_action": s.get("next_action"),
        "fair": p.get("fair"),
        "open": p.get("open"),
        "walk_away": p.get("walk_away"),
        "cpm_icp": p.get("cpm_icp"),
        "est_icp_impressions_per_post": icp.get("value") if isinstance(icp, dict) else icp,
        "icp_share": share.get("value") if isinstance(share, dict) else share,
        "gates": gate_s,
        "source": creator.get("source"),
    }


def render(rows: list[dict]) -> str:
    for r in rows:
        for k in list(r):
            if k in FORBIDDEN:
                raise RuntimeError(f"export refused: column '{k}' is engager PII")
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(FIELDS), extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow({k: r.get(k, "") for k in FIELDS})
    return buf.getvalue()
