"""Keyless and optional-key search backends.

Returns the same hit shape `parse_google` already wants (`url` / `title` /
`snippet`). Never invents a name, handle, or URL — if a backend fails, the
caller gets an empty list and an error string, not a guessed identity.

These functions never raise. The search waterfall decides whether a failure
is a gap or a reason to try the next backend.
"""

from __future__ import annotations

import html as htmlmod
import json
import re
import shutil
import subprocess
from urllib.parse import parse_qs, urlparse

from . import http

DDG_HTML = "https://html.duckduckgo.com/html/"
BRAVE_URL = "https://api.search.brave.com/res/v1/web/search"
HN_URL = "https://hn.algolia.com/api/v1/search"

_TAG_RE = re.compile(r"<[^>]+>")
_RESULT_A_RE = re.compile(
    r'class="result__a"[^>]*href="(?P<href>[^"]+)"[^>]*>(?P<title>.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)
_SNIPPET_RE = re.compile(
    r'class="result__snippet"[^>]*>(?P<snippet>.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)


def _strip_html(fragment: str) -> str:
    return htmlmod.unescape(_TAG_RE.sub("", fragment or "")).strip()


def unwrap_ddg(href: str) -> str:
    """DuckDuckGo wraps result links as //duckduckgo.com/l/?uddg=<encoded>."""
    raw = (href or "").strip()
    if not raw:
        return ""
    if "uddg=" not in raw:
        if raw.startswith("//"):
            return f"https:{raw}"
        return raw
    try:
        loc = raw if raw.startswith("http") else f"https:{raw}" if raw.startswith("//") else raw
        target = parse_qs(urlparse(loc).query).get("uddg", [""])[0]
        return target or raw
    except (ValueError, AttributeError):
        return raw


def parse_ddg_html(text: str, limit: int = 20) -> list[dict]:
    """Turn DDG HTML into `{url, title, snippet}` rows. No network."""
    if not text:
        return []
    items: list[dict] = []
    matches = list(_RESULT_A_RE.finditer(text))
    for idx, match in enumerate(matches):
        if len(items) >= limit:
            break
        target = unwrap_ddg(match.group("href"))
        if not target.startswith("http"):
            continue
        next_start = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        window = text[match.end() : next_start]
        snippet_match = _SNIPPET_RE.search(window)
        snippet = _strip_html(snippet_match.group("snippet")) if snippet_match else ""
        items.append(
            {
                "url": target,
                "title": _strip_html(match.group("title")),
                "snippet": snippet[:500],
            }
        )
    return items


def search_ddg(query: str, limit: int) -> tuple[list[dict], str | None]:
    try:
        text = http.get_text(
            DDG_HTML,
            params={"q": query, "kl": "us-en"},
            headers={"Accept": "text/html"},
            timeout=25,
        )
    except Exception as exc:
        return [], str(exc)
    if not (text or "").strip():
        return [], "empty DuckDuckGo response"
    return parse_ddg_html(text, limit), None


def search_brave(token: str, query: str, limit: int) -> tuple[list[dict], str | None]:
    if not token:
        return [], "missing Brave key"
    try:
        data = http.get(
            BRAVE_URL,
            params={"q": query, "count": min(max(int(limit), 1), 20)},
            headers={"X-Subscription-Token": token, "Accept": "application/json"},
            timeout=20,
        )
    except Exception as exc:
        return [], str(exc)
    rows = ((data.get("web") or {}) if isinstance(data, dict) else {}).get("results") or []
    items = []
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        url = str(raw.get("url") or "").strip()
        if not url.startswith("http"):
            continue
        items.append(
            {
                "url": url,
                "title": str(raw.get("title") or ""),
                "snippet": str(raw.get("description") or raw.get("snippet") or ""),
            }
        )
        if len(items) >= limit:
            break
    return items, None


def search_hn(query: str, limit: int) -> tuple[list[dict], str | None]:
    try:
        data = http.get(
            HN_URL,
            params={"query": query, "hitsPerPage": min(max(int(limit), 1), 30), "tags": "story"},
            timeout=20,
        )
    except Exception as exc:
        return [], str(exc)
    items = []
    for raw in data.get("hits") or []:
        if not isinstance(raw, dict):
            continue
        oid = str(raw.get("objectID") or "")
        url = str(raw.get("url") or "").strip()
        if not url.startswith("http"):
            url = f"https://news.ycombinator.com/item?id={oid}" if oid else ""
        if not url:
            continue
        author = str(raw.get("author") or "")
        items.append(
            {
                "url": url,
                "title": str(raw.get("title") or ""),
                "snippet": f"HN via {author}" if author else "Hacker News",
            }
        )
        if len(items) >= limit:
            break
    return items, None


def ytdlp_bin() -> str:
    return shutil.which("yt-dlp") or ""


def search_ytdlp(query: str, limit: int) -> tuple[list[dict], str | None]:
    bin_path = ytdlp_bin()
    if not bin_path:
        return [], "yt-dlp not on PATH"
    n = min(max(int(limit), 1), 15)
    try:
        proc = subprocess.run(
            [bin_path, "--flat-playlist", "--dump-json", "--no-warnings", f"ytsearch{n}:{query}"],
            capture_output=True,
            text=True,
            timeout=45,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return [], str(exc)
    items = []
    for line in (proc.stdout or "").splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            raw = json.loads(line)
        except ValueError:
            continue
        if not isinstance(raw, dict):
            continue
        url = str(
            raw.get("channel_url") or raw.get("uploader_url") or raw.get("url") or ""
        ).strip()
        if not url.startswith("http"):
            handle = str(raw.get("uploader_id") or raw.get("channel_id") or "").lstrip("@")
            if handle and not handle.startswith("UC"):
                url = f"https://www.youtube.com/@{handle}"
            else:
                continue
        title = str(raw.get("uploader") or raw.get("channel") or raw.get("title") or "")
        items.append(
            {
                "url": url,
                "title": title,
                "snippet": str(raw.get("title") or ""),
            }
        )
        if len(items) >= limit:
            break
    if not items:
        err = (proc.stderr or "").strip()[:200]
        return [], err or "yt-dlp returned no rows"
    return items, None


def last30days_bin() -> str:
    return shutil.which("last30days") or ""
