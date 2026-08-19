"""Longlist ingest. Dedupe on profile URL.

Sources, cheapest first: CSV, who-finder, Clay table, public search,
manual URL, Bright Data keyword (last).
"""

from __future__ import annotations

from pathlib import Path

from . import db, economy
from .collectors import brightdata, clay, csv_import, public, who_finder
from .collectors.csv_import import hits_to_posts
from .util import clean, handle_from, norm_url, platform_of


def ingest_profiles(conn, profiles: list[dict], ts: str, source: str = "") -> dict:
    n_new = n_known = 0
    ids = []
    for raw in profiles:
        row = dict(raw)
        if source and not row.get("source"):
            row["source"] = source
        novelty = db.upsert_creator(conn, row, ts)
        if novelty == "new":
            n_new += 1
        else:
            n_known += 1
        stored = db.get_by_url(conn, row["url"]) or db.get_creator(conn, row.get("id") or "")
        if not stored:
            continue
        ids.append(stored["id"])
        for post in hits_to_posts(row, stored["id"]):
            db.upsert_post(conn, post, ts)
    return {"n_new": n_new, "n_known": n_known, "n": n_new + n_known, "ids": ids}


def from_csv(conn, path: str, ts: str, source: str = "csv") -> dict:
    profiles = csv_import.CSVCollector().load(path, source=source)
    return ingest_profiles(conn, profiles, ts, source=source)


def from_who_finder(conn, data, ts: str) -> dict:
    profiles = who_finder.WhoFinderCollector().ingest(data)
    return ingest_profiles(conn, profiles, ts, source="who-finder")


def from_manual(conn, *, url: str, name: str = "", headline: str = "",
                followers: int = 0, about: str = "", ts: str) -> dict:
    url = norm_url(url)
    if not url:
        raise ValueError("manual nomination needs a profile url")
    handle = handle_from(url, name)
    profile = {
        "url": url,
        "name": name or handle,
        "handle": handle,
        "headline": clean(headline),
        "about": clean(about),
        "followers": followers,
        "platform": platform_of(url),
        "source": "manual",
    }
    return ingest_profiles(conn, [profile], ts, source="manual")


def from_clay(conn, path: str, ts: str) -> dict:
    profiles = clay.parse_path(path)
    return ingest_profiles(conn, profiles, ts, source="clay")


def from_search(conn, query: str, ts: str, *, limit: int = 25, cheap: bool = True) -> dict:
    """Public first, Clay next, Bright Data only when not --cheap."""
    used = []
    profiles = public.PublicCollector().search(query, limit=limit)
    if profiles:
        used.append("public")
    if len(profiles) < limit:
        col = clay.ClayCollector()
        if col.available():
            extra = col.search(query, limit=limit - len(profiles))
            if extra:
                used.append("clay")
                profiles.extend(extra)
    if not cheap and len(profiles) < max(3, limit // 2):
        col = brightdata.BrightDataCollector()
        if col.available():
            extra = col.search(query, limit=limit)
            if extra:
                used.append("brightdata")
                profiles.extend(extra)
    result = ingest_profiles(conn, profiles, ts, source=used[0] if used else "public")
    result["backends"] = used
    result["plan"] = economy.search_plan(cheap=cheap)
    return result


def from_brightdata(conn, query: str, ts: str, limit: int = 50) -> dict:
    return from_search(conn, query, ts, limit=limit, cheap=False)


def from_path(conn, path: str, ts: str) -> dict:
    p = Path(path).expanduser()
    text = p.read_text(encoding="utf-8")
    if p.suffix.lower() == ".json":
        return from_who_finder(conn, text, ts)
    return from_csv(conn, str(p), ts)
