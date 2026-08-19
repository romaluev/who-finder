"""Bright Data LinkedIn scrapers. Profiles, posts-by-profile, people search.

Without a key this collector reports unavailable and returns empty lists —
the pipeline continues on the floor below it.
"""

from __future__ import annotations

from .. import auth, http
from ..util import clean, handle_from, norm_url, platform_of, to_int
from .base import Collector, Post, Profile

# Dataset ids are the public Bright Data LinkedIn scrapers. A missing/invalid
# key fails the HTTP call; we never invent a profile to paper over that.
POSTS_DATASET = "gd_lyy3jxxn1c1v3bm86"
PROFILES_DATASET = "gd_l1viktl72bvl7bjuj0"


class BrightDataCollector(Collector):
    name = "brightdata"
    cost_per_profile = 0.0015
    cost_per_post = 0.0015

    def __init__(self, token: str | None = None):
        self._token = token if token is not None else auth.token("brightdata")

    def available(self) -> bool:
        return bool(self._token)

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"}

    def profile(self, url: str) -> Profile | None:
        if not self._token:
            return None
        try:
            data = http.post(
                "https://api.brightdata.com/datasets/v3/scrape",
                payload={"input": [{"url": norm_url(url)}], "dataset_id": PROFILES_DATASET},
                headers=self._headers(),
                timeout=60,
            )
        except Exception:
            return None
        row = _first_row(data)
        if not row:
            return None
        return _profile_from(row, source="brightdata")

    def posts(self, url: str, n: int = 40) -> list[Post]:
        if not self._token:
            return []
        try:
            data = http.post(
                "https://api.brightdata.com/datasets/v3/scrape",
                payload={"input": [{"url": norm_url(url), "limit": n}], "dataset_id": POSTS_DATASET},
                headers=self._headers(),
                timeout=90,
            )
        except Exception:
            return []
        rows = _rows(data)
        out = []
        for raw in rows[:n]:
            p = _post_from(raw)
            if p:
                out.append(p)
        return out

    def search(self, query: str, limit: int = 50) -> list[Profile]:
        if not self._token:
            return []
        try:
            data = http.post(
                "https://api.brightdata.com/datasets/v3/scrape",
                payload={"input": [{"keyword": query, "limit": limit}], "dataset_id": PROFILES_DATASET},
                headers=self._headers(),
                timeout=90,
            )
        except Exception:
            return []
        out = []
        for raw in _rows(data)[:limit]:
            p = _profile_from(raw, source="brightdata")
            if p:
                out.append(p)
        return out


def _rows(data) -> list[dict]:
    if not isinstance(data, dict):
        return []
    for key in ("data", "results", "snapshot"):
        val = data.get(key)
        if isinstance(val, list):
            return [r for r in val if isinstance(r, dict)]
    if isinstance(data.get("input"), list):
        return [r for r in data["input"] if isinstance(r, dict)]
    return []


def _first_row(data) -> dict:
    rows = _rows(data)
    return rows[0] if rows else {}


def _profile_from(raw: dict, source: str) -> Profile | None:
    url = norm_url(raw.get("url") or raw.get("profile_url") or raw.get("linkedin_url") or "")
    name = clean(raw.get("name") or raw.get("full_name") or "")
    if not url and not name:
        return None
    handle = handle_from(url, name)
    if not url:
        url = f"https://www.linkedin.com/in/{handle}"
    return Profile(
        url=url,
        name=name or handle,
        handle=handle,
        headline=clean(raw.get("headline") or raw.get("position") or ""),
        about=clean(raw.get("about") or raw.get("description") or ""),
        followers=to_int(raw.get("followers") or raw.get("follower_count")),
        connections=to_int(raw.get("connections") or raw.get("connection_count")),
        location=clean(raw.get("location") or raw.get("city") or ""),
        platform=platform_of(url) or "linkedin",
        source=source,
    )


def _post_from(raw: dict) -> Post | None:
    url = norm_url(raw.get("url") or raw.get("post_url") or "")
    text = clean(raw.get("text") or raw.get("content") or raw.get("title") or "")
    if not url and not text:
        return None
    pid = str(raw.get("id") or raw.get("post_id") or url or f"bd:{abs(hash(text))}")
    return Post(
        id=pid,
        url=url,
        text=text,
        posted_at=str(raw.get("date") or raw.get("posted_at") or raw.get("timestamp") or ""),
        reactions=to_int(raw.get("likes") or raw.get("num_likes") or raw.get("reactions")),
        comments=to_int(raw.get("comments") or raw.get("num_comments")),
        reposts=to_int(raw.get("reposts") or raw.get("shares") or raw.get("num_shares")),
        impressions=to_int(raw.get("impressions")) or None,
        format=str(raw.get("type") or raw.get("format") or ""),
        source="brightdata",
    )
