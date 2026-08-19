"""Public contacts, extracted — never guessed.

A work email you invent from a name and a domain is the most expensive kind
of wrong: it looks like a finding and bounces. This module only returns
addresses and URLs that already appear on a public profile or in a link the
profile published. Pattern-guessing (`jane@acme.com`) is contact-goat's job,
and only when the user has that tool and has agreed to spend.
"""

from __future__ import annotations

import re
import shutil
from urllib.parse import urlparse

from .util import clean

EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
# Common "email me at name [at] domain [dot] com" obfuscation on creator bios.
OBFUSCATED = re.compile(
    r"\b([A-Z0-9._%+-]+)\s*(?:\[|\()?\s*at\s*(?:\]|\))?\s*([A-Z0-9.-]+)\s*(?:\[|\()?\s*dot\s*(?:\]|\))?\s*([A-Z]{2,})\b",
    re.I,
)
URL = re.compile(r"https?://[^\s<>\"']+", re.I)
HANDLE = re.compile(r"(?<!\w)@([A-Za-z0-9_.]{2,30})")

SOCIAL = {
    "linkedin.com": "linkedin",
    "youtube.com": "youtube",
    "youtu.be": "youtube",
    "x.com": "x",
    "twitter.com": "x",
    "instagram.com": "instagram",
    "tiktok.com": "tiktok",
    "github.com": "github",
    "calendly.com": "calendly",
    "cal.com": "calendar",
    "notion.site": "notion",
    "substack.com": "substack",
    "medium.com": "medium",
    "crunchbase.com": "crunchbase",
    "facebook.com": "facebook",
    "threads.net": "threads",
}

# Addresses that look like contacts but aren't.
THROW_AWAY = frozenset({
    "example.com", "email.com", "domain.com", "sentry.io", "wixpress.com",
    "googleapis.com", "schema.org", "w3.org", "placeholder.com",
})

PERSONAL_MAIL = frozenset({
    "gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "icloud.com",
    "me.com", "proton.me", "protonmail.com", "aol.com", "live.com",
})


def _host(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower().lstrip("www.")
    except Exception:
        return ""


def _kind_of(url: str) -> str:
    host = _host(url)
    for needle, kind in SOCIAL.items():
        if needle in host:
            return kind
    if host.endswith(".edu"):
        return "edu"
    if "linktr.ee" in host or "bio.link" in host or host.startswith("beacons."):
        return "link-in-bio"
    return "website"


def from_row(r: dict) -> dict:
    """Rebuild a harvestable dossier from a roster row + stored payload."""
    d = dict(r.get("payload") or {})
    for k in (
        "id", "kind", "platform", "handle", "name", "url", "headline", "bio",
        "snippet", "location", "audience", "audience_kind", "signals", "links",
        "similar", "people", "company", "recent", "masked", "audience_detail",
    ):
        if r.get(k) not in (None, "", [], {}) and not d.get(k):
            d[k] = r[k]
    return d


def harvest(d: dict, extra_text: str = "") -> dict:
    """Pull every public contact out of a dossier. Nothing is inferred."""
    blobs = [
        d.get("bio") or "",
        d.get("headline") or "",
        d.get("snippet") or "",
        extra_text,
        " ".join(str(x) for x in (d.get("links") or [])),
        str(d.get("url") or ""),
    ]
    for item in d.get("recent") or []:
        if isinstance(item, dict):
            blobs.append(item.get("url") or "")
            blobs.append(item.get("title") or "")
        else:
            blobs.append(str(item))
    co = d.get("company") or {}
    if isinstance(co, dict):
        blobs.append(co.get("website") or "")
        blobs.append(co.get("url") or "")
    text = " ".join(blobs)

    emails: list[str] = []
    for m in EMAIL.findall(text):
        addr = m.lower().rstrip(".,;)")
        if addr.split("@")[-1] not in THROW_AWAY and addr not in emails:
            emails.append(addr)
    for m in OBFUSCATED.finditer(text):
        addr = f"{m.group(1)}@{m.group(2)}.{m.group(3)}".lower()
        if addr.split("@")[-1] not in THROW_AWAY and addr not in emails:
            emails.append(addr)

    links: list[dict] = []
    seen = set()
    raw_links = list(d.get("links") or [])
    raw_links += URL.findall(text)
    if d.get("url"):
        raw_links.insert(0, d["url"])
    for raw in raw_links:
        url = clean(raw).rstrip(".,);")
        if not url or url in seen:
            continue
        if not url.startswith("http"):
            if "@" in url and "." in url and " " not in url:
                # YouTube's `email` field is sometimes a bare address.
                addr = url.lower()
                if addr not in emails and addr.split("@")[-1] not in THROW_AWAY:
                    emails.append(addr)
                continue
            url = "https://" + url
        seen.add(url)
        kind = _kind_of(url)
        # The profile URL itself is already on the card; keep other links.
        if kind == "linkedin" and url.rstrip("/") == str(d.get("url") or "").rstrip("/"):
            continue
        links.append({"url": url, "kind": kind, "host": _host(url)})

    handles = []
    for m in HANDLE.findall(text):
        h = m.lower()
        if h not in handles and h not in {"handle", "username"}:
            handles.append(h)

    takes_meetings = any(l["kind"] in {"calendly", "calendar"} for l in links)
    personal = [e for e in emails if e.split("@")[-1] in PERSONAL_MAIL]
    edu = [e for e in emails if e.split("@")[-1].endswith(".edu")]
    return {
        "emails": emails[:4],
        "links": links[:10],
        "handles": handles[:6],
        "takes_meetings": takes_meetings,
        "has_personal_site": any(l["kind"] == "website" for l in links),
        "personal_emails": personal[:4],
        "edu_emails": edu[:4],
    }


def attach(d: dict) -> dict:
    """Store the harvest on the dossier so later reads do not re-walk text."""
    d["contacts"] = harvest(d)
    return d


def label(link: dict) -> str:
    kind = link.get("kind") or "link"
    host = link.get("host") or ""
    names = {
        "calendly": "books meetings",
        "calendar": "books meetings",
        "github": "GitHub",
        "x": "X",
        "youtube": "YouTube",
        "instagram": "Instagram",
        "tiktok": "TikTok",
        "substack": "Substack",
        "link-in-bio": "link-in-bio",
        "crunchbase": "Crunchbase",
        "website": host or "website",
        "edu": host or ".edu",
    }
    return names.get(kind, host or kind)


def reach_line(c: dict) -> str:
    """One line a card can print: emails, then the most useful links."""
    bits = list(c.get("emails") or [])
    for l in c.get("links") or []:
        if l.get("kind") in {"calendly", "calendar"}:
            bits.append(l["url"])
        elif l.get("kind") == "website":
            bits.append(l["url"])
    # De-dupe, keep order.
    seen, out = set(), []
    for b in bits:
        if b and b not in seen:
            seen.add(b)
            out.append(b)
    return " · ".join(out[:5])


def contact_goat_bin() -> str | None:
    return shutil.which("contact-goat-pp-cli")


def handoff_lines(name: str, company: str = "") -> list[str]:
    """What an agent should run next if contact-goat is installed.

    We do not run it. Email lookup and warm-intro spend other people's credits
    and need logins this tool promised not to require. The agent runs it, and
    only after the user asked for an email or an intro.
    """
    bin_path = contact_goat_bin()
    if not bin_path:
        return []
    target = f'"{name}"' + (f' --company "{company}"' if company else "")
    return [
        f"{bin_path} doctor --agent",
        f"{bin_path} dossier {target} --agent",
        f"{bin_path} waterfall {target} --dry-run --agent",
    ]
