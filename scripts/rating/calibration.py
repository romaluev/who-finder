"""Pilots → k_format refit. Flip estimated → calibrated at R² ≥ 0.6 over ≥ 30."""

from __future__ import annotations

from .pricing import calibrate_k, follower_tier, w_engagement

R2_FLOOR = 0.6
N_FLOOR = 30


def from_pilots(pilots: list[dict], creators: dict[str, dict], posts_by: dict[str, list]) -> dict:
    """Each pilot with impressions + a creator with posts contributes a pair."""
    pairs = []
    by_tier: dict[str, list] = {}
    icp_pairs = []
    for p in pilots:
        cid = p.get("creator_id")
        impr = p.get("impressions")
        if not cid or impr in (None, ""):
            continue
        posts = posts_by.get(cid) or []
        weng = w_engagement(posts)
        if weng <= 0:
            continue
        pair = (weng, float(impr))
        pairs.append(pair)
        cr = creators.get(cid) or {}
        tier = follower_tier(int(cr.get("followers") or 0))
        by_tier.setdefault(tier, []).append(pair)
        if p.get("icp_share") is not None:
            icp_pairs.append({
                "creator_id": cid,
                "actual": float(p["icp_share"]),
                "predicted": cr.get("icp_share_pred"),
            })

    k, r2 = calibrate_k(pairs)
    k_tier = {}
    for tier, pts in by_tier.items():
        kt, _ = calibrate_k(pts)
        k_tier[tier] = kt

    calibrated = bool(r2 is not None and r2 >= R2_FLOOR and len(pairs) >= N_FLOOR)
    drift = []
    for row in icp_pairs:
        if row["predicted"] is None:
            continue
        drift.append({
            **row,
            "delta": row["actual"] - float(row["predicted"]),
        })
    return {
        "n": len(pairs),
        "k": k,
        "r2": r2,
        "k_by_tier": k_tier,
        "calibrated": calibrated,
        "impressions_label": "calibrated" if calibrated else "estimated",
        "threshold": {"r2": R2_FLOOR, "n": N_FLOOR},
        "icp_drift": drift,
        "note": (
            f"R²={r2:.2f} on {len(pairs)} creators — "
            + ("impressions flip to calibrated" if calibrated else
               f"need R²≥{R2_FLOOR} on ≥{N_FLOOR} creators to flip estimated→calibrated")
        ) if r2 is not None else f"{len(pairs)} pairs; need ≥2 to fit k",
    }
