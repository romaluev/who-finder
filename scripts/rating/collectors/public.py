"""Own scripts for the free floor.

ScrapeCreators is optional video depth, not the only way to a post count.
This collector never logs into LinkedIn, never fetches linkedin.com, and
never invents a name or a number — a failed fetch is an empty list.
"""

from __future__ import annotations

import html as htmlmod
import json
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from urllib.parse import parse_qs, urljoin, urlparse

from .. import auth, http
from ..util import clean, handle_from, norm_url, platform_of, to_int
from .base import Collector, Post, Profile

DDG_HTML = "https://html.duckduckgo.com/html/"
BRAVE_URL = "https://api.search.brave.com/res/v1/web/search"
HN_URL = "https://hn.algolia.com/api/v1/search"

BLOCKED_HOSTS = frozenset({
    "linkedin.com", "www.linkedin.com", "lnkd.in",
})

VIDEO_HOSTS = (
    "youtube.com", "www.youtube.com", "youtu.be", "m.youtube.com",
    "tiktok.com", "www.tiktok.com", "vm.tiktok.com",
)

_TAG_RE = re.compile(r"<[^>]+>")
_RESULT_A_RE = re.compile(
    r'class="result__a"[^>]*href="(?P<href>[^"]+)"[^>]*>(?P<title>.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)
_SNIPPET_RE = re.compile(
    r'class="result__snippet"[^>]*>(?P<snippet>.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)
_OG_RE = re.compile(
    r'<meta[^>]+(?:property|name)=["\']og:(?P<key>title|description|site_name)["\']'
    r'[^>]+content=["\'](?P<val>[^"\']+)["\']',
    re.I,
)
_OG_RE_SWAP = re.compile(
    r'<meta[^>]+content=["\'](?P<val>[^"\']+)["\']'
    r'[^>]+(?:property|name)=["\']og:(?P<key>title|description|site_name)["\']',
    re.I,
)
_FEED_RE = re.compile(
    r'<link[^>]+rel=["\'][^"\']*alternate[^"\']*["\'][^>]*>',
    re.I,
)
_HREF_RE = re.compile(r'href=["\']([^"\']+)["\']', re.I)
_TYPE_RE = re.compile(r'type=["\']([^"\']+)["\']', re.I)
_JSONLD_RE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(?P<body>.*?)</script>',
    re.I | re.S,
)


def host_of(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except ValueError:
        return ""


def is_blocked(url: str) -> bool:
    host = host_of(url)
    return host in BLOCKED_HOSTS or host.endswith(".linkedin.com")


def is_video(url: str) -> bool:
    host = host_of(url)
    return any(host == h or host.endswith("." + h.split(".", 1)[-1]) for h in VIDEO_HOSTS) or host in {
        "youtu.be", "youtube.com", "www.youtube.com", "tiktok.com", "www.tiktok.com",
    }


def _strip_html(fragment: str) -> str:
    return htmlmod.unescape(_TAG_RE.sub("", fragment or "")).strip()


def unwrap_ddg(href: str) -> str:
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
        window = text[match.end(): next_start]
        snippet_match = _SNIPPET_RE.search(window)
        snippet = _strip_html(snippet_match.group("snippet")) if snippet_match else ""
        items.append({
            "url": target,
            "title": _strip_html(match.group("title")),
            "snippet": snippet[:500],
        })
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
        items.append({
            "url": url,
            "title": str(raw.get("title") or ""),
            "snippet": str(raw.get("description") or raw.get("snippet") or ""),
        })
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
        items.append({
            "url": url,
            "title": str(raw.get("title") or ""),
            "snippet": f"HN via {author}" if author else "Hacker News",
        })
        if len(items) >= limit:
            break
    return items, None


def search_web(query: str, limit: int = 15) -> tuple[list[dict], str]:
    """Brave if a key is set, otherwise DuckDuckGo. Always returns a backend name."""
    brave = auth.token("brave")
    if brave:
        hits, err = search_brave(brave, query, limit)
        if hits:
            return hits, "brave"
        # fall through on empty or error
        _ = err
    hits, err = search_ddg(query, limit)
    if hits:
        return hits, "ddg"
    return [], err or "no public search hits"


def ytdlp_bin() -> str:
    return shutil.which("yt-dlp") or ""


def parse_ytdlp_lines(text: str, limit: int = 20) -> list[Post]:
    """Turn `yt-dlp --dump-json` stdout into posts. No network."""
    posts: list[Post] = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            raw = json.loads(line)
        except ValueError:
            continue
        if not isinstance(raw, dict):
            continue
        url = str(raw.get("webpage_url") or raw.get("url") or "").strip()
        title = clean(raw.get("title") or "")
        if not url and not title:
            continue
        if url and not url.startswith("http"):
            vid = str(raw.get("id") or "")
            url = f"https://www.youtube.com/watch?v={vid}" if vid else ""
        posted = str(raw.get("upload_date") or raw.get("timestamp") or "")
        if posted.isdigit() and len(posted) == 8:
            posted = f"{posted[:4]}-{posted[4:6]}-{posted[6:8]}"
        pid = str(raw.get("id") or url or title)
        posts.append(Post(
            id=pid,
            url=url,
            text=title or clean(raw.get("description") or "", 240),
            posted_at=posted,
            reactions=to_int(raw.get("like_count")),
            comments=to_int(raw.get("comment_count")),
            reposts=0,
            impressions=to_int(raw.get("view_count")) or None,
            format="video",
            source="ytdlp",
        ))
        if len(posts) >= limit:
            break
    return posts


def ytdlp_profile_from_raw(raw: dict, url: str) -> Profile | None:
    if not isinstance(raw, dict):
        return None
    name = clean(
        raw.get("channel") or raw.get("uploader") or raw.get("playlist_uploader") or ""
    )
    handle = clean(
        raw.get("channel_id") or raw.get("uploader_id") or raw.get("channel") or ""
    ).lstrip("@")
    about = clean(raw.get("description") or raw.get("channel_description") or "", 800)
    followers = to_int(
        raw.get("channel_follower_count") or raw.get("channel_follower_count")
        or raw.get("subscriber_count")
    )
    channel_url = str(
        raw.get("channel_url") or raw.get("uploader_url") or raw.get("webpage_url") or url
    )
    if not name and not channel_url:
        return None
    return Profile(
        url=norm_url(channel_url) or url,
        name=name or handle_from(channel_url, handle),
        handle=handle or handle_from(channel_url, name),
        headline=about[:180],
        about=about,
        followers=followers,
        platform=platform_of(channel_url) or "youtube",
        source="ytdlp",
    )


def ytdlp_channel(url: str, n: int = 20) -> tuple[Profile | None, list[Post]]:
    bin_path = ytdlp_bin()
    if not bin_path:
        return None, []
    n = min(max(int(n), 1), 40)
    try:
        proc = subprocess.run(
            [bin_path, "--dump-json", "--no-warnings", "--playlist-end", str(n), url],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None, []
    posts = parse_ytdlp_lines(proc.stdout or "", limit=n)
    prof = None
    for line in (proc.stdout or "").splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            raw = json.loads(line)
        except ValueError:
            continue
        prof = ytdlp_profile_from_raw(raw, url)
        if prof:
            break
    return prof, posts


def parse_feed(xml: str, limit: int = 20) -> list[Post]:
    """RSS 2.0 or Atom. No network."""
    if not (xml or "").strip():
        return []
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return []
    ns = {"a": "http://www.w3.org/2005/Atom"}
    items = []
    for item in root.findall(".//item"):
        title = clean((item.findtext("title") or ""))
        link = clean((item.findtext("link") or ""))
        body = clean(item.findtext("description") or item.findtext("content:encoded") or "")
        date = clean(item.findtext("pubDate") or item.findtext("date") or "")
        items.append((title, link, body, date))
    for entry in root.findall(".//a:entry", ns) or root.findall(".//{http://www.w3.org/2005/Atom}entry"):
        title = clean(entry.findtext("a:title", default="", namespaces=ns) or entry.findtext("{http://www.w3.org/2005/Atom}title") or "")
        link_el = entry.find("a:link", ns)
        if link_el is None:
            link_el = entry.find("{http://www.w3.org/2005/Atom}link")
        link = (link_el.get("href") if link_el is not None else "") or clean(
            entry.findtext("a:id", default="", namespaces=ns) or ""
        )
        body = clean(
            entry.findtext("a:summary", default="", namespaces=ns)
            or entry.findtext("{http://www.w3.org/2005/Atom}summary")
            or entry.findtext("{http://www.w3.org/2005/Atom}content")
            or ""
        )
        date = clean(
            entry.findtext("a:updated", default="", namespaces=ns)
            or entry.findtext("{http://www.w3.org/2005/Atom}updated")
            or entry.findtext("{http://www.w3.org/2005/Atom}published")
            or ""
        )
        items.append((title, link, body, date))
    posts = []
    for title, link, body, date in items:
        if not title and not link and not body:
            continue
        url = norm_url(link) if link else ""
        pid = url or f"rss:{abs(hash(title + body))}"
        posts.append(Post(
            id=pid,
            url=url,
            text=title or body[:240],
            posted_at=date,
            reactions=0,
            comments=0,
            reposts=0,
            impressions=None,
            format="article",
            source="rss",
        ))
        if len(posts) >= limit:
            break
    return posts


def discover_feeds(html: str, base: str) -> list[str]:
    found = []
    for tag in _FEED_RE.findall(html or ""):
        type_match = _TYPE_RE.search(tag)
        typ = (type_match.group(1) if type_match else "").lower()
        if typ and "rss" not in typ and "atom" not in typ and "xml" not in typ:
            continue
        href_m = _HREF_RE.search(tag)
        if not href_m:
            continue
        found.append(urljoin(base, href_m.group(1)))
    for guess in ("/feed", "/rss.xml", "/atom.xml", "/feed.xml", "/rss"):
        found.append(urljoin(base, guess))
    # de-dupe, keep order
    seen, out = set(), []
    for u in found:
        n = norm_url(u)
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    return out[:8]


def parse_public_html(html: str, url: str) -> Profile | None:
    """og: + JSON-LD Person. Never invents a follower count."""
    if not html:
        return None
    og = {}
    for rx in (_OG_RE, _OG_RE_SWAP):
        for m in rx.finditer(html):
            og.setdefault(m.group("key").lower(), htmlmod.unescape(m.group("val")))
    name = clean(og.get("title") or "")
    about = clean(og.get("description") or "")
    for m in _JSONLD_RE.finditer(html):
        try:
            data = json.loads(m.group("body"))
        except ValueError:
            continue
        blobs = data if isinstance(data, list) else [data]
        for blob in blobs:
            if not isinstance(blob, dict):
                continue
            typ = blob.get("@type") or ""
            if isinstance(typ, list):
                typ = " ".join(str(x) for x in typ)
            if "person" not in str(typ).lower() and "organization" not in str(typ).lower():
                continue
            name = clean(blob.get("name") or name)
            about = clean(blob.get("description") or blob.get("jobTitle") or about)
    if not name and not about:
        return None
    return Profile(
        url=norm_url(url),
        name=name.split("|")[0].split(" - ")[0].strip() or handle_from(url),
        handle=handle_from(url, name),
        headline=about[:180],
        about=about,
        followers=0,
        platform=platform_of(url) or "web",
        source="public",
    )


def _looks_like_profile(url: str) -> bool:
    u = (url or "").lower()
    host = host_of(u)
    if "linkedin.com" in host and "/in/" in u:
        return True
    if "youtube.com" in host and ("/@" in u or "/channel/" in u or "/c/" in u):
        return True
    if "youtu.be" in host:
        return False
    if "tiktok.com" in host and "/@" in u:
        return True
    if "instagram.com" in host and u.rstrip("/").count("/") >= 3:
        return True
    return False


def hits_to_profiles(hits: list[dict], source: str = "public") -> list[Profile]:
    out = []
    seen = set()
    for h in hits:
        url = norm_url(h.get("url") or "")
        if not url or url in seen:
            continue
        if not _looks_like_profile(url):
            continue
        seen.add(url)
        title = clean(h.get("title") or "")
        name = title.split("|")[0].split(" - ")[0].split(" – ")[0].strip()
        out.append(Profile(
            url=url,
            name=name or handle_from(url),
            handle=handle_from(url, name),
            headline=clean(h.get("snippet") or ""),
            about="",
            followers=0,
            platform=platform_of(url),
            source=source,
        ))
    return out


class PublicCollector(Collector):
    """yt-dlp, RSS, public HTML, and web search. Always available."""

    name = "public"
    cost_per_profile = 0.0
    cost_per_post = 0.0

    def available(self) -> bool:
        return True

    def can_touch(self, url: str) -> bool:
        if not url:
            return False
        if is_blocked(url):
            return False
        return True

    def profile(self, url: str) -> Profile | None:
        url = norm_url(url)
        if not url or is_blocked(url):
            return None
        if is_video(url) and ytdlp_bin():
            prof, _ = ytdlp_channel(url, n=1)
            if prof:
                return prof
        try:
            html = http.get_text(url, timeout=20)
        except Exception:
            return None
        return parse_public_html(html, url)

    def posts(self, url: str, n: int = 20) -> list[Post]:
        url = norm_url(url)
        if not url or is_blocked(url):
            return []
        if is_video(url) and ytdlp_bin():
            _, posts = ytdlp_channel(url, n=n)
            if posts:
                return posts
        try:
            html = http.get_text(url, timeout=20)
        except Exception:
            return []
        for feed in discover_feeds(html, url):
            if is_blocked(feed):
                continue
            try:
                xml = http.get_text(feed, timeout=15)
            except Exception:
                continue
            posts = parse_feed(xml, limit=n)
            if posts:
                return posts
        return []

    def search(self, query: str, limit: int = 20) -> list[Profile]:
        hits, backend = search_web(query, limit=limit)
        extra, _ = search_hn(query, limit=min(8, limit))
        return hits_to_profiles(hits + extra, source=f"public:{backend}")
