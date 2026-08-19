"""Capability index. Printing Press `which` — the agent asks the engine, not SKILL.md."""

from __future__ import annotations

INDEX = (
    {
        "needles": ("health", "doctor", "key", "credit", "broken", "setup", "install"),
        "run": "doctor --agent",
        "note": "four-state: ready | skipped-unconfigured | auth-failed | error",
    },
    {
        "needles": ("probe", "smoke", "is it working"),
        "run": "doctor --probe --agent",
        "note": "spends one credit on YouTube",
    },
    {
        "needles": ("which scenario", "query type", "list scenarios"),
        "run": "scenarios --agent",
    },
    {
        "needles": ("icp", "fit rules", "scoring rules", "ideal customer", "qualify"),
        "run": "icp show --agent",
        "note": "`icp init` writes an editable template to .who-finder/icp.json",
    },
    {
        "needles": ("signal", "what signals", "hiring signal", "funded signal"),
        "run": "signals --agent",
    },
    {
        "needles": ("report", "again", "re-render", "without spending", "no credits", "recap"),
        "run": "report --status new --agent",
        "note": "rebuilds the full brief from the roster for zero credits",
    },
    {
        "needles": ("enrich", "dossier", "profile", "audience", "how big", "followers", "what do they do"),
        "run": "enrich --status new --limit 10 --agent",
        "note": "1 credit per entity; adds audience, bio, recent posts, ICP fit",
    },
    {
        "needles": ("more like", "similar", "expand", "lookalike", "who else", "employees at"),
        "run": "expand kind/platform/handle --agent",
        "note": "reuses names already inside a stored dossier — no new search",
    },
    {
        "needles": ("deep", "research", "analys", "analyze", "insight", "prioriti", "shortlist"),
        "run": 'find "BRIEF" --deep 10 --agent',
        "note": "discovery + dossiers + ICP fit + priority in one call",
    },
    {
        "needles": ("creator", "influencer", "ugc", "youtuber", "tiktoker", "who posts"),
        "run": 'find "BRIEF" --scenario creators --deep 10 --agent',
        "scenario": "creators",
    },
    {
        "needles": ("hiring", "jobs", "open role", "recruiting", "headcount"),
        "run": 'find "BRIEF" --scenario hiring --deep 10 --agent',
        "scenario": "hiring",
    },
    {
        "needles": ("journalist", "reporter", "press", "byline", "media"),
        "run": 'find "BRIEF" --scenario press --deep 10 --agent',
        "scenario": "press",
    },
    {
        "needles": (" vs ", "versus", "compare"),
        "run": 'find "A vs B" --scenario compare --deep 10 --agent',
        "scenario": "compare",
    },
    {
        "needles": ("company", "companies", "startup", "vendor", "agency", "brand"),
        "run": 'find "BRIEF" --scenario companies --deep 10 --agent',
        "scenario": "companies",
    },
    {
        "needles": ("people", "person", "founder", "operator", "expert", "linkedin"),
        "run": 'find "BRIEF" --scenario people --deep 10 --agent',
        "scenario": "people",
    },
    {
        "needles": ("export", "csv", "sheet", "handoff"),
        "run": "export --status new --out who-handoff.csv --agent",
        "note": "carries headline, audience, fit_score, fit_band, priority, signals",
    },
    {
        "needles": ("show", "this person", "this company", "detail"),
        "run": "show kind/platform/handle --agent",
    },
    {
        "needles": ("mark", "messaged", "skip", "contacted", "customer"),
        "run": "mark kind/platform/handle --status outreached --agent",
    },
    {
        "needles": ("import", "seed", "skip list"),
        "run": "import skip.csv --agent",
    },
)


def resolve(text: str) -> dict:
    t = f" {(text or '').lower()} "
    for item in INDEX:
        if any(n in t or n in (text or "").lower() for n in item["needles"]):
            return {**item, "matched": True}
    return {
        "matched": False,
        "run": 'find "BRIEF" --deep 10 --agent',
        "scenario": "people",
        "note": "default: detect scenario from the brief, enrich the top 10",
    }
