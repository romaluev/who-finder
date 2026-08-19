"""Turn a URL + title into a person or company identity.

Identity is kind/platform/handle. Same human on YouTube vs LinkedIn is two
rows — we do not merge across platforms (that is a later CRM job).
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

HANDLE_RE = re.compile(r"[^A-Za-z0-9._-]+")

COMPANY_HINTS = (
    " inc", " ltd", " llc", " gmbh", " company", " startup", " official",
    " careers", " we're hiring", "we are hiring", "headquarters",
    " pte", " corp", " corporation", " studios", " agency", " labs",
)


def _handle(raw: str) -> str:
    h = raw.strip().lstrip("@")
    h = HANDLE_RE.sub("", h.split("/")[0].split("?")[0])
    return h.strip()


def parse_identity(
    url: str,
    title: str = "",
    snippet: str = "",
    *,
    source: str = "",
    scenario_kind: str = "person",
) -> dict | None:
    if not url:
        return None
    p = urlparse(url)
    host = p.netloc.lower().replace("www.", "")
    parts = [x for x in p.path.split("/") if x]

    if "linkedin.com" in host:
        return _linkedin(parts, title, url, snippet, source)

    if host in {"youtube.com", "m.youtube.com", "youtu.be"}:
        handle = ""
        if parts and parts[0].startswith("@"):
            handle = _handle(parts[0])
        elif parts and parts[0] in {"channel", "c", "user"} and len(parts) > 1:
            handle = _handle(parts[1])
        else:
            handle = _handle(title.split("-")[-1] if title else "")
        if not handle:
            return None
        kind = "company" if (scenario_kind == "company" or _looks_company(title, snippet)) else "person"
        return _ent(kind, "youtube", handle, title, url, snippet)

    if host in {"tiktok.com", "vm.tiktok.com"}:
        if parts and parts[0].startswith("@"):
            handle = _handle(parts[0])
        elif parts:
            handle = _handle(parts[0])
        else:
            return None
        return _ent("person", "tiktok", handle, title, url, snippet)

    if host in {"instagram.com"}:
        if not parts or parts[0] in {"reel", "p", "stories", "explore"}:
            return None
        return _ent("person", "instagram", _handle(parts[0]), title, url, snippet)

    if host in {"x.com", "twitter.com"}:
        if not parts or parts[0] in {"search", "i", "intent", "hashtag", "home"}:
            return None
        return _ent("person", "x", _handle(parts[0]), title, url, snippet)

    if host in {"reddit.com", "old.reddit.com"}:
        if parts and parts[0] == "user" and len(parts) > 1:
            return _ent("person", "reddit", _handle(parts[1]), title, url, snippet)
        if parts and parts[0] == "r" and len(parts) > 1:
            return _ent("company", "reddit", _handle(parts[1]), title, url, snippet)

    if source in {"web", "linkedin_jobs"} or scenario_kind:
        return _web_fallback(host, title, url, snippet, source, scenario_kind)
    return None


def _linkedin(parts, title, url, snippet, source):
    if not parts:
        return None
    head = parts[0].lower()
    if head == "company" and len(parts) > 1:
        slug = _handle(parts[1])
        return _ent("company", "linkedin", slug, title, url, snippet)
    if head == "in" and len(parts) > 1:
        slug = _handle(parts[1])
        return _ent("person", "linkedin", slug, title, url, snippet)
    if head == "jobs":
        # Title is usually "Role | Company | LinkedIn"
        company = ""
        bits = [b.strip() for b in re.split(r"\s*\|\s*", title) if b.strip()]
        if len(bits) >= 2:
            company = bits[1]
        if not company and " at " in title.lower():
            company = re.split(r"\s+at\s+", title, maxsplit=1, flags=re.I)[-1]
            company = company.split("|")[0].strip()
        slug = _handle(company.replace(" ", "-")) or "job"
        return _ent("company", "linkedin", slug, title, url, snippet, role="job")
    if head == "posts" and len(parts) > 1:
        slug = re.sub(r"[-_]activity[-_].*$", "", parts[1], flags=re.I)
        return _ent("person", "linkedin", _handle(slug), title, url, snippet)
    if head in {"pulse", "feed", "showcase"}:
        name = title.split("|")[0].split(" on LinkedIn")[0].strip()
        kind = "company" if source == "linkedin_companies" else "person"
        return _ent(kind, "linkedin", _handle(name), title, url, snippet)
    return None


def _web_fallback(host, title, url, snippet, source, scenario_kind):
    if source == "web" and scenario_kind == "person":
        name = title.split("|")[0].split(" - ")[0].split(",")[0].strip()
        handle = _handle(name.replace(" ", "-"))
        if handle and len(handle) > 2:
            return _ent("person", "web", handle, title, url, snippet)
    if _looks_company(title, snippet) or scenario_kind == "company":
        slug = _handle(host.split(".")[0])
        if slug and slug not in {"www", "com", "news", "blog"}:
            return _ent("company", "web", slug, title, url, snippet)
    return None


def _looks_company(title: str, snippet: str) -> bool:
    t = f"{title} {snippet}".lower()
    return any(w in t for w in COMPANY_HINTS)


def _ent(kind, platform, handle, title, url, snippet, role=""):
    if not handle:
        return None
    name = title.split("|")[0].split(" - ")[0].split(" on LinkedIn")[0].strip() or handle
    return {
        "kind": kind,
        "platform": platform,
        "handle": handle,
        "name": name[:180],
        "url": url,
        "title": (title or "")[:180],
        "snippet": (snippet or "")[:240],
        "role": role,
        "creator_url": url,
        "content_id": url,
        "views": 0,
        "likes": 0,
        "comments": 0,
        "shares": 0,
        "score": 0,
    }


def identity_key(row: dict) -> tuple[str, str, str]:
    return (row["kind"], row["platform"], row["handle"])


def identity_id(row: dict) -> str:
    return f"{row['kind']}/{row['platform']}/{row['handle']}"


def parse_id(s: str) -> tuple[str, str, str]:
    """kind/platform/handle, or platform/handle (kind defaults to person)."""
    parts = [p for p in s.strip().split("/") if p]
    if len(parts) == 3:
        return parts[0].lower(), parts[1].lower(), parts[2].lstrip("@")
    if len(parts) == 2:
        return "person", parts[0].lower(), parts[1].lstrip("@")
    raise ValueError("identity is kind/platform/handle, e.g. person/youtube/mkbhd")
