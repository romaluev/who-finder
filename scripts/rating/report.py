"""One build, two parts: portfolio summary then a page per creator.

Block vocabulary matches who-finder so the three renderers cannot drift.
The HTML is an editorial dossier — same house as who-finder — because a
buyer reads this next to a shortlist, not next to a dashboard.
"""

from __future__ import annotations

import html as _html
import json
import re
from datetime import datetime, timezone

from . import __version__, pdf
from .features.provenance import Metric
from .scoring import decision_line
from .util import human, money

FORMATS = ("md", "html", "pdf", "json")

TIER_LABEL = {"A": "PILOT NOW", "B": "NEGOTIATE", "C": "WATCH", "D": "PASS", "?": "COLLECT MORE"}
TIER_BAND = {"A": "strong", "B": "possible", "C": "weak", "D": "off", "?": "unknown"}

GRAPH_METRICS = {
    "social": (
        "icp_share_engagers", "director_plus_share", "enterprise_share",
        "target_account_hits", "icp_share_seed_pool", "geo_fit_share", "followers",
    ),
    "engagement": (
        "median_impressions_est", "authenticity", "eng_per_1k_followers",
        "comment_depth", "posts_per_week", "trend_90d",
    ),
    "interest": (
        "brand_topic_fit", "topic_concentration", "audience_interest_alignment",
        "headline_alignment",
    ),
}


def _m(row: dict, name: str) -> Metric | None:
    metrics = row.get("metrics") or {}
    v = metrics.get(name)
    if isinstance(v, Metric):
        return v
    if isinstance(v, dict):
        return Metric(v.get("name") or name, v.get("value"), v.get("source") or "insufficient",
                      v.get("basis") or "", v.get("scaled"))
    return None


def _fmt(m: Metric | None) -> str:
    if not m or not m.present:
        return "—"
    v = m.value
    if isinstance(v, float):
        if 0 < abs(v) < 1.5:
            return f"{v:.0%}" if abs(v) <= 1 else f"{v:.2f}"
        if abs(v) >= 100:
            return human(int(v))
        return f"{v:.2f}"
    if isinstance(v, int):
        return human(v)
    return str(v)


def _score(v) -> str:
    if v is None:
        return "—"
    try:
        return str(int(round(float(v))))
    except (TypeError, ValueError):
        return "—"


def _score_n(v) -> int | None:
    if v is None:
        return None
    try:
        return int(round(float(v)))
    except (TypeError, ValueError):
        return None


def build(
    rows: list[dict],
    *,
    brief: str,
    preset: str,
    icp_name: str,
    rung: int,
    rung_label: str,
    findings: list[str],
    notices: list[dict],
    portfolio: dict | None,
    connect_next: list[dict],
    pairs: list[dict],
    names: dict[str, str],
    calibrated: bool = False,
    economy: list[str] | None = None,
) -> list[dict]:
    blocks: list[dict] = []
    now = datetime.now(timezone.utc).strftime("%d %B %Y")
    n = len(rows)
    chosen = (portfolio or {}).get("chosen") or []
    spend = (portfolio or {}).get("spend")
    reach = (portfolio or {}).get("icp_impressions")

    meta = [
        ("Objective", preset),
        ("ICP", icp_name),
        ("Depth", rung_label),
        ("Impressions", "calibrated" if calibrated else "estimated"),
        ("Date", now),
    ]
    if economy:
        meta.append(("Spend", economy[0]))

    blocks.append({
        "t": "cover",
        "title": brief or "Creator rating",
        "subtitle": f"{n} {'creator' if n == 1 else 'creators'} · {preset} · {now}",
        "meta": meta,
    })

    blocks.append({"t": "h1", "text": "The decision"})
    if chosen:
        names_c = ", ".join(f"**{c.get('name') or c.get('id')}**" for c in chosen[:8])
        extra = f" and {len(chosen) - 8} more" if len(chosen) > 8 else ""
        line = f"Buy these {len(chosen)} under budget: {names_c}{extra}."
        if reach:
            line += f" Expected ICP impressions per post across the set: {human(int(reach))}."
        if spend is not None:
            line += f" Total at fair: {money(spend)}."
        blocks.append({"t": "p", "text": line})
    else:
        blocks.append({"t": "p", "text":
                       "No priced shortlist yet — this run did not have enough post history "
                       "to emit a price. The ranking below is still the buying order once you connect a source."})
    ov = [note for note in notices if note.get("kind") == "overlap"]
    for ntc in ov[:6]:
        blocks.append({"t": "bullet", "text": ntc["text"]})

    blocks.append({"t": "h2", "text": "At a glance"})
    tiers: dict[str, int] = {}
    for r in rows:
        tiers[r.get("tier") or "?"] = tiers.get(r.get("tier") or "?", 0) + 1
    auds = sorted(int(r.get("followers") or 0) for r in rows if r.get("followers"))
    confs = [float(r.get("confidence") or 0) for r in rows]
    med_conf = confs[len(confs) // 2] if confs else 0
    glance = [
        ("Creators rated", str(n)),
        ("Tiers", ", ".join(f"{tiers[t]} {t}" for t in ("A", "B", "C", "D", "?") if tiers.get(t))),
        ("Median audience", human(auds[len(auds) // 2]) if auds else "—"),
        ("Median confidence", f"{med_conf:.0%}"),
        ("Impressions", "calibrated" if calibrated else "estimated"),
    ]
    blocks.append({"t": "kv", "rows": glance})

    if findings:
        blocks.append({"t": "h2", "text": "What I found"})
        for line in findings:
            blocks.append({"t": "bullet", "text": line})

    easy = [note for note in notices if note.get("kind") != "overlap"]
    if easy:
        blocks.append({"t": "h2", "text": "Easy to miss"})
        for ntc in easy[:8]:
            blocks.append({"t": "bullet", "text": ntc["text"]})

    if rows:
        blocks.append({"t": "h2", "text": "The ranking"})
        table_rows = []
        for i, r in enumerate(rows, start=1):
            pr = r.get("price") or {}
            table_rows.append([
                str(i),
                r.get("name") or r.get("handle") or r.get("id") or "",
                r.get("tier") or "?",
                _score(r.get("social")),
                _score(r.get("engagement")),
                _score(r.get("interest")),
                human(int(r.get("followers") or 0)) if r.get("followers") else "—",
                human(int(r.get("icp_impressions") or 0)) if r.get("icp_impressions") else "—",
                money(pr.get("fair")) if pr else "—",
                f"${pr['cpm_icp']:.0f}" if pr and pr.get("cpm_icp") is not None else "—",
                r.get("next_action") or "",
            ])
        blocks.append({
            "t": "table",
            "cols": ["#", "Name", "Tier", "Soc", "Eng", "Int", "Audience", "ICP impr.", "Fair", "CPM-ICP", "Do"],
            "rows": table_rows,
        })

    blocks.append({"t": "h2", "text": "What this report does not cover"})
    assumed = _coverage_gaps(rows)
    for g in assumed:
        blocks.append({"t": "bullet", "text": g})
    if connect_next:
        top = connect_next[0]
        blocks.append({"t": "note", "text":
                       f"{top['line']}. Guide: {top.get('guide') or 'docs/connect.md'}"})
    elif not assumed:
        blocks.append({"t": "bullet", "text": "Every weighted metric had a measured value."})
    if economy:
        for line in economy[:4]:
            blocks.append({"t": "bullet", "text": line})

    if rows:
        blocks.append({"t": "pagebreak"})
        blocks.append({"t": "h1", "text": "The people"})
        for i, r in enumerate(rows, start=1):
            blocks.append(_person(i, r, pairs, names, connect_next))

    blocks.append({"t": "footer", "text":
                   f"who-finder v{__version__} · generated {now} · {rung_label}"})
    return blocks


def _coverage_gaps(rows: list[dict]) -> list[str]:
    counts: dict[str, int] = {}
    for r in rows:
        for name, m in (r.get("metrics") or {}).items():
            src = m.source if isinstance(m, Metric) else (m.get("source") if isinstance(m, dict) else "")
            if src in {"assumed", "insufficient", "estimated"}:
                counts[f"{name} ({src})"] = counts.get(f"{name} ({src})", 0) + 1
        for g in r.get("gates") or []:
            if isinstance(g, dict):
                counts[f"gate:{g.get('name')}"] = counts.get(f"gate:{g.get('name')}", 0) + 1
    return [f"**{k}** — {n} creator{'s' if n != 1 else ''}" for k, n in sorted(counts.items(), key=lambda kv: -kv[1])[:12]]


def _person(i: int, r: dict, pairs: list[dict], names: dict[str, str], connect_next: list[dict]) -> dict:
    pr = r.get("price") or {}
    fields = []
    fields.append(("Decision", decision_line(r, r.get("name") or r.get("handle") or r.get("id") or "")))
    if pr:
        fields.append((
            "Price",
            f"fair {money(pr.get('fair'))} · open {money(pr.get('open'))} · "
            f"walk-away {money(pr.get('walk_away'))}"
            + (f" · CPM-ICP ${pr['cpm_icp']:.0f}" if pr.get("cpm_icp") is not None else ""),
        ))
        fields.append(("Assumptions", " · ".join(pr.get("assumptions") or [])))
        if pr.get("do_not_buy"):
            fields.append(("Do not buy", "authenticity below 60"))
    else:
        fields.append(("Price", "not emitted — no post history"))

    scoreboard = [
        ("Social", _score_n(r.get("social"))),
        ("Engagement", _score_n(r.get("engagement"))),
        ("Interest", _score_n(r.get("interest"))),
    ]

    for graph, names_m in GRAPH_METRICS.items():
        bits = []
        for nm in names_m:
            m = _m(r, nm)
            if not m or m.source in {"insufficient", "assumed"}:
                continue
            scaled = f" → {m.scaled:.0f}" if m.scaled is not None else ""
            bits.append(f"{nm}={_fmt(m)}{scaled} [{m.source}]")
        score = r.get(graph)
        if bits:
            fields.append((graph.title(), f"{_score(score)}/100. " + "; ".join(bits)))
        else:
            fields.append((graph.title(), "not measured yet"))

    authn = _m(r, "authenticity")
    if authn and authn.present:
        fields.append(("Authenticity", f"{_fmt(authn)} — {authn.basis}"))
    fired = [g for g in (r.get("gates") or []) if isinstance(g, dict)]
    if fired:
        fields.append(("Gates", "; ".join(f"{g['name']}: {g['why']}" for g in fired)))

    from . import overlap as ovmod
    ovs = ovmod.overlaps_for(r.get("id") or "", pairs, names, threshold=0.15)
    if ovs:
        fields.append(("Overlap", "; ".join(
            f"{o['name']} {o['score']:.0%} ({o['kind']})" for o in ovs[:4]
        )))

    evidence = r.get("evidence") or []
    if evidence:
        fields.append(("Evidence", " · ".join(
            (e.get("title") or e.get("url") or "")[:80] for e in evidence[:3]
        )))

    blanks = []
    for name, m in (r.get("metrics") or {}).items():
        src = m.source if isinstance(m, Metric) else (m.get("source") if isinstance(m, dict) else "")
        basis = m.basis if isinstance(m, Metric) else (m.get("basis") if isinstance(m, dict) else "")
        if src in {"insufficient", "assumed"}:
            blanks.append(f"{name} ({src}: {basis})")
    if blanks:
        action = connect_next[0]["line"] if connect_next else (
            "a Clay export or Bright Data key unlocks LinkedIn post counts"
        )
        fields.append((
            "Not measured",
            f"{len(blanks)} metrics need posts or an engager source. {action}.",
        ))

    band = TIER_BAND.get(r.get("tier") or "?", "unknown")
    return {
        "t": "person",
        "rank": i,
        "name": r.get("name") or r.get("handle") or r.get("id"),
        "role": r.get("headline") or "",
        "id": r.get("id") or "",
        "band": r.get("tier") or "?",
        "band_class": band,
        "fit_score": r.get("creator_score"),
        "confidence": r.get("confidence"),
        "scoreboard": scoreboard,
        "fields": fields,
        "links": [u for u in [r.get("url")] if u],
        "found_by": [],
        "evidence": evidence[:3],
    }


def findings_of(rows: list[dict], rung_label: str, portfolio: dict | None) -> list[str]:
    out = [f"This run reached {rung_label}."]
    n = len(rows)
    a = sum(1 for r in rows if r.get("tier") == "A")
    q = sum(1 for r in rows if r.get("tier") == "?")
    if n:
        out.append(f"{n} creators scored. {a} tier A, {q} waiting on more data.")
    if portfolio and portfolio.get("chosen"):
        out.append(
            f"Under the budget, {portfolio['n']} names add "
            f"{human(int(portfolio.get('icp_impressions') or 0))} ICP impressions "
            f"at {money(portfolio.get('spend'))}."
        )
    return out


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
        elif t == "kv":
            out += ["", "| | |", "|---|---|"]
            out += [f"| **{k}** | {_cell(v)} |" for k, v in b["rows"]] + [""]
        elif t == "table":
            out += ["", "| " + " | ".join(b["cols"]) + " |",
                    "|" + "|".join("---" for _ in b["cols"]) + "|"]
            out += ["| " + " | ".join(_cell(c) for c in row) + " |" for row in b["rows"]]
            out.append("")
        elif t == "person":
            out += ["", "---", "", f"### {b['rank']}. {b['name']}", ""]
            head = [f"**{TIER_LABEL.get(b['band'], b['band'])}**"]
            if b.get("fit_score") is not None:
                head.append(f"{int(b['fit_score'])}/100")
            if b.get("confidence") is not None:
                head.append(f"confidence {float(b['confidence']):.0%}")
            if b.get("role"):
                head.append(b["role"][:90])
            out += [" · ".join(head), ""]
            board = b.get("scoreboard") or []
            if board:
                bits = []
                for name, val in board:
                    bits.append(f"{name} {val if val is not None else '—'}")
                out.append("**Graphs:** " + " · ".join(bits))
                out.append("")
            out += [f"- **{k}:** {_cell(v)}" for k, v in b["fields"]]
            if b.get("links"):
                out.append("- **Links:** " + " · ".join(b["links"]))
            out.append("")
        elif t == "footer":
            out += ["", "---", "", f"*{b['text']}*"]
        elif t == "pagebreak":
            out.append("")
    return "\n".join(out).strip() + "\n"


def _cell(v) -> str:
    return str(v).replace("|", "\\|").replace("\n", " ")


# --------------------------------------------------------------------------
# HTML
# --------------------------------------------------------------------------

# Self-contained: system fonts only. Print stylesheet strips chrome so a
# browser "Save as PDF" matches the generated PDF well enough to forward.
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
.masthead{background:var(--dark);color:var(--dark-ink);padding:3.4rem 0 2.8rem;position:relative}
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
.glance{display:grid;grid-template-columns:repeat(auto-fit,minmax(10rem,1fr));
 gap:0;border-top:1px solid var(--rule);margin:1rem 0 1.6rem}
.glance .m{padding:.9rem 1.2rem .9rem 0;border-bottom:1px solid var(--line)}
.glance .k{font:600 .6rem/1 var(--grot);letter-spacing:.16em;text-transform:uppercase;
 color:var(--muted);margin-bottom:.35rem}
.glance .v{font-size:.92rem;color:var(--ink);line-height:1.35}
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
table{border-collapse:collapse;width:100%;margin:1rem 0 1.6rem;font-size:.88rem}
thead th{font:600 .62rem/1 var(--grot);letter-spacing:.12em;text-transform:uppercase;
 color:var(--muted);text-align:left;padding:.6rem .7rem .6rem 0;border-bottom:2px solid var(--ink)}
tbody td{padding:.65rem .7rem .65rem 0;border-bottom:1px solid var(--line);vertical-align:middle}
tbody tr:last-child td{border-bottom:none}
td.rk{font:600 .95rem/1 var(--grot);color:var(--faint);font-variant-numeric:tabular-nums;width:2rem}
td.nm{font-weight:600;color:var(--ink)}
td.num{font-variant-numeric:tabular-nums;white-space:nowrap}
.fit{font:600 .62rem/1 var(--grot);letter-spacing:.08em;text-transform:uppercase;
 padding:.28rem .5rem;border-radius:3px;white-space:nowrap}
.fit.strong{color:var(--strong);background:#e3f0e8}
.fit.possible{color:var(--possible);background:#f4ecd6}
.fit.weak{color:var(--weak);background:#eceadf}
.fit.off{color:var(--off);background:#f3e2dc}
.fit.unknown{color:var(--weak);background:#eceadf}
.person{background:var(--card);border:1px solid var(--line);border-top:3px solid var(--ink);
 padding:1.6rem 1.7rem 1.5rem;margin:1.3rem 0;break-inside:avoid;page-break-inside:avoid;
 box-shadow:0 1px 2px rgba(22,19,14,.04)}
.person header{display:flex;align-items:flex-start;gap:1rem;margin-bottom:1.1rem;
 padding-bottom:1rem;border-bottom:1px solid var(--line)}
.person .rank{font:400 1.9rem/1 var(--disp);color:var(--faint);min-width:2.4rem;
 font-variant-numeric:tabular-nums}
.person .who{flex:1;min-width:0}
.person h4{font:400 1.35rem/1.15 var(--disp);color:var(--ink);margin:0 0 .3rem;letter-spacing:-.01em}
.person .role{font-size:.88rem;color:var(--muted)}
.person .fitbox{text-align:right;flex-shrink:0}
.person .fitbox .score{font:400 1.5rem/1 var(--disp);font-variant-numeric:tabular-nums;color:var(--ink)}
.person .fitbox .of{font-size:.66rem;color:var(--muted);letter-spacing:.06em}
.badge{display:inline-block;font:600 .6rem/1 var(--grot);letter-spacing:.1em;text-transform:uppercase;
 padding:.32rem .55rem;border-radius:3px;margin-top:.4rem;color:#fff}
.badge.strong{background:var(--strong)}
.badge.possible{background:var(--possible)}
.badge.weak{background:var(--weak)}
.badge.off{background:var(--off)}
.badge.unknown{background:var(--weak)}
.board{display:grid;grid-template-columns:repeat(3,1fr);gap:1rem;margin:0 0 1.2rem}
.board .g{min-width:0}
.board .gl{font:600 .6rem/1 var(--grot);letter-spacing:.14em;text-transform:uppercase;color:var(--muted)}
.board .gn{font:400 1.45rem/1.1 var(--disp);color:var(--ink);margin:.35rem 0 .4rem;font-variant-numeric:tabular-nums}
.bar{height:4px;background:var(--line);border-radius:2px;overflow:hidden}
.bar > i{display:block;height:100%;background:var(--ink)}
dl.f{display:grid;grid-template-columns:7.5rem 1fr;gap:.5rem 1.2rem;margin:0;font-size:.9rem}
dl.f dt{font:600 .62rem/1.5 var(--grot);letter-spacing:.1em;text-transform:uppercase;
 color:var(--muted);padding-top:.15rem}
dl.f dd{margin:0;color:var(--body);line-height:1.5}
dl.f dd strong{color:var(--ink);font-weight:600}
a{color:var(--accent);text-decoration:none;border-bottom:1px solid transparent}
a:hover{border-bottom-color:var(--accent)}
.links{margin-top:1rem}
.links a{margin-right:.9rem;font-size:.84rem;word-break:break-all;border-bottom:1px solid var(--rule)}
footer{margin-top:3.5rem;padding-top:1.4rem;border-top:2px solid var(--ink);
 color:var(--muted);font-size:.78rem;display:flex;justify-content:space-between;gap:1rem}
footer .brand{font:600 .62rem/1.5 var(--grot);letter-spacing:.2em;text-transform:uppercase;color:var(--ink)}
.pagebreak{page-break-before:always}
@media print{
 body{background:#fff}
 .sheet{max-width:none;padding:0}
 .masthead{margin:0 0 1.5rem}
 h2{page-break-after:avoid}
 .person{box-shadow:none}
 a{color:var(--ink);border-bottom:none}
}
@page{margin:16mm 15mm}
"""


def to_html(blocks: list[dict], *, title: str = "who-finder report") -> str:
    b: list[str] = []
    pending: list[str] = []
    h2n = 0

    def flush() -> None:
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
            meta = "".join(
                f'<div class="m"><div class="k">{_esc(k)}</div><div class="v">{_esc(str(v))}</div></div>'
                for k, v in blk["meta"]
            )
            b.append(
                f'<div class="masthead"><div class="inner">'
                f'<div class="kicker"><span>CREATOR RATING</span><b>DOSSIER</b></div>'
                f'<h1 class="cover">{_esc(blk["title"])}</h1>'
                f'<p class="sub">{_esc(blk["subtitle"])}</p>'
                f'<div class="cover-meta">{meta}</div></div></div>'
            )
        elif t == "h1":
            h2n += 1
            b.append(f'<h2 data-n="{h2n:02d}">{_esc(blk["text"])}</h2>')
        elif t == "h2":
            b.append(f"<h3>{_esc(blk['text'])}</h3>")
        elif t == "p":
            b.append(f"<p>{_bold(blk['text'])}</p>")
        elif t == "note":
            b.append(f'<div class="note">{_bold(blk["text"])}</div>')
        elif t == "kv":
            rows = "".join(
                f'<div class="m"><div class="k">{_esc(k)}</div><div class="v">{_esc(str(v))}</div></div>'
                for k, v in blk["rows"]
            )
            b.append(f'<div class="glance">{rows}</div>')
        elif t == "table":
            head = "".join(f"<th>{_esc(c)}</th>" for c in blk["cols"])
            body_rows = []
            for row in blk["rows"]:
                cells = []
                for j, c in enumerate(row):
                    cls = ""
                    inner = _esc(str(c))
                    if j == 0:
                        cls = "rk"
                    elif j == 1:
                        cls = "nm"
                    elif j == 2:
                        band = TIER_BAND.get(str(c), "unknown")
                        inner = f'<span class="fit {band}">{_esc(TIER_LABEL.get(str(c), str(c)))}</span>'
                    elif j in {3, 4, 5, 6, 7, 8, 9}:
                        cls = "num"
                    cells.append(f'<td class="{cls}">{inner}</td>')
                body_rows.append("<tr>" + "".join(cells) + "</tr>")
            b.append(f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body_rows)}</tbody></table>")
        elif t == "person":
            band = blk.get("band_class") or TIER_BAND.get(blk.get("band"), "unknown")
            score = ""
            if blk.get("fit_score") is not None:
                score = (
                    f'<div class="fitbox"><div class="score">{int(blk["fit_score"])}</div>'
                    f'<div class="of">/100</div></div>'
                )
            board_html = ""
            if blk.get("scoreboard"):
                cells = []
                for name, val in blk["scoreboard"]:
                    width = max(0, min(100, val or 0))
                    shown = "—" if val is None else str(val)
                    cells.append(
                        f'<div class="g"><div class="gl">{_esc(name)}</div>'
                        f'<div class="gn">{shown}</div>'
                        f'<div class="bar"><i style="width:{width}%"></i></div></div>'
                    )
                board_html = f'<div class="board">{"".join(cells)}</div>'
            fields = "".join(
                f"<dt>{_esc(k)}</dt><dd>{_bold(str(v))}</dd>" for k, v in blk["fields"]
            )
            links = " ".join(
                f'<a href="{_esc(u)}">{_esc(u)}</a>' for u in blk.get("links") or []
            )
            conf = ""
            if blk.get("confidence") is not None:
                conf = f' · conf {float(blk["confidence"]):.0%}'
            b.append(
                f'<article class="person"><header>'
                f'<div class="rank">{blk["rank"]}</div>'
                f'<div class="who"><h4>{_esc(blk["name"])}</h4>'
                f'<div class="role">{_esc(blk.get("role") or "")}{conf}</div>'
                f'<span class="badge {band}">{_esc(TIER_LABEL.get(blk["band"], blk["band"]))}</span>'
                f'</div>{score}</header>'
                f'{board_html}<dl class="f">{fields}</dl>'
                + (f'<p class="links">{links}</p>' if links else "")
                + "</article>"
            )
        elif t == "footer":
            b.append(
                f'<footer><span class="brand">Higgsfield · who-finder</span>'
                f"<span>{_esc(blk['text'])}</span></footer>"
            )
        elif t == "pagebreak":
            b.append('<div class="pagebreak"></div>')
    flush()
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>{_esc(title)}</title><style>{CSS}</style></head>"
        f"<body><div class='sheet'>{''.join(b)}</div></body></html>"
    )


def _esc(s: str) -> str:
    return _html.escape(str(s or ""))


def _bold(s: str) -> str:
    s = _esc(s)
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)


# --------------------------------------------------------------------------
# PDF
# --------------------------------------------------------------------------

INK = (0.09, 0.07, 0.05)
BODY = (0.24, 0.22, 0.18)
MUTED = (0.54, 0.51, 0.45)
DARK = (0.08, 0.07, 0.04)
DARK_INK = (0.94, 0.91, 0.86)
ACCENT = (0.11, 0.31, 0.84)
STRONG = (0.10, 0.48, 0.29)
POSSIBLE = (0.63, 0.42, 0.00)
OFF = (0.66, 0.24, 0.16)
LINE = (0.89, 0.87, 0.80)


def _tier_rgb(band: str) -> tuple:
    return {
        "strong": STRONG, "possible": POSSIBLE, "weak": MUTED, "off": OFF, "unknown": MUTED,
    }.get(band, MUTED)


def to_pdf(blocks: list[dict]) -> bytes:
    c = pdf.Canvas()
    for blk in blocks:
        t = blk["t"]
        if t == "cover":
            c.need(200)
            top = c.y
            c.page.rect(0, top - 176, c.w, 196, DARK)
            c.page.rect(0, top - 180, c.w * 0.34, 4, ACCENT)
            c.page.rect(c.w * 0.34, top - 180, c.w * 0.33, 4, STRONG)
            c.page.rect(c.w * 0.67, top - 180, c.w * 0.33, 4, POSSIBLE)
            c.y = top - 32
            c.page.text(c.margin, c.y, "CREATOR RATING", 8, True, MUTED)
            c.y -= 30
            for line in pdf.wrap(pdf.sanitize(blk["title"]), 22, c.col, True):
                c.page.text(c.margin, c.y, line, 22, True, DARK_INK)
                c.y -= 26
            for line in pdf.wrap(pdf.sanitize(blk["subtitle"]), 10, c.col):
                c.page.text(c.margin, c.y, line, 10, False, MUTED)
                c.y -= 13
            c.y = top - 188
            for k, v in blk["meta"]:
                c.label(k, str(v), key_w=100, size=9)
            c.space(10)
        elif t == "h1":
            c.space(16)
            c.para(blk["text"], size=16, bold=True, rgb=INK, gap=6)
        elif t == "h2":
            c.space(12)
            c.para(blk["text"], size=11, bold=True, rgb=INK, gap=4)
        elif t == "p":
            c.para(blk["text"].replace("**", ""), size=9.5, rgb=BODY, gap=4)
        elif t == "bullet":
            c.para("- " + blk["text"].replace("**", ""), size=9.2, rgb=BODY, indent=10, gap=2)
        elif t == "note":
            c.para(blk["text"].replace("**", ""), size=9, rgb=(0.42, 0.33, 0.06), gap=6)
        elif t == "kv":
            for k, v in blk["rows"]:
                c.label(k, str(v), key_w=120, size=9)
        elif t == "table":
            _pdf_table(c, blk["cols"], blk["rows"])
        elif t == "person":
            c.need(110)
            c.space(12)
            c.page.line(c.margin, c.y, c.w - c.margin, c.y, INK, 1.2)
            c.space(8)
            band = blk.get("band_class") or TIER_BAND.get(blk.get("band"), "unknown")
            title = f"{blk['rank']}. {blk['name']}"
            c.para(title, size=13, bold=True, rgb=INK, gap=2)
            tier = TIER_LABEL.get(blk["band"], blk["band"])
            score = f"{int(blk['fit_score'])}/100" if blk.get("fit_score") is not None else ""
            c.para(f"{tier}  {score}  {blk.get('role') or ''}", size=8.5, rgb=_tier_rgb(band), gap=3)
            board = blk.get("scoreboard") or []
            if board:
                bits = []
                for name, val in board:
                    bits.append(f"{name} {val if val is not None else '--'}")
                c.para("  ·  ".join(bits), size=9, rgb=INK, gap=4)
            for k, v in blk["fields"]:
                c.label(k, str(v).replace("**", ""), key_w=92, size=8.4, val_rgb=BODY)
            c.space(4)
        elif t == "footer":
            c.space(16)
            c.rule(rgb=INK)
            c.para(blk["text"], size=8, rgb=MUTED)
        elif t == "pagebreak":
            c._new_page()
    return c.render()


def _pdf_table(c: pdf.Canvas, cols: list[str], rows: list[list[str]]) -> None:
    weights = [0.4 if col == "#" else 1.4 if col == "Name" else 0.85 for col in cols]
    total = sum(weights)
    widths = [c.col * w / total for w in weights]
    c.space(6)
    c.need(24)
    x = c.margin
    c.y -= 10
    for col, w in zip(cols, widths):
        c.page.text(x, c.y, pdf.sanitize(col.upper())[:18], 6.4, True, MUTED)
        x += w
    c.y -= 3
    c.page.line(c.margin, c.y, c.w - c.margin, c.y, INK, 1.0)
    for row in rows:
        cells = [pdf.wrap(pdf.sanitize(str(v)), 7.6, w - 4) for v, w in zip(row, widths)]
        height = max(len(cl) for cl in cells) * 10 + 3
        c.need(height)
        top = c.y
        for j, (cl, w) in enumerate(zip(cells, widths)):
            x = c.margin + sum(widths[:j])
            yy = top
            for line in cl:
                yy -= 10
                c.page.text(x, yy, line, 7.6, j == 1, INK if j == 1 else BODY)
        c.y = top - height
    c.space(6)


def render(blocks: list[dict], fmt: str, *, title: str = "who-finder report"):
    if fmt == "md":
        return to_markdown(blocks)
    if fmt == "html":
        return to_html(blocks, title=title)
    if fmt == "pdf":
        return to_pdf(blocks)
    if fmt == "json":
        return json.dumps(blocks, ensure_ascii=False, indent=2, default=str)
    raise ValueError(f"unknown format '{fmt}'. want one of {list(FORMATS)}")


def write(blocks: list[dict], fmts: list[str], out: str, *, title: str) -> list[str]:
    from pathlib import Path
    dest = Path(out)
    dest.parent.mkdir(parents=True, exist_ok=True)
    written = []
    for fmt in fmts:
        body = render(blocks, fmt, title=title)
        path = dest.with_suffix("." + fmt)
        if fmt == "pdf":
            path.write_bytes(body)  # type: ignore[arg-type]
        else:
            path.write_text(body, encoding="utf-8")  # type: ignore[arg-type]
        written.append(str(path))
    if "html" in fmts:
        written.extend(_write_people(blocks, dest.parent / "people", title=title))
    return written


def _write_people(blocks: list[dict], folder, *, title: str) -> list[str]:
    from pathlib import Path
    people = [b for b in blocks if b.get("t") == "person"]
    if not people:
        return []
    cover = next((b for b in blocks if b.get("t") == "cover"), None)
    dest = Path(folder)
    dest.mkdir(parents=True, exist_ok=True)
    written = []
    for b in people:
        slug = re.sub(r"[^a-z0-9]+", "-", str(b.get("name") or b.get("id") or "person").lower()).strip("-")[:48]
        mini = ([cover] if cover else []) + [b]
        path = dest / f"{int(b.get('rank') or 0):02d}-{slug or 'person'}.html"
        path.write_text(to_html(mini, title=str(b.get("name") or title)), encoding="utf-8")
        written.append(str(path))
    return written
