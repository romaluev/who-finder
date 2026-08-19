"""Where keys live.

Env wins, then ~/.creator-rating/keys.json (or CREATOR_RATING_HOME/keys.json
when the test suite isolates the home). Missing keys are a thinner run.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

from . import db

ENV = {
    "brightdata": "BRIGHTDATA_API_KEY",
    "unipile": "UNIPILE_API_KEY",
    "apollo": "APOLLO_API_KEY",
    "llm": "CREATOR_RATING_LLM_KEY",
    "openai": "OPENAI_API_KEY",
    "scrapecreators": "SCRAPECREATORS_API_KEY",
    "clay": "CLAY_PUBLIC_API_KEY",
    "brave": "BRAVE_API_KEY",
}

HINTS = {
    "brightdata": "https://brightdata.com",
    "unipile": "https://www.unipile.com",
    "apollo": "https://www.apollo.io",
    "llm": "an OpenAI or compatible key",
    "scrapecreators": "https://scrapecreators.com",
    "clay": "https://app.clay.com → Settings → API keys",
    "brave": "https://brave.com/search/api/",
}

PLACEHOLDERS = frozenset({
    "", "...", "your-key", "your-key-here", "xxx", "changeme", "paste-here",
})


def keys_file() -> Path:
    return db.home() / "keys.json"


def config_file() -> Path:
    return db.home() / "config.json"


def _looks_like_key(raw: str) -> bool:
    key = (raw or "").strip()
    return bool(key) and key.lower() not in PLACEHOLDERS and len(key) >= 8


def _read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_json(path: Path, data: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    try:
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass
    return path


def read_named(name: str) -> tuple[str, str]:
    env_name = ENV.get(name, "")
    if env_name:
        env = os.environ.get(env_name, "").strip()
        if env:
            return env, "env"
    # openai is an alias for llm
    if name == "llm":
        env = os.environ.get("OPENAI_API_KEY", "").strip()
        if env:
            return env, "env"
    if name == "clay":
        env = os.environ.get("CLAY_API_KEY", "").strip()
        if env:
            return env, "env"
    stored = (_read_json(keys_file()).get(name) or "").strip()
    if _looks_like_key(stored):
        return stored, f"file:{keys_file()}"
    if name == "llm":
        stored = (_read_json(keys_file()).get("openai") or "").strip()
        if _looks_like_key(stored):
            return stored, f"file:{keys_file()}"
    return "", "missing"


def token(name: str) -> str:
    return read_named(name)[0]


def save(raw: str, name: str) -> Path:
    key = (raw or "").strip()
    if not _looks_like_key(key):
        hint = HINTS.get(name, "the vendor")
        raise ValueError(f"that does not look like a key. get one at {hint} and paste the whole thing")
    data = _read_json(keys_file())
    data[name] = key
    return _write_json(keys_file(), data)


def clear(name: str) -> bool:
    data = _read_json(keys_file())
    if name not in data:
        return False
    data.pop(name, None)
    if data:
        _write_json(keys_file(), data)
    else:
        try:
            keys_file().unlink()
        except OSError:
            pass
    return True


def read_config() -> dict:
    return _read_json(config_file())


def write_config(data: dict) -> Path:
    current = read_config()
    current.update(data)
    return _write_json(config_file(), current)


def capabilities() -> dict:
    """One line per backend. Tokens are never included."""
    out = {}
    from .collectors.public import ytdlp_bin

    for name, unlocks in (
        ("csv", "longlist from a sheet; no key"),
        ("who_finder", "roster JSON / hits; compose only"),
        ("public", "yt-dlp, RSS, DuckDuckGo / Brave — no new invoice"),
        ("clay", "table export or people search; already subscribed"),
        ("brightdata", "LinkedIn posts and counts — last resort"),
        ("unipile", "engager lists on a dedicated account"),
        ("apollo", "seed-pool and ABM match — skip if Clay is on"),
        ("llm", "post and headline classification"),
        ("scrapecreators", "who-finder video — skip if yt-dlp ran"),
        ("brave", "optional search key for the public waterfall"),
        ("pilots", "consented analytics and paid pilots"),
    ):
        if name in {"csv", "who_finder"}:
            out[name] = {"available": True, "kind": "always", "unlocks": unlocks}
            continue
        if name == "public":
            out[name] = {
                "available": True,
                "kind": "always",
                "unlocks": unlocks,
                "ytdlp": bool(ytdlp_bin()),
            }
            continue
        if name == "pilots":
            out[name] = {"available": True, "kind": "file", "unlocks": unlocks}
            continue
        tok, src = read_named(name)
        out[name] = {
            "available": bool(tok),
            "source": src,
            "unlocks": unlocks,
            "hint": HINTS.get(name, ""),
        }
    cfg = read_config()
    out["session"] = {
        "ack": bool(cfg.get("session_ack") or cfg.get("i_understand")),
        "collection_account": bool(cfg.get("collection_account")),
        "brand_account": bool(cfg.get("brand_account")),
        "dedicated": (
            bool(cfg.get("collection_account"))
            and cfg.get("collection_account") != cfg.get("brand_account")
        ),
    }
    return out
