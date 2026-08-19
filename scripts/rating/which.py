"""Capability index. The agent asks the engine, not SKILL.md."""

from __future__ import annotations

INDEX = (
    {
        "needles": ("setup", "install", "api key", "save key", "how do i start",
                    "getting started", "first run", "save a key"),
        "run": "setup",
        "note": "saves a named key (clay|brightdata|unipile|apollo|llm). "
                "guides: docs/start.md docs/economy.md docs/connect.md",
    },
    {
        "needles": ("health", "doctor", "broken", "what is connected", "rung"),
        "run": "doctor --agent",
        "note": "rungs 0–4. thin is proceed-with-caveat. docs/no-keys.md",
    },
    {
        "needles": ("what can this do", "capabilities", "commands", "what flags",
                    "exit code", "introspect"),
        "run": "agent-context --agent",
    },
    {
        "needles": ("ingest", "import", "longlist", "who-finder", "nominate",
                    "add creator", "load sheet", "load csv"),
        "run": "ingest --csv PATH --agent",
        "note": "also: --clay export.csv · --who-finder envelope.json · --search 'topic' · --url URL",
    },
    {
        "needles": ("rate", "score", "rank", "tier", "shortlist"),
        "run": "rate --agent",
        "note": "classify + score + price whatever is already stored. works at rung 0",
    },
    {
        "needles": ("report", "pdf", "document", "write it up", "markdown", "html"),
        "run": "report --format md,pdf --out shortlist --agent",
        "note": "one file: summary then a page per creator",
    },
    {
        "needles": ("price", "fair", "walk-away", "cpm", "what should i pay"),
        "run": "rate --agent --select results.creators.price",
        "note": "no price without posts. assumptions print on the same card",
    },
    {
        "needles": ("portfolio", "budget", "which ones to buy", "overlap"),
        "run": "portfolio --budget 5000 --agent",
    },
    {
        "needles": ("calibrat", "pilot", "consented", "impressions actual", "refit"),
        "run": "pilot --creator ID --impressions N --agent",
        "note": "then calibrate. estimated→calibrated at R²≥0.6 over ≥30 creators. docs/connect.md#consented-analytics",
    },
    {
        "needles": ("engager", "reactors", "session", "unipile", "deep collect"),
        "run": "collect --deep --i-understand --agent",
        "note": "dedicated account only. docs/connect.md#engager-source",
    },
    {
        "needles": ("export", "csv handoff", "sheet out"),
        "run": "export --out handoff.csv --agent",
        "note": "creator rows only. physically cannot emit engager PII",
    },
    {
        "needles": ("prune", "forget engagers", "90 day", "hygiene"),
        "run": "prune --agent",
        "note": "drops raw engager rows older than 90 days; keeps aggregates",
    },
    {
        "needles": ("no key", "nothing connected", "thin", "without tools"),
        "run": "doctor --agent",
        "note": "rung 0 is a real report. docs/no-keys.md",
    },
    {
        "needles": ("clay", "already pay", "don't spend", "cheap", "economy",
                    "scrapecreators", "bright data last"),
        "run": "doctor --agent",
        "note": "Clay first, public scripts free, Bright Data last. docs/economy.md",
    },
    {
        "needles": ("icp", "fit rules", "brief"),
        "run": "icp show --agent",
    },
    {
        "needles": ("surprised", "feedback", "bug"),
        "run": 'feedback "what surprised you" --agent',
    },
)


def resolve(text: str) -> dict:
    t = f" {(text or '').lower()} "
    for item in INDEX:
        if any(n in t or n in (text or "").lower() for n in item["needles"]):
            return {**item, "matched": True}
    return {
        "matched": False,
        "run": "rate --agent",
        "note": "default: score whatever is already stored. ingest a CSV first if the store is empty",
    }
