"""Spend the subscription you already have before buying another scraper.

Clay covers profile / seniority / company size. yt-dlp and public search
cover video and the open web. Bright Data is last, and only for LinkedIn
posts that nothing else can see. ScrapeCreators and Apollo are skipped
when a cheaper source already did their job.
"""

from __future__ import annotations

from . import auth
from .collectors.public import is_blocked, is_video
from .util import platform_of

# New invoice. Clay is already on the company card.
PAID_NEW = frozenset({"brightdata", "apollo", "scrapecreators", "unipile"})
ALREADY_PAID = frozenset({"clay", "brave"})
FREE = frozenset({"csv", "who_finder", "public", "ytdlp", "rss", "pilots"})


def skip_reason(
    backend: str,
    *,
    caps: dict | None = None,
    has_posts: bool = False,
    has_video: bool = False,
    cheap: bool = False,
    platform: str = "",
) -> str | None:
    """Why this backend should not run. None means go ahead."""
    caps = caps if caps is not None else auth.capabilities()
    clay_on = bool((caps.get("clay") or {}).get("available"))
    if cheap and backend in PAID_NEW:
        return "cheap mode: skip a new invoice"
    if backend == "apollo" and clay_on:
        return "clay already covers seed-pool and ABM-style firmographics"
    if backend == "scrapecreators" and has_video and platform in {"youtube", "tiktok"}:
        return "public video (yt-dlp) already measures this YouTube/TikTok URL"
    if backend == "brightdata" and has_posts:
        return "posts already stored"
    if backend == "brightdata" and platform in {"youtube", "tiktok"} and has_video:
        return "video platform — yt-dlp is enough"
    return None


def lite_plan(
    url: str,
    *,
    caps: dict | None = None,
    cheap: bool = False,
    has_posts: bool = False,
    has_video: bool = False,
) -> list[dict]:
    """Ordered collect-lite steps. First successful posts win."""
    caps = caps if caps is not None else auth.capabilities()
    platform = platform_of(url)
    steps = []

    if platform == "linkedin" or is_blocked(url):
        steps.append({
            "backend": "public",
            "cost": 0,
            "why": "public LinkedIn index (DuckDuckGo/Brave) — linkedin.com is never fetched",
        })
    else:
        steps.append({
            "backend": "public",
            "cost": 0,
            "why": "yt-dlp / RSS / public HTML — no key",
        })

    if (caps.get("clay") or {}).get("available"):
        steps.append({
            "backend": "clay",
            "cost": 0,
            "why": "already subscribed — profile, title, company size",
        })

    reason = skip_reason(
        "brightdata", caps=caps, has_posts=has_posts,
        has_video=has_video, cheap=cheap, platform=platform,
    )
    if not reason and (caps.get("brightdata") or {}).get("available"):
        if platform == "linkedin" or is_blocked(url):
            steps.append({
                "backend": "brightdata",
                "cost": 0.06,
                "why": "LinkedIn posts and counts — last resort",
            })
    return steps


def search_plan(*, caps: dict | None = None, cheap: bool = True) -> list[dict]:
    """Discovery waterfall. Public first; Clay next; Bright Data last."""
    caps = caps if caps is not None else auth.capabilities()
    steps = [{"backend": "public", "cost": 0, "why": "DuckDuckGo / Brave / HN"}]
    if (caps.get("clay") or {}).get("available"):
        steps.append({"backend": "clay", "cost": 0, "why": "Clay people search (existing credits)"})
    if not cheap and (caps.get("brightdata") or {}).get("available"):
        steps.append({"backend": "brightdata", "cost": 0.06, "why": "LinkedIn keyword scrape"})
    return steps


def card(caps: dict | None = None, *, cheap: bool = False) -> list[str]:
    """Human lines for doctor: what we will spend, what we will skip."""
    caps = caps if caps is not None else auth.capabilities()
    lines = []
    clay_on = bool((caps.get("clay") or {}).get("available"))
    bd_on = bool((caps.get("brightdata") or {}).get("available"))
    ytdlp = bool((caps.get("public") or {}).get("ytdlp"))
    lines.append("public web + yt-dlp + RSS are free and run first")
    if clay_on:
        lines.append("clay is connected — use it instead of Apollo or a Bright Data profile pull")
    else:
        lines.append("clay table export is enough (no API key) — ingest --clay export.csv")
    if ytdlp:
        lines.append("yt-dlp is on PATH — YouTube/TikTok posts do not need ScrapeCreators")
    else:
        lines.append("install yt-dlp to measure video without ScrapeCreators")
    if cheap:
        lines.append("cheap mode is on — Bright Data / Unipile / Apollo will not run")
    elif bd_on:
        lines.append("bright data is reserved for LinkedIn posts still missing after the free floor")
    else:
        lines.append("no bright data key — LinkedIn post counts stay blank until a CSV or a key")
    skip_apollo = skip_reason("apollo", caps=caps)
    if skip_apollo:
        lines.append(f"skip apollo: {skip_apollo}")
    return lines
