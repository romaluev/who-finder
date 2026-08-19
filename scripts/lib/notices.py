"""Things a ranking table hides.

A shortlist is easy to scan and easy to misread. The same person on two
platforms looks like two leads. A Calendly in a bio is the actual next step
and sits below the fold. Three people at one company is a buying committee,
not three unrelated outreach targets. Every notice here cites a field we
already stored; if the field is missing the notice is omitted, never guessed.
"""

from __future__ import annotations

import re
from collections import defaultdict
from urllib.parse import urlparse

from . import contacts, portrait
from .util import clean, human, plural, to_int

_FORMER = re.compile(r"\b(former(?:ly)?|ex-|previously(?: at)?|used to)\b", re.I)
_AT_CO = re.compile(r"\b(?:at|@)\s+(.+)$", re.I)
_FILLER_CO = frozenset({
    "scale", "the", "work", "home", "large", "least", "heart", "night",
    "last", "first", "once",
})


def _ident(r: dict, d: dict | None = None) -> str:
    if r.get("id"):
        return r["id"]
    if d and d.get("id"):
        return d["id"]
    return f"{r.get('kind') or (d or {}).get('kind')}/" \
           f"{r.get('platform') or (d or {}).get('platform')}/" \
           f"{r.get('handle') or (d or {}).get('handle')}"


def _name(r: dict, d: dict) -> str:
    return (r.get("name") or d.get("name") or r.get("handle") or d.get("handle") or "").strip()


def _norm_name(s: str) -> str:
    s = re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()
    for w in ("phd", "mba", "jr", "sr", "iii", "ii"):
        s = re.sub(rf"\b{w}\b", "", s)
    return " ".join(s.split())


def _loose_handle(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _norm_co(s: str) -> str:
    s = re.sub(r"\b(inc|llc|ltd|limited|corp|corporation|co|the|studio|studios|labs|lab)\b",
               "", (s or "").lower())
    return re.sub(r"[^a-z0-9]+", "", s)


def _li_slug(url: str) -> str:
    m = re.search(r"linkedin\.com/(?:in|company|school)/([^/?#]+)", url or "", re.I)
    return (m.group(1) if m else "").lower().rstrip("/")


def _host(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower().lstrip("www.")
    except Exception:
        return ""


def employer(r: dict, d: dict) -> str:
    co = d.get("company") if isinstance(d.get("company"), dict) else {}
    for key in ("current", "name"):
        val = clean(co.get(key) or "")
        if val:
            return val
    role = portrait._role(d, r)
    m = _AT_CO.search(role)
    if not m:
        return ""
    name = m.group(1).strip(" .")
    if name.lower() in _FILLER_CO or len(name) < 2:
        return ""
    return name


def _pair(rows: list[dict], dossiers: list[dict]) -> list[tuple[dict, dict]]:
    by_id = {d.get("id"): d for d in dossiers if d.get("id")}
    out = []
    for r in rows:
        ident = _ident(r)
        d = by_id.get(ident) or {}
        if not d.get("id"):
            d = dict(d)
            d["id"] = ident
        out.append((r, d))
    return out


def _notice(kind: str, text: str, ids: list[str], evidence: str = "") -> dict:
    return {"kind": kind, "text": text, "ids": ids, "evidence": evidence}


def of_set(rows: list[dict], dossiers: list[dict], limit: int = 8) -> list[dict]:
    """Cross-row notices. Order is wow-first; cap so a page stays readable."""
    named = _pair(rows, dossiers)
    if len(named) < 2:
        return []
    out: list[dict] = []
    seen_kinds: set[str] = set()

    def add(n: dict) -> None:
        if len(out) >= limit:
            return
        # One notice of each kind, except same-person / hub which can stack
        # once each because they name different people.
        key = n["kind"] if n["kind"] not in {"same-person", "hub", "same-company"} else n["text"]
        if key in seen_kinds:
            return
        seen_kinds.add(key)
        out.append(n)

    # Same display name on two platforms — the classic double-count.
    by_name: dict[str, list] = defaultdict(list)
    for r, d in named:
        n = _norm_name(_name(r, d))
        if n.count(" ") >= 1:  # first + last; "Sam" matching "Sam" is coincidence
            by_name[n].append((r, d))
    for n, group in by_name.items():
        plats = {r.get("platform") for r, _ in group}
        if len(plats) < 2:
            continue
        names = [f"**{_name(r, d)}** on {r.get('platform')}" for r, d in group[:3]]
        add(_notice(
            "same-person",
            f"{' and '.join(names)} look like the same person — count them once, not twice.",
            [_ident(r, d) for r, d in group],
            "same display name, different platforms",
        ))

    # Same handle, stripped of punctuation, on two platforms.
    by_handle: dict[str, list] = defaultdict(list)
    for r, d in named:
        h = _loose_handle(r.get("handle") or d.get("handle") or "")
        if len(h) >= 4:
            by_handle[h].append((r, d))
    for h, group in by_handle.items():
        plats = {r.get("platform") for r, _ in group}
        if len(plats) < 2:
            continue
        names = [f"**{_name(r, d)}** ({r.get('platform')})" for r, d in group[:3]]
        add(_notice(
            "same-person",
            f"{' and '.join(names)} share the handle `{h}` — treat as one person until proven otherwise.",
            [_ident(r, d) for r, d in group],
            f"handle {h}",
        ))

    # Similar-profiles pointing into this shortlist (a hub).
    slug_to = {}
    for r, d in named:
        slug = _li_slug(d.get("url") or r.get("url") or "") or (r.get("handle") or "")
        if slug:
            slug_to[slug.lower()] = (r, d)
    for r, d in named:
        pointed = []
        for s in d.get("similar") or []:
            url = s.get("url") if isinstance(s, dict) else ""
            slug = _li_slug(url)
            hit = slug_to.get(slug)
            if hit and _ident(hit[0], hit[1]) != _ident(r, d):
                pointed.append(_name(*hit))
        if len(pointed) >= 2:
            add(_notice(
                "hub",
                f"**{_name(r, d)}** is the hub: their similar-profiles list includes "
                f"{', '.join(pointed[:4])} — also in this set.",
                [_ident(r, d)],
                "similar[] ∩ shortlist",
            ))
        elif len(pointed) == 1:
            add(_notice(
                "hub",
                f"**{_name(r, d)}** lists **{pointed[0]}** as a similar profile — "
                "they already sit next to each other in public data.",
                [_ident(r, d)],
                "similar[] ∩ shortlist",
            ))

    # Several people at the same company.
    by_co: dict[str, list] = defaultdict(list)
    for r, d in named:
        if (r.get("kind") or d.get("kind")) == "company":
            continue
        co = employer(r, d)
        key = _norm_co(co)
        if key and len(key) >= 3:
            by_co[key].append((_name(r, d), co, _ident(r, d)))
    for _, group in by_co.items():
        if len(group) < 2:
            continue
        co = group[0][1]
        names = [g[0] for g in group]
        add(_notice(
            "same-company",
            f"{', '.join(f'**{n}**' for n in names[:4])} all list {co} — "
            "that is a cluster, not three unrelated conversations.",
            [g[2] for g in group],
            f"employer={co}",
        ))

    # A company row whose listed staff also appear as people.
    people_slugs = {
        (r.get("handle") or "").lower(): _name(r, d)
        for r, d in named if (r.get("kind") or "person") == "person"
    }
    for r, d in named:
        if (r.get("kind") or d.get("kind")) != "company":
            continue
        listed = []
        unseen = 0
        for p in d.get("people") or []:
            if not isinstance(p, dict):
                continue
            slug = _li_slug(p.get("url") or "")
            if slug in people_slugs:
                listed.append(people_slugs[slug])
            else:
                unseen += 1
        if listed:
            extra = f" The page also lists {unseen} more not in this shortlist — `expand {_ident(r, d)}` pulls them for free." if unseen else ""
            add(_notice(
                "staff-overlap",
                f"**{_name(r, d)}**'s company page lists {', '.join(f'**{n}**' for n in listed[:4])} "
                f"in this set.{extra}",
                [_ident(r, d)],
                "people[] ∩ shortlist",
            ))
        elif unseen >= 3:
            add(_notice(
                "expand",
                f"**{_name(r, d)}** lists {unseen} people on the company page, none of them "
                f"in this shortlist — `expand {_ident(r, d)}` turns those titles into names, free.",
                [_ident(r, d)],
                f"{unseen} employees on the page",
            ))

    # Shared personal site / domain (not LinkedIn, not a social).
    by_host: dict[str, list] = defaultdict(list)
    for r, d in named:
        c = d.get("contacts") or contacts.harvest(d)
        for l in c.get("links") or []:
            if l.get("kind") != "website":
                continue
            host = l.get("host") or ""
            if host and host not in {"linktr.ee", "bio.link"}:
                by_host[host].append((_name(r, d), _ident(r, d)))
    for host, group in by_host.items():
        ids = list(dict.fromkeys(g[1] for g in group))
        if len(ids) < 2:
            continue
        names = list(dict.fromkeys(g[0] for g in group))
        add(_notice(
            "shared-site",
            f"{', '.join(f'**{n}**' for n in names[:4])} all publish {host} — "
            "same shop, same brand, or the same person twice.",
            ids,
            f"host={host}",
        ))

    # Location cluster.
    by_city: dict[str, list] = defaultdict(list)
    for r, d in named:
        loc = (d.get("location") or r.get("location") or "").strip()
        city = loc.split(",")[0].strip()
        if len(city) >= 3:
            by_city[city.lower()].append((_name(r, d), city, _ident(r, d)))
    for _, group in by_city.items():
        if len(group) < 3:
            continue
        city = group[0][1]
        names = [g[0] for g in group[:5]]
        add(_notice(
            "geo",
            f"{len(group)} of this set sit in {city} "
            f"({', '.join(names)}{'…' if len(group) > 5 else ''}) — "
            "a trip or a local event covers more than one conversation.",
            [g[2] for g in group],
            f"city={city}",
        ))

    # Shared investors across two company rows.
    inv_to: dict[str, list] = defaultdict(list)
    for r, d in named:
        co = d.get("company") if isinstance(d.get("company"), dict) else {}
        for inv in co.get("investors") or []:
            name = clean(inv if isinstance(inv, str) else "")
            if name:
                inv_to[name].append((_name(r, d), _ident(r, d)))
    for inv, group in inv_to.items():
        ids = list(dict.fromkeys(g[1] for g in group))
        if len(ids) < 2:
            continue
        names = list(dict.fromkeys(g[0] for g in group))
        add(_notice(
            "investors",
            f"{' and '.join(f'**{n}**' for n in names[:3])} share an investor ({inv}) — "
            "same cheque-writer, often the same introduction path.",
            ids,
            f"investor={inv}",
        ))

    # Hiring + recently funded, as a set fact.
    both = [(r, d) for r, d in named
            if "hiring" in (d.get("signals") or r.get("signals") or [])
            and ({"funded", "recent-round"} & set(d.get("signals") or r.get("signals") or []))]
    if both:
        names = [f"**{_name(r, d)}**" for r, d in both[:3]]
        add(_notice(
            "spend-window",
            f"{', '.join(names)} {'is' if len(both) == 1 else 'are'} hiring *and* recently funded — "
            "the two signals that together usually mean they are spending.",
            [_ident(r, d) for r, d in both],
            "signals hiring ∩ funded",
        ))

    return out[:limit]


def of_one(r: dict, d: dict, *, peers: list[dict] | None = None, limit: int = 3) -> list[dict]:
    """Per-person notices a ranking card will not show on its own."""
    out: list[dict] = []
    c = d.get("contacts") or contacts.harvest(d)
    sig = set(d.get("signals") or r.get("signals") or [])
    name = _name(r, d)
    ident = _ident(r, d)

    if c.get("emails"):
        extra = ""
        if c.get("personal_emails") and c["personal_emails"] == c["emails"]:
            extra = " — a personal inbox, not a work domain."
        elif c.get("edu_emails"):
            extra = " — a .edu address, so they may still be at a university."
        out.append(_notice(
            "email",
            f"They published {', '.join(c['emails'])}{extra}",
            [ident],
            "email on the public profile",
        ))
    if c.get("takes_meetings"):
        cal = next((l["url"] for l in c.get("links") or []
                    if l.get("kind") in {"calendly", "calendar"}), "")
        out.append(_notice(
            "calendly",
            f"They book meetings in public{(' — ' + cal) if cal else ''}. That is the door, not the LinkedIn form.",
            [ident],
            cal or "calendly/cal.com link",
        ))

    detail = d.get("audience_detail") or {}
    fl = to_int(detail.get("followers") or d.get("audience"))
    cn = to_int(detail.get("connections"))
    if fl and cn and (d.get("audience_kind") or r.get("audience_kind")) == "followers":
        if fl >= 8_000 and fl >= max(cn, 1) * 6:
            out.append(_notice(
                "shape",
                f"Creator-shaped LinkedIn: {human(fl)} followers vs {human(cn)} connections — "
                "they broadcast more than they network.",
                [ident],
                f"followers={fl} connections={cn}",
            ))
        elif cn >= 400 and cn >= fl * 2 and fl < 15_000:
            out.append(_notice(
                "shape",
                f"Operator-shaped LinkedIn: {human(cn)} connections vs {human(fl)} followers — "
                "they network more than they publish.",
                [ident],
                f"followers={fl} connections={cn}",
            ))

    if "hiring" in sig and ("smb" in sig or to_int((d.get("company") or {}).get("employees")) < 80):
        emp = to_int((d.get("company") or {}).get("employees"))
        out.append(_notice(
            "hiring-small",
            "Hiring on a small team" + (f" ({human(emp)} people)" if emp else "") +
            " — the person you write is probably the person who decides.",
            [ident],
            "hiring + smb",
        ))

    blob = " ".join([d.get("headline") or "", d.get("bio") or "", d.get("snippet") or ""])
    if _FORMER.search(blob):
        m = _FORMER.search(blob)
        # Keep this tight: the word is on the profile, we do not invent the old employer.
        out.append(_notice(
            "former",
            f"The profile uses “{m.group(0)}” — they are describing a past role, "
            "so the company on the line may not be where they sit today.",
            [ident],
            m.group(0),
        ))

    if d.get("masked") or "masked-profile" in sig:
        out.append(_notice(
            "masked",
            "LinkedIn hid their job history. The role line is from the search result, not the profile page.",
            [ident],
            "masked-profile",
        ))

    if peers:
        me = _norm_name(name)
        twins = []
        for p in peers:
            if (p.get("id") or "") == ident:
                continue
            other = _norm_name(p.get("name") or "")
            if me and other and me == other and (p.get("platform") or "") != (r.get("platform") or d.get("platform") or ""):
                twins.append(f"{p.get('name')} on {p.get('platform')}")
        if twins:
            out.append(_notice(
                "twin",
                f"Also in this set as {twins[0]} — same name, different platform.",
                [ident],
                "name match across platforms",
            ))

    # De-dupe by kind, keep the first (highest-signal) of each.
    seen, uniq = set(), []
    for n in out:
        if n["kind"] in seen:
            continue
        seen.add(n["kind"])
        uniq.append(n)
        if len(uniq) >= limit:
            break
    return uniq
