"""Engine-owned brief. The agent pastes `table`; it does not redesign it.

last30days puts the badge in the engine for the same reason: the model
will invent a blog post if you let it.
"""

from __future__ import annotations

import textwrap

from . import __version__
from .scenarios import SCENARIOS
from .util import human, to_int

BAND_MARK = {"strong": "STRONG", "possible": "MAYBE ", "weak": "weak  ", "off": "off   ", "unknown": "?     "}


def brief(
    rows: list[dict],
    dossiers: dict[str, dict],
    ins: dict,
    *,
    scenario: str,
    topic: str,
    n_new: int,
    n_known: int,
    steps: list[str],
    icp_name: str,
    enriched_n: int,
    credits: int,
    side_b: str | None = None,
    show: int = 12,
) -> str:
    """The deep report. `find --deep` and `report` both emit exactly this."""
    head = (
        f"who-finder v{__version__}  scenario={scenario}  topic={topic}"
        + (f" vs {side_b}" if side_b else "")
        + f"  new={n_new} known={n_known}"
    )
    lines = [head]
    if steps:
        lines.append("plan:     " + " | ".join(steps[:8]))
    if ins.get("coverage"):
        lines.append("coverage: " + " | ".join(ins["coverage"][:8]))
    lines.append(
        f"depth:    enriched {enriched_n}/{len(rows)}  icp={icp_name}  credits~{credits}"
    )

    lines.append("")
    lines.append("WHAT I FOUND")
    for f in ins.get("findings") or ["(nothing to summarise)"]:
        lines.extend(_wrap(f, bullet="- "))

    lines.append("")
    lines.append("WHO TO CONTACT   priority = 60% ICP fit + 25% reach + new-name bonus")
    ranked = rows[:show]
    if not ranked:
        lines.append("  (no entities)")
    for i, r in enumerate(ranked, 1):
        lines.extend(_card(i, r, dossiers.get(_ident(r), {})))

    if ins.get("gaps"):
        lines.append("")
        lines.append("GAPS")
        for g in ins["gaps"][:6]:
            lines.extend(_wrap(g, bullet="- "))
    return "\n".join(lines)


def _wrap(text: str, bullet: str = "", width: int = 96) -> list[str]:
    pad = " " * len(bullet)
    wrapped = textwrap.wrap(text, width=width) or [""]
    return [bullet + wrapped[0]] + [pad + w for w in wrapped[1:]]


def _card(i: int, r: dict, d: dict) -> list[str]:
    band = r.get("fit_band") or "unknown"
    pri = r.get("priority")
    pri_s = f"{int(pri):>3}" if pri is not None else "  -"
    aud = to_int(d.get("audience") or r.get("audience"))
    aud_s = ""
    if aud:
        unit = {"subscribers": "subs", "employees": "emp", "followers": "flw"}.get(
            d.get("audience_kind") or r.get("audience_kind") or "", ""
        )
        aud_s = f"{human(aud)} {unit}".strip()
    elif to_int(r.get("views")):
        aud_s = f"{human(to_int(r.get('views')))} views"

    out = [f"{i:>2}. {pri_s}  {BAND_MARK.get(band, band)}  {_ident(r):<40} {aud_s:>12}"]

    does = (d.get("headline") or r.get("headline") or r.get("sample") or r.get("sample_title") or "").strip()
    if does:
        src = d.get("headline_source") or ""
        tail = f"  [{src}]" if src else ""
        out.extend(_prefixed("does ", does[:150] + tail))

    reasons = r.get("fit_reasons") or []
    if reasons:
        out.extend(_prefixed("why  ", " · ".join(reasons[:4])))

    recent = (d.get("payload") or d).get("recent") or []
    if recent:
        out.extend(_prefixed("now  ", '"' + (recent[0].get("title") or "")[:120] + '"'))

    tags = [s for s in (d.get("signals") or []) if s not in {"posting", "small-audience", "mid-audience", "large-audience"}]
    if tags:
        out.extend(_prefixed("tags ", ", ".join(tags[:6])))

    url = r.get("url") or d.get("url") or r.get("sample_url") or ""
    if url:
        out.append(f"      url   {url}")
    return out


def _prefixed(label: str, text: str, width: int = 88) -> list[str]:
    wrapped = textwrap.wrap(text, width=width) or [""]
    first = f"      {label} {wrapped[0]}"
    rest = [" " * (7 + len(label)) + w for w in wrapped[1:]]
    return [first] + rest


def dossier_card(d: dict, r: dict | None = None) -> str:
    """Single-entity deep view for `show --deep`."""
    r = r or {}
    lines = [f"{d.get('id')}  {d.get('name') or ''}"]
    if d.get("headline"):
        lines.append(f"  does      {d['headline']}")
    if d.get("audience"):
        unit = {"subscribers": "subscribers", "employees": "employees", "followers": "followers"}.get(
            d.get("audience_kind", ""), ""
        )
        lines.append(f"  audience  {human(to_int(d['audience']))} {unit}".rstrip())
    if d.get("location"):
        lines.append(f"  where     {d['location']}")
    if d.get("fit_band"):
        lines.append(f"  fit       {d.get('fit_score')} {d.get('fit_band')}  (icp={d.get('icp') or 'generic'})")
    for reason in (d.get("fit_reasons") or [])[:6]:
        lines.append(f"              · {reason}")
    if d.get("signals"):
        lines.append(f"  signals   {', '.join(d['signals'])}")
    if d.get("topics"):
        lines.append(f"  topics    {', '.join(d['topics'][:10])}")
    payload = d.get("payload") or {}
    for post in (payload.get("recent") or [])[:3]:
        lines.append(f"  posted    \"{(post.get('title') or '')[:110]}\"")
    for person in (payload.get("people") or [])[:6]:
        lines.append(f"  employee  {person.get('name')} — {person.get('title')}")
    for sim in (payload.get("similar") or [])[:6]:
        lines.append(f"  similar   {sim.get('name')}  {sim.get('url')}")
    for link in (payload.get("links") or [])[:5]:
        lines.append(f"  link      {link}")
    if d.get("bio"):
        lines.extend(_wrap(d["bio"][:400], bullet="  bio       "))
    for gap in (d.get("fit_gaps") or [])[:4]:
        lines.append(f"  gap       {gap}")
    return "\n".join(lines)


def table(
    rows: list[dict],
    *,
    scenario: str,
    n_new: int,
    n_known: int,
    topic: str,
    errors: list[str],
    steps: list[str],
    side_b: str | None = None,
) -> str:
    spec = SCENARIOS.get(scenario) or {}
    cols = spec.get("table") or ("novelty", "kind", "id", "score", "hits", "sample")
    header = (
        f"who-finder v{__version__}  scenario={scenario}  topic={topic}"
        + (f" vs {side_b}" if side_b else "")
        + f"  new={n_new} known={n_known}"
    )
    lines = [header]
    if steps:
        lines.append("plan: " + " | ".join(steps[:8]))
    if errors:
        lines.append("errors: " + " | ".join(errors))

    shown = [r for r in rows if r.get("novelty") == "new"][:15]
    if scenario == "compare":
        a = [r for r in shown if "a" in (r.get("side") or "")]
        b = [r for r in shown if "b" in (r.get("side") or "")]
        rest = [r for r in shown if r not in a and r not in b]
        lines.append(_col_header(cols))
        if a:
            lines.append(f"-- side a: {topic}")
            lines.extend(_row_line(r, cols) for r in a[:8])
        if b:
            lines.append(f"-- side b: {side_b}")
            lines.extend(_row_line(r, cols) for r in b[:8])
        if rest:
            lines.append("-- unassigned")
            lines.extend(_row_line(r, cols) for r in rest[:4])
        if not shown:
            lines.append("(no new entities)")
        return "\n".join(lines)

    lines.append(_col_header(cols))
    if not shown:
        lines.append("(no new entities)")
    for r in shown:
        lines.append(_row_line(r, cols))
    return "\n".join(lines)


def _ident(r: dict) -> str:
    return f"{r.get('kind')}/{r.get('platform')}/{r.get('handle')}"


def _col_header(cols: tuple) -> str:
    parts = []
    for c in cols:
        if c == "novelty":
            parts.append("NEW")
        elif c == "kind":
            parts.append("kind")
        elif c == "id":
            parts.append("id")
        elif c == "score":
            parts.append("   score")
        elif c == "hits":
            parts.append("hits")
        elif c == "views":
            parts.append("    views")
        elif c == "side":
            parts.append("side")
        elif c == "sample":
            parts.append("sample")
        else:
            parts.append(c)
    return "  ".join(parts)


def _row_line(r: dict, cols: tuple) -> str:
    bits = []
    extra = " [compilation]" if "compilation" in (r.get("flags") or []) else ""
    for c in cols:
        if c == "novelty":
            bits.append("NEW" if r.get("novelty") == "new" else "   ")
        elif c == "kind":
            bits.append(f"{r.get('kind') or '':<7}")
        elif c == "id":
            bits.append(f"{_ident(r):<36}")
        elif c == "score":
            bits.append(f"{int(r.get('score') or 0):>8}")
        elif c == "hits":
            bits.append(f"{int(r.get('hit_count') or 0):>4}")
        elif c == "views":
            bits.append(f"{int(r.get('views') or 0):>9}")
        elif c == "side":
            bits.append(f"{r.get('side') or '':<4}")
        elif c == "sample":
            sample = (r.get("sample") or r.get("sample_title") or "")[:48]
            bits.append(sample + extra)
        else:
            bits.append(str(r.get(c) or ""))
    return "  ".join(bits)
