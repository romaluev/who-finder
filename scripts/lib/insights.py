"""Engine-owned synthesis.

The reason this is Python and not a prompt: a model handed twenty rows will
write a confident paragraph whether or not the rows support it. Every line
this module emits is derived from a count it can point at, and sources that
returned nothing are reported as `no-results` rather than silently dropped —
"we found no X" and "we did not successfully look for X" are different claims.
"""

from __future__ import annotations

from collections import Counter

from .util import CLUSTER_MIN_LEN, human, plural, to_int

# Below this many enriched profiles, shared vocabulary is coincidence, not a theme.
CLUSTER_MIN_DOCS = 4


def coverage(source_status: list[dict]) -> list[str]:
    out = []
    for s in source_status or []:
        label = f"{s.get('source')}:{s.get('label')}" if s.get("label") else str(s.get("source"))
        state = s.get("state") or ("ok" if s.get("ok") else "error")
        if state == "ok":
            out.append(f"{label} ok({s.get('n', 0)})")
        elif state == "no-results":
            out.append(f"{label} no-results")
        else:
            out.append(f"{label} ERROR")
    return out


def _median(nums: list[int]) -> int:
    vals = sorted(n for n in nums if n > 0)
    if not vals:
        return 0
    mid = len(vals) // 2
    return vals[mid] if len(vals) % 2 else (vals[mid - 1] + vals[mid]) // 2


def clusters(dossiers: list[dict], min_members: int = 2, limit: int = 5) -> list[dict]:
    """Group by shared profile vocabulary. Names the themes that actually recur."""
    docs = [(d["id"], set(d.get("topics") or [])) for d in dossiers if d.get("topics")]
    if len(docs) < max(min_members, CLUSTER_MIN_DOCS):
        return []
    df = Counter()
    for _, terms in docs:
        df.update(terms)
    ceiling = max(min_members, int(len(docs) * 0.8))
    candidates = [
        t
        for t, c in df.most_common(40)
        if min_members <= c <= ceiling and len(t) >= CLUSTER_MIN_LEN
    ]
    out = []
    used: set[str] = set()
    for term in candidates:
        members = [i for i, terms in docs if term in terms and i not in used]
        if len(members) < min_members:
            continue
        out.append({"theme": term, "n": len(members), "members": members[:8]})
        used.update(members)
        if len(out) >= limit:
            break
    return out


def findings(
    rows: list[dict],
    dossiers: list[dict],
    *,
    scenario: str,
    topic: str,
    n_new: int,
    n_known: int,
) -> list[str]:
    out: list[str] = []
    if not rows:
        return ["No entities matched. Widen freshness or drop a source filter."]

    plats = Counter(r.get("platform") for r in rows)
    plat_str = ", ".join(f"{p} {c}" for p, c in plats.most_common(4))
    out.append(
        f"{len(rows)} {plural(len(rows), 'entity', 'entities')} "
        f"({n_new} new, {n_known} already in roster) across {plat_str}."
    )

    enriched = [d for d in dossiers if d.get("enriched")]
    if enriched:
        auds = [to_int(d.get("audience")) for d in enriched]
        sized = [a for a in auds if a > 0]
        if sized:
            out.append(
                f"Audience: median {human(_median(sized))}, largest {human(max(sized))}, "
                f"{len(sized)}/{len(enriched)} enriched profiles report a number."
            )
        masked = [d for d in enriched if d.get("masked")]
        if masked:
            n = len(masked)
            out.append(
                f"{n} LinkedIn {plural(n, 'profile')} {plural(n, 'hides', 'hide')} job history "
                "publicly — that role line comes from the search snippet, not the profile."
            )

    bands = Counter(r.get("fit_band") for r in rows if r.get("fit_band"))
    if bands:
        parts = [f"{bands[b]} {b}" for b in ("strong", "possible", "weak", "off", "unknown") if bands.get(b)]
        out.append("ICP fit: " + ", ".join(parts) + ".")

    sig = Counter()
    for d in dossiers:
        sig.update(s for s in (d.get("signals") or []) if s not in {"posting", "small-audience", "mid-audience", "large-audience"})
    notable = [f"{c} {s}" for s, c in sig.most_common(5) if c > 0]
    if notable:
        out.append("Signals: " + ", ".join(notable) + ".")

    themes = clusters(dossiers)
    if themes:
        out.append(
            "Recurring themes: "
            + ", ".join(f"{t['theme']} ({t['n']})" for t in themes)
            + "."
        )

    unenriched = [d for d in dossiers if not d.get("enriched")]
    if unenriched:
        n = len(unenriched)
        out.append(
            f"{n} {plural(n, 'row')} {plural(n, 'is', 'are')} discovery-only "
            "(no profile endpoint, or the fetch failed); their fit is provisional."
        )
    return out


def gaps(dossiers: list[dict], source_status: list[dict], errors: list[str]) -> list[str]:
    out = []
    dead = [s for s in (source_status or []) if s.get("state") == "error"]
    if dead:
        out.append(
            "Sources that errored (absence here is not evidence): "
            + ", ".join(f"{s.get('source')}:{s.get('label')}" for s in dead)
        )
    empty = [s for s in (source_status or []) if s.get("state") == "no-results"]
    if empty:
        out.append(
            "Sources that ran and returned nothing: "
            + ", ".join(f"{s.get('source')}:{s.get('label')}" for s in empty)
        )
    no_aud = [d for d in dossiers if d.get("enriched") and not to_int(d.get("audience"))]
    if no_aud:
        n = len(no_aud)
        out.append(f"{n} enriched {plural(n, 'profile')} {plural(n, 'exposes', 'expose')} no follower count.")
    for e in (errors or [])[:3]:
        out.append(f"error: {e}")
    return out


def build(
    rows: list[dict],
    dossiers: list[dict],
    *,
    scenario: str,
    topic: str,
    n_new: int,
    n_known: int,
    source_status: list[dict],
    errors: list[str],
) -> dict:
    return {
        "coverage": coverage(source_status),
        "findings": findings(
            rows, dossiers, scenario=scenario, topic=topic, n_new=n_new, n_known=n_known
        ),
        "clusters": clusters(dossiers),
        "gaps": gaps(dossiers, source_status, errors),
    }
