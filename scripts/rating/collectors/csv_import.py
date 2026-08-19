"""CSV / JSON longlist. Favikon, Marketplace, consented analytics, manual sheets."""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path

from ..util import clean, handle_from, norm_url, platform_of, to_float, to_int
from .base import Collector, Post, Profile

URL_KEYS = (
    "url", "profile_url", "linkedin_url", "linkedin", "profile", "link",
    "linkedin profile", "linkedin profile url", "person linkedin url",
)
NAME_KEYS = ("name", "creator", "full_name", "fullname", "full name", "person name")
HEADLINE_KEYS = ("headline", "title", "role", "job_title", "job title", "current title")
ABOUT_KEYS = ("about", "bio", "description")
FOLLOWER_KEYS = ("followers", "audience", "subscriber_count", "fans", "linkedin followers")
CONN_KEYS = ("connections",)
LOC_KEYS = ("location", "geo", "country", "person location")


def _first(row: dict, keys: tuple[str, ...]) -> str:
    lower = {str(k).strip().lower(): v for k, v in row.items()}
    for k in keys:
        v = lower.get(k)
        if v not in (None, ""):
            return str(v).strip()
    return ""


def parse_row(row: dict, source: str = "csv") -> Profile | None:
    url = norm_url(_first(row, URL_KEYS))
    name = clean(_first(row, NAME_KEYS))
    if not url and not name:
        return None
    if not url:
        slug = handle_from("", name)
        url = f"https://www.linkedin.com/in/{slug}"
    handle = handle_from(url, name)
    return Profile(
        url=url,
        name=name or handle,
        handle=handle,
        headline=clean(_first(row, HEADLINE_KEYS)),
        about=clean(_first(row, ABOUT_KEYS)),
        followers=to_int(_first(row, FOLLOWER_KEYS) or row.get("followers")),
        connections=to_int(_first(row, CONN_KEYS)),
        location=clean(_first(row, LOC_KEYS)),
        platform=platform_of(url) or "linkedin",
        source=source,
    )


def parse_csv(text: str, source: str = "csv") -> list[Profile]:
    reader = csv.DictReader(io.StringIO(text))
    out = []
    for raw in reader:
        p = parse_row(raw, source=source)
        if p:
            out.append(p)
    return out


def parse_posts_csv(text: str, creator_url: str = "") -> list[Post]:
    reader = csv.DictReader(io.StringIO(text))
    out = []
    for raw in reader:
        lower = {str(k).strip().lower(): v for k, v in raw.items()}
        url = norm_url(str(lower.get("url") or lower.get("post_url") or ""))
        text_body = clean(lower.get("text") or lower.get("content") or "")
        if not url and not text_body:
            continue
        pid = url or f"csv:{abs(hash(text_body))}"
        out.append(Post(
            id=pid,
            url=url,
            text=text_body,
            posted_at=str(lower.get("posted_at") or lower.get("date") or ""),
            reactions=to_int(lower.get("reactions") or lower.get("likes") or 0),
            comments=to_int(lower.get("comments") or 0),
            reposts=to_int(lower.get("reposts") or lower.get("shares") or 0),
            impressions=to_int(lower.get("impressions")) or None,
            format=str(lower.get("format") or ""),
            source="csv",
            creator_url=creator_url,
        ))
    return out


def parse_who_finder_json(data) -> list[Profile]:
    """Accept a who-finder --agent envelope, a results object, or a list."""
    if isinstance(data, str):
        data = json.loads(data)
    entities = []
    hits = []
    if isinstance(data, dict):
        results = data.get("results") or data
        entities = results.get("entities") or results.get("creators") or []
        hits = results.get("hits") or []
        if not entities and isinstance(results, list):
            entities = results
    elif isinstance(data, list):
        entities = data
    out = []
    hits_by_id: dict[str, list] = {}
    for h in hits:
        if not isinstance(h, dict):
            continue
        ident = h.get("id") or f"{h.get('kind')}/{h.get('platform')}/{h.get('handle')}"
        hits_by_id.setdefault(ident, []).append(h)
    for raw in entities:
        if not isinstance(raw, dict):
            continue
        url = norm_url(raw.get("url") or "")
        name = clean(raw.get("name") or raw.get("handle") or "")
        if not url and not name:
            continue
        handle = raw.get("handle") or handle_from(url, name)
        platform = raw.get("platform") or platform_of(url) or "linkedin"
        if not url:
            url = f"https://www.{platform}.com/{handle}"
        ident = raw.get("id") or f"{raw.get('kind') or 'person'}/{platform}/{handle}"
        extra_hits = raw.get("hits") or raw.get("recent") or hits_by_id.get(ident) or []
        p = Profile(
            url=url,
            name=name or handle,
            handle=handle,
            headline=clean(raw.get("headline") or raw.get("snippet") or ""),
            about=clean(raw.get("bio") or raw.get("about") or ""),
            followers=to_int(raw.get("audience") or raw.get("followers") or raw.get("views")),
            connections=to_int(raw.get("connections")),
            location=clean(raw.get("location") or ""),
            platform=platform,
            source="who-finder",
            hits=extra_hits,
            likes=to_int(raw.get("likes")),
            comments=to_int(raw.get("comments")),
            shares=to_int(raw.get("shares")),
            views=to_int(raw.get("views")),
        )
        out.append(p)
    return out


def hits_to_posts(profile: Profile, creator_id: str) -> list[Post]:
    posts = []
    for i, h in enumerate(profile.get("hits") or []):
        if not isinstance(h, dict):
            continue
        url = norm_url(h.get("url") or h.get("sample_url") or "")
        text = clean(h.get("title") or h.get("text") or h.get("sample") or "")
        if not url and not text:
            continue
        pid = h.get("content_id") or url or f"{creator_id}:hit:{i}"
        posts.append(Post(
            id=str(pid),
            creator_id=creator_id,
            url=url,
            text=text,
            posted_at=str(h.get("posted_at") or ""),
            reactions=to_int(h.get("likes") or h.get("reactions")),
            comments=to_int(h.get("comments")),
            reposts=to_int(h.get("shares") or h.get("reposts")),
            impressions=to_int(h.get("views")) or None,
            format="",
            source="who-finder",
        ))
    return posts


class CSVCollector(Collector):
    name = "csv"

    def available(self) -> bool:
        return True

    def load(self, path: str | Path, source: str = "csv") -> list[Profile]:
        p = Path(path).expanduser()
        text = p.read_text(encoding="utf-8")
        if p.suffix.lower() == ".json":
            return parse_who_finder_json(text)
        return parse_csv(text, source=source)
