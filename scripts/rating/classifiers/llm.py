"""Optional LLM classification. Missing key → caller keeps the rules floor."""

from __future__ import annotations

import json

from .. import auth, http

PROMPT = (
    "Classify this LinkedIn post. Return JSON only with keys: "
    "topic (string), relevance (0-1), bait (bool), ai_likelihood (0-1), "
    "safety (ok|caution|fail), language (iso639-1). "
    "Topic should be one of: AI video, Generative creative, Ad creative, "
    "Brand content, Creative production, Marketing strategy, Growth, "
    "Demand gen, LinkedIn advice, Leadership, Other.\n\nPOST:\n"
)


def available() -> bool:
    return bool(auth.token("llm"))


def classify_post(text: str, *, brief: str = "") -> dict | None:
    token = auth.token("llm")
    if not token:
        return None
    body = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": "You classify LinkedIn posts. JSON only."},
            {"role": "user", "content": PROMPT + (text or "")[:4000]},
        ],
        "temperature": 0,
    }
    try:
        data = http.post(
            "https://api.openai.com/v1/chat/completions",
            payload=body,
            headers={"Authorization": f"Bearer {token}"},
            timeout=40,
        )
    except Exception:
        return None
    try:
        content = (((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "")
        parsed = json.loads(content)
    except (TypeError, ValueError, IndexError):
        return None
    if not isinstance(parsed, dict):
        return None
    parsed["classifier"] = "llm"
    parsed["version"] = "1"
    return parsed
