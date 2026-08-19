"""Scores are scenario-local. Never rank a YouTube creator against a LinkedIn company."""

from __future__ import annotations

import re

COMPILATION_RE = re.compile(
    r"\b(compilation|best of|top\s*\d+|lofi|lo-fi|\d+\s*hours?|playlist)\b",
    re.I,
)


def hit_score(views=0, likes=0, comments=0, shares=0) -> int:
    return int(views or 0) + 10 * int(likes or 0) + 20 * int(comments or 0) + 5 * int(shares or 0)


def title_flags(title: str) -> list[str]:
    return ["compilation"] if COMPILATION_RE.search(title or "") else []


def apply_flags(hit: dict) -> dict:
    flags = title_flags(hit.get("title") or "")
    hit["flags"] = flags
    if "compilation" in flags:
        hit["score"] = int(hit.get("score") or 0) // 5
    return hit


def entity_score(hits: list[dict], scenario: str) -> dict:
    if not hits:
        return {"hit_count": 0, "score": 0, "views": 0, "likes": 0, "comments": 0, "shares": 0, "flags": []}
    views = sum(int(h.get("views") or 0) for h in hits)
    likes = sum(int(h.get("likes") or 0) for h in hits)
    comments = sum(int(h.get("comments") or 0) for h in hits)
    shares = sum(int(h.get("shares") or 0) for h in hits)
    flags: list[str] = []
    for h in hits:
        for f in h.get("flags") or []:
            if f not in flags:
                flags.append(f)
    raw = hit_score(views, likes, comments, shares)
    if scenario in {"people", "press", "hiring", "companies"} and raw == 0:
        # Google-indexed identities have no engagement. Rank by how often they appeared.
        raw = 10 * len(hits)
    if "compilation" in flags:
        raw //= 5
    return {
        "hit_count": len(hits),
        "score": raw,
        "views": views,
        "likes": likes,
        "comments": comments,
        "shares": shares,
        "flags": flags,
    }
