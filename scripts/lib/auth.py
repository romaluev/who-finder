"""Where the API key lives.

`export SCRAPECREATORS_API_KEY=...` works, and is forgotten the next time the
terminal opens — the usual reason a clone 'stopped working overnight'. A key
file next to the roster survives that. Env still wins, so CI and agents that
already inject the variable are unchanged.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

from . import db

ENV_KEY = "SCRAPECREATORS_API_KEY"

PLACEHOLDERS = frozenset({
    "", "...", "your-key", "your-key-here", "xxx", "changeme", "paste-here",
})


def key_file() -> Path:
    """Where `setup` writes. Follows WHO_FINDER_HOME so tests stay isolated.

    No WHO_FINDER_HOME → `~/.who-finder/key`, so a key set once works from
    every directory. With WHO_FINDER_HOME set, we never read the real home
    file — a developer key must not leak into the test suite.
    """
    if os.environ.get("WHO_FINDER_HOME"):
        return db.home() / "key"
    return Path.home() / ".who-finder" / "key"


def candidates() -> list[Path]:
    """Places we will read, in order, after the environment variable."""
    seen, out = set(), []
    for path in (key_file(), db.home() / "key"):
        resolved = path.expanduser()
        if resolved in seen:
            continue
        seen.add(resolved)
        out.append(resolved)
    return out


def read() -> tuple[str, str]:
    """Return (token, source). source is `env`, `file:<path>`, or `missing`."""
    env = os.environ.get(ENV_KEY, "").strip()
    if env:
        return env, "env"
    for path in candidates():
        try:
            raw = path.read_text(encoding="utf-8").strip().splitlines()[0].strip()
        except (OSError, IndexError):
            continue
        if raw and raw.lower() not in PLACEHOLDERS:
            return raw, f"file:{path}"
    return "", "missing"


def token() -> str:
    return read()[0]


def save(raw: str) -> Path:
    key = (raw or "").strip()
    if key.lower() in PLACEHOLDERS or len(key) < 8:
        raise ValueError(
            "that does not look like a key. get one at https://scrapecreators.com "
            "and paste the whole thing"
        )
    path = key_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(key + "\n", encoding="utf-8")
    try:
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass
    return path


def clear() -> bool:
    path = key_file()
    if not path.exists():
        return False
    path.unlink()
    return True
