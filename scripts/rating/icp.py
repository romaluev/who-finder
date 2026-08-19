"""ICP rules. Same idea as who-finder: a file you own, reasons attributed."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from . import db

DIRECTOR_PLUS = ("Director", "VP", "C-level", "Founder/Owner")
FUNCTIONS = (
    "Marketing", "Growth", "Brand", "Content", "Demand Gen", "CMO",
    "Creative", "Digital", "Performance",
)

SENIORITY_PATTERNS = [
    (r"\b(cmo|ceo|cto|cfo|coo|chief\b)", "C-level"),
    (r"\b(founder|co-founder|owner|proprietor)\b", "Founder/Owner"),
    (r"\b(vp\b|vice president|svp|evp)\b", "VP"),
    (r"\b(director|head of)\b", "Director"),
    (r"\b(manager|lead)\b", "Manager"),
    (r"\b(specialist|coordinator|associate|intern|student)\b", "IC"),
]

FUNCTION_PATTERNS = [
    (r"\b(cmo|marketing|growth|demand|brand|content|creative|digital|performance)\b", None),
]

FUNCTION_MAP = [
    (r"\bcmo\b|chief marketing", "CMO"),
    (r"\bdemand\b", "Demand Gen"),
    (r"\bgrowth\b", "Growth"),
    (r"\bbrand\b", "Brand"),
    (r"\bcontent\b", "Content"),
    (r"\bcreative\b", "Creative"),
    (r"\bperformance\b", "Performance"),
    (r"\bdigital\b", "Digital"),
    (r"\bmarketing\b", "Marketing"),
]

GEO_PATTERNS = [
    (r"\b(united states|usa|u\.s\.|new york|san francisco|los angeles|austin|chicago|seattle|boston)\b", "US"),
    (r"\b(united kingdom|uk|london|manchester)\b", "UK"),
    (r"\b(germany|berlin|munich|hamburg)\b", "DE"),
    (r"\b(france|paris)\b", "FR"),
    (r"\b(netherlands|amsterdam)\b", "NL"),
    (r"\b(sweden|stockholm|norway|oslo|denmark|copenhagen|finland|helsinki|nordic)\b", "Nordics"),
    (r"\b(canada|toronto|vancouver)\b", "CA"),
]


class ConfigError(RuntimeError):
    pass


def package_config() -> Path:
    return Path(__file__).resolve().parents[2] / "config" / "icp.json"


def config_path(explicit: str | None = None) -> Path:
    if explicit:
        return Path(explicit).expanduser()
    env = os.environ.get("CREATOR_RATING_ICP")
    if env:
        return Path(env).expanduser()
    local = db.home() / "icp.json"
    if local.exists():
        return local
    return package_config()


def load(explicit: str | None = None) -> dict:
    path = config_path(explicit)
    try:
        cfg = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        cfg = json.loads(package_config().read_text(encoding="utf-8"))
        cfg["_path"] = ""
        return cfg
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{path} is not valid JSON (line {exc.lineno}: {exc.msg})") from exc
    except OSError as exc:
        raise ConfigError(f"{path} could not be read: {exc}") from exc
    if not isinstance(cfg, dict):
        raise ConfigError(f"{path} must contain a JSON object")
    cfg["_path"] = str(path)
    return cfg


def write_template(explicit: str | None = None) -> Path:
    src = package_config()
    dest = Path(explicit).expanduser() if explicit else db.home() / "icp.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    return dest


def classify_headline(headline: str, about: str = "", location: str = "") -> dict:
    """Rule-based seniority / function / geo from a headline. Never invents a company."""
    blob = f"{headline or ''} {about or ''} {location or ''}".lower()
    seniority = ""
    for pat, label in SENIORITY_PATTERNS:
        if re.search(pat, blob):
            seniority = label
            break
    function = ""
    for pat, label in FUNCTION_MAP:
        if re.search(pat, blob):
            function = label
            break
    geo = ""
    for pat, label in GEO_PATTERNS:
        if re.search(pat, blob):
            geo = label
            break
    agency = bool(re.search(r"\b(agency|studio)\b", blob))
    return {
        "seniority": seniority,
        "function": function,
        "geo": geo,
        "agency": agency,
        "headline": headline or "",
    }


def is_icp(row: dict, cfg: dict | None = None) -> bool:
    cfg = cfg or load()
    seniority = row.get("seniority") or ""
    function = row.get("function") or ""
    title = (row.get("headline") or "").lower()
    director = seniority in set(cfg.get("seniority_director_plus") or DIRECTOR_PLUS)
    fn_ok = function in set(cfg.get("functions") or FUNCTIONS)
    titles = [t.lower() for t in (cfg.get("title_contains") or [])]
    title_hit = any(t in title for t in titles)
    if director and fn_ok:
        return True
    if title_hit:
        return True
    if row.get("agency") and seniority in {"Founder/Owner", "C-level"}:
        agency_titles = [t.lower() for t in (cfg.get("agency_titles") or [])]
        if any(t in title for t in agency_titles) or seniority in {"Founder/Owner", "C-level"}:
            return True
    return False


def is_director_plus(row: dict, cfg: dict | None = None) -> bool:
    cfg = cfg or load()
    return (row.get("seniority") or "") in set(cfg.get("seniority_director_plus") or DIRECTOR_PLUS)


def is_marketing(row: dict, cfg: dict | None = None) -> bool:
    cfg = cfg or load()
    return (row.get("function") or "") in set(cfg.get("functions") or FUNCTIONS)


def geo_fit(row: dict, cfg: dict | None = None) -> bool:
    cfg = cfg or load()
    geo = (row.get("geo") or "").lower()
    targets = [g.lower() for g in (cfg.get("geo") or [])]
    return bool(geo) and any(geo == t or geo in t or t in geo for t in targets)
