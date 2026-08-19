"""Greedy picker: max ICP impressions, penalise overlap, stay under budget."""

from __future__ import annotations


def pick(
    rows: list[dict],
    pairs: list[dict],
    *,
    budget: float,
    overlap_penalty: float = 0.35,
    overlap_threshold: float = 0.35,
) -> dict:
    """rows need id, fair (or asking), icp_impressions, tier, name."""
    remaining = [r for r in rows if r.get("tier") not in {"D"} and (r.get("fair") or 0) > 0]
    remaining.sort(key=lambda r: -float(r.get("icp_impressions") or 0))
    overlap = {(p["a"], p["b"]): p["score"] for p in pairs}
    overlap.update({(p["b"], p["a"]): p["score"] for p in pairs})

    chosen: list[dict] = []
    spend = 0.0
    reach = 0.0
    skipped = []

    def ov(a: str, b: str) -> float:
        return overlap.get((a, b), 0.0)

    for row in remaining:
        cost = float(row.get("fair") or 0)
        if spend + cost > budget:
            skipped.append({**row, "why": "over budget"})
            continue
        hit = None
        for c in chosen:
            score = ov(row["id"], c["id"])
            if score >= overlap_threshold:
                hit = (c, score)
                break
        if hit:
            other, score = hit
            skipped.append({
                **row,
                "why": f"overlap {score:.2f} with {other.get('name') or other['id']} — buy one",
            })
            continue
        # Soft penalty: reduce credited reach by overlap with the set.
        penalty = 0.0
        for c in chosen:
            penalty = max(penalty, ov(row["id"], c["id"]))
        credited = float(row.get("icp_impressions") or 0) * (1.0 - overlap_penalty * penalty)
        chosen.append(row)
        spend += cost
        reach += credited

    return {
        "chosen": chosen,
        "skipped": skipped,
        "spend": spend,
        "budget": budget,
        "icp_impressions": reach,
        "n": len(chosen),
    }
