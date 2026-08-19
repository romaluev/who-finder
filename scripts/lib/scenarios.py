"""Scenarios = query types. last30days has GENERAL/COMPARISON/NEWS; this skill
has who-you-are-looking-for. Creator search is one scenario, not the product.

`angles` are the engine-owned query plan. The agent does not invent Google
operators. `{topic}` is the stripped brief (planner.core_topic).
"""

from __future__ import annotations

SCENARIOS = {
    "people": {
        "kind": "person",
        "blurb": "Operators, founders, practitioners — public profiles and posts, not just video talent.",
        "default_sources": ("linkedin_people", "youtube", "x"),
        "triggers": (
            "people", "person", "founders", "founder", "operators", "operator",
            "practitioners", "experts", "expert", "profiles", "who are", "who is",
        ),
        "angles": (
            {"source": "linkedin_people", "template": "site:linkedin.com/in {topic}", "label": "li-in", "weight": 1.0},
            {"source": "linkedin_people", "template": 'site:linkedin.com/in {topic} (founder OR ceo OR "head of")', "label": "li-titles", "weight": 0.85},
            {"source": "youtube", "template": "{topic}", "label": "yt", "weight": 0.8},
            {"source": "youtube", "template": "{topic} interview", "label": "yt-talks", "weight": 0.55},
            {"source": "x", "template": "site:x.com OR site:twitter.com {topic}", "label": "x", "weight": 0.7},
        ),
        "table": ("novelty", "kind", "id", "score", "hits", "sample"),
        "score_mode": "presence",  # Google identities have no engagement
    },
    "companies": {
        "kind": "company",
        "blurb": "Companies in a space or talking about a topic (LinkedIn company pages + web).",
        "default_sources": ("linkedin_companies", "youtube", "web"),
        "triggers": (
            "company", "companies", "startup", "startups", "vendor", "vendors",
            "agency", "agencies", "brand", "brands", "studio", "studios",
        ),
        "angles": (
            {"source": "linkedin_companies", "template": "site:linkedin.com/company {topic}", "label": "li-co", "weight": 1.0},
            {"source": "web", "template": '{topic} (company OR startup) -site:linkedin.com', "label": "web-co", "weight": 0.85},
            {"source": "youtube", "template": "{topic}", "label": "yt", "weight": 0.6},
            {"source": "web", "template": '{topic} ("about us" OR careers OR "founded")', "label": "web-about", "weight": 0.5},
        ),
        "table": ("novelty", "kind", "id", "score", "hits", "sample"),
        "score_mode": "presence",
    },
    "creators": {
        "kind": "person",
        "blurb": "People publishing on-topic video/posts, ranked by engagement on matching content.",
        "default_sources": ("youtube", "tiktok"),
        "triggers": (
            "creator", "creators", "influencer", "influencers", "ugc",
            "youtuber", "tiktoker", "who posts", "who is posting",
        ),
        "angles": (
            {"source": "youtube", "template": "{topic}", "label": "yt", "weight": 1.0},
            {"source": "youtube", "template": "{topic} tutorial", "label": "yt-how", "weight": 0.7},
            {"source": "tiktok", "template": "{topic}", "label": "tt", "weight": 0.85},
        ),
        "table": ("novelty", "kind", "id", "score", "hits", "views", "sample"),
        "score_mode": "engagement",
    },
    "hiring": {
        "kind": "company",
        "blurb": "Companies hiring for a capability — public job index, not a logged-in board.",
        "default_sources": ("linkedin_jobs", "web"),
        "triggers": (
            "hiring", "hire", "job", "jobs", "open role", "open roles",
            "we're hiring", "recruiting", "headcount", "careers",
        ),
        "angles": (
            {"source": "linkedin_jobs", "template": "site:linkedin.com/jobs {topic}", "label": "li-jobs", "weight": 1.0},
            {"source": "web", "template": '{topic} (hiring OR "open role" OR careers)', "label": "web-hire", "weight": 0.85},
            {"source": "web", "template": "site:greenhouse.io OR site:lever.co OR site:ashbyhq.com {topic}", "label": "ats", "weight": 0.7},
        ),
        "table": ("novelty", "kind", "id", "score", "hits", "sample"),
        "score_mode": "presence",
    },
    "press": {
        "kind": "person",
        "blurb": "Journalists and outlets covering a topic (web + YouTube interviews).",
        "default_sources": ("web", "youtube"),
        "triggers": (
            "journalist", "journalists", "reporter", "reporters", "press",
            "byline", "coverage", "media", "podcast host", "outlet",
        ),
        "angles": (
            {"source": "web", "template": '{topic} (journalist OR reporter OR "staff writer" OR byline)', "label": "bylines", "weight": 1.0},
            {"source": "web", "template": '{topic} (interview OR "talks to" OR "spoke with")', "label": "interviews", "weight": 0.75},
            {"source": "youtube", "template": "{topic} interview", "label": "yt-int", "weight": 0.7},
            {"source": "web", "template": "site:substack.com {topic}", "label": "substack", "weight": 0.5},
        ),
        "table": ("novelty", "kind", "id", "score", "hits", "sample"),
        "score_mode": "presence",
    },
    "compare": {
        "kind": "person",
        "blurb": "Two briefs side by side. Engine runs the same source set on both sides.",
        "default_sources": ("linkedin_people", "linkedin_companies", "youtube"),
        "triggers": (" vs ", " versus ", "compare "),
        "angles": (
            {"source": "linkedin_people", "template": "site:linkedin.com/in {topic}", "label": "li-in", "weight": 1.0},
            {"source": "linkedin_companies", "template": "site:linkedin.com/company {topic}", "label": "li-co", "weight": 1.0},
            {"source": "youtube", "template": "{topic}", "label": "yt", "weight": 0.8},
        ),
        "table": ("side", "novelty", "kind", "id", "score", "hits", "sample"),
        "score_mode": "presence",
    },
}

# Precedence when several trigger lists match. compare/hiring/press/creators
# beat generic people. companies vs people is resolved in planner.detect_scenario
# (person-words win: "people at AI video companies" is people).
DETECT_ORDER = ("compare", "hiring", "press", "creators", "companies", "people")

PERSON_WORDS = frozenset({
    "people", "person", "founders", "founder", "operators", "operator",
    "practitioners", "experts", "expert", "profiles", "journalist",
    "journalists", "reporter", "reporters", "creator", "creators",
})
COMPANY_WORDS = frozenset({
    "company", "companies", "startup", "startups", "vendor", "vendors",
    "agency", "agencies", "brand", "brands", "studio", "studios",
})

SOURCES = (
    "linkedin_people",
    "linkedin_companies",
    "linkedin_jobs",
    "youtube",
    "tiktok",
    "instagram",
    "x",
    "web",
    "reddit",
)

DEFAULT_FRESHNESS = "month"
