"""Engine-owned synthesis.

The reason this is Python and not a prompt: a model handed twenty rows will
write a confident paragraph whether or not the rows support it. Every line
this module emits is derived from a count it can point at, and sources that
returned nothing are reported as `no-results` rather than silently dropped —
"we found no X" and "we did not successfully look for X" are different claims.
"""

from __future__ import annotations

from collections import Counter

from . import notices, portrait
from .util import CLUSTER_MIN_LEN, plural, to_int

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
        elif state == "unparsed":
            out.append(f"{label} UNPARSED({s.get('raw_n', 0)} raw)")
        else:
            out.append(f"{label} ERROR")
    return out


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
    source_status: list[dict] | None = None,
) -> list[str]:
    out: list[str] = []
    if not rows:
        steps = source_status or []
        drifted = [s for s in steps if s.get("state") == "unparsed"]
        if drifted and len(drifted) == len(steps):
            return [
                "Nothing was read. Every source answered, but in a shape this build "
                "could not parse (see GAPS) — that is a parser failure, not evidence "
                "that nobody matches. Do not report this as an empty market."
            ]
        if drifted:
            n = len(drifted)
            return [
                f"No entities matched among the sources that parsed, but {n} "
                f"{plural(n, 'source')} drifted (see GAPS). Treat this as partial."
            ]
        return ["No entities matched. Widen freshness or drop a source filter."]

    # Attach ids so landscape can join rows to dossiers even when the caller
    # built dossiers without going through report._ident.
    ds = []
    for i, d in enumerate(dossiers):
        d = dict(d)
        if not d.get("id") and i < len(rows):
            r = rows[i]
            d["id"] = r.get("id") or f"{r.get('kind')}/{r.get('platform')}/{r.get('handle')}"
        ds.append(d)
    out.extend(portrait.landscape(rows, ds, topic=topic, n_new=n_new, n_known=n_known))
    return out


def easy_to_miss(rows: list[dict], dossiers: list[dict]) -> list[str]:
    """Notices a ranking table will not show. Empty if nothing surprising."""
    ds = []
    for i, d in enumerate(dossiers):
        d = dict(d)
        if not d.get("id") and i < len(rows):
            r = rows[i]
            d["id"] = r.get("id") or f"{r.get('kind')}/{r.get('platform')}/{r.get('handle')}"
        ds.append(d)
    return [n["text"] for n in notices.of_set(rows, ds)]


def gaps(dossiers: list[dict], source_status: list[dict], errors: list[str]) -> list[str]:
    out = []
    dead = [s for s in (source_status or []) if s.get("state") == "error"]
    if dead:
        out.append(
            "Sources that errored (absence here is not evidence): "
            + ", ".join(f"{s.get('source')}:{s.get('label')}" for s in dead)
        )
    drifted = [s for s in (source_status or []) if s.get("state") == "unparsed"]
    if drifted:
        parts = []
        for s in drifted:
            where = s.get("stray_at")
            if s.get("raw_n"):
                why = f"{s['raw_n']} records we could not read"
            elif where:
                why = f"records moved to '{where}' ({s.get('stray_n', 0)})"
            else:
                why = f"expected container missing (keys: {'/'.join(s.get('response_keys') or []) or 'none'})"
            parts.append(f"{s.get('source')}:{s.get('label')} — {why}")
        out.append(
            "SCHEMA DRIFT — these sources answered but this build could not read them, "
            "so their silence is a parser bug, not an absence: " + "; ".join(parts)
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
            rows,
            dossiers,
            scenario=scenario,
            topic=topic,
            n_new=n_new,
            n_known=n_known,
            source_status=source_status,
        ),
        "notices": easy_to_miss(rows, dossiers),
        "clusters": clusters(dossiers),
        "gaps": gaps(dossiers, source_status, errors),
    }
