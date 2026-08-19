"""Second pass: turn an identity into a dossier.

Discovery (Google index) gives a name and a URL. That is a list, not research.
This module spends 1 credit per entity to answer the three questions a GTM
person actually asks: what do they do, how big is their audience, what are
they saying right now.

Two hard constraints live here:

1. LinkedIn no longer exposes job title / work history publicly. The API
   returns asterisk-masked strings for those fields. We detect the mask and
   fall back to the Google snippet rather than printing `******`.
2. YouTube and TikTok support `cache_max_age`, which serves a cached profile
   for 0 credits. Enrichment is the expensive half of this tool, so we always
   send it.
"""

from __future__ import annotations

from typing import Any

from . import http
from .util import clean, human, keywords, to_int, to_str

SC = "https://api.scrapecreators.com"

# Platforms with a profile endpoint. Anything else is discovery-only.
ENRICHABLE = frozenset({"linkedin", "youtube", "tiktok", "instagram", "x"})

CACHE_CHOICES = ("1d", "3d", "7d", "14d", "30d")

HIRING_WORDS = ("hiring", "we're hiring", "we are hiring", "join our team", "open role", "careers", "join us")
FUNDING_WORDS = ("raised", "series a", "series b", "series c", "seed round", "funding")


def enrichable(kind: str, platform: str) -> bool:
    return platform in ENRICHABLE


def profile_url(kind: str, platform: str, handle: str) -> str:
    if platform == "linkedin":
        seg = "company" if kind == "company" else "in"
        return f"https://www.linkedin.com/{seg}/{handle}/"
    if platform == "youtube":
        return f"https://www.youtube.com/@{handle}"
    if platform == "tiktok":
        return f"https://www.tiktok.com/@{handle}"
    if platform == "instagram":
        return f"https://www.instagram.com/{handle}/"
    if platform == "x":
        return f"https://x.com/{handle}"
    return ""


def _blank(kind: str, platform: str, handle: str, name: str = "") -> dict:
    return {
        "id": f"{kind}/{platform}/{handle}",
        "kind": kind,
        "platform": platform,
        "handle": handle,
        "name": name or handle,
        "headline": "",
        "headline_source": "",
        "snippet": "",
        "bio": "",
        "location": "",
        "country": "",
        "audience": 0,
        "audience_kind": "",
        "audience_detail": {},
        "recent": [],
        "topics": [],
        "links": [],
        "similar": [],
        "people": [],
        "signals": [],
        "company": {},
        "verified": False,
        "endpoint": "",
        "cached": False,
        "masked": False,
        "enriched": False,
        "error": "",
    }


def shallow(ent: dict) -> dict:
    """A dossier for an entity we did not spend a credit on.

    Carries whatever the search snippet gave us so unenriched rows still say
    something about the person instead of appearing as a bare handle.
    """
    kind = ent.get("kind") or "person"
    platform = ent.get("platform") or ""
    handle = ent.get("handle") or ""
    d = _blank(kind, platform, handle, to_str(ent.get("name")))
    d["url"] = ent.get("url") or profile_url(kind, platform, handle)
    snippet = clean(ent.get("sample_title") or ent.get("sample") or ent.get("title"))
    d["snippet"] = snippet
    d["headline"] = _headline_from_snippet(snippet, d["name"])
    d["headline_source"] = "search-snippet" if d["headline"] else ""
    d["topics"] = keywords(f"{d['headline']} {snippet}", limit=8)
    d["error"] = "not enriched"
    return d


def enrich(
    token: str,
    ent: dict,
    *,
    cache: str = "7d",
    timeout: int = 45,
) -> dict:
    """One entity -> dossier. Never raises; failures land in `error`."""
    kind = ent.get("kind") or "person"
    platform = ent.get("platform") or ""
    handle = ent.get("handle") or ""
    d = _blank(kind, platform, handle, to_str(ent.get("name")))
    d["url"] = ent.get("url") or profile_url(kind, platform, handle)

    fallback = clean(ent.get("sample_title") or ent.get("sample") or ent.get("title"))
    d["snippet"] = fallback
    if not enrichable(kind, platform):
        d["error"] = f"no profile endpoint for {platform}"
        d["headline"] = _headline_from_snippet(fallback, d["name"])
        d["headline_source"] = "search-snippet" if d["headline"] else ""
        return d

    try:
        if platform == "linkedin" and kind == "company":
            raw = http.get(
                f"{SC}/v1/linkedin/company",
                params={"url": profile_url(kind, platform, handle)},
                headers=http.sc_headers(token),
                timeout=timeout,
            )
            _linkedin_company(d, raw)
        elif platform == "linkedin":
            raw = http.get(
                f"{SC}/v1/linkedin/profile",
                params={"url": profile_url(kind, platform, handle)},
                headers=http.sc_headers(token),
                timeout=timeout,
            )
            _linkedin_person(d, raw)
        elif platform == "youtube":
            raw = http.get(
                f"{SC}/v1/youtube/channel",
                params={"handle": handle, "cache_max_age": cache},
                headers=http.sc_headers(token),
                timeout=timeout,
            )
            _youtube(d, raw)
        elif platform == "tiktok":
            raw = http.get(
                f"{SC}/v1/tiktok/profile",
                params={"handle": handle, "cache_max_age": cache},
                headers=http.sc_headers(token),
                timeout=timeout,
            )
            _tiktok(d, raw)
        elif platform == "instagram":
            raw = http.get(
                f"{SC}/v1/instagram/profile",
                params={"handle": handle},
                headers=http.sc_headers(token),
                timeout=timeout,
            )
            _instagram(d, raw)
        elif platform == "x":
            raw = http.get(
                f"{SC}/v1/twitter/profile",
                params={"handle": handle},
                headers=http.sc_headers(token),
                timeout=timeout,
            )
            _twitter(d, raw)
    except http.HTTPError as exc:
        d["error"] = f"HTTP {exc.status}"
        d["headline"] = _headline_from_snippet(fallback, d["name"])
        d["headline_source"] = "search-snippet" if d["headline"] else ""
        return d
    except Exception as exc:  # network, JSON, shape drift
        d["error"] = str(exc)[:160]
        d["headline"] = _headline_from_snippet(fallback, d["name"])
        d["headline_source"] = "search-snippet" if d["headline"] else ""
        return d

    d["enriched"] = True
    snip = _headline_from_snippet(fallback, d["name"])
    # Google indexes a LinkedIn person as "Name - Headline - LinkedIn", so the
    # snippet still carries the job title the profile API no longer returns.
    # Prefer it over an about-derived sentence for people on LinkedIn.
    prefer_snippet = (
        snip
        and platform == "linkedin"
        and kind == "person"
        and (not d["headline"] or d["masked"] or d["headline_source"] == "linkedin-about")
    )
    if prefer_snippet or (snip and not d["headline"]):
        d["headline"] = snip
        d["headline_source"] = "search-snippet"
    d["topics"] = keywords(
        " ".join([d["bio"], d["headline"], d["snippet"]]
                 + [r.get("title", "") for r in d["recent"]]),
        limit=10,
    )
    d["signals"] = sorted(set(d["signals"]) | _derive_signals(d))
    return d


def _headline_from_snippet(snippet: str, name: str) -> str:
    """`Jane Doe - Head of Content at Acme - LinkedIn` -> `Head of Content at Acme`."""
    s = clean(snippet)
    if not s:
        return ""
    for junk in (" | LinkedIn", " - LinkedIn", " | YouTube", " - YouTube"):
        s = s.replace(junk, "")
    if name and s.lower().startswith(name.lower()):
        s = s[len(name) :].lstrip(" -–—|·,")
    return s[:180].strip()


def _linkedin_person(d: dict, raw: dict) -> None:
    d["endpoint"] = "/v1/linkedin/profile"
    d["name"] = clean(raw.get("name")) or d["name"]
    d["location"] = clean(raw.get("location"))
    d["country"] = d["location"].split(",")[-1].strip().lower() if d["location"] else ""
    d["audience"] = to_int(raw.get("followers"))
    d["audience_kind"] = "followers"
    d["audience_detail"] = {
        "followers": to_int(raw.get("followers")),
        "connections": to_int(raw.get("connections")),
    }
    d["bio"] = clean(raw.get("about"), 600)

    # experience[] is usually masked on public profiles; use it only if real.
    exp = raw.get("experience")
    if isinstance(exp, list) and exp:
        org = clean(exp[0].get("name")) if isinstance(exp[0], dict) else ""
        if org:
            # Usually a bare company name, but some payloads put the whole
            # "Title at Company" in here, and "at Title at Company" reads badly.
            d["headline"] = org if " at " in org else f"at {org}"
            d["headline_source"] = "linkedin-experience"
            d["company"]["current"] = org
            d["company"]["url"] = clean(exp[0].get("url"))
        else:
            d["masked"] = True
    if not d["headline"] and d["bio"]:
        d["headline"] = d["bio"].split(".")[0][:180]
        d["headline_source"] = "linkedin-about"

    posts = raw.get("recentPosts") if isinstance(raw.get("recentPosts"), list) else []
    acts = raw.get("activity") if isinstance(raw.get("activity"), list) else []
    for p in (posts + acts)[:6]:
        if not isinstance(p, dict):
            continue
        title = clean(p.get("title"), 200)
        if title:
            d["recent"].append(
                {"title": title, "url": clean(p.get("link")), "kind": clean(p.get("activityType"))}
            )
    for sp in (raw.get("similarProfiles") or [])[:10]:
        if isinstance(sp, dict) and sp.get("link"):
            d["similar"].append({"name": clean(sp.get("name")), "url": clean(sp.get("link"))})


def _linkedin_company(d: dict, raw: dict) -> None:
    d["endpoint"] = "/v1/linkedin/company"
    d["name"] = clean(raw.get("name")) or d["name"]
    d["bio"] = clean(raw.get("description"), 800)
    loc = raw.get("location") if isinstance(raw.get("location"), dict) else {}
    d["location"] = clean(raw.get("headquarters")) or ", ".join(
        x for x in (clean(loc.get("city")), clean(loc.get("state")), clean(loc.get("country"))) if x
    )
    d["country"] = clean(loc.get("country")).lower()
    d["audience"] = to_int(raw.get("employeeCount"))
    d["audience_kind"] = "employees"
    d["audience_detail"] = {"employees": to_int(raw.get("employeeCount")), "size_band": clean(raw.get("size"))}

    specialties = [clean(s) for s in (raw.get("specialties") or []) if clean(s)]
    funding = raw.get("funding") if isinstance(raw.get("funding"), dict) else {}
    last = funding.get("lastRound") if isinstance(funding.get("lastRound"), dict) else {}
    d["company"] = {
        "industry": clean(raw.get("industry")),
        "size_band": clean(raw.get("size")),
        "employees": to_int(raw.get("employeeCount")),
        "founded": to_int(raw.get("founded")),
        "type": clean(raw.get("type")),
        "website": clean(raw.get("website")),
        "slogan": clean(raw.get("slogan")),
        "specialties": specialties[:20],
        "funding_rounds": to_int(funding.get("numberOfRounds")),
        "last_round": clean(last.get("type")),
        "last_round_date": clean(last.get("date"))[:10],
        "last_round_amount": clean(last.get("amount")),
        "investors": [clean(i.get("name")) for i in (funding.get("investors") or []) if isinstance(i, dict)][:10],
    }
    d["headline"] = " · ".join(
        x for x in (d["company"]["industry"], d["company"]["size_band"], clean(raw.get("slogan"))) if x
    )[:200]
    d["headline_source"] = "linkedin-company"
    if d["company"]["website"]:
        d["links"].append(d["company"]["website"])

    for p in (raw.get("posts") or [])[:6]:
        if isinstance(p, dict):
            title = clean(p.get("text"), 220)
            if title:
                d["recent"].append(
                    {"title": title, "url": clean(p.get("url")), "kind": "post",
                     "date": clean(p.get("datePublished"))[:10]}
                )
    # employees[] still carries real job titles -- the workaround for masked
    # person profiles, and the cheapest path to "who works there".
    for e in (raw.get("employees") or [])[:15]:
        if isinstance(e, dict) and e.get("link"):
            d["people"].append(
                {"name": clean(e.get("name")), "title": clean(e.get("title")), "url": clean(e.get("link"))}
            )
    for sp in (raw.get("similarPages") or [])[:10]:
        if isinstance(sp, dict) and sp.get("link"):
            d["similar"].append({"name": clean(sp.get("name")), "url": clean(sp.get("link"))})


def _youtube(d: dict, raw: dict) -> None:
    d["endpoint"] = "/v1/youtube/channel"
    d["cached"] = bool(raw.get("cached"))
    d["name"] = clean(raw.get("name")) or d["name"]
    d["bio"] = clean(raw.get("description"), 600)
    d["audience"] = to_int(raw.get("subscriberCount"))
    d["audience_kind"] = "subscribers"
    d["audience_detail"] = {
        "subscribers": to_int(raw.get("subscriberCount")),
        "videos": to_int(raw.get("videoCountText")),
        "total_views": to_int(raw.get("viewCountText")),
        "joined": clean(raw.get("joinedDateText")),
    }
    d["country"] = clean(raw.get("country")).lower()
    tags = clean(raw.get("tags"))
    d["headline"] = (d["bio"].split("\n")[0] or tags)[:180]
    d["headline_source"] = "youtube-about" if d["bio"] else ("youtube-tags" if tags else "")
    for link in raw.get("links") or []:
        if clean(link):
            d["links"].append(clean(link))
    for extra in ("twitter", "instagram", "store", "email"):
        if clean(raw.get(extra)):
            d["links"].append(clean(raw.get(extra)))


def _tiktok(d: dict, raw: dict) -> None:
    d["endpoint"] = "/v1/tiktok/profile"
    d["cached"] = bool(raw.get("cached"))
    user = raw.get("user") if isinstance(raw.get("user"), dict) else {}
    stats = raw.get("stats") if isinstance(raw.get("stats"), dict) else {}
    d["name"] = clean(user.get("nickname")) or d["name"]
    d["bio"] = clean(user.get("signature"), 400)
    d["headline"] = d["bio"][:180]
    d["headline_source"] = "tiktok-bio" if d["bio"] else ""
    d["verified"] = bool(user.get("verified"))
    d["audience"] = to_int(stats.get("followerCount"))
    d["audience_kind"] = "followers"
    d["audience_detail"] = {
        "followers": to_int(stats.get("followerCount")),
        "likes": to_int(stats.get("heartCount")),
        "videos": to_int(stats.get("videoCount")),
    }
    bio_link = user.get("bioLink") if isinstance(user.get("bioLink"), dict) else {}
    if clean(bio_link.get("link")):
        d["links"].append(clean(bio_link.get("link")))


def _instagram(d: dict, raw: dict) -> None:
    d["endpoint"] = "/v1/instagram/profile"
    user = raw.get("data") if isinstance(raw.get("data"), dict) else raw
    user = user.get("user") if isinstance(user.get("user"), dict) else user
    d["name"] = clean(user.get("full_name")) or d["name"]
    d["bio"] = clean(user.get("biography"), 400)
    d["headline"] = d["bio"][:180]
    d["headline_source"] = "instagram-bio" if d["bio"] else ""
    d["verified"] = bool(user.get("is_verified"))
    followers = user.get("edge_followed_by") if isinstance(user.get("edge_followed_by"), dict) else {}
    d["audience"] = to_int(followers.get("count")) or to_int(user.get("follower_count"))
    d["audience_kind"] = "followers"
    d["audience_detail"] = {"followers": d["audience"]}
    if clean(user.get("external_url")):
        d["links"].append(clean(user.get("external_url")))


def _twitter(d: dict, raw: dict) -> None:
    d["endpoint"] = "/v1/twitter/profile"
    user = raw.get("user") if isinstance(raw.get("user"), dict) else raw
    legacy = user.get("legacy") if isinstance(user.get("legacy"), dict) else user
    d["name"] = clean(legacy.get("name")) or d["name"]
    d["bio"] = clean(legacy.get("description"), 400)
    d["headline"] = d["bio"][:180]
    d["headline_source"] = "x-bio" if d["bio"] else ""
    d["verified"] = bool(legacy.get("verified") or user.get("is_blue_verified"))
    d["audience"] = to_int(legacy.get("followers_count"))
    d["audience_kind"] = "followers"
    d["audience_detail"] = {
        "followers": to_int(legacy.get("followers_count")),
        "posts": to_int(legacy.get("statuses_count")),
    }
    d["location"] = clean(legacy.get("location"))


def _derive_signals(d: dict) -> set[str]:
    sig: set[str] = set()
    text = " ".join([d.get("bio", ""), d.get("headline", "")]
                    + [r.get("title", "") for r in d.get("recent", [])]).lower()
    if any(w in text for w in HIRING_WORDS):
        sig.add("hiring")
    if any(w in text for w in FUNDING_WORDS):
        sig.add("funding-talk")
    if d.get("verified"):
        sig.add("verified")
    if d.get("recent"):
        sig.add("posting")
    if d.get("masked"):
        sig.add("masked-profile")
    co = d.get("company") or {}
    if to_int(co.get("funding_rounds")):
        sig.add("funded")
    if co.get("last_round_date", "")[:4] >= "2024":
        sig.add("recent-round")
    emp = to_int(co.get("employees"))
    if emp:
        sig.add("smb" if emp < 200 else ("midmarket" if emp < 2000 else "enterprise"))
    # Audience-size bands describe reach. Applying them to an employee count
    # would label a healthy 120-person company "small-audience".
    aud = to_int(d.get("audience"))
    if d.get("audience_kind") in {"followers", "subscribers"} and aud:
        if aud >= 100_000:
            sig.add("large-audience")
        elif aud >= 10_000:
            sig.add("mid-audience")
        else:
            sig.add("small-audience")
    return sig


def audience_label(d: dict) -> str:
    n = to_int(d.get("audience"))
    if not n:
        return "-"
    kind = {"subscribers": "subs", "employees": "emp", "followers": "flw"}.get(d.get("audience_kind"), "")
    return f"{human(n)}{kind}"


def enrich_many(
    token: str,
    entities: list[dict],
    *,
    limit: int,
    cache: str = "7d",
    on_progress=None,
) -> tuple[dict[str, dict], list[str], int]:
    """Enrich the top `limit` enrichable entities. Returns (by_id, errors, spent)."""
    out: dict[str, dict] = {}
    errors: list[str] = []
    spent = 0
    queued = [e for e in entities if enrichable(e.get("kind", ""), e.get("platform", ""))][:limit]
    for i, ent in enumerate(queued, 1):
        d = enrich(token, ent, cache=cache)
        out[d["id"]] = d
        if d.get("error"):
            errors.append(f"{d['id']}: {d['error']}")
        elif not d.get("cached"):
            spent += 1
        if on_progress:
            on_progress(i, len(queued), d)
    return out, errors, spent


def similar_identities(d: dict) -> list[dict]:
    """similarProfiles / similarPages -> candidate rows for lateral expansion."""
    from .identity import parse_identity

    rows = []
    for s in d.get("similar") or []:
        ent = parse_identity(
            s.get("url", ""),
            s.get("name", ""),
            source="linkedin_people" if d.get("kind") == "person" else "linkedin_companies",
            scenario_kind=d.get("kind", "person"),
        )
        if ent:
            ent["via"] = d["id"]
            rows.append(ent)
    return rows


def people_identities(d: dict) -> list[dict]:
    """LinkedIn company employees[] -> person rows, titles intact."""
    from .identity import parse_identity

    rows = []
    for p in d.get("people") or []:
        ent = parse_identity(
            p.get("url", ""),
            p.get("name", ""),
            p.get("title", ""),
            source="linkedin_people",
            scenario_kind="person",
        )
        if ent:
            ent["title"] = p.get("title", "")
            ent["sample_title"] = p.get("title", "")
            ent["via"] = d["id"]
            rows.append(ent)
    return rows
