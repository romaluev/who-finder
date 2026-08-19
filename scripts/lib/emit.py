"""Engine-owned brief. The agent pastes `table`; it does not redesign it.

last30days puts the badge in the engine for the same reason: the model
will invent a blog post if you let it.
"""

from __future__ import annotations

import textwrap

from . import __version__, contacts
from .scenarios import SCENARIOS
from .util import human, to_int

BAND_MARK = {"strong": "STRONG", "possible": "MAYBE ", "weak": "weak  ", "off": "off   ", "unknown": "?     "}


def welcome(*, invocation: str, python: str, key_set: bool, db_path: str, db_exists: bool) -> str:
    """First contact. Shown for no arguments, `help`, and unrecognised commands.

    The default argparse error lists nineteen subcommands and says a required
    argument is missing, which tells someone who has never used this what they
    typed wrong but not what to type instead. This answers the second question.
    """
    key_lines = (
        ["  2. A key     set — you're ready."]
        if key_set else
        ["  2. A key     not set yet. Get one at https://scrapecreators.com,",
         f"               then paste:  {invocation} setup YOUR_KEY"]
    )
    return "\n".join([
        "who-finder — describe who you're looking for, get back a shortlist",
        "of real people with a page on each, written up as a document you can send.",
        "",
        "You don't learn commands for this. If it's set up with your AI assistant,",
        "you just ask, in plain English:",
        "",
        '    "Find me the top 10 people building AI video tools, as a PDF."',
        "",
        "------------------------------------------------------------------------",
        "Just cloned this? Three steps, no programming:",
        "",
        f"  1. Python    {python}  — already here, good.",
        *key_lines,
        "",
        "See it work before you spend anything — free, no key needed:",
        f'    {invocation} find "founders of AI video tools" --deep 10 --dry-run',
        "",
        "That prints the exact searches it would run and what they'd cost.",
        "",
        "Once your key is set:",
        f"    {invocation} doctor",
        "        confirm the key works and see your balance",
        f'    {invocation} find "founders of AI video tools" --deep 10 --format md,html --out shortlist',
        "        the real thing, written up as a document you can send",
        "",
        "Guides (in this folder):  docs/start.md   docs/ask.md   docs/key.md",
        "",
        "It never sends email, never logs into LinkedIn, and never invents a name",
        "or an inbox. Emails in the report are ones they published themselves.",
        f"Stuck? {invocation} help lists everything.",
    ])


def doctor_card(r: dict) -> str:
    """Human-readable health. The JSON form is for agents; this is for people."""
    state = r.get("state", "unknown")
    headline = {
        "ready": "READY — everything works",
        "skipped-unconfigured": "NOT SET UP — no API key yet",
        "auth-failed": "KEY REJECTED — the API did not accept this key",
        "error": "PROBLEM — see below",
    }.get(state, state)
    lines = [f"who-finder v{__version__}  ·  {headline}", ""]

    if r.get("key") == "missing":
        lines += [
            "  API key    missing",
            "             get one at https://scrapecreators.com",
            "             then:  who-finder setup YOUR_KEY",
        ]
    else:
        src = r.get("key_source") or "set"
        lines.append(f"  API key    present ({src})")
    if r.get("credits") is not None:
        lines.append(f"  credits    {r['credits']} left")
    if r.get("credits_error"):
        lines.append(f"  credits    could not read — {r['credits_error']}")

    lines += [
        f"  roster     {r.get('db')}" + ("" if r.get("db_exists") else "   (not created yet)"),
        f"  fit rules  " + (str(r.get("icp")) if r.get("icp_exists") else "built-in generic rules"),
    ]
    goat = r.get("contact_goat") or {}
    if goat.get("installed"):
        lines.append(f"  contact-goat  installed at {goat.get('bin')}  (optional — work-email lookup)")
    else:
        lines.append("  contact-goat  not installed  (optional — we still print emails they published)")
    probe = r.get("probe")
    if probe:
        lines.append(
            f"  live test  {probe.get('youtube_hits')} results from YouTube — the whole path works"
            if probe.get("ok") else f"  live test  FAILED — {probe.get('error')}"
        )

    lines.append("")
    if state == "ready":
        lines += [
            "Next:",
            '  find "founders of AI video tools" --deep 10 --dry-run   preview, free',
            '  find "founders of AI video tools" --deep 10             run it',
        ]
    elif state == "skipped-unconfigured":
        lines += [
            "You can still preview searches without a key:",
            '  find "founders of AI video tools" --deep 10 --dry-run',
            "",
            "When you have a key:",
            "  setup YOUR_KEY",
        ]
    else:
        lines.append(f"Fix: {r.get('fix') or 'check the key and try again'}")
    return "\n".join(lines)


def plan_card(plan, est: dict, *, depth: int, icp_name: str) -> str:
    """What `--dry-run` shows: the exact queries and the ceiling on cost.

    Printed before anything is spent so the operator approves a real number
    instead of agreeing to "a search".
    """
    lines = [
        f"who-finder v{__version__}  DRY RUN — nothing spent, nothing stored",
        f"scenario: {plan.scenario} ({plan.kind})   topic: {plan.topic}"
        + (f"   vs: {plan.side_b}" if plan.side_b else ""),
        f"icp:      {icp_name}",
        "",
        f"PLANNED QUERIES ({len(plan.steps)})",
    ]
    for i, s in enumerate(plan.steps, 1):
        side = f" [side {s.side}]" if s.side else ""
        lines.append(f" {i:>2}. {s.source:<19} {s.label:<12}{side}")
        lines.extend(_wrap(s.query, bullet="     q: ", width=96))
    lines.append("")
    lines.append("COST CEILING")
    lines.append(f"  discovery      {est['discovery']:>3} credits (1 per query above)")
    if depth:
        lines.append(f"  enrichment  <= {est['enrichment_max']:>3} credits (1 per profile, 0 on a cache hit)")
    lines.append(f"  total       <= {est['total_max']:>3} credits")
    lines.append("")
    lines.append("Re-run without --dry-run to execute. Add --max-credits N to hard-cap it.")
    if plan.note:
        lines.append(f"note: {plan.note}")
    return "\n".join(lines)


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

    if ins.get("notices"):
        lines.append("")
        lines.append("EASY TO MISS")
        for n in ins["notices"][:8]:
            lines.extend(_wrap(n, bullet="- "))

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
    reach = contacts.reach_line(d.get("contacts") or contacts.harvest(d))
    if reach:
        out.extend(_prefixed("reach ", reach))
    return out


def _prefixed(label: str, text: str, width: int = 88) -> list[str]:
    wrapped = textwrap.wrap(text, width=width) or [""]
    first = f"      {label} {wrapped[0]}"
    rest = [" " * (7 + len(label)) + w for w in wrapped[1:]]
    return [first] + rest


def contacts_card(people: list[dict], *, goat: str | None = None) -> str:
    """The `contacts` command: public addresses only, named as such."""
    lines = [
        f"who-finder v{__version__}  PUBLIC CONTACTS — only what they published",
        "Nothing here is a guessed work email. Those are a different tool.",
        "",
    ]
    if not people:
        lines.append("(no stored profiles to harvest)")
        return "\n".join(lines)
    n_email = sum(1 for p in people if p.get("emails"))
    n_meet = sum(1 for p in people if p.get("takes_meetings"))
    lines.append(f"{len(people)} people  ·  {n_email} published an email  ·  {n_meet} book meetings in public")
    lines.append("")
    for i, p in enumerate(people, 1):
        lines.append(f"{i:>2}. {p.get('name') or p.get('id')}")
        if p.get("emails"):
            lines.append(f"      email  {', '.join(p['emails'])}")
        if p.get("reach"):
            lines.append(f"      reach  {p['reach']}")
        elif p.get("links"):
            shown = []
            for l in p["links"][:4]:
                if isinstance(l, dict):
                    shown.append(l.get("url") or "")
                else:
                    shown.append(str(l))
            shown = [s for s in shown if s]
            if shown:
                lines.append(f"      links  {' · '.join(shown)}")
        if p.get("id"):
            lines.append(f"      id     {p['id']}")
    if goat:
        lines += [
            "",
            "contact-goat is installed. To look up a work email the profile did not",
            "publish, ask first — it spends other credits — then:",
            f"  {goat} doctor --agent",
            f'  {goat} dossier "NAME" --company "CO" --agent',
        ]
    else:
        lines += [
            "",
            "No contact-goat on PATH. Install it only if you want guessed work emails",
            "or warm intros; this command will keep printing what they published.",
        ]
    return "\n".join(lines)


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
    c = d.get("contacts") or contacts.harvest({**payload, **d})
    if c.get("emails"):
        lines.append(f"  email     {', '.join(c['emails'])}")
    if c.get("takes_meetings"):
        cal = next((l["url"] for l in c.get("links") or []
                    if l.get("kind") in {"calendly", "calendar"}), "")
        lines.append(f"  meetings  {cal or 'yes'}")
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
