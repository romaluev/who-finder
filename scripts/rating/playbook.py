"""Section 7 decision playbook as engine-owned notices.

A notice is omitted when the inputs are missing. Never guessed.
"""

from __future__ import annotations

from .features.provenance import Metric


def _f(m: Metric | None) -> float | None:
    if m and m.present:
        try:
            return float(m.value)
        except (TypeError, ValueError):
            return None
    return None


def of_one(name: str, cid: str, metrics: dict[str, Metric], *, social: float | None,
           engagement: float | None, interest: float | None) -> list[dict]:
    out = []

    def add(kind: str, text: str, evidence: str) -> None:
        out.append({"kind": kind, "text": text, "ids": [cid], "evidence": evidence})

    s, e, i = social, engagement, interest
    icp = _f(metrics.get("icp_share_engagers"))
    seed = _f(metrics.get("icp_share_seed_pool"))
    auth = _f(metrics.get("authenticity"))
    hits = _f(metrics.get("target_account_hits"))
    fit = _f(metrics.get("brand_topic_fit"))

    if s is not None and s >= 65 and auth is not None and auth < 55:
        add(
            "social-fake",
            f"**{name}** — the audience is right but engagement looks manufactured. "
            "Ask for the in-/out-of-network split; pilot with a Thought Leader Ad "
            "(you buy the audience, not the organic reach).",
            f"social {s:.0f}, authenticity {auth:.0f}",
        )
    if e is not None and e >= 65 and icp is not None and icp < 0.18:
        add(
            "reach-wrong-people",
            f"**{name}** — real reach into the wrong people. Good for awareness only "
            f"if the topic fit is high{'' if (fit or 0) >= 0.5 else '; otherwise pass'}.",
            f"engagement {e:.0f}, icp_share {icp:.0%}",
        )
    if i is not None and i >= 65 and (e is None or e < 45):
        add(
            "niche-expert",
            f"**{name}** — niche expert; cheap. Use for credibility content, "
            "comment sections, Collaborative posts — not for reach.",
            f"interest {i:.0f}, engagement {e}",
        )
    if s is not None and e is not None and i is not None and min(s, e, i) >= 60 and (hits is None or hits < 2):
        add(
            "coverage-no-abm",
            f"**{name}** — high on all three graphs, low target-account hits. "
            "Good for market coverage; pair with ABM ads for the named accounts.",
            f"target_account_hits={hits}",
        )
    if seed is not None and icp is not None and seed >= icp + 0.12:
        add(
            "seed-beats-engager",
            f"**{name}** — seed-pool ICP ({seed:.0%}) is well above engager ICP ({icp:.0%}). "
            "The core is right; posts start with the right first-hour signals "
            "and often outperform the estimate.",
            f"seed {seed:.0%} vs engager {icp:.0%}",
        )
    return out


def of_set(pairs: list[dict], names: dict[str, str], threshold: float = 0.35) -> list[dict]:
    out = []
    for p in pairs:
        if p.get("score", 0) < threshold:
            continue
        a = names.get(p["a"], p["a"])
        b = names.get(p["b"], p["b"])
        kind = p.get("kind") or "jaccard"
        proxy = " (topic proxy — no engager lists)" if kind == "proxy" else ""
        out.append({
            "kind": "overlap",
            "text": f"**{a}** and **{b}** share {p['score']:.0%} of their audience{proxy} — buy one, or sequence them.",
            "ids": [p["a"], p["b"]],
            "evidence": f"{kind}={p['score']:.2f}",
        })
    return out
