"""Agent-mediated batch. Engine emits work; returned JSON is schema-validated."""

from __future__ import annotations

import json
from pathlib import Path

SAFETY = frozenset({"ok", "caution", "fail"})


def emit_batch(posts: list[dict], path: str | Path) -> Path:
    work = []
    for p in posts:
        work.append({
            "post_id": p.get("id") or p.get("post_id") or "",
            "text": (p.get("text") or "")[:1500],
            "topic": None,
            "relevance": None,
            "bait": None,
            "ai_likelihood": None,
            "safety": None,
            "language": None,
        })
    dest = Path(path).expanduser()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps({"items": work}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return dest


def validate_item(raw: dict) -> dict | None:
    if not isinstance(raw, dict):
        return None
    pid = str(raw.get("post_id") or "").strip()
    if not pid:
        return None
    try:
        relevance = float(raw["relevance"]) if raw.get("relevance") is not None else None
    except (TypeError, ValueError):
        return None
    safety = str(raw.get("safety") or "ok").lower()
    if safety not in SAFETY:
        return None
    try:
        ai = float(raw["ai_likelihood"]) if raw.get("ai_likelihood") is not None else None
    except (TypeError, ValueError):
        ai = None
    return {
        "post_id": pid,
        "topic": str(raw.get("topic") or "Other"),
        "relevance": relevance,
        "bait": bool(raw.get("bait")),
        "ai_likelihood": ai,
        "safety": safety,
        "language": str(raw.get("language") or "en"),
        "classifier": "agent",
        "version": "1",
    }


def apply_batch(path: str | Path) -> list[dict]:
    data = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    items = data.get("items") if isinstance(data, dict) else data
    out = []
    for raw in items or []:
        item = validate_item(raw)
        if item:
            out.append(item)
    return out
