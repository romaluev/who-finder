"""Audience overlap. Jaccard on engager hashes; topic proxy when absent."""

from __future__ import annotations

from .util import jaccard


def matrix(sets: dict[str, set], *, kind: str = "jaccard") -> list[dict]:
    ids = list(sets)
    out = []
    for i, a in enumerate(ids):
        for b in ids[i + 1 :]:
            score = jaccard(sets[a], sets[b])
            out.append({"a": a, "b": b, "score": score, "kind": kind})
    return out


def proxy_sets(creators: list[dict]) -> dict[str, set]:
    """Topic + source proxy when engager sets are empty. Labelled as such."""
    out: dict[str, set] = {}
    for c in creators:
        tokens = set()
        mix = c.get("topic_mix")
        if isinstance(mix, dict):
            tokens.update(k for k, v in mix.items() if v)
        elif isinstance(mix, str) and mix:
            tokens.add(mix)
        if c.get("source"):
            tokens.add("src:" + str(c["source"]))
        if c.get("headline"):
            tokens.update(w.lower() for w in str(c["headline"]).split() if len(w) > 4)
        out[c["id"]] = tokens
    return out


def overlaps_for(cid: str, pairs: list[dict], names: dict[str, str], threshold: float = 0.0) -> list[dict]:
    hits = []
    for p in pairs:
        if cid not in {p["a"], p["b"]}:
            continue
        other = p["b"] if p["a"] == cid else p["a"]
        if p["score"] < threshold:
            continue
        hits.append({
            "id": other,
            "name": names.get(other, other),
            "score": p["score"],
            "kind": p.get("kind") or "jaccard",
        })
    hits.sort(key=lambda r: -r["score"])
    return hits
