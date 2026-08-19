"""Is this person or company worth your time?

Fit is a local, inspectable rule set — a JSON file you own, not a model
judgement. Every point is attributed to a named reason, so the answer to
"why is this a 78?" is always in the output.

Absence of evidence is not evidence of a bad fit. An entity we could not
enrich gets band `unknown`, never `off`. Ranking an unknown as a hard no is
how a tool like this quietly buries the best lead in the list.
"""

from __future__ import annotations

import json
import math
import os
import re
from pathlib import Path

from .util import human, to_int

BANDS = ("strong", "possible", "weak", "off", "unknown")

# Used when the operator has not written an ICP file yet. Topic terms are
# injected from the search brief so the tool is useful on first run.
GENERIC = {
    "name": "generic",
    "must_any": [],
    "boost": {
        "founder": 12, "co-founder": 12, "ceo": 12, "cto": 8, "head of": 10,
        "director": 8, "vp ": 8, "lead": 5, "owner": 8, "agency": 8,
        "studio": 6, "producer": 6, "marketing": 5, "growth": 6, "creative": 5,
    },
    "penalty": {
        "student": -18, "intern": -14, "aspiring": -12, "looking for work": -10,
        "seeking opportunities": -10, "job seeker": -12,
    },
    "audience": {"min": 500, "sweet_min": 5_000, "sweet_max": 3_000_000, "weight": 18},
    "geo": {"prefer": [], "weight": 6},
    "signals": {
        "hiring": 8, "funded": 10, "recent-round": 8, "posting": 6,
        "verified": 4, "large-audience": 6, "mid-audience": 4,
    },
}

TEMPLATE = {
    "name": "my-icp",
    "_note": "Every key is optional. Delete what you do not need.",
    "_must_any": "Topic gate. If set and none of these appear in bio/headline/topics, the row is capped at weak.",
    "must_any": ["ai video", "generative video", "video ads"],
    "_boost": "Substring -> points. Matched against headline + bio + title.",
    "boost": {"founder": 15, "head of": 12, "creative director": 12, "agency": 10, "ugc": 8},
    "_penalty": "Substring -> negative points.",
    "penalty": {"student": -20, "intern": -15, "aspiring": -12},
    "_audience": "Followers / subscribers / employees. sweet_min..sweet_max earns full weight.",
    "audience": {"min": 1_000, "sweet_min": 10_000, "sweet_max": 2_000_000, "weight": 20},
    "_geo": "Lowercase country or city substrings.",
    "geo": {"prefer": ["united states", "united kingdom", "canada"], "weight": 8},
    "_signals": "Signal name -> points. See `who-finder signals` for the list.",
    "signals": {"hiring": 10, "funded": 12, "recent-round": 10, "posting": 6, "verified": 4},
}


def config_path(explicit: str | None = None) -> Path:
    if explicit:
        return Path(explicit).expanduser()
    env = os.environ.get("WHO_FINDER_ICP")
    if env:
        return Path(env).expanduser()
    from .db import home

    return home() / "icp.json"


class ConfigError(RuntimeError):
    """A hand-edited ICP file that cannot be used.

    Raised rather than silently falling back to the generic rules: someone who
    edited this file expects their rules to be the ones scoring the run, and a
    quiet fallback would produce a plausible ranking against the wrong ICP.
    """


def load(explicit: str | None = None, topic: str = "") -> dict:
    """Explicit path > env > <home>/icp.json > GENERIC seeded with the topic."""
    path = config_path(explicit)
    if path.exists():
        try:
            cfg = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ConfigError(f"{path} is not valid JSON (line {exc.lineno}: {exc.msg})") from exc
        except OSError as exc:
            raise ConfigError(f"{path} could not be read: {exc}") from exc
        if not isinstance(cfg, dict):
            raise ConfigError(f"{path} must contain a JSON object, got {type(cfg).__name__}")
        cfg.setdefault("name", path.stem)
        cfg["_path"] = str(path)
        return cfg
    cfg = json.loads(json.dumps(GENERIC))
    cfg["must_any"] = topic_terms(topic)
    cfg["_path"] = ""
    cfg["_derived_from_topic"] = bool(cfg["must_any"])
    return cfg


def write_template(explicit: str | None = None) -> Path:
    path = config_path(explicit)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(TEMPLATE, indent=2) + "\n", encoding="utf-8")
    return path


STOP_TOPIC = frozenset({
    "people", "person", "company", "companies", "startup", "startups", "creator",
    "creators", "founder", "founders", "who", "are", "the", "for", "with", "and",
    "top", "best", "list", "find", "about", "using", "from", "that",
    "of", "in", "to", "at", "on", "by", "is", "or", "an", "as", "we", "it", "my",
})


def topic_terms(topic: str) -> list[str]:
    """Keep multi-word phrases intact; they are far better gates than single tokens.

    Two-letter tokens survive on purpose: `ai` and `ar` are the whole point of
    a brief like "ai video ads", and a length floor of 3 would silently drop them.
    """
    t = (topic or "").lower().strip()
    if not t:
        return []
    words = [w for w in re.findall(r"[a-z0-9+#.]+", t) if w not in STOP_TOPIC and len(w) >= 2]
    if not words:
        return []
    terms = [" ".join(words)] if len(words) > 1 else []
    terms += words[:4]
    return terms


def _haystack(d: dict) -> str:
    parts = [
        d.get("headline", ""),
        # The discovery snippet is kept alongside the fetched profile because it
        # is often the only place the job title survives.
        d.get("snippet", ""),
        d.get("bio", ""),
        d.get("name", ""),
        " ".join(d.get("topics") or []),
        " ".join(r.get("title", "") for r in (d.get("recent") or [])),
    ]
    co = d.get("company") or {}
    parts += [co.get("industry", ""), " ".join(co.get("specialties") or [])]
    return " ".join(p for p in parts if p).lower()


def fit(d: dict, cfg: dict) -> dict:
    """Dossier + config -> {score, band, reasons, gaps}."""
    hay = _haystack(d)
    reasons: list[str] = []
    gaps: list[str] = []
    score = 40.0

    has_text = len(hay.strip()) > 20
    must = [m.lower() for m in (cfg.get("must_any") or []) if m]
    topic_hit = [m for m in must if m in hay]
    if must:
        if topic_hit:
            score += 18
            reasons.append(f"topic match: {topic_hit[0]} (+18)")
        elif has_text:
            score -= 12
            reasons.append("no topic keyword in profile (-12)")
        else:
            gaps.append("no profile text to match topic against")

    boost_total = 0.0
    for term, pts in (cfg.get("boost") or {}).items():
        if term.lower() in hay:
            boost_total += float(pts)
            reasons.append(f"match '{term.strip()}' (+{pts})")
    boost_total = min(boost_total, 30.0)
    score += boost_total

    pen_total = 0.0
    for term, pts in (cfg.get("penalty") or {}).items():
        if term.lower() in hay:
            pen_total += float(pts)
            reasons.append(f"match '{term.strip()}' ({pts})")
    score += max(pen_total, -30.0)

    aud_cfg = cfg.get("audience") or {}
    aud = to_int(d.get("audience"))
    weight = float(aud_cfg.get("weight") or 0)
    if weight:
        if not aud:
            gaps.append(f"no audience number for {d.get('platform')}")
        elif aud < int(aud_cfg.get("min") or 0):
            score -= weight / 2
            reasons.append(f"audience {human(aud)} below floor (-{weight / 2:.0f})")
        elif int(aud_cfg.get("sweet_min") or 0) <= aud <= int(aud_cfg.get("sweet_max") or 10**12):
            score += weight
            reasons.append(f"audience {human(aud)} in target band (+{weight:.0f})")
        else:
            score += weight / 3
            reasons.append(f"audience {human(aud)} outside target band (+{weight / 3:.0f})")

    geo_cfg = cfg.get("geo") or {}
    prefer = [g.lower() for g in (geo_cfg.get("prefer") or [])]
    loc = f"{d.get('location', '')} {d.get('country', '')}".lower()
    if prefer:
        if not loc.strip():
            gaps.append("no location")
        elif any(g in loc for g in prefer):
            gw = float(geo_cfg.get("weight") or 0)
            score += gw
            reasons.append(f"geo match (+{gw:.0f})")

    for sig, pts in (cfg.get("signals") or {}).items():
        if sig in (d.get("signals") or []):
            score += float(pts)
            reasons.append(f"signal {sig} (+{pts})")

    score = max(0.0, min(100.0, score))

    if not d.get("enriched") and not has_text:
        band = "unknown"
        gaps.append("not enriched — score is provisional")
    elif must and not topic_hit and has_text:
        band = "weak" if score >= 40 else "off"
    elif score >= 70:
        band = "strong"
    elif score >= 52:
        band = "possible"
    elif score >= 34:
        band = "weak"
    else:
        band = "off"

    # A search snippet can look excellent, but we did not open the profile.
    # Calling that a strong fit is the kind of overclaim this tool exists to avoid.
    if band == "strong" and not d.get("enriched"):
        band = "possible"
        gaps.append("profile not fetched — capped at possible; run `enrich` to confirm")

    return {
        "score": round(score),
        "band": band,
        "reasons": reasons[:8],
        "gaps": gaps[:4],
        "icp": cfg.get("name", "generic"),
    }


def reach_points(audience: int) -> float:
    """Log scale: 1k -> 30, 10k -> 50, 100k -> 70, 1M -> 90.

    Linear reach would let one huge account dominate every ranking; the
    difference between 5k and 50k followers matters far more than the
    difference between 2M and 5M.
    """
    n = to_int(audience)
    if n <= 0:
        return 0.0
    return max(0.0, min(100.0, math.log10(n) * 20 - 30))


def priority(d: dict, f: dict, novelty: str = "new", engagement: int = 0) -> float:
    """Blend fit, reach and novelty into one sort key. Fit dominates."""
    p = 0.60 * float(f.get("score") or 0)
    p += 0.25 * reach_points(d.get("audience") or 0)
    if not to_int(d.get("audience")) and engagement:
        p += 0.25 * reach_points(engagement / 50)
    if novelty == "new":
        p += 8
    if f.get("band") == "unknown":
        p -= 6
    return round(max(0.0, min(100.0, p)), 1)


def rank(rows: list[dict]) -> list[dict]:
    return sorted(rows, key=lambda r: (r.get("priority") or 0, r.get("fit_score") or 0), reverse=True)
