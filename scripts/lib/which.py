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
        "needles": ("what can this do", "capabilities", "commands", "what flags", "how do i use",
                    "exit code", "introspect"),
        "run": "agent-context --agent",
        "note": "the whole CLI described from live constants — commands, costs, codes, paths",
    },
    {
        "needles": ("how much", "cost", "credits", "price", "expensive", "budget", "preview",
                    "before running", "estimate", "dry run"),
        "run": 'find "BRIEF" --deep 10 --dry-run --agent',
        "note": "prints the exact queries and the credit ceiling; spends nothing, needs no key",
    },
    {
        "needles": ("cap", "limit spend", "max credits", "do not overspend"),
        "run": 'find "BRIEF" --deep 10 --max-credits 20 --agent',
        "note": "exits 8 before the first request if the plan would cost more",
    },
    {
        "needles": ("too much output", "smaller", "fewer fields", "context", "just the ids",
                    "trim", "select"),
        "run": 'find "BRIEF" --deep 10 --agent --select results.entities.id,results.entities.priority',
        "note": "dotted paths, element-wise over lists; meta and error always survive",
    },
    {
        "needles": ("report", "pdf", "document", "write it up", "writeup", "share with",
                    "send to", "forward", "deck", "one pager", "markdown file", "html"),
        "run": 'find "BRIEF" --deep 10 --format md,pdf --out ~/Desktop/shortlist --agent',
        "note": "md | html | pdf | json, comma-separated. the pdf needs nothing installed; "
                "html is the best-looking and prints to a better pdf from a browser",
    },
    {
        "needles": ("more", "next ten", "another batch", "keep going", "show me more",
                    "beyond the top", "page", "offset", "rest of them"),
        "run": "more --offset 10 --limit 10 --agent",
        "note": "continues down the ranking already discovered. enrichment only, no new "
                "search. use `report --offset N` for a free re-cut of what is already enriched",
    },
    {
        "needles": ("synonym", "other words", "rephrase", "reframe", "different wording",
                    "broaden", "not finding anyone", "too narrow", "framing"),
        "run": 'find "BRIEF" --frames 4 --frame "the field\'s other name for it" --agent',
        "note": "engine derives literal/exact/broad; you supply the vocabulary it cannot know. "
                "one extra search per frame",
    },
    {
        "needles": ("save to file", "write to", "webhook", "deliver", "pipe", "send output"),
        "run": "export --status new --deliver file:handoff.csv --agent",
        "note": "sinks: stdout | file:<path> | webhook:<url>",
    },
    {
        "needles": ("same flags", "every time", "reuse", "profile", "saved settings", "scheduled"),
        "run": "profile save nightly --set deep=10 --set scenario=people",
        "note": "then `--profile nightly find \"BRIEF\"`; explicit flags still win",
    },
    {
        "needles": ("surprised", "feedback", "bug", "wrong", "report an issue"),
        "run": 'feedback "what surprised you" --agent',
        "note": "appends to <home>/feedback.jsonl; never transmitted",
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
