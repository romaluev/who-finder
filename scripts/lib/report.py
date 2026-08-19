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

from . import __version__, pdf
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
                       ("Ranked by", "ICP fit, then audience reach, then novelty"),
                       ("Fit rules", icp_name),
                       ("New names", f"{n_new} not seen before, {n_known} already in the roster"),
                       ("Cost", f"{credits} credits" if credits else "0 credits (from stored data)"),
                   ]})

    # ---- Summary -------------------------------------------------------
    blocks.append({"t": "h1", "text": "Summary"})
    for line in ins.get("findings") or []:
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
                   "Every name here came from a public profile returned by one of the "
                   "searches below. Nothing was inferred, and no private or logged-in "
                   "source was used."})
    if frames:
        blocks.append({"t": "h2", "text": "How the question was asked"})
        blocks.append({"t": "p", "text":
                       "The same request was framed several ways, because one phrasing "
                       "only reaches the people who describe themselves that way."})
        for f in frames:
            blocks.append({"t": "bullet", "text": f})
    if steps:
        blocks.append({"t": "h2", "text": "Searches run"})
        for s in steps:
            blocks.append({"t": "mono", "text": s})
    if source_status:
        blocks.append({"t": "h2", "text": "Source coverage"})
        blocks.append({"t": "table", "cols": ["Source", "Result", "Rows"],
                       "rows": [[f"{s.get('source')}:{s.get('label')}",
                                 s.get("state", "?"), str(s.get("n", 0))]
                                for s in source_status]})
    blocks.append({"t": "h2", "text": "Reading the fit score"})
    blocks.append({"t": "p", "text":
                   "Fit is scored against a rules file you control, not a model's opinion. "
                   "Every point that moved a score is listed on that person's entry. "
                   "Anyone whose profile could not be fetched is capped at POSSIBLE, however "
                   "good the search snippet looked."})
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


def _person(i: int, r: dict, dossiers: dict, hits: list[dict],
            found_by: list[str] | None = None) -> dict:
    ident = _ident(r)
    d = dossiers.get(ident, {})
    aud = to_int(d.get("audience") or r.get("audience"))
    fields: list[tuple] = []

    role = d.get("headline") or r.get("headline")
    if role:
        src = d.get("headline_source") or ""
        fields.append(("Role", role + (f"  [{src}]" if src else "")))
    else:
        fields.append(("Role", "not public"))
    if aud:
        kind = d.get("audience_kind") or r.get("audience_kind") or "followers"
        fields.append(("Audience", f"{human(aud)} {kind}"))
    if d.get("location"):
        fields.append(("Based in", d["location"]))
    if d.get("bio"):
        fields.append(("About", d["bio"][:600]))

    reasons = r.get("fit_reasons") or d.get("fit_reasons") or []
    if reasons:
        fields.append(("Why they fit", " · ".join(reasons)))
    gaps = r.get("fit_gaps") or []
    if gaps:
        fields.append(("What is missing", " · ".join(gaps)))
    sig = d.get("signals") or r.get("signals") or []
    if sig:
        fields.append(("Signals", ", ".join(sig)))
    topics = d.get("topics") or []
    if topics:
        fields.append(("Topics", ", ".join(topics[:8])))

    recent = d.get("recent") or []
    if recent:
        fields.append(("Recently", _first_text(recent)))
    elif r.get("sample"):
        fields.append(("Recently", str(r["sample"])))

    if found_by and len(found_by) > 1:
        # Independent phrasings converging on the same person is corroboration
        # the fit score cannot see, so it is called out rather than left implicit.
        fields.append(("Corroboration",
                       f"surfaced by {len(found_by)} different framings of the search"))

    if not r.get("enriched"):
        fields.append(("Note", "Profile could not be fetched, so this entry rests on the "
                               "search result alone and is capped at POSSIBLE."))

    links = [r.get("url") or d.get("url")] + list(d.get("links") or [])
    links = [l for l in dict.fromkeys(links) if l]

    return {
        "t": "person",
        "rank": i,
        "name": r.get("name") or r.get("handle") or ident,
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
            head.append(f"`{b['id']}`")
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

CSS = """
:root{--ink:#14161a;--muted:#6b7280;--line:#e6e8ec;--bg:#fff;--accent:#1e40af;--soft:#f7f8fa}
*{box-sizing:border-box}
body{margin:0;background:var(--soft);color:var(--ink);
 font:16px/1.6 ui-sans-serif,-apple-system,"Segoe UI",Inter,Roboto,Helvetica,Arial,sans-serif;
 -webkit-font-smoothing:antialiased}
.sheet{max-width:52rem;margin:0 auto;background:var(--bg);padding:4rem 3.5rem 5rem;
 box-shadow:0 1px 3px rgba(0,0,0,.06),0 12px 40px rgba(0,0,0,.05)}
h1.cover{font-size:2.2rem;line-height:1.15;letter-spacing:-.02em;margin:0 0 .4rem;font-weight:700}
.sub{color:var(--muted);font-size:1rem;margin-bottom:2rem}
h2{font-size:1.35rem;letter-spacing:-.01em;margin:2.8rem 0 .9rem;padding-top:1.4rem;
 border-top:1px solid var(--line);font-weight:650}
h3{font-size:.82rem;text-transform:uppercase;letter-spacing:.09em;color:var(--muted);
 margin:1.8rem 0 .6rem;font-weight:650}
p{margin:.6rem 0}
ul{margin:.5rem 0 1rem;padding-left:1.1rem}
li{margin:.3rem 0}
table{border-collapse:collapse;width:100%;margin:.8rem 0 1.4rem;font-size:.9rem}
th{text-align:left;font-weight:600;color:var(--muted);font-size:.72rem;text-transform:uppercase;
 letter-spacing:.07em;border-bottom:1px solid var(--line);padding:.5rem .6rem .5rem 0}
td{padding:.55rem .6rem .55rem 0;border-bottom:1px solid var(--line);vertical-align:top}
tr:last-child td{border-bottom:none}
.meta{display:grid;grid-template-columns:auto 1fr;gap:.35rem 1.4rem;font-size:.9rem;
 padding:1.1rem 1.3rem;background:var(--soft);border-radius:10px;margin-bottom:1rem}
.meta dt{color:var(--muted)}
.meta dd{margin:0}
.note{background:#fffbeb;border-left:3px solid #f0b429;padding:.85rem 1.1rem;
 border-radius:0 8px 8px 0;font-size:.9rem;margin:1rem 0;color:#5c4708}
code,.mono{font:.83rem/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;
 background:var(--soft);padding:.15rem .4rem;border-radius:5px;color:#374151}
.mono{display:block;padding:.45rem .7rem;margin:.25rem 0;word-break:break-all}
.person{border:1px solid var(--line);border-radius:14px;padding:1.5rem 1.6rem;margin:1.1rem 0;
 background:var(--bg);break-inside:avoid;page-break-inside:avoid}
.person header{display:flex;align-items:baseline;gap:.7rem;flex-wrap:wrap;margin-bottom:.2rem}
.person h4{font-size:1.18rem;margin:0;font-weight:650;letter-spacing:-.01em}
.rank{color:var(--muted);font-variant-numeric:tabular-nums;font-weight:600}
.badge{font-size:.68rem;font-weight:700;letter-spacing:.06em;padding:.2rem .5rem;
 border-radius:20px;color:#fff;white-space:nowrap}
.scores{color:var(--muted);font-size:.82rem;margin-bottom:.9rem;font-variant-numeric:tabular-nums}
dl.f{display:grid;grid-template-columns:8.5rem 1fr;gap:.45rem 1rem;margin:0;font-size:.92rem}
dl.f dt{color:var(--muted);font-size:.8rem;padding-top:.1rem}
dl.f dd{margin:0}
a{color:var(--accent);text-decoration:none}
a:hover{text-decoration:underline}
.links a{margin-right:.7rem;font-size:.85rem;word-break:break-all}
footer{margin-top:3rem;padding-top:1.2rem;border-top:1px solid var(--line);
 color:var(--muted);font-size:.8rem}
@media print{
 body{background:#fff}
 .sheet{box-shadow:none;max-width:none;padding:0;margin:0}
 .pagebreak{page-break-before:always}
 h2{page-break-after:avoid}
 a{color:var(--ink)}
}
@page{margin:18mm 16mm}
"""


def to_html(blocks: list[dict], *, title: str = "who-finder report") -> str:
    b: list[str] = []
    pending: list[str] = []

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
            b.append(f'<h1 class="cover">{_e(blk["title"])}</h1>')
            b.append(f'<div class="sub">{_e(blk["subtitle"])}</div>')
            b.append('<dl class="meta">' + "".join(
                f"<dt>{_e(k)}</dt><dd>{_e(v)}</dd>" for k, v in blk["meta"]) + "</dl>")
        elif t == "h1":
            b.append(f"<h2>{_e(blk['text'])}</h2>")
        elif t == "h2":
            b.append(f"<h3>{_e(blk['text'])}</h3>")
        elif t == "p":
            b.append(f"<p>{_e(blk['text'])}</p>")
        elif t == "note":
            b.append(f'<div class="note">{_e(blk["text"])}</div>')
        elif t == "mono":
            b.append(f'<span class="mono">{_e(blk["text"])}</span>')
        elif t == "kv":
            b.append('<dl class="meta">' + "".join(
                f"<dt>{_e(k)}</dt><dd>{_e(v)}</dd>" for k, v in blk["rows"]) + "</dl>")
        elif t == "table":
            head = "".join(f"<th>{_e(c)}</th>" for c in blk["cols"])
            body = "".join("<tr>" + "".join(f"<td>{_e(c)}</td>" for c in row) + "</tr>"
                           for row in blk["rows"])
            b.append(f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>")
        elif t == "person":
            b.append(_person_html(blk))
        elif t == "footer":
            b.append(f"<footer>{_e(blk['text'])}</footer>")
        elif t == "pagebreak":
            b.append('<div class="pagebreak"></div>')
    flush()
    return (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        f"<title>{_e(title)}</title><style>{CSS}</style></head>"
        f"<body><main class=\"sheet\">{''.join(b)}</main></body></html>"
    )


def _person_html(p: dict) -> str:
    color = BAND_COLOR.get(p["band"], "#6b7280")
    scores = []
    if p.get("priority") is not None:
        scores.append(f"priority {int(p['priority'])}")
    if p.get("fit_score") is not None:
        scores.append(f"fit {int(p['fit_score'])}/100")
    scores.append(p["id"])
    fields = "".join(f"<dt>{_e(k)}</dt><dd>{_bold(str(v))}</dd>" for k, v in p["fields"])
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
    return (
        f'<section class="person"><header><span class="rank">{p["rank"]}</span>'
        f'<h4>{_e(p["name"])}</h4>'
        f'<span class="badge" style="background:{color}">'
        f'{_e(BAND_LABEL.get(p["band"], p["band"]))}</span></header>'
        f'<div class="scores">{_e(" · ".join(scores))}</div>'
        f'<dl class="f">{fields}</dl></section>'
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

INK = (0.08, 0.09, 0.11)
MUTED = (0.42, 0.45, 0.50)
LINE = (0.87, 0.88, 0.91)


def to_pdf(blocks: list[dict]) -> bytes:
    c = pdf.Canvas()
    for blk in blocks:
        t = blk["t"]
        if t == "cover":
            c.space(28)
            c.para(blk["title"], size=23, bold=True, rgb=INK, leading=1.2, gap=3)
            c.para(blk["subtitle"], size=10.5, rgb=MUTED, gap=12)
            for k, v in blk["meta"]:
                c.label(k, str(v), key_w=104, size=9)
            c.space(6)
            c.rule()
        elif t == "h1":
            c.need(56)
            c.space(14)
            c.para(blk["text"], size=15.5, bold=True, rgb=INK, gap=4)
            c.rule(gap=3)
        elif t == "h2":
            c.need(40)
            c.space(9)
            c.para(blk["text"].upper(), size=8, bold=True, rgb=MUTED, gap=3)
        elif t == "p":
            c.para(_plain(blk["text"]), size=9.5, gap=5)
        elif t == "bullet":
            c.para("- " + _plain(blk["text"]), size=9.5, indent=6, gap=2)
        elif t == "note":
            c.space(4)
            c.para(_plain(blk["text"]), size=8.8, rgb=(0.36, 0.28, 0.03), indent=10, gap=6)
        elif t == "mono":
            c.para(blk["text"], size=8.2, rgb=(0.3, 0.32, 0.36), indent=10, gap=1)
        elif t == "kv":
            c.space(3)
            for k, v in blk["rows"]:
                c.label(k, str(v), key_w=124, size=9)
            c.space(5)
        elif t == "table":
            _pdf_table(c, blk["cols"], blk["rows"])
        elif t == "person":
            _pdf_person(c, blk)
        elif t == "footer":
            c.space(10)
            c.rule(gap=4)
            c.para(blk["text"], size=8, rgb=MUTED)
        elif t == "pagebreak":
            c._new_page()
    return c.render()


def _pdf_table(c: pdf.Canvas, cols: list[str], rows: list[list[str]]) -> None:
    # Proportional columns, narrow for the numeric ones so names get the room.
    weights = [0.5 if col in ("#",) else 1.4 if col in ("Name", "Role", "Source") else 1.0
               for col in cols]
    total = sum(weights)
    widths = [c.col * w / total for w in weights]
    c.space(6)
    c.need(30)
    x = c.margin
    c.y -= 11
    for col, w in zip(cols, widths):
        c.page.text(x, c.y, pdf.sanitize(col.upper()), 7.2, True, MUTED)
        x += w
    c.y -= 4
    c.page.line(c.margin, c.y, c.w - c.margin, c.y, LINE)
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
                c.page.text(x, yy, line, 8.6, j == 1, INK if j == 1 else (0.25, 0.27, 0.3))
        c.y = top - height
        c.page.line(c.margin, c.y + 2, c.w - c.margin, c.y + 2, (0.94, 0.95, 0.96))
    c.space(8)


def _pdf_person(c: pdf.Canvas, p: dict) -> None:
    c.need(96)
    c.space(11)
    band = BAND_LABEL.get(p["band"], p["band"])
    title = f"{p['rank']}. {p['name']}"
    c.para(title, size=12.5, bold=True, rgb=INK, gap=1)
    scores = [band]
    if p.get("priority") is not None:
        scores.append(f"priority {int(p['priority'])}")
    if p.get("fit_score") is not None:
        scores.append(f"fit {int(p['fit_score'])}/100")
    scores.append(p["id"])
    c.para("  ·  ".join(scores), size=8, rgb=_band_rgb(p["band"]), gap=4)
    for k, v in p["fields"]:
        c.label(k, _plain(str(v)), key_w=92, size=8.8)
    for l in p["links"][:3]:
        c.label("Link", str(l), key_w=92, size=8.2)
    if p.get("found_by"):
        c.label("Found by", "  |  ".join(_short_query(q) for q in p["found_by"]),
                key_w=92, size=8.2)
    for e in p["evidence"][:3]:
        c.label("Seen in", f"{e['title'][:80]}" + (f"  {e['url']}" if e["url"] else ""),
                key_w=92, size=8.2)
    c.space(5)
    c.page.line(c.margin, c.y, c.w - c.margin, c.y, (0.93, 0.94, 0.96))


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
