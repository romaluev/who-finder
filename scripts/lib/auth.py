"""Where keys live.

`export SCRAPECREATORS_API_KEY=...` works, and is forgotten the next time the
terminal opens — the usual reason a clone 'stopped working overnight'. A key
file next to the roster survives that. Env still wins, so CI and agents that
already inject the variable are unchanged.

Brave is optional: `BRAVE_API_KEY` or `setup --brave KEY`. Missing
ScrapeCreators is a thinner run, not a refusal.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

from . import db

ENV_KEY = "SCRAPECREATORS_API_KEY"
ENV_BRAVE = "BRAVE_API_KEY"

PLACEHOLDERS = frozenset({
    "", "...", "your-key", "your-key-here", "xxx", "changeme", "paste-here",
})

HINTS = {
    "scrapecreators": "https://scrapecreators.com",
    "brave": "https://brave.com/search/api/",
}


def key_file() -> Path:
    """Where `setup` writes the ScrapeCreators key.

    No WHO_FINDER_HOME → `~/.who-finder/key`, so a key set once works from
    every directory. With WHO_FINDER_HOME set, we never read the real home
    file — a developer key must not leak into the test suite.
    """
    if os.environ.get("WHO_FINDER_HOME"):
        return db.home() / "key"
    return Path.home() / ".who-finder" / "key"


def keys_file() -> Path:
    return key_file().parent / "keys.json"


def candidates() -> list[Path]:
    """Places we will read the ScrapeCreators key, in order, after env."""
    seen, out = set(), []
    for path in (key_file(), db.home() / "key"):
        resolved = path.expanduser()
        if resolved in seen:
            continue
        seen.add(resolved)
        out.append(resolved)
    return out


def _read_keys_json() -> dict:
    path = keys_file()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_keys_json(data: dict) -> Path:
    path = keys_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    try:
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass
    return path


def _looks_like_key(raw: str) -> bool:
    key = (raw or "").strip()
    return bool(key) and key.lower() not in PLACEHOLDERS and len(key) >= 8


def read() -> tuple[str, str]:
    """Return (token, source) for ScrapeCreators. source is env, file:<path>, or missing."""
    return read_named("scrapecreators")


def read_named(name: str) -> tuple[str, str]:
    env_name = ENV_KEY if name == "scrapecreators" else ENV_BRAVE if name == "brave" else ""
    if env_name:
        env = os.environ.get(env_name, "").strip()
        if env:
            return env, "env"
    if name == "scrapecreators":
        for path in candidates():
            try:
                raw = path.read_text(encoding="utf-8").strip().splitlines()[0].strip()
            except (OSError, IndexError):
                continue
            if _looks_like_key(raw):
                return raw, f"file:{path}"
    stored = (_read_keys_json().get(name) or "").strip()
    if _looks_like_key(stored):
        return stored, f"file:{keys_file()}"
    return "", "missing"


def token() -> str:
    return read()[0]


def brave_token() -> str:
    return read_named("brave")[0]


def save(raw: str, name: str = "scrapecreators") -> Path:
    key = (raw or "").strip()
    if not _looks_like_key(key):
        hint = HINTS.get(name, "the vendor")
        raise ValueError(f"that does not look like a key. get one at {hint} and paste the whole thing")
    if name == "scrapecreators":
        path = key_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(key + "\n", encoding="utf-8")
        try:
            path.chmod(stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass
        data = _read_keys_json()
        data[name] = key
        _write_keys_json(data)
        return path
    data = _read_keys_json()
    data[name] = key
    return _write_keys_json(data)


def clear(name: str = "scrapecreators") -> bool:
    gone = False
    if name == "scrapecreators":
        path = key_file()
        if path.exists():
            path.unlink()
            gone = True
    data = _read_keys_json()
    if name in data:
        data.pop(name, None)
        if data:
            _write_keys_json(data)
        else:
            try:
                keys_file().unlink()
            except OSError:
                pass
        gone = True
    return gone


def capabilities() -> dict:
    """One line per backend. Tokens are never included."""
    from . import contacts, providers

    sc, sc_src = read()
    br, br_src = read_named("brave")
    ytdlp = providers.ytdlp_bin()
    l30 = providers.last30days_bin()
    goat = contacts.contact_goat_bin()
    return {
        "ddg": {"available": True, "kind": "always", "unlocks": "LinkedIn/web/X identities, no key"},
        "hn": {"available": True, "kind": "always", "unlocks": "press / who is writing about this"},
        "scrapecreators": {
            "available": bool(sc),
            "source": sc_src,
            "unlocks": "Google, YouTube, TikTok, Instagram, profile enrich",
        },
        "brave": {
            "available": bool(br),
            "source": br_src,
            "unlocks": "better web than DDG, 0 ScrapeCreators credits",
        },
        "ytdlp": {
            "available": bool(ytdlp),
            "bin": ytdlp,
            "unlocks": "YouTube search without ScrapeCreators",
        },
        "last30days": {
            "available": bool(l30),
            "bin": l30,
            "note": "compose only; never impersonate",
        },
        "contact_goat": {
            "available": bool(goat),
            "bin": goat or "",
            "note": "compose only; never impersonate",
        },
    }
