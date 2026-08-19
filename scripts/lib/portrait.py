"""Per-person and landscape synthesis — engine-owned, no invented facts.

A field dump is not research. `who they are` has to be a sentence a colleague
can act on, not a bag of tokens and a `+18`. Every line here is derived from a
field we already stored; if the field is missing the line is omitted, never
filled in.
"""

from __future__ import annotations

import re

from .util import human, plural, to_int

# Internal scoring phrases -> a sentence a person would say out loud.
_REASON = (
    (r"^topic match:\s*(.+?)\s*\(", "their profile talks about {0}"),
    (r"^match '(.+?)'", "described as {0}"),
    (r"^audience (.+) in target band", "audience {0}, in the size you asked for"),
    (r"^audience (.+) below floor", "audience {0}, smaller than you asked for"),
    (r"^audience (.+) outside target band", "audience {0}, outside the size you asked for"),
    (r"^geo match", "based where you prefer"),
    (r"^signal hiring", "they're hiring"),
    (r"^signal funded", "they've raised money"),
    (r"^signal posting", "they've posted recently"),
    (r"^signal verified", "the account is verified"),
    (r"^signal large-audience", "a large audience relative to this set"),
    (r"^signal mid-audience", "a mid-sized audience"),
    (r"^signal small-audience", "a small audience"),
    (r"^no topic keyword", "the topic does not appear on their profile"),
)

# Search labels the planner emits -> English a reader can use.
ANGLE = {
    "li-in": "LinkedIn profiles",
    "li-titles": "LinkedIn profiles with a senior title",
    "li-co": "LinkedIn company pages",
    "li-jobs": "LinkedIn job posts",
    "yt": "YouTube",
    "yt-talks": "YouTube interviews and talks",
    "x": "X / Twitter",
    "web": "the open web",
    "reddit": "Reddit",
    "tiktok": "TikTok",
    "ig": "Instagram",
}

SOURCE = {
    "linkedin_people": "LinkedIn",
    "linkedin_companies": "LinkedIn companies",
    "linkedin_jobs": "LinkedIn jobs",
    "youtube": "YouTube",
    "x": "X",
    "web": "the web",
    "reddit": "Reddit",
    "tiktok": "TikTok",
    "instagram": "Instagram",
}

STATE = {
    "ok": "returned people",
    "no-results": "ran and found nobody",
    "unparsed": "answered in a format we could not read",
    "error": "failed",
}


def english_reason(raw: str) -> str:
    s = (raw or "").strip()
    for pat, tmpl in _REASON:
        m = re.search(pat, s, re.I)
        if m:
            return tmpl.format(m.group(1).strip(" '\"")) if "{0}" in tmpl else tmpl
    # Fall back to the human part, drop the (+N).
    return re.sub(r"\s*\([+-][\d.]+\)\s*$", "", s).strip() or s


def english_reasons(raws: list) -> list[str]:
    out, seen = [], set()
    for r in raws or []:
        e = english_reason(str(r))
        if e and e not in seen:
            seen.add(e)
            out.append(e)
    return out


def english_step(step: str) -> str:
    """`linkedin_people:li-in~exact` -> `LinkedIn profiles, as an exact phrase`."""
    src, _, rest = (step or "").partition(":")
    label, _, frame = rest.partition("~")
    base = ANGLE.get(label) or SOURCE.get(src) or (label or src or step)
    if frame == "exact":
        return f"{base}, as an exact phrase"
    if frame == "broad":
        return f"{base}, without the leading qualifier"
    if frame == "given":
        return f"{base}, using a phrasing you supplied"
    if frame == "category":
        return f"{base}, paired with what we are looking for"
    return base


def english_source_row(s: dict) -> list[str]:
    src = SOURCE.get(s.get("source") or "", s.get("source") or "?")
    label = ANGLE.get(s.get("label") or "", "")
    name = f"{src}" + (f" — {label}" if label and label.lower() not in src.lower() else "")
    return [name, STATE.get(s.get("state") or "", s.get("state") or "?"), str(s.get("n", 0))]


def _role(d: dict, r: dict | None = None) -> str:
    raw = (d.get("headline") or (r or {}).get("headline") or "").strip()
    raw = re.sub(r"\s*\[.*?\]\s*$", "", raw)
    return raw


def _name(r: dict, d: dict) -> str:
    return (r.get("name") or d.get("name") or r.get("handle") or "").strip()


def _bio_sentence(d: dict) -> str:
    bio = (d.get("bio") or "").strip()
    if not bio:
        return ""
    # First sentence, but keep a second if the first is a title fragment.
    parts = re.split(r"(?<=[.!?])\s+", bio)
    first = (parts[0] or "").rstrip(".")
    if len(first) < 40 and len(parts) > 1:
        return (first + ". " + parts[1]).rstrip(".")
    return first


def lede(r: dict, d: dict, *, peers: list[dict] | None = None) -> str:
    """One paragraph: who they are, what they do, how big, where."""
    name = _name(r, d)
    role = _role(d, r)
    bio = _bio_sentence(d)
    loc = (d.get("location") or "").strip()
    aud = to_int(d.get("audience") or r.get("audience"))
    kind = d.get("audience_kind") or r.get("audience_kind") or "followers"

    bits = []
    if role and role.lower() not in ("not public",):
        # A bio fragment used as a headline is already a sentence — don't
        # write "Ad Lab is We teach ai video ads."
        sent = role[:1].isupper() and role.rstrip().endswith((".", "!", "?"))
        if name and sent:
            bits.append(f"{name}. {role.rstrip('.')}")
        elif name:
            bits.append(f"{name} is {role}")
        else:
            bits.append(role)
    elif name:
        bits.append(name)
    if loc:
        bits.append(f"based in {loc}")
    if aud:
        bits.append(f"{human(aud)} {kind}")
    head = ", ".join(bits) + "."

    extra = []
    if bio and bio.lower() not in (role or "").lower():
        extra.append(bio if bio.endswith((".", "!", "?")) else bio + ".")
    if peers:
        extra.append(_vs_set(r, d, peers))
    return " ".join(x for x in [head] + extra if x).strip()


def _vs_set(r: dict, d: dict, peers: list[dict]) -> str:
    aud = to_int(d.get("audience") or r.get("audience"))
    sized = sorted(to_int(p.get("audience")) for p in peers if to_int(p.get("audience")))
    if not aud or len(sized) < 2:
        return ""
    rank = sum(1 for a in sized if a > aud) + 1
    if rank == 1:
        return f"Largest audience in this set ({human(aud)})."
    if rank == len(sized):
        return f"Smallest audience in this set ({human(aud)})."
    med = sized[len(sized) // 2]
    if aud >= med * 2:
        return f"Well above the median audience here ({human(med)})."
    if aud <= med / 2:
        return f"Below the median audience here ({human(med)})."
    return f"Around the middle of this set for audience (median {human(med)})."


def _best_hook(r: dict, d: dict) -> str:
    """The one phrase that explains why this name leads the shortlist.

    Topic-match is true of almost everyone who appeared, so it is the worst
    thing to lead with. Prefer a role, a hiring signal, or a distinctive
    audience over 'their profile talks about the thing you searched'.
    """
    role = _role(d, r)
    if role and not role.lower().startswith("at "):
        return role
    sig = set(d.get("signals") or r.get("signals") or [])
    if "hiring" in sig:
        return "hiring right now"
    if "funded" in sig:
        return "recently funded"
    why = why_english(r, d)
    prefer = [w for w in why if not w.startswith("their profile talks about")
              and not w.startswith("a mid-sized") and not w.startswith("they've posted")]
    if prefer:
        return prefer[0]
    if role:
        return role
    return why[0] if why else ""


def why_english(r: dict, d: dict) -> list[str]:
    return english_reasons(r.get("fit_reasons") or d.get("fit_reasons") or [])


def recent_lines(d: dict, limit: int = 4) -> list[str]:
    out = []
    for item in d.get("recent") or []:
        if isinstance(item, str) and item.strip():
            out.append(item.strip()[:220])
        elif isinstance(item, dict):
            title = (item.get("title") or item.get("text") or item.get("name") or "").strip()
            if not title:
                continue
            date = (item.get("date") or "")[:10]
            out.append(f"{date} — {title}" if date else title[:220])
        if len(out) >= limit:
            break
    return out


def angle(r: dict, d: dict, found_by: list[str] | None = None) -> str:
    """The one reason you'd reach out *now*, derived from evidence we have."""
    sig = set(d.get("signals") or r.get("signals") or [])
    posts = recent_lines(d, limit=1)
    role = _role(d, r).lower()

    if "hiring" in sig:
        return "They're hiring — usually the best time to start a conversation."
    if posts:
        return f'Their latest public post: "{posts[0][:140]}".'
    if found_by and len(found_by) > 1:
        n = len(found_by)
        return f"Showed up in {n} different ways of asking the same question — central to the topic, not a one-query fluke."
    if any(w in role for w in ("founder", "ceo", "owner")):
        return "They own the decision; no one to route through."
    if "funded" in sig:
        return "They've raised recently, which usually means they're spending."
    if not r.get("enriched") and not d.get("enriched"):
        return "We only have the search snippet — fetch the profile before you write to them."
    return ""


def similar_names(d: dict, limit: int = 5) -> list[str]:
    out = []
    for s in d.get("similar") or []:
        n = (s.get("name") or "").strip() if isinstance(s, dict) else str(s).strip()
        if n:
            out.append(n)
        if len(out) >= limit:
            break
    return out


def colleagues(d: dict, limit: int = 6) -> list[str]:
    out = []
    for p in d.get("people") or []:
        if not isinstance(p, dict):
            continue
        n = (p.get("name") or "").strip()
        t = (p.get("title") or "").strip()
        if n:
            out.append(f"{n} — {t}" if t else n)
        if len(out) >= limit:
            break
    return out


def company_lines(d: dict) -> list[str]:
    c = d.get("company") or {}
    if not isinstance(c, dict) or not c:
        return []
    out = []
    bits = [c.get("industry"), c.get("size_band"),
            f"{human(c['employees'])} employees" if to_int(c.get("employees")) else ""]
    head = " · ".join(x for x in bits if x)
    if head:
        out.append(head)
    if c.get("last_round"):
        amt = c.get("last_round_amount")
        when = c.get("last_round_date")
        line = f"Last raise: {c['last_round']}"
        if amt:
            line += f" ({amt})"
        if when:
            line += f", {when}"
        out.append(line)
    if c.get("specialties"):
        out.append("Specialties: " + ", ".join(c["specialties"][:6]))
    return out


def audience_detail(d: dict, r: dict | None = None) -> str:
    aud = to_int(d.get("audience") or (r or {}).get("audience"))
    kind = d.get("audience_kind") or (r or {}).get("audience_kind") or "followers"
    if not aud:
        return ""
    extra = d.get("audience_detail") or {}
    bits = [f"{human(aud)} {kind}"]
    if to_int(extra.get("connections")):
        bits.append(f"{human(extra['connections'])} connections")
    if to_int(extra.get("videos")):
        bits.append(f"{human(extra['videos'])} videos")
    if to_int(extra.get("total_views")):
        bits.append(f"{human(extra['total_views'])} total views")
    if extra.get("joined"):
        bits.append(f"joined {extra['joined']}")
    return " · ".join(bits)


def landscape(rows: list[dict], dossiers: list[dict], *, topic: str,
              n_new: int, n_known: int, thin: bool = False) -> list[str]:
    """The opening of a research brief — who showed up and who to talk to."""
    if not rows:
        return []
    by_id = {d.get("id"): d for d in dossiers if d.get("id")}
    named = []
    for r in rows:
        ident = r.get("id") or f"{r.get('kind')}/{r.get('platform')}/{r.get('handle')}"
        named.append((r, by_id.get(ident, {})))

    out: list[str] = []
    n = len(rows)
    plats = {}
    for r, _ in named:
        plats[r.get("platform") or "?"] = plats.get(r.get("platform") or "?", 0) + 1
    where = ", ".join(f"{c} on {p}" for p, c in sorted(plats.items(), key=lambda x: -x[1]))
    newbit = f"{n_new} new to you" if n_new == n else f"{n_new} new, {n_known} already seen"
    out.append(f"{n} {plural(n, 'person', 'people')} — {newbit} — found {where}.")
    if thin:
        out.append(
            "This run used public search only; no profile pages were fetched. "
            "Fit is capped at MAYBE."
        )

    # Who to talk to first: the top strong fits, named, with a reason.
    strong = [(r, d) for r, d in named if r.get("fit_band") == "strong"]
    if strong:
        leads = []
        for r, d in strong[:3]:
            name = _name(r, d)
            hook = _best_hook(r, d)
            leads.append(f"**{name}** ({hook})" if hook else f"**{name}**")
        verb = "is" if len(leads) == 1 else "are"
        out.append(f"Talk to first: {', '.join(leads)} {verb} why this set is worth opening.")

    # Character of the set — operators vs creators vs companies.
    kinds = {}
    for r, _ in named:
        kinds[r.get("kind") or "person"] = kinds.get(r.get("kind") or "person", 0) + 1
    if kinds.get("company") and kinds.get("person"):
        out.append(
            f"Mix of {kinds.get('person', 0)} {plural(kinds.get('person', 0), 'person', 'people')} "
            f"and {kinds['company']} {plural(kinds['company'], 'company', 'companies')} — "
            "don't treat the ranking as one list of the same thing."
        )

    posting = sum(1 for _, d in named if "posting" in (d.get("signals") or []))
    hiring = sum(1 for _, d in named if "hiring" in (d.get("signals") or []))
    if hiring:
        out.append(
            f"{hiring} {plural(hiring, 'is', 'are')} hiring right now — "
            "that is usually the strongest outreach window in a set like this."
        )
    if posting and posting >= max(2, n // 2):
        out.append(
            f"{posting} of {n} have posted recently, so this is an active conversation, "
            "not a graveyard of old headlines."
        )

    # Audience shape.
    auds = sorted(to_int(d.get("audience") or r.get("audience")) for r, d in named)
    auds = [a for a in auds if a]
    if len(auds) >= 2:
        lo, hi, med = min(auds), max(auds), auds[len(auds) // 2]
        if hi >= lo * 8 and hi >= 50_000:
            big = next((_name(r, d) for r, d in named
                        if to_int(d.get("audience") or r.get("audience")) == hi), "")
            out.append(
                f"Audience is skewed: median {human(med)}, but {big or 'one name'} "
                f"is {human(hi)} — a different kind of reach from everyone else."
            )
        else:
            out.append(f"Audience: median {human(med)}, from {human(lo)} to {human(hi)}.")

    bands = {}
    for r, _ in named:
        b = r.get("fit_band") or "unknown"
        bands[b] = bands.get(b, 0) + 1
    if bands.get("off") or bands.get("weak"):
        n_bad = bands.get("off", 0) + bands.get("weak", 0)
        out.append(
            f"{n_bad} {plural(n_bad, 'looks', 'look')} like a weak or off fit — "
            "useful as contrast, not as a contact list."
        )
    elif bands.get("strong") == n:
        out.append("Every name in this slice scored as a strong fit under the current rules.")

    masked = sum(1 for _, d in named if d.get("masked"))
    if masked:
        out.append(
            f"{masked} LinkedIn {plural(masked, 'profile')} "
            f"{plural(masked, 'hides', 'hide')} job history publicly — "
            "the role line is from the search result, not the profile page."
        )

    thin = sum(1 for r, d in named if not (r.get("enriched") or d.get("enriched")))
    if thin:
        out.append(
            f"{thin} {plural(thin, 'entry', 'entries')} "
            f"{plural(thin, 'rests', 'rest')} on a search snippet only — "
            "treat their fit as provisional until the profile is fetched."
        )

    if topic:
        out.append(
            f"Asked as “{topic}”. Anyone who describes the same work in other words "
            "only appears if a framing reached them."
        )
    return out
