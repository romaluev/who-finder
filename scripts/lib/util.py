"""Coercion helpers shared by the enrichment/scoring layer.

LinkedIn masks public profile fields with asterisks (`"******* ** * ******"`).
Treating that as a real headline is the worst failure this tool can have, so
masking detection lives here and every extractor runs through it.
"""

from __future__ import annotations

import re
from typing import Any

_NUM_SUFFIX = {None: 1, "k": 1_000, "m": 1_000_000, "b": 1_000_000_000}


def to_int(v: Any) -> int:
    if isinstance(v, bool):
        return 0
    if isinstance(v, (int, float)):
        return int(v)
    if isinstance(v, str):
        s = v.lower().replace(",", "").strip()
        m = re.match(r"^([\d.]+)\s*([kmb])?\b", s)
        if m:
            return int(float(m.group(1)) * _NUM_SUFFIX[m.group(2)])
        digits = re.sub(r"[^\d]", "", s)
        return int(digits) if digits else 0
    if isinstance(v, dict):
        for k in ("count", "value", "text", "simpleText"):
            if k in v:
                return to_int(v[k])
    return 0


def to_str(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, dict):
        for k in ("name", "title", "text", "description", "simpleText"):
            if k in v:
                return to_str(v[k])
        return ""
    if isinstance(v, list):
        return " ".join(to_str(x) for x in v if x)
    return str(v).strip()


def is_masked(text: str) -> bool:
    """LinkedIn returns asterisk-masked strings for non-public fields."""
    s = (text or "").strip()
    if not s:
        return False
    stars = s.count("*")
    return stars >= 3 and stars / max(len(s), 1) > 0.25


def clean(text: Any, limit: int = 0) -> str:
    s = re.sub(r"<[^>]+>", " ", to_str(text))
    s = re.sub(r"\s+", " ", s).strip()
    if is_masked(s):
        return ""
    return s[:limit] if limit else s


def human(n: int) -> str:
    n = int(n or 0)
    for cutoff, suffix, div in ((1_000_000_000, "B", 1_000_000_000), (1_000_000, "M", 1_000_000), (1_000, "k", 1_000)):
        if n >= cutoff:
            val = n / div
            return f"{val:.1f}".rstrip("0").rstrip(".") + suffix
    return str(n)


STOP = frozenset("""
a an the and or of for to in on with at by from is are was were be been being this that these those
i we you they he she it our your their his her its my me us them who whom whose what which when where
how why all any both each few more most other some such no nor not only own same so than too very can
will just don should now about into over after before above below up down out off again further then
once here there as if because while during through against between under s t don t re ve ll d m o y
make makes making made build builds building built teach teaches help helps helping work works working
use uses using used get gets getting got want wants need needs like likes look looks looking know knows
come comes take takes see sees based love loves join joins learn learns share shares create creates
creating creator best new news also every year years day days time times thing things way ways lot
people person team teams company companies world today great good really much many well back going
""".split())

# Cluster themes must read like a topic, not a verb. Four characters is the
# shortest that reliably does (`saas`, `ugc` is allowed via the keyword pass).
CLUSTER_MIN_LEN = 4


def keywords(text: str, limit: int = 12) -> list[str]:
    toks = re.findall(r"[a-z][a-z0-9+.#-]{2,}", (text or "").lower())
    seen: dict[str, int] = {}
    for t in toks:
        if t in STOP or len(t) < 3:
            continue
        seen[t] = seen.get(t, 0) + 1
    ranked = sorted(seen.items(), key=lambda kv: (-kv[1], kv[0]))
    return [k for k, _ in ranked[:limit]]


def plural(n: int, one: str, many: str = "") -> str:
    return one if n == 1 else (many or one + "s")
