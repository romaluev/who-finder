"""Engine-owned brief. The agent pastes `table`; it does not redesign it."""

from __future__ import annotations

from . import __version__
from .util import human, money


def welcome(*, invocation: str, python: str) -> str:
    return "\n".join([
        "creator-rating — rate LinkedIn creators on three graphs and put a",
        "price ceiling on the ones worth buying. Works with nothing connected.",
        "",
        "You don't learn commands for this. If it's set up with your AI assistant,",
        "you just ask, in plain English:",
        "",
        '    "Rate these creators from this CSV and write it up as a PDF."',
        "",
        "------------------------------------------------------------------------",
        "Just cloned this? Three steps, no programming:",
        "",
        f"  1. Python    {python}  — already here, good.",
        "  2. A sheet    optional. A CSV of names and LinkedIn URLs is enough",
        "               for a rung-0 report (interest graph from profile text).",
        "  3. Keys       optional. Clay (already paid) first; Bright Data last.",
        "               See docs/economy.md for what we spend and skip.",
        "",
        "See it work — free, no key needed:",
        f"    {invocation} doctor",
        f"    {invocation} ingest --csv creators.csv",
        f"    {invocation} rate --format md --out shortlist",
        "",
        "Guides:  docs/start.md  docs/economy.md  docs/no-keys.md  docs/connect.md  docs/ask.md",
        "",
        "It never messages engagers, never uses the brand's LinkedIn login,",
        "and never invents a name or a number.",
        f"Stuck? {invocation} help lists everything.",
    ])


def doctor_card(r: dict) -> str:
    rung = r.get("rung", 0)
    headline = {
        0: "READY — thinner path (profile text only, no price)",
        1: "READY — video engagement (yt-dlp / who-finder)",
        2: "READY — LinkedIn posts (counts exist)",
        3: "READY — social graph (engager source connected)",
        4: "READY — calibrated (consented analytics / pilots)",
    }.get(rung, f"rung {rung}")
    lines = [f"creator-rating v{__version__}  ·  {headline}", ""]
    lines.append(f"  depth         {r.get('label') or f'rung {rung}'}")
    lines.append(f"  store         {r.get('db')}" + ("" if r.get("db_exists") else "   (not created yet)"))
    lines.append(f"  ICP           {r.get('icp') or 'built-in marketing-buyers'}")
    backends = r.get("backends") or {}
    pub = backends.get("public") or {}
    ytdlp = "yt-dlp on PATH" if pub.get("ytdlp") else "yt-dlp not installed"
    lines.append(f"  public        always  — {ytdlp}")
    for name in ("clay", "brightdata", "unipile", "apollo", "llm", "scrapecreators"):
        info = backends.get(name) or {}
        if info.get("available"):
            lines.append(f"  {name:<13} present ({info.get('source') or 'set'})")
        else:
            lines.append(f"  {name:<13} not set  — {info.get('unlocks') or ''}  {info.get('hint') or ''}")
    for line in r.get("economy") or []:
        lines.append(f"  spend         {line}")
    sess = backends.get("session") or {}
    if sess.get("dedicated") and sess.get("ack"):
        lines.append("  session       dedicated account acknowledged")
    elif sess.get("collection_account"):
        lines.append("  session       account named, --i-understand not recorded")
    else:
        lines.append("  session       no dedicated account (engager collection refused)")
    nxt = r.get("next") or []
    if nxt:
        lines += ["", "  what to connect next:", f"    {nxt[0]['line']}", f"    guide: {nxt[0].get('guide')}"]
    else:
        lines += ["", "  what to connect next: nothing — or add consented analytics to calibrate k"]
    lines += ["", "  guides        docs/start.md  docs/economy.md  docs/connect.md  docs/no-keys.md"]
    return "\n".join(lines)


def table(rows: list[dict], *, preset: str, rung_label: str, n: int) -> str:
    lines = [
        f"who-finder rate  preset={preset}  {rung_label}  n={n}",
        "",
    ]
    for i, r in enumerate(rows, start=1):
        name = r.get("name") or r.get("handle") or r.get("id")
        tier = r.get("tier") or "?"
        score = r.get("creator_score")
        sc = f"{int(score):3d}" if score is not None else "  ?"
        conf = r.get("confidence") or 0
        used = r.get("used_points") or 0
        pr = r.get("price") or {}
        price = money(pr.get("fair")) if pr else "no price"
        lines.append(
            f"{i:2d}. [{tier}] {sc}  {name}  "
            f"S{_n(r.get('social'))} E{_n(r.get('engagement'))} I{_n(r.get('interest'))}  "
            f"{price}  conf {conf:.0%} ({used:.0f}/100)  {r.get('next_action') or ''}"
        )
        if r.get("headline"):
            lines.append(f"    {r['headline'][:90]}")
    return "\n".join(lines)


def _n(v) -> str:
    if v is None:
        return "—"
    try:
        return f"{int(round(float(v))):2d}"
    except (TypeError, ValueError):
        return "—"
