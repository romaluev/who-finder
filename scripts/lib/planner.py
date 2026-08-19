"""Intent + query plan. Lives in the engine so the agent cannot skip it.

Named failure this exists to prevent: the agent treating a sentence as a
single Google query, or mixing four platforms because they are available.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .scenarios import (
    COMPANY_WORDS,
    DETECT_ORDER,
    PERSON_WORDS,
    SCENARIOS,
)

FILLER = {
    "a", "an", "the", "find", "me", "us", "our", "we", "please", "who",
    "about", "for", "to", "and", "or", "new", "some", "any", "looking",
    "can", "could", "should", "want", "get", "make", "list", "of",
    "search", "deep", "give", "names", "are", "is", "in", "on", "with",
    "that", "this", "those", "these", "them",
}

SCENARIO_STRIP = {
    "people", "person", "creators", "creator", "influencer", "influencers",
    "companies", "company", "startups", "startup", "journalists", "journalist",
    "hiring", "jobs", "job", "press", "media", "vendors", "vendor",
    "reporters", "reporter", "operators", "operator", "founders", "founder",
    "experts", "expert", "profiles", "agencies", "agency", "brands", "brand",
    "studios", "studio", "ugc", "youtuber", "tiktoker", "coverage", "byline",
    "recruiting", "headcount", "careers", "outlet", "compare",
}


@dataclass
class Step:
    source: str
    query: str
    label: str
    weight: float = 1.0
    side: str = ""  # "a" | "b" | "" for compare


@dataclass
class Plan:
    scenario: str
    kind: str
    topic: str
    steps: list[Step] = field(default_factory=list)
    side_b: str | None = None
    note: str = ""

    def as_dict(self) -> dict:
        return {
            "scenario": self.scenario,
            "kind": self.kind,
            "topic": self.topic,
            "side_b": self.side_b,
            "note": self.note,
            "steps": [
                {
                    "source": s.source,
                    "query": s.query,
                    "label": s.label,
                    "weight": s.weight,
                    "side": s.side,
                }
                for s in self.steps
            ],
        }


def _tokens(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9+#._-]+", text.lower())


def core_topic(brief: str) -> str:
    quoted = re.findall(r'"([^"]+)"', brief)
    if quoted:
        return quoted[0].strip()
    toks = [t for t in _tokens(brief) if t not in FILLER and t not in SCENARIO_STRIP]
    if not toks:
        toks = [t for t in _tokens(brief) if t not in FILLER]
    return " ".join(toks[:8]).strip() or brief.strip()


def detect_scenario(brief: str, forced: str | None = None) -> str:
    if forced and forced in SCENARIOS:
        return forced
    t = f" {brief.lower()} "
    if re.search(r"\s+vs\.?\s+|\s+versus\s+", t) or "compare " in t:
        return "compare"
    hits: list[str] = []
    for name in DETECT_ORDER:
        if name == "compare":
            continue
        for trig in SCENARIOS[name]["triggers"]:
            if trig in t or trig in brief.lower():
                hits.append(name)
                break
    if not hits:
        return "people"
    # Person-words beat company-words: "people at AI video companies" is people.
    toks = set(_tokens(brief))
    if "companies" in hits and "people" in hits:
        if toks & PERSON_WORDS:
            hits = [h for h in hits if h != "companies"]
        elif toks & COMPANY_WORDS:
            hits = [h for h in hits if h != "people"]
    for name in DETECT_ORDER:
        if name in hits:
            return name
    return hits[0]


def split_compare(brief: str) -> tuple[str, str]:
    parts = re.split(r"\s+vs\.?\s+|\s+versus\s+", brief, maxsplit=1, flags=re.I)
    if len(parts) != 2:
        return core_topic(brief), ""
    return core_topic(parts[0]), core_topic(parts[1])


def _render(template: str, topic: str) -> str:
    return re.sub(r"\s+", " ", template.replace("{topic}", topic)).strip()


def _angles_for(scenario: str, sources: list[str] | None) -> list[dict]:
    spec = SCENARIOS[scenario]
    angles = list(spec["angles"])
    if sources:
        wanted = set(sources)
        angles = [a for a in angles if a["source"] in wanted]
        have = {a["source"] for a in angles}
        for src in sources:
            if src not in have:
                angles.append(
                    {
                        "source": src,
                        "template": _fallback_query(src, "{topic}", scenario),
                        "label": src,
                        "weight": 0.6,
                    }
                )
    return angles


def _fallback_query(source: str, topic_tmpl: str, scenario: str) -> str:
    # topic_tmpl is either "{topic}" or an already-rendered topic
    if source == "linkedin_people":
        return f"site:linkedin.com/in {topic_tmpl}"
    if source == "linkedin_companies":
        return f"site:linkedin.com/company {topic_tmpl}"
    if source == "linkedin_jobs":
        return f"site:linkedin.com/jobs {topic_tmpl}"
    if source == "x":
        return f"site:x.com OR site:twitter.com {topic_tmpl}"
    if source == "reddit":
        return f"site:reddit.com {topic_tmpl}"
    if source == "web":
        if scenario == "press":
            return f"{topic_tmpl} (interview OR byline OR journalist)"
        if scenario == "hiring":
            return f'{topic_tmpl} (hiring OR "open role" OR careers)'
        if scenario == "companies":
            return f"{topic_tmpl} (company OR startup) -site:linkedin.com"
        return topic_tmpl
    return topic_tmpl


def plan(brief: str, scenario: str | None = None, extra_sources: list[str] | None = None) -> Plan:
    scenario = detect_scenario(brief, scenario)
    spec = SCENARIOS[scenario]
    if scenario == "compare":
        a, b = split_compare(brief)
        p = Plan(
            scenario=scenario,
            kind=spec["kind"],
            topic=a,
            side_b=b or None,
            note="compare runs the same source set on both sides",
        )
        angles = _angles_for(scenario, extra_sources)
        for side, topic in (("a", a), ("b", b)):
            if not topic:
                continue
            for ang in angles:
                p.steps.append(
                    Step(
                        source=ang["source"],
                        query=_render(ang["template"], topic),
                        label=ang["label"],
                        weight=float(ang.get("weight") or 1.0),
                        side=side,
                    )
                )
        return _dedupe(p)

    topic = core_topic(brief)
    p = Plan(scenario=scenario, kind=spec["kind"], topic=topic)
    for ang in _angles_for(scenario, extra_sources):
        p.steps.append(
            Step(
                source=ang["source"],
                query=_render(ang["template"], topic),
                label=ang["label"],
                weight=float(ang.get("weight") or 1.0),
            )
        )
    return _dedupe(p)


def _dedupe(p: Plan) -> Plan:
    seen: set[tuple] = set()
    uniq: list[Step] = []
    for s in p.steps:
        k = (s.source, s.query.lower(), s.side)
        if k in seen:
            continue
        seen.add(k)
        uniq.append(s)
    p.steps = uniq
    return p
