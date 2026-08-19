"""Classifier waterfall: rules always, optional LLM, optional agent batch."""

from __future__ import annotations

from . import agent, llm, rules

VERSION = "1"

SCHEMA = {
    "post_id": str,
    "topic": str,
    "relevance": float,
    "bait": bool,
    "ai_likelihood": float,
    "safety": str,
    "language": str,
    "generic": bool,
}


def classify_post(text: str, *, brief: str = "", taxonomy: dict | None = None) -> dict:
    """Rules floor. Callers overlay LLM / agent results when present."""
    return rules.classify_post(text, brief=brief, taxonomy=taxonomy)


def classify_comment(text: str) -> dict:
    return rules.classify_comment(text)


def classify_headline(text: str, about: str = "") -> dict:
    return rules.classify_headline_topics(text, about=about)
