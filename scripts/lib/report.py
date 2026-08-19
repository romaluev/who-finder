"""Shareable reports: one document model, three renderers.

A report is built once as a list of blocks and then rendered to Markdown, HTML
or PDF. Three hand-written report writers would drift apart within a release —
the PDF would quietly lose the section the Markdown gained — so the content
decisions live in `build()` and the renderers only know how to draw.

The document answers two questions the terminal brief cannot. `build()` opens
with the landscape, because someone reading a shortlist needs to know what was
searched before they trust the ranking, and then gives every person a full page
of context so the sheet can be forwarded to whoever does the outreach.
"""

from __future__ import annotations

import html as _html
import json
import re
from datetime import datetime, timezone

from . import __version__, contacts, notices, pdf, portrait
from .util import human, to_int

BAND_LABEL = {
    "strong": "STRONG FIT", "possible": "POSSIBLE", "weak": "WEAK",
    "off": "NOT A FIT", "unknown": "UNVERIFIED",
}
BAND_COLOR = {
    "strong": "#0f7b3d", "possible": "#8a6100", "weak": "#6b7280",
    "off": "#9b2c2c", "unknown": "#6b7280",
}


# --------------------------------------------------------------------------
# Build
# --------------------------------------------------------------------------


def build(
    rows: list[dict],
    dossiers: dict[str, dict],
    ins: dict,
    *,
    brief: str,
    scenario: str,
    topic: str,
    n_new: int,
    n_known: int,
    steps: list[str],
    frames: list[str] | None = None,
    icp_name: str = "generic",
    credits: int = 0,
    source_status: list[dict] | None = None,
    hits_by_id: dict[str, list[dict]] | None = None,
    found_by: dict[str, list[str]] | None = None,
    offset: int = 0,
) -> list[dict]:
    blocks: list[dict] = []
    now = datetime.now(timezone.utc).strftime("%d %B %Y")
    shown = len(rows)

    found = n_new + n_known
    rank_from = f"ranked {offset + 1}-{offset + shown}" if offset else f"top {shown}"
    blocks.append({"t": "cover", "title": brief or topic or "who-finder shortlist",
                   "subtitle": f"{shown} {'person' if shown == 1 else 'people'} in detail"
                               f" · {scenario} · {now}",
                   "meta": [
                       ("In this report", f"the {rank_from} of {found} found"),
                       ("Ranked by", "how well they fit, then audience, then whether they're new"),
                       ("Fit rules", icp_name),
                       ("New names", f"{n_new} not seen before, {n_known} already in the roster"),
                       ("Cost", f"{credits} credits" if credits else "0 credits (from stored data)"),
                   ]})
    if ins.get("thin"):
        blocks[-1]["meta"].append(
            ("Depth", "public search only; no profile pages fetched")
        )

    # ---- Summary -------------------------------------------------------
    blocks.append({"t": "h1", "text": "Summary"})
    for line in ins.get("findings") or []:
        blocks.append({"t": "bullet", "text": line})

    missed = ins.get("notices") or []
    if missed:
        blocks.append({"t": "h2", "text": "Easy to miss"})
        for line in missed:
            blocks.append({"t": "bullet", "text": line})

    stats = _at_a_glance(rows, dossiers, n_new, n_known)
    if stats:
        blocks.append({"t": "h2", "text": "At a glance"})
        blocks.append({"t": "kv", "rows": stats})

    if shown:
        blocks.append({"t": "h2", "text": "Priority ranking"})
        blocks.append({"t": "table",
                       "cols": ["#", "Name", "Fit", "Priority", "Audience", "Role"],
                       "rows": [_rank_row(i + 1 + offset, r, dossiers) for i, r in enumerate(rows)]})

    themes = [(c.get("term") or c.get("label") or "", c.get("n") or c.get("count") or 0)
              for c in (ins.get("clusters") or [])]
    themes = [(t, n) for t, n in themes if t]
    if themes:
        blocks.append({"t": "h2", "text": "What they are talking about"})
        for t, n in themes:
            blocks.append({"t": "bullet", "text": f"**{t}** — {n} of them"})

    gaps = ins.get("gaps") or []
    if gaps:
        blocks.append({"t": "h2", "text": "What this report does not cover"})
        for g in gaps:
            blocks.append({"t": "bullet", "text": g})
        blocks.append({"t": "note", "text":
                       "Sources that errored or returned an unreadable response are not "
                       "evidence of absence. Only a source that ran and came back empty is."})

    # ---- The people ----------------------------------------------------
    if shown:
        blocks.append({"t": "pagebreak"})
        blocks.append({"t": "h1", "text": "The people"})
        for i, r in enumerate(rows, start=1 + offset):
            blocks.append(_person(i, r, dossiers,
                                  (hits_by_id or {}).get(_ident(r)) or [],
                                  (found_by or {}).get(_ident(r)) or []))

    # ---- Method --------------------------------------------------------
    blocks.append({"t": "pagebreak"})
    blocks.append({"t": "h1", "text": "How this was researched"})
    blocks.append({"t": "p", "text":
                   "Every name here came from a public profile. Nothing was guessed, "
                   "and nothing behind a login was used."})
    if frames:
        blocks.append({"t": "h2", "text": "How the question was asked"})
        blocks.append({"t": "p", "text":
                       "The same request was asked several ways, because one phrasing "
                       "only reaches the people who describe themselves that way."})
        for f in frames:
            blocks.append({"t": "bullet", "text": _plain_frame(f)})
    if steps:
        blocks.append({"t": "h2", "text": "Where we looked"})
        for s in steps:
            blocks.append({"t": "bullet", "text": portrait.english_step(s)})
    if source_status:
        blocks.append({"t": "h2", "text": "What each search returned"})
        blocks.append({"t": "table", "cols": ["Where", "What happened", "People"],
                       "rows": [portrait.english_source_row(s) for s in source_status]})
    blocks.append({"t": "h2", "text": "How fit is scored"})
    blocks.append({"t": "p", "text":
                   "Fit is scored against a rules file you control, not an opinion. "
                   "Every reason is listed on that person's page in plain language. "
                   "Anyone whose profile could not be fetched is marked unverified, "
                   "however good the search snippet looked."})
    blocks.append({"t": "footer", "text":
                   f"who-finder v{__version__} · generated {now} · public data only"})
    return blocks


def _ident(r: dict) -> str:
    return r.get("id") or f"{r.get('kind')}/{r.get('platform')}/{r.get('handle')}"


def _at_a_glance(rows, dossiers, n_new, n_known) -> list[tuple]:
    if not rows:
        return []
    out = [("People", f"{len(rows)}"), ("New to you", f"{n_new} of {n_new + n_known}")]
    bands: dict[str, int] = {}
    for r in rows:
        bands[r.get("fit_band") or "unknown"] = bands.get(r.get("fit_band") or "unknown", 0) + 1
    if bands:
        out.append(("Fit spread", ", ".join(
            f"{n} {BAND_LABEL.get(b, b).lower()}" for b, n in sorted(bands.items(), key=lambda x: -x[1]))))
    auds = sorted(to_int(dossiers.get(_ident(r), {}).get("audience") or r.get("audience"))
                  for r in rows)
    auds = [a for a in auds if a]
    if auds:
        out.append(("Audience", f"median {human(auds[len(auds) // 2])}, largest {human(auds[-1])}"))
    plats: dict[str, int] = {}
    for r in rows:
        plats[r.get("platform") or "?"] = plats.get(r.get("platform") or "?", 0) + 1
    out.append(("Where they were found", ", ".join(f"{k} {v}" for k, v in sorted(plats.items(), key=lambda x: -x[1]))))
    n_enriched = sum(1 for r in rows if r.get("enriched"))
    out.append(("Profiles fetched", f"{n_enriched} of {len(rows)}"))
    return out


def _rank_row(i: int, r: dict, dossiers: dict) -> list[str]:
    d = dossiers.get(_ident(r), {})
    aud = to_int(d.get("audience") or r.get("audience"))
    pri = r.get("priority")
    return [
        str(i),
        r.get("name") or r.get("handle") or "",
        BAND_LABEL.get(r.get("fit_band") or "unknown", "?"),
        f"{int(pri)}" if pri is not None else "-",
        f"{human(aud)} {d.get('audience_kind') or r.get('audience_kind') or ''}".strip() if aud else "-",
        (d.get("headline") or r.get("headline") or "role not public")[:70],
    ]


def _plain_frame(raw: str) -> str:
    """`literal: ai video ads — the topic exactly as asked` stays readable;
    a bare internal label gets translated."""
    s = str(raw or "")
    if ":" in s and " — " in s:
        label, _, rest = s.partition(":")
        topic, _, why = rest.partition(" — ")
        nice = {"literal": "Exactly as asked", "exact": "As one phrase",
                "broad": "Without the leading qualifier",
                "given": "A phrasing you supplied",
                "category": "Paired with what we are looking for"}.get(label.strip(), label.strip())
        return f"**{nice}** — {topic.strip()}" + (f" ({why.strip()})" if why.strip() else "")
    return portrait.english_step(s)


def _person(i: int, r: dict, dossiers: dict, hits: list[dict],
            found_by: list[str] | None = None) -> dict:
    ident = _ident(r)
    d = dossiers.get(ident, {})
    peers = list(dossiers.values())
    fields: list[tuple] = []

    lede = portrait.lede(r, d, peers=peers)
    if lede:
        fields.append(("Who they are", lede))

    # Role / location / audience already live in the lede. Repeat them only
    # when the lede could not be built, so the card is never an empty name.
    if not lede:
        role = portrait._role(d, r)
        if role:
            fields.append(("Role", role))
        aud = portrait.audience_detail(d, r)
        if aud:
            fields.append(("Audience", aud))
        if d.get("location"):
            fields.append(("Based in", d["location"]))
    else:
        extra_aud = portrait.audience_detail(d, r)
        # Keep the richer audience line (videos, views, connections) when the
        # lede only had the headline number.
        if extra_aud and " · " in extra_aud:
            fields.append(("Audience", extra_aud))

    why = portrait.why_english(r, d)
    if why:
        fields.append(("Why they fit", " · ".join(why)))
    gaps = r.get("fit_gaps") or []
    if gaps:
        fields.append(("What we could not check", " · ".join(gaps)))

    hook = portrait.angle(r, d, found_by)
    if hook:
        fields.append(("Why reach out", hook))

    c = d.get("contacts") or contacts.harvest(d)
    reach = contacts.reach_line(c)
    if reach:
        fields.append(("How to reach them", reach))
    extra_links = [
        f"{contacts.label(l)} — {l['url']}"
        for l in c.get("links") or []
        if l.get("kind") not in {"linkedin"} and l.get("url") not in (reach or "")
    ]
    if extra_links:
        fields.append(("Also on", " · ".join(extra_links[:6])))

    missed = notices.of_one(r, d, peers=peers)
    # Skip the email/calendly notices — those already have their own fields.
    missed = [n for n in missed if n["kind"] not in {"email", "calendly"}]
    if missed:
        fields.append(("Easy to miss", " · ".join(n["text"] for n in missed)))

    posts = portrait.recent_lines(d)
    if posts:
        fields.append(("What they've been saying", " · ".join(posts)))
    elif r.get("sample"):
        fields.append(("What they've been saying", str(r["sample"])))

    company = portrait.company_lines(d)
    if company:
        fields.append(("The company", " · ".join(company)))
    people = portrait.colleagues(d)
    if people:
        fields.append(("People there", " · ".join(people)))
    similar = portrait.similar_names(d)
    if similar:
        fields.append(("Similar profiles", " · ".join(similar)))

    if found_by and len(found_by) > 1:
        fields.append(("Found how many ways",
                       f"{len(found_by)} different phrasings of the search all surfaced them"))

    if not (r.get("enriched") or d.get("enriched")):
        fields.append(("Note", "Profile could not be fetched, so this entry rests on the "
                               "search result alone and is marked unverified."))

    # Profile URL first; harvested links already appear as labelled fields.
    links = [l for l in dict.fromkeys([r.get("url") or d.get("url")]) if l]

    return {
        "t": "person",
        "rank": i,
        "name": r.get("name") or r.get("handle") or ident,
        "role": portrait._role(d, r),
        "id": ident,
        "band": r.get("fit_band") or "unknown",
        "priority": r.get("priority"),
        "fit_score": r.get("fit_score"),
        "fields": fields,
        "links": links,
        # From the live run when available: the roster keys hits by URL, so a
        # person surfaced by three framings leaves only the last one on disk.
        "found_by": (found_by or list(dict.fromkeys(
            str(h.get("query") or "").strip() for h in hits if h.get("query"))))[:4],
        "evidence": [
            {"title": _evidence_title(h), "url": h.get("url") or h.get("sample_url") or ""}
            for h in hits if _is_content(h)
        ][:3],
    }


def _is_content(h: dict) -> bool:
    """True for a post or video, false for a profile that merely matched.

    A Google hit stores the result blurb in `title`, which is a sentence lifted
    from the profile and already shown under "About". Citing it a second time
    as evidence adds nothing, so only real content earns a "Seen in" line —
    everyone still gets "Found by", which says which query surfaced them.
    """
    if any(to_int(h.get(k)) for k in ("views", "likes", "comments", "shares")):
        return True
    return str(h.get("platform") or "") in ("youtube", "tiktok", "instagram")


def _evidence_title(h: dict) -> str:
    for key in ("title", "sample_title", "sample"):
        v = str(h.get(key) or "").strip()
        if v:
            return v
    return h.get("url") or "(untitled)"


def _first_text(recent: list) -> str:
    for item in recent:
        if isinstance(item, str) and item.strip():
            return item.strip()[:300]
        if isinstance(item, dict):
            for k in ("title", "text", "name"):
                if item.get(k):
                    return str(item[k])[:300]
    return ""


# --------------------------------------------------------------------------
# Markdown
# --------------------------------------------------------------------------


def to_markdown(blocks: list[dict]) -> str:
    out: list[str] = []
    for b in blocks:
        t = b["t"]
        if t == "cover":
            out += [f"# {b['title']}", "", f"*{b['subtitle']}*", ""]
            out += [f"- **{k}:** {v}" for k, v in b["meta"]] + [""]
        elif t == "h1":
            out += ["", f"## {b['text']}", ""]
        elif t == "h2":
            out += ["", f"### {b['text']}", ""]
        elif t == "p":
            out += [b["text"], ""]
        elif t == "bullet":
            out.append(f"- {b['text']}")
        elif t == "note":
            out += ["", f"> {b['text']}", ""]
        elif t == "mono":
            out.append(f"    {b['text']}")
        elif t == "kv":
            out += ["", "| | |", "|---|---|"]
            out += [f"| **{k}** | {_md_cell(v)} |" for k, v in b["rows"]] + [""]
        elif t == "table":
            out += ["", "| " + " | ".join(b["cols"]) + " |",
                    "|" + "|".join("---" for _ in b["cols"]) + "|"]
            out += ["| " + " | ".join(_md_cell(c) for c in row) + " |" for row in b["rows"]]
            out.append("")
        elif t == "person":
            out += ["", f"#### {b['rank']}. {b['name']}", ""]
            head = [f"**{BAND_LABEL.get(b['band'], b['band'])}**"]
            if b.get("priority") is not None:
                head.append(f"priority {int(b['priority'])}")
            if b.get("fit_score") is not None:
                head.append(f"fit {int(b['fit_score'])}/100")
            head.append(_human_id(b["id"]))
            out += [" · ".join(head), ""]
            out += [f"- **{k}:** {_md_cell(v)}" for k, v in b["fields"]]
            if b["links"]:
                out.append("- **Links:** " + " · ".join(f"[{_short(l)}]({l})" for l in b["links"]))
            if b.get("found_by"):
                out.append("- **Found by:** " + " · ".join(f"`{_md_cell(_short_query(q))}`" for q in b["found_by"]))
            if b["evidence"]:
                out.append("- **Seen in:** " + " · ".join(
                    f"[{_md_cell(e['title'])[:60]}]({e['url']})" if e["url"]
                    else _md_cell(e["title"])[:60] for e in b["evidence"]))
            out.append("")
        elif t == "footer":
            out += ["", "---", "", f"*{b['text']}*"]
        elif t == "pagebreak":
            out.append("")
    return "\n".join(out).strip() + "\n"


def _md_cell(v) -> str:
    return str(v).replace("|", "\\|").replace("\n", " ")


def _human_id(ident: str) -> str:
    """`person/linkedin/jane-doe` -> `LinkedIn · jane-doe` — the kind is implied."""
    parts = str(ident or "").split("/")
    if len(parts) >= 3:
        plat = {"linkedin": "LinkedIn", "youtube": "YouTube", "tiktok": "TikTok",
                "instagram": "Instagram", "x": "X"}.get(parts[1], parts[1])
        return f"{plat} · {parts[2]}"
    return ident


def _short(url: str) -> str:
    u = str(url).replace("https://", "").replace("http://", "").replace("www.", "")
    return u[:44] + ("..." if len(u) > 44 else "")


def _short_query(q: str) -> str:
    """Drop the search operators so the framing is what the reader sees.

    Every LinkedIn query starts `site:linkedin.com/in`, and repeating that on
    four lines buries the one part that differs between them.
    """
    out = re.sub(r"\bsite:\S+\s*", "", str(q or "")).strip()
    out = re.sub(r"\s+", " ", out)
    return out or str(q or "")


# --------------------------------------------------------------------------
# HTML
# --------------------------------------------------------------------------

# The whole design is self-contained: system fonts only, no fetched assets, and
# a print stylesheet that strips the chrome so the document survives being
# printed to PDF from a browser. The look is an editorial dossier — a dark
# masthead, a display serif for the title against a grotesque body, hairline
# rules, tabular numerals, and fit as the single accent colour.
CSS = r"""
:root{
 --ink:#16130e; --body:#3d382f; --muted:#8a8272; --faint:#b3ab99;
 --line:#e4ddcd; --rule:#cdc4ae; --paper:#fbf9f3; --card:#fffdf8;
 --dark:#14110b; --dark-ink:#efe9db; --dark-mut:#9a917c;
 --accent:#1c4fd6;
 --strong:#1a7a4a; --possible:#a06a00; --weak:#7c7462; --off:#a83c2a;
 --disp:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,"Times New Roman",serif;
 --grot:"Avenir Next","Helvetica Neue",Helvetica,Arial,sans-serif;
 --mono:ui-monospace,"SF Mono",SFMono-Regular,Menlo,Consolas,monospace;
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--paper);color:var(--body);
 font:16px/1.62 var(--grot);-webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility}
.sheet{max-width:46rem;margin:0 auto;padding:0 1.5rem 6rem}

/* ---- masthead -------------------------------------------------------- */
.masthead{background:var(--dark);color:var(--dark-ink);padding:3.4rem 0 2.8rem;
 margin:0 0 0;position:relative}
.masthead::after{content:"";position:absolute;left:0;right:0;bottom:0;height:4px;
 background:linear-gradient(90deg,var(--accent) 0 34%,var(--strong) 34% 67%,var(--possible) 67% 100%)}
.masthead .inner{max-width:46rem;margin:0 auto;padding:0 1.5rem}
.kicker{font:600 .68rem/1 var(--grot);letter-spacing:.24em;text-transform:uppercase;
 color:var(--dark-mut);display:flex;justify-content:space-between;gap:1rem;margin-bottom:1.6rem}
.kicker b{color:var(--dark-ink);font-weight:600}
h1.cover{font:400 clamp(2rem,5.2vw,3rem)/1.08 var(--disp);letter-spacing:-.015em;
 color:var(--dark-ink);margin:0 0 1rem}
.sub{color:var(--dark-mut);font-size:.95rem;max-width:34rem;line-height:1.5}
.cover-meta{display:grid;grid-template-columns:repeat(auto-fit,minmax(9rem,1fr));
 gap:1.4rem 2rem;margin-top:2.2rem;padding-top:1.6rem;border-top:1px solid #2c2718}
.cover-meta .m{min-width:0}
.cover-meta .k{font:600 .6rem/1 var(--grot);letter-spacing:.18em;text-transform:uppercase;
 color:var(--dark-mut);margin-bottom:.4rem}
.cover-meta .v{font-size:.86rem;color:var(--dark-ink);line-height:1.4}

/* ---- sections -------------------------------------------------------- */
h2{font:400 1.5rem/1.2 var(--disp);letter-spacing:-.01em;color:var(--ink);
 margin:3.2rem 0 1rem;display:flex;align-items:baseline;gap:.8rem}
h2::before{content:attr(data-n);font:600 .72rem/1 var(--grot);letter-spacing:.1em;
 color:var(--accent);border-bottom:2px solid var(--accent);padding-bottom:.15rem}
h3{font:600 .68rem/1 var(--grot);letter-spacing:.16em;text-transform:uppercase;
 color:var(--muted);margin:2rem 0 .8rem}
p{margin:.7rem 0;max-width:40rem}
ul{margin:.6rem 0 1.1rem;padding-left:1.15rem}
li{margin:.4rem 0;padding-left:.2rem}
li::marker{color:var(--accent)}
.note{background:#f6efdd;border-left:3px solid var(--possible);padding:.9rem 1.1rem;
 font-size:.88rem;margin:1.2rem 0;color:#6b5410;border-radius:0 4px 4px 0}
code,.mono{font:.8rem/1.5 var(--mono);background:#efe9da;padding:.12rem .38rem;
 border-radius:3px;color:#4a4436}
.mono{display:block;padding:.5rem .8rem;margin:.3rem 0;word-break:break-all;
 border-left:2px solid var(--rule)}

/* ---- at a glance ------------------------------------------------------ */
.meta{list-style:none;margin:1rem 0;padding:0;display:grid;
 grid-template-columns:repeat(auto-fit,minmax(10rem,1fr));gap:0;border-top:1px solid var(--rule)}
.meta .m{padding:.9rem 1.2rem .9rem 0;border-bottom:1px solid var(--line)}
.meta .k{font:600 .6rem/1 var(--grot);letter-spacing:.16em;text-transform:uppercase;
 color:var(--muted);margin-bottom:.35rem}
.meta .v{font-size:.92rem;color:var(--ink);line-height:1.35}

/* ---- ranking table ---------------------------------------------------- */
table{border-collapse:collapse;width:100%;margin:1rem 0 1.6rem;font-size:.9rem}
thead th{font:600 .62rem/1 var(--grot);letter-spacing:.12em;text-transform:uppercase;
 color:var(--muted);text-align:left;padding:.6rem .8rem .6rem 0;border-bottom:2px solid var(--ink)}
tbody td{padding:.7rem .8rem .7rem 0;border-bottom:1px solid var(--line);vertical-align:middle}
tbody tr:last-child td{border-bottom:none}
td.rk{font:600 .95rem/1 var(--grot);color:var(--faint);font-variant-numeric:tabular-nums;width:2rem}
td.nm{font-weight:600;color:var(--ink)}
td.nm small{display:block;font-weight:400;color:var(--muted);font-size:.78rem;margin-top:.1rem}
td.num{font-variant-numeric:tabular-nums;color:var(--ink);white-space:nowrap}
td .fit{font:600 .62rem/1 var(--grot);letter-spacing:.08em;text-transform:uppercase;
 padding:.28rem .5rem;border-radius:3px;white-space:nowrap}
.fit.strong{color:var(--strong);background:#e3f0e8}
.fit.possible{color:var(--possible);background:#f4ecd6}
.fit.weak{color:var(--weak);background:#eceadf}
.fit.off{color:var(--off);background:#f3e2dc}
.fit.unknown{color:var(--weak);background:#eceadf}

/* ---- person cards ------------------------------------------------------ */
.person{background:var(--card);border:1px solid var(--line);border-top:3px solid var(--ink);
 padding:1.6rem 1.7rem 1.5rem;margin:1.3rem 0;break-inside:avoid;page-break-inside:avoid;
 box-shadow:0 1px 2px rgba(22,19,14,.04)}
.person header{display:flex;align-items:flex-start;gap:1rem;margin-bottom:1rem;
 padding-bottom:1rem;border-bottom:1px solid var(--line)}
.person .rank{font:400 1.9rem/1 var(--disp);color:var(--faint);min-width:2.4rem;
 font-variant-numeric:tabular-nums}
.person .who{flex:1;min-width:0}
.person h4{font:400 1.35rem/1.15 var(--disp);color:var(--ink);margin:0 0 .3rem;letter-spacing:-.01em}
.person .role{font-size:.88rem;color:var(--muted)}
.person .fitbox{text-align:right;flex-shrink:0}
.person .fitbox .score{font:400 1.5rem/1 var(--disp);font-variant-numeric:tabular-nums}
.person .fitbox .of{font-size:.66rem;color:var(--muted);letter-spacing:.06em}
.badge{display:inline-block;font:600 .6rem/1 var(--grot);letter-spacing:.1em;text-transform:uppercase;
 padding:.32rem .55rem;border-radius:3px;margin-top:.4rem}
.badge.strong{color:#fff;background:var(--strong)}
.badge.possible{color:#fff;background:var(--possible)}
.badge.weak{color:#fff;background:var(--weak)}
.badge.off{color:#fff;background:var(--off)}
.badge.unknown{color:#fff;background:var(--weak)}
dl.f{display:grid;grid-template-columns:7.5rem 1fr;gap:.5rem 1.2rem;margin:0;font-size:.9rem}
dl.f dt{font:600 .62rem/1.5 var(--grot);letter-spacing:.1em;text-transform:uppercase;
 color:var(--muted);padding-top:.15rem}
dl.f dd{margin:0;color:var(--body);line-height:1.5}
dl.f dd strong{color:var(--ink);font-weight:600}
a{color:var(--accent);text-decoration:none;border-bottom:1px solid transparent}
a:hover{border-bottom-color:var(--accent)}
.links a{margin-right:.9rem;font-size:.84rem;word-break:break-all;border-bottom:1px solid var(--rule)}
.links a:hover{border-bottom-color:var(--accent)}
footer{margin-top:3.5rem;padding-top:1.4rem;border-top:2px solid var(--ink);
 color:var(--muted);font-size:.78rem;display:flex;justify-content:space-between;gap:1rem}
footer .brand{font:600 .62rem/1.5 var(--grot);letter-spacing:.2em;text-transform:uppercase;color:var(--ink)}

@media print{
 body{background:#fff}
 .sheet{max-width:none;padding:0}
 .masthead{margin:0 0 1.5rem}
 .pagebreak{page-break-before:always}
 h2{page-break-after:avoid}
 .person{box-shadow:none}
 a{color:var(--ink);border-bottom:none}
}
@page{margin:16mm 15mm}
"""


def to_html(blocks: list[dict], *, title: str = "who-finder report") -> str:
    b: list[str] = []
    pending: list[str] = []
    section = 0

    def flush() -> None:
        # Consecutive bullets are one list. Emitting a <ul> per bullet gives
        # every item the list's top and bottom margin and looks double-spaced.
        if pending:
            b.append("<ul>" + "".join(f"<li>{_bold(x)}</li>" for x in pending) + "</ul>")
            pending.clear()

    for blk in blocks:
        t = blk["t"]
        if t == "bullet":
            pending.append(blk["text"])
            continue
        flush()
        if t == "cover":
            b.append(
                '<div class="masthead"><div class="inner">'
                '<div class="kicker"><b>who-finder</b><span>research dossier</span></div>'
                f'<h1 class="cover">{_e(blk["title"])}</h1>'
                f'<div class="sub">{_e(blk["subtitle"])}</div>'
                '<div class="cover-meta">'
                + "".join(f'<div class="m"><div class="k">{_e(k)}</div>'
                          f'<div class="v">{_e(v)}</div></div>' for k, v in blk["meta"])
                + "</div></div></div>"
            )
        elif t == "h1":
            section += 1
            b.append(f'<h2 data-n="{section:02d}">{_e(blk["text"])}</h2>')
        elif t == "h2":
            b.append(f"<h3>{_e(blk['text'])}</h3>")
        elif t == "p":
            b.append(f"<p>{_e(blk['text'])}</p>")
        elif t == "note":
            b.append(f'<div class="note">{_e(blk["text"])}</div>')
        elif t == "mono":
            b.append(f'<span class="mono">{_e(blk["text"])}</span>')
        elif t == "kv":
            b.append('<div class="meta">' + "".join(
                f'<div class="m"><div class="k">{_e(k)}</div><div class="v">{_e(v)}</div></div>'
                for k, v in blk["rows"]) + "</div>")
        elif t == "table":
            b.append(_table_html(blk))
        elif t == "person":
            b.append(_person_html(blk))
        elif t == "footer":
            b.append(f'<footer><span class="brand">who-finder</span>'
                     f'<span>{_e(blk["text"])}</span></footer>')
        elif t == "pagebreak":
            b.append('<div class="pagebreak"></div>')
    flush()
    return (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        f"<title>{_e(title)}</title><style>{CSS}</style></head>"
        f"<body><main class=\"sheet\">{''.join(b)}</main></body></html>"
    )


def _table_html(blk: dict) -> str:
    cols = blk["cols"]
    head = "".join(f"<th>{_e(c)}</th>" for c in cols)
    rows = []
    for row in blk["rows"]:
        cells = []
        for j, cell in enumerate(row):
            cls = cols[j].lower() if j < len(cols) else ""
            if cls == "#":
                cells.append(f'<td class="rk">{_e(cell)}</td>')
            elif cls == "name":
                cells.append(f'<td class="nm">{_e(cell)}</td>')
            elif cls == "fit":
                key = str(cell).lower().split()[0]
                cells.append(f'<td><span class="fit {key}">{_e(cell)}</span></td>')
            elif cls in ("priority", "audience", "rows"):
                cells.append(f'<td class="num">{_e(cell)}</td>')
            else:
                cells.append(f"<td>{_e(cell)}</td>")
        rows.append("<tr>" + "".join(cells) + "</tr>")
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(rows)}</tbody></table>"


def _person_html(p: dict) -> str:
    band = p["band"]
    role = p.get("role") or next((v for k, v in p["fields"] if k == "Role"), "")
    fields = "".join(f"<dt>{_e(k)}</dt><dd>{_bold(str(v))}</dd>"
                     for k, v in p["fields"] if k != "Role")
    # Links and evidence are rows of the same definition list as everything
    # else, so their values line up with the fields above them.
    if p["links"]:
        fields += '<dt>Links</dt><dd class="links">' + "".join(
            f'<a href="{_e(l)}">{_e(_short(l))}</a>' for l in p["links"]) + "</dd>"
    if p.get("found_by"):
        fields += "<dt>Found by</dt><dd>" + " ".join(
            f"<code>{_e(_short_query(q))}</code>" for q in p["found_by"]) + "</dd>"
    if p["evidence"]:
        fields += '<dt>Seen in</dt><dd class="links">' + "".join(
            (f'<a href="{_e(e["url"])}">{_e(e["title"][:70])}</a>' if e["url"]
             else _e(e["title"][:70])) for e in p["evidence"]) + "</dd>"

    score = f'{int(p["fit_score"])}' if p.get("fit_score") is not None else "—"
    pri = f' · priority {int(p["priority"])}' if p.get("priority") is not None else ""
    return (
        f'<section class="person"><header>'
        f'<span class="rank">{p["rank"]}</span>'
        f'<div class="who"><h4>{_e(p["name"])}</h4>'
        + (f'<div class="role">{_e(role)}</div>' if role else "")
        + f'<div class="role" style="font-size:.74rem">{_e(_human_id(p["id"]))}{pri}</div></div>'
        f'<div class="fitbox"><div class="score">{score}<span class="of">/100</span></div>'
        f'<span class="badge {band}">{_e(BAND_LABEL.get(band, band))}</span></div>'
        f'</header><dl class="f">{fields}</dl></section>'
    )


def _e(v) -> str:
    return _html.escape(str(v), quote=True)


def _bold(text: str) -> str:
    """Render the `**x**` the insight engine emits, without a markdown parser."""
    parts = _e(text).split("**")
    return "".join(p if i % 2 == 0 else f"<strong>{p}</strong>" for i, p in enumerate(parts))


# --------------------------------------------------------------------------
# PDF
# --------------------------------------------------------------------------

INK = (0.086, 0.075, 0.055)
BODY = (0.24, 0.22, 0.18)
MUTED = (0.54, 0.51, 0.45)
FAINT = (0.70, 0.67, 0.60)
LINE = (0.80, 0.77, 0.68)
DARK = (0.078, 0.066, 0.043)
DARK_INK = (0.937, 0.914, 0.859)
DARK_MUT = (0.604, 0.569, 0.486)
ACCENT = (0.11, 0.31, 0.84)


def _hex(rgb: str) -> tuple:
    rgb = rgb.lstrip("#")
    return tuple(int(rgb[i:i + 2], 16) / 255 for i in (0, 2, 4))


BAND_RGB = {k: _hex(v) for k, v in BAND_COLOR.items()}


def to_pdf(blocks: list[dict]) -> bytes:
    c = pdf.Canvas()
    section = 0
    for blk in blocks:
        t = blk["t"]
        if t == "cover":
            _pdf_cover(c, blk)
        elif t == "h1":
            section += 1
            c.need(64)
            c.space(16)
            # Section number as a small accent tab, then the title.
            c.page.rect(c.margin, c.y - 3, 16, 13, ACCENT)
            c.page.text(c.margin + 4.5, c.y, f"{section:02d}", 8, True, (1, 1, 1))
            c.page.text(c.margin + 24, c.y, pdf.sanitize(blk["text"]), 15.5, True, INK)
            c.y -= 12
            c.rule(gap=4)
        elif t == "h2":
            c.need(40)
            c.space(10)
            c.para(blk["text"].upper(), size=7.6, bold=True, rgb=MUTED, gap=3)
        elif t == "p":
            c.para(_plain(blk["text"]), size=9.5, rgb=BODY, gap=5)
        elif t == "bullet":
            c.para("- " + _plain(blk["text"]), size=9.5, rgb=BODY, indent=6, gap=2)
        elif t == "note":
            c.space(4)
            c.para(_plain(blk["text"]), size=8.8, rgb=(0.42, 0.33, 0.06), indent=10, gap=6)
        elif t == "mono":
            c.para(blk["text"], size=8.2, rgb=(0.29, 0.27, 0.21), indent=10, gap=1)
        elif t == "kv":
            c.space(3)
            for k, v in blk["rows"]:
                c.label(k, str(v), key_w=124, size=9, val_rgb=BODY)
            c.space(5)
        elif t == "table":
            _pdf_table(c, blk["cols"], blk["rows"])
        elif t == "person":
            _pdf_person(c, blk)
        elif t == "footer":
            c.space(12)
            c.page.line(c.margin, c.y, c.w - c.margin, c.y, INK, 1.4)
            c.y -= 12
            c.page.text(c.margin, c.y, "WHO-FINDER", 7, True, INK)
            w = pdf.text_width(pdf.sanitize(blk["text"]), 7.5)
            c.page.text(c.w - c.margin - w, c.y, pdf.sanitize(blk["text"]), 7.5, False, MUTED)
        elif t == "pagebreak":
            c._new_page()
    return c.render()


def _pdf_cover(c: pdf.Canvas, blk: dict) -> None:
    """A dark masthead band with the title set in it, like the HTML cover."""
    band_h = 150.0
    top = c.h
    c.page.rect(0, top - band_h, c.w, band_h, DARK)
    # The tri-colour rule along the foot of the band.
    thirds = [(ACCENT, 0.34), (BAND_RGB["strong"], 0.33), (BAND_RGB["possible"], 0.33)]
    x = 0.0
    for col, frac in thirds:
        wseg = c.w * frac
        c.page.rect(x, top - band_h - 3, wseg, 3, col)
        x += wseg

    tx = c.margin
    ty = top - 40
    c.page.text(tx, ty, "WHO-FINDER", 8, True, DARK_MUT)
    w = pdf.text_width("RESEARCH DOSSIER", 8, True)
    c.page.text(c.w - c.margin - w, ty, "RESEARCH DOSSIER", 8, True, DARK_MUT)
    ty -= 30
    for line in pdf.wrap(pdf.sanitize(blk["title"]), 22, c.col, True):
        c.page.text(tx, ty, line, 22, True, DARK_INK)
        ty -= 26
    ty -= 4
    for line in pdf.wrap(pdf.sanitize(blk["subtitle"]), 9.5, c.col):
        c.page.text(tx, ty, line, 9.5, False, DARK_MUT)
        ty -= 13

    c.y = top - band_h - 3 - 22
    for k, v in blk["meta"]:
        c.label(k, str(v), key_w=104, size=9, val_rgb=BODY)
    c.space(6)
    c.rule()


def _pdf_table(c: pdf.Canvas, cols: list[str], rows: list[list[str]]) -> None:
    # Proportional columns, narrow for the numeric ones so names get the room.
    weights = [0.5 if col in ("#",) else 1.4 if col in ("Name", "Role", "Source") else 1.0
               for col in cols]
    total = sum(weights)
    widths = [c.col * w / total for w in weights]
    fit_idx = next((i for i, col in enumerate(cols) if col.lower() == "fit"), None)
    c.space(6)
    c.need(30)
    x = c.margin
    c.y -= 11
    for col, w in zip(cols, widths):
        c.page.text(x, c.y, pdf.sanitize(col.upper()), 7.0, True, MUTED)
        x += w
    c.y -= 4
    c.page.line(c.margin, c.y, c.w - c.margin, c.y, INK, 1.0)
    for row in rows:
        cells = [pdf.wrap(pdf.sanitize(str(v)), 8.6, w - 8) for v, w in zip(row, widths)]
        height = max(len(cl) for cl in cells) * 12.5 + 4
        c.need(height)
        top = c.y
        for j, (cl, w) in enumerate(zip(cells, widths)):
            x = c.margin + sum(widths[:j])
            yy = top
            for line in cl:
                yy -= 12.5
                if j == fit_idx:
                    _pdf_chip(c, x, yy, line)
                else:
                    c.page.text(x, yy, line, 8.6, j == 1, INK if j == 1 else BODY)
        c.y = top - height
        c.page.line(c.margin, c.y + 2, c.w - c.margin, c.y + 2, (0.90, 0.88, 0.82))
    c.space(8)


def _pdf_chip(c: pdf.Canvas, x: float, y: float, label: str) -> None:
    """A small filled lozenge for a fit band inside the ranking table."""
    key = label.lower().split()[0] if label else "unknown"
    col = BAND_RGB.get(key, BAND_RGB["unknown"])
    w = pdf.text_width(label, 6.8, True) + 9
    c.page.rect(x, y - 2.2, w, 11, col)
    c.page.text(x + 4.5, y, pdf.sanitize(label), 6.8, True, (1, 1, 1))


def _pdf_person(c: pdf.Canvas, p: dict) -> None:
    c.need(108)
    c.space(12)
    band = p["band"]
    accent = BAND_RGB.get(band, BAND_RGB["unknown"])

    # A coloured bar on the left edge carries the fit at a glance.
    bar_x = c.margin
    body_x = c.margin + 12
    top = c.y

    # Header: rank, name, and a fit score block on the right.
    c.page.text(body_x, top - 14, str(p["rank"]), 20, True, FAINT)
    name_x = body_x + 30
    c.page.text(name_x, top - 14, pdf.sanitize(p["name"]), 13.5, True, INK)
    if p.get("fit_score") is not None:
        sc = str(int(p["fit_score"]))
        c.page.text(c.w - c.margin - pdf.text_width(sc, 16, True) - 30, top - 16,
                    sc, 16, True, INK)
        c.page.text(c.w - c.margin - 26, top - 13, "/100", 7, False, MUTED)
    # Fit chip under the score.
    label = BAND_LABEL.get(band, band)
    chip_w = pdf.text_width(label, 6.6, True) + 9
    c.page.rect(c.w - c.margin - chip_w, top - 32, chip_w, 11, accent)
    c.page.text(c.w - c.margin - chip_w + 4.5, top - 29, pdf.sanitize(label), 6.6, True, (1, 1, 1))

    role = p.get("role") or next((v for k, v in p["fields"] if k == "Role"), "")
    c.y = top - 32
    if role:
        c.page.text(name_x, c.y, pdf.sanitize(_plain(str(role)))[:90], 8.6, False, MUTED)
    sub = _human_id(p["id"]) + (f"  ·  priority {int(p['priority'])}" if p.get("priority") is not None else "")
    c.y -= 12
    c.page.text(name_x, c.y, pdf.sanitize(sub), 7.4, False, FAINT)
    c.y -= 6
    c.page.line(body_x, c.y, c.w - c.margin, c.y, LINE)
    c.y -= 4

    for k, v in p["fields"]:
        if k == "Role":
            continue
        c.label(k, _plain(str(v)), key_w=92, size=8.8, val_rgb=BODY, x=body_x)
    for l in p["links"][:3]:
        c.label("Link", str(l), key_w=92, size=8.2, val_rgb=BODY, x=body_x)
    if p.get("found_by"):
        c.label("Found by", "  |  ".join(_short_query(q) for q in p["found_by"]),
                key_w=92, size=8.2, val_rgb=BODY, x=body_x)
    for e in p["evidence"][:3]:
        c.label("Seen in", f"{e['title'][:80]}" + (f"  {e['url']}" if e["url"] else ""),
                key_w=92, size=8.2, val_rgb=BODY, x=body_x)

    # The accent bar runs the full height of the card.
    c.page.rect(bar_x, c.y + 2, 3, top - c.y - 2, accent)
    c.space(6)


def _band_rgb(band: str) -> tuple:
    return {
        "strong": (0.06, 0.48, 0.24), "possible": (0.54, 0.38, 0.0),
        "off": (0.61, 0.17, 0.17),
    }.get(band, MUTED)


def _plain(text: str) -> str:
    return str(text).replace("**", "")


# --------------------------------------------------------------------------
# Dispatch
# --------------------------------------------------------------------------

FORMATS = ("md", "html", "pdf", "json")


def render(blocks: list[dict], fmt: str, *, title: str = "who-finder report"):
    if fmt == "md":
        return to_markdown(blocks)
    if fmt == "html":
        return to_html(blocks, title=title)
    if fmt == "pdf":
        return to_pdf(blocks)
    if fmt == "json":
        return json.dumps(blocks, ensure_ascii=False, indent=2)
    raise ValueError(f"unknown format '{fmt}'. want one of {list(FORMATS)}")
