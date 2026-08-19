"""Rule-based floor. Always available, no key, no network."""

from __future__ import annotations

import json
import re
from pathlib import Path

BAIT = re.compile(
    r"\b(comment\s+\w+|comment below|repost if|tag someone|tag a|like if|"
    r"drop a|thoughts\?|agree\?|yes or no|poll\b|link in comments)\b",
    re.I,
)

GENERIC = re.compile(
    r"^(great (post|insights?|share|content|stuff)!?|so true!?|this\.?|"
    r"love this!?|couldn't agree more.?|well said.?|100%!?|"
    r"[\U0001F300-\U0001FAFF\u2600-\u27BF]+)$",
    re.I,
)

AI_COMMENT = re.compile(
    r"great insights?.{0,40}couldn't agree more|this (really )?resonates|"
    r"such a (valuable|powerful) (reminder|perspective)|"
    r"thanks for sharing.{0,20}(your|this) (perspective|insight)",
    re.I,
)

PROFANITY = re.compile(
    r"\b(fuck|shit|bitch|asshole|cunt|nigger|faggot)\b",
    re.I,
)

POLITICS = re.compile(
    r"\b(trump|biden|maga|democrat|republican|vote blue|vote red|"
    r"genocide|from the river)\b",
    re.I,
)

HATE = re.compile(
    r"\b(hate speech|kill (all|them)|subhuman)\b",
    re.I,
)

LUNATIC = re.compile(
    r"\b(i'm 1%|linkedinfied|hustle porn|rise and grind.{0,10}bro)\b",
    re.I,
)

EN = frozenset("the and for that with this have from they will your not are but".split())
DE = frozenset("und der die das ist nicht ein eine mit von den dem".split())
FR = frozenset("les des une est pas dans pour que qui avec".split())
ES = frozenset("los las una del que con por para esta".split())
NL = frozenset("het een van voor niet met zijn naar".split())

LANG_PROFILES = {"en": EN, "de": DE, "fr": FR, "es": ES, "nl": NL}

AI_POST = re.compile(
    r"\b(in today's rapidly evolving|delve into|in the realm of|"
    r"it's important to note|a testament to|landscape of)\b",
    re.I,
)


def _taxonomy() -> dict:
    path = Path(__file__).resolve().parents[3] / "config" / "taxonomy.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"topics": {}, "brief_terms": []}


def match_topic(text: str, taxonomy: dict | None = None) -> tuple[str, list[str]]:
    tax = taxonomy or _taxonomy()
    blob = (text or "").lower()
    hits = []
    for topic, kws in (tax.get("topics") or {}).items():
        if topic == "Other":
            continue
        if any(k in blob for k in kws):
            hits.append(topic)
    if not hits:
        return "Other", []
    return hits[0], hits[1:]


def relevance_to_brief(text: str, brief: str = "", taxonomy: dict | None = None) -> float:
    tax = taxonomy or _taxonomy()
    terms = [t.lower() for t in (tax.get("brief_terms") or [])]
    if brief:
        terms += [w for w in re.findall(r"[a-z0-9+#-]{3,}", brief.lower())]
    blob = (text or "").lower()
    if not terms:
        return 0.0
    hits = sum(1 for t in set(terms) if t in blob)
    return min(1.0, hits / max(3, min(len(set(terms)), 8)))


def is_bait(text: str) -> bool:
    return bool(BAIT.search(text or ""))


def is_generic_comment(text: str) -> bool:
    s = (text or "").strip()
    if not s:
        return True
    if len(s.split()) <= 2 and not re.search(r"[?]", s):
        return True
    return bool(GENERIC.match(s))


def is_ai_comment(text: str) -> bool:
    return bool(AI_COMMENT.search(text or ""))


def is_ai_post(text: str) -> float:
    if AI_POST.search(text or ""):
        return 0.7
    return 0.0


def brand_safety(text: str) -> str:
    s = text or ""
    if HATE.search(s) or PROFANITY.search(s):
        return "fail"
    if POLITICS.search(s) or LUNATIC.search(s):
        return "caution"
    return "ok"


def language_of(text: str) -> str:
    words = re.findall(r"[a-zA-ZÀ-ÿ']+", (text or "").lower())
    if len(words) < 4:
        return "en"
    best, score = "en", 0
    for lang, stops in LANG_PROFILES.items():
        n = sum(1 for w in words if w in stops)
        if n > score:
            best, score = lang, n
    return best


def classify_post(text: str, *, brief: str = "", taxonomy: dict | None = None) -> dict:
    topic, secondary = match_topic(text, taxonomy)
    return {
        "topic": topic,
        "secondary": secondary,
        "relevance": relevance_to_brief(text, brief=brief, taxonomy=taxonomy),
        "bait": is_bait(text),
        "ai_likelihood": is_ai_post(text),
        "safety": brand_safety(text),
        "language": language_of(text),
        "generic": False,
        "classifier": "rules",
        "version": "1",
    }


def classify_comment(text: str) -> dict:
    return {
        "generic": is_generic_comment(text),
        "ai_flag": is_ai_comment(text),
        "word_count": len((text or "").split()),
    }


def classify_headline_topics(text: str, about: str = "", brief: str = "") -> dict:
    blob = f"{text or ''} {about or ''}"
    topic, secondary = match_topic(blob)
    return {
        "topic": topic,
        "secondary": secondary,
        "relevance": relevance_to_brief(blob, brief=brief),
        "headline_alignment": relevance_to_brief(blob, brief=brief),
    }
