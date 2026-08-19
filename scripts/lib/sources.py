"""Public search via ScrapeCreators. No logged-in sessions.

LinkedIn discovery is Google-indexed public URLs (official Google search
endpoint), not a member cookie and not Sales Nav.
"""

from __future__ import annotations

import re
from typing import Any

from . import http
from .identity import parse_identity
from .scenarios import SCENARIOS
from .score import apply_flags, entity_score, hit_score

SC = "https://api.scrapecreators.com"

FRESHNESS = {
    "month": {
        "youtube": "this_month",
        "tiktok": "this-month",
        "instagram": "last-month",
        "google": "last-month",
    },
    "year": {
        "youtube": "this_year",
        "tiktok": "last-6-months",
        "instagram": "last-year",
        "google": "last-year",
    },
    "all": {
        "youtube": None,
        "tiktok": "all-time",
        "instagram": None,
        "google": None,
    },
}

GOOGLE_SOURCES = frozenset({
    "linkedin_people",
    "linkedin_companies",
    "linkedin_jobs",
    "x",
    "web",
    "reddit",
})


def _n(v: Any) -> int:
    if isinstance(v, bool):
        return 0
    if isinstance(v, (int, float)):
        return int(v)
    if isinstance(v, str):
        s = v.lower().replace(",", "").strip()
        m = re.match(r"^([\d.]+)\s*([kmb])?$", s)
        if m:
            num = float(m.group(1))
            mul = {None: 1, "k": 1_000, "m": 1_000_000, "b": 1_000_000_000}[m.group(2)]
            return int(num * mul)
        digits = re.sub(r"[^\d]", "", s)
        return int(digits) if digits else 0
    if isinstance(v, dict):
        for k in ("count", "text", "simpleText", "viewCount", "value"):
            if k in v:
                return _n(v[k])
    return 0


def _s(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, dict):
        return str(
            v.get("name")
            or v.get("title")
            or v.get("handle")
            or v.get("username")
            or v.get("text")
            or ""
        )
    return str(v).strip()


def _handle(raw: str) -> str:
    h = raw.strip().lstrip("@")
    h = re.sub(
        r"^https?://(www\.)?(youtube\.com|tiktok\.com|instagram\.com|linkedin\.com)/",
        "",
        h,
        flags=re.I,
    )
    h = h.split("?")[0].strip("/")
    for prefix in ("in/", "company/", "@", "channel/", "c/", "user/", "posts/"):
        if h.lower().startswith(prefix):
            h = h[len(prefix) :]
            break
    h = h.split("/")[0]
    h = re.sub(r"[^A-Za-z0-9._-]+", "", h)
    return h.strip() or raw.strip()


def youtube(token: str, query: str, limit: int, freshness: str = "month") -> list[dict]:
    params: dict[str, Any] = {"query": query, "includeExtras": "true"}
    upload = FRESHNESS.get(freshness, FRESHNESS["month"]).get("youtube")
    if upload:
        params["uploadDate"] = upload
    data = http.get(f"{SC}/v1/youtube/search", params=params, headers=http.sc_headers(token))
    return parse_youtube(data, limit)


def parse_youtube(data: dict, limit: int, scenario_kind: str = "person") -> list[dict]:
    videos: list = []
    for key in ("videos", "shorts", "items", "data"):
        block = data.get(key)
        if isinstance(block, list):
            videos.extend(block)
    hits = []
    for raw in videos:
        if not isinstance(raw, dict):
            continue
        if str(raw.get("type") or "").lower() in {"channel", "playlist", "shelf"}:
            continue
        ch = raw.get("channel") or raw.get("channel_name") or raw.get("uploader") or {}
        if isinstance(ch, dict):
            handle = _handle(
                _s(ch.get("handle") or ch.get("id") or ch.get("name") or ch.get("title"))
            )
            name = _s(ch.get("name") or ch.get("title") or handle)
            url = _s(ch.get("url")) or (
                f"https://www.youtube.com/@{handle}" if handle else ""
            )
        else:
            handle = _handle(_s(ch))
            name = handle
            url = f"https://www.youtube.com/@{handle}" if handle else ""
        if not handle:
            continue
        extras = raw.get("extras") if isinstance(raw.get("extras"), dict) else {}
        vid = _s(raw.get("id") or raw.get("video_id") or raw.get("videoId"))
        views = _n(
            raw.get("viewCountInt")
            or raw.get("view_count")
            or raw.get("views")
            or extras.get("viewCount")
        )
        likes = _n(
            raw.get("likeCount")
            or raw.get("like_count")
            or raw.get("likes")
            or extras.get("likeCount")
            or extras.get("likes")
        )
        comments = _n(
            raw.get("commentCount")
            or raw.get("comment_count")
            or raw.get("comments")
            or extras.get("commentCount")
        )
        hits.append(
            {
                "kind": scenario_kind,
                "platform": "youtube",
                "handle": handle,
                "name": name,
                "creator_url": url,
                "url": url,
                "content_id": vid or _s(raw.get("url")),
                "hit_url": _s(raw.get("url"))
                or (f"https://www.youtube.com/watch?v={vid}" if vid else url),
                "title": _s(raw.get("title")),
                "snippet": "",
                "posted_at": _s(
                    raw.get("publishedTime")
                    or raw.get("upload_date")
                    or raw.get("published_at")
                    or raw.get("date")
                )[:10],
                "views": views,
                "likes": likes,
                "comments": comments,
                "shares": 0,
                "score": hit_score(views, likes, comments),
            }
        )
        if len(hits) >= limit:
            break
    return hits


def tiktok(token: str, query: str, limit: int, freshness: str = "month") -> list[dict]:
    params: dict[str, Any] = {"query": query, "sort_by": "relevance"}
    posted = FRESHNESS.get(freshness, FRESHNESS["month"]).get("tiktok")
    if posted:
        params["date_posted"] = posted
    data = http.get(
        f"{SC}/v1/tiktok/search/keyword",
        params=params,
        headers=http.sc_headers(token),
    )
    return parse_tiktok(data, limit)


def parse_tiktok(data: dict, limit: int) -> list[dict]:
    entries = data.get("search_item_list") or data.get("data") or []
    hits = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        raw = entry.get("aweme_info") or entry
        if not isinstance(raw, dict):
            continue
        author = raw.get("author") or {}
        handle = _handle(_s(author.get("unique_id") if isinstance(author, dict) else author))
        name = _s(author.get("nickname") if isinstance(author, dict) else handle) or handle
        if not handle:
            continue
        stats = raw.get("statistics") if isinstance(raw.get("statistics"), dict) else {}
        vid = _s(raw.get("aweme_id") or raw.get("id"))
        views = _n(stats.get("play_count") or raw.get("play_count"))
        likes = _n(stats.get("digg_count") or raw.get("digg_count"))
        comments = _n(stats.get("comment_count"))
        shares = _n(stats.get("share_count"))
        hits.append(
            {
                "kind": "person",
                "platform": "tiktok",
                "handle": handle,
                "name": name,
                "creator_url": f"https://www.tiktok.com/@{handle}",
                "url": f"https://www.tiktok.com/@{handle}",
                "content_id": vid,
                "hit_url": _s(raw.get("share_url")).split("?")[0]
                or (f"https://www.tiktok.com/@{handle}/video/{vid}" if vid else ""),
                "title": _s(raw.get("desc"))[:180],
                "snippet": "",
                "posted_at": "",
                "views": views,
                "likes": likes,
                "comments": comments,
                "shares": shares,
                "score": hit_score(views, likes, comments, shares),
            }
        )
        if len(hits) >= limit:
            break
    return hits


def instagram(token: str, query: str, limit: int, freshness: str = "month") -> list[dict]:
    posted = FRESHNESS.get(freshness, FRESHNESS["month"]).get("instagram")
    try:
        data = http.get(
            f"{SC}/v2/instagram/reels/search",
            params={"query": query, "date_posted": posted},
            headers=http.sc_headers(token),
        )
    except http.HTTPError as exc:
        if exc.status == 500 and " " in query:
            data = http.get(
                f"{SC}/v2/instagram/reels/search",
                params={"query": re.sub(r"\s+", "", query).lower(), "date_posted": posted},
                headers=http.sc_headers(token),
            )
        else:
            raise
    return parse_instagram(data, limit)


def parse_instagram(data: dict, limit: int) -> list[dict]:
    items = data.get("items") or data.get("data") or data.get("reels") or []
    hits = []
    for raw in items:
        if not isinstance(raw, dict):
            continue
        owner = raw.get("owner") or raw.get("user") or {}
        handle = _handle(_s(owner.get("username") if isinstance(owner, dict) else owner))
        name = _s(owner.get("full_name") if isinstance(owner, dict) else handle) or handle
        if not handle:
            continue
        short = _s(raw.get("code") or raw.get("shortcode"))
        pk = _s(raw.get("pk") or raw.get("id") or short)
        views = _n(
            raw.get("video_play_count") or raw.get("play_count") or raw.get("view_count")
        )
        likes = _n(raw.get("like_count") or raw.get("likes"))
        comments = _n(raw.get("comment_count") or raw.get("comments"))
        cap = raw.get("caption")
        title = _s(cap.get("text") if isinstance(cap, dict) else cap)[:180]
        hits.append(
            {
                "kind": "person",
                "platform": "instagram",
                "handle": handle,
                "name": name,
                "creator_url": f"https://www.instagram.com/{handle}/",
                "url": f"https://www.instagram.com/{handle}/",
                "content_id": pk or short,
                "hit_url": _s(raw.get("url"))
                or (f"https://www.instagram.com/reel/{short}" if short else ""),
                "title": title,
                "snippet": "",
                "posted_at": "",
                "views": views,
                "likes": likes,
                "comments": comments,
                "shares": 0,
                "score": hit_score(views, likes, comments),
            }
        )
        if len(hits) >= limit:
            break
    return hits


def google_search(token: str, query: str, freshness: str = "month") -> dict:
    posted = FRESHNESS.get(freshness, FRESHNESS["month"]).get("google")
    params: dict[str, Any] = {"query": query}
    if posted:
        params["date_posted"] = posted
    return http.get(f"{SC}/v1/google/search", params=params, headers=http.sc_headers(token))


def parse_google(
    data: dict,
    limit: int,
    *,
    source: str,
    scenario_kind: str,
) -> list[dict]:
    results = data.get("results") or data.get("items") or data.get("data") or []
    hits = []
    for i, raw in enumerate(results):
        if not isinstance(raw, dict):
            continue
        url = _s(raw.get("url") or raw.get("link"))
        title = _s(raw.get("title"))
        snippet = _s(raw.get("description") or raw.get("snippet"))
        if not url:
            continue
        low = url.lower()
        if source == "linkedin_people" and "/company/" in low:
            continue
        if source == "linkedin_companies" and "/in/" in low:
            continue
        if source == "linkedin_jobs" and "linkedin.com" in low and "/jobs" not in low:
            continue
        ent = parse_identity(
            url, title, snippet, source=source, scenario_kind=scenario_kind
        )
        if not ent:
            continue
        if source == "linkedin_people" and ent["kind"] != "person":
            continue
        if source == "linkedin_companies" and ent["kind"] != "company":
            continue
        ent["content_id"] = url or f"{source}-{i}"
        ent["hit_url"] = url
        ent["title"] = (snippet or title)[:180]
        ent["note"] = "google-index: no engagement counts"
        hits.append(ent)
        if len(hits) >= limit:
            break
    return hits


def _kind_for(scenario: str, source: str) -> str:
    if source in {"linkedin_companies", "linkedin_jobs"}:
        return "company"
    spec = SCENARIOS.get(scenario) or {}
    if source in {"youtube", "web"} and spec.get("kind") == "company":
        return "company"
    if scenario == "compare" and source == "linkedin_companies":
        return "company"
    return spec.get("kind") or "person"


def _run_one(
    token: str,
    source: str,
    query: str,
    limit: int,
    freshness: str,
    scenario_kind: str,
) -> list[dict]:
    if source == "youtube":
        hits = youtube(token, query, limit, freshness)
        for h in hits:
            h["kind"] = scenario_kind
        return hits
    if source == "tiktok":
        return tiktok(token, query, limit, freshness)
    if source == "instagram":
        return instagram(token, query, limit, freshness)
    if source in GOOGLE_SOURCES:
        data = google_search(token, query, freshness)
        return parse_google(data, limit, source=source, scenario_kind=scenario_kind)
    raise ValueError(f"unknown source {source}")


def search_step(
    token: str,
    source: str,
    query: str,
    limit: int,
    freshness: str,
    scenario: str,
    side: str = "",
    label: str = "",
    weight: float = 1.0,
) -> tuple[list[dict], str | None]:
    kind = _kind_for(scenario, source)
    try:
        hits = _run_one(token, source, query, limit, freshness, kind)
    except Exception as exc:
        return [], f"{source}/{label or query}: {exc}"
    out = []
    for h in hits:
        h = apply_flags(h)
        h["side"] = side
        h["step_label"] = label
        h["weight"] = weight
        h["query"] = query
        out.append(h)
    return out, None


def run_plan(
    token: str,
    plan,
    limit: int,
    freshness: str,
) -> tuple[list[dict], list[dict], list[str], list[dict]]:
    """Execute every planned step. Returns entities, hits, errors, source_status."""
    all_hits: list[dict] = []
    errors: list[str] = []
    status: list[dict] = []
    per = max(8, limit)
    for step in plan.steps:
        hits, err = search_step(
            token,
            step.source,
            step.query,
            per,
            freshness,
            plan.scenario,
            side=step.side,
            label=step.label,
            weight=step.weight,
        )
        if err:
            errors.append(err)
            status.append(
                {
                    "source": step.source,
                    "label": step.label,
                    "query": step.query,
                    "ok": False,
                    "error": err,
                    "n": 0,
                    "state": "error",
                }
            )
            continue
        all_hits.extend(hits)
        status.append(
            {
                "source": step.source,
                "label": step.label,
                "query": step.query,
                "ok": True,
                "n": len(hits),
                "state": "ok" if hits else "no-results",
            }
        )
    entities = rollup_entities(all_hits, plan.scenario)[:limit]
    return entities, all_hits, errors, status


def rollup_entities(hits: list[dict], scenario: str) -> list[dict]:
    by: dict[tuple[str, str, str], list[dict]] = {}
    meta: dict[tuple[str, str, str], dict] = {}
    for h in hits:
        key = (h["kind"], h["platform"], h["handle"])
        by.setdefault(key, []).append(h)
        meta[key] = h
    rows = []
    for key, group in by.items():
        h0 = meta[key]
        stats = entity_score(group, scenario)
        best = max(group, key=lambda x: (x.get("score") or 0, x.get("views") or 0))
        sides = sorted({g.get("side") or "" for g in group if g.get("side")})
        rows.append(
            {
                "kind": key[0],
                "platform": key[1],
                "handle": key[2],
                "name": h0.get("name") or key[2],
                "url": h0.get("creator_url") or h0.get("url"),
                **stats,
                "sample": best.get("title"),
                "sample_url": best.get("hit_url") or best.get("url"),
                "side": ",".join(sides),
                "flags": stats.get("flags") or [],
            }
        )
    rows.sort(key=lambda r: r["score"], reverse=True)
    return rows
