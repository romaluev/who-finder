"""Agent-facing I/O: exit codes, field projection, delivery sinks, profiles, feedback.

Everything here exists to make the CLI cheap and predictable to drive from an
agent loop rather than a terminal. Two constraints shape it:

*Context is the scarce resource.* A deep run returns dossiers big enough to
crowd out the reasoning that should follow them, so `--select` lets the caller
name the handful of fields it will actually read.

*Failures must be branchable.* An agent cannot act on a stack trace. Every
non-zero exit pairs a stable numeric code with an envelope carrying a `fix`
string, so the caller can decide between retrying, asking the user for a key,
and giving up without parsing prose.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .db import home

# Stable contract. Callers branch on these, so a code never changes meaning —
# a new condition gets a new number instead.
OK = 0
E_USAGE = 2
E_NOTFOUND = 3
E_AUTH = 4
E_API = 5
E_BUDGET = 8
E_DELIVERY = 9
E_CONFIG = 10

EXIT_CODES = {
    OK: "success",
    E_USAGE: "usage error — bad arguments or an unknown source/scenario",
    E_NOTFOUND: "not found — no such entity in the roster",
    E_AUTH: "auth required — SCRAPECREATORS_API_KEY missing or rejected",
    E_API: "upstream API error — the vendor failed or returned nonsense",
    E_BUDGET: "budget refused — the plan costs more than --max-credits allows",
    E_DELIVERY: "delivery failed — the --deliver sink could not be written",
    E_CONFIG: "config error — the ICP file or roster path is unusable",
}


# --------------------------------------------------------------------------
# Envelopes
# --------------------------------------------------------------------------


def ok(results: Any, *, meta: dict | None = None, table: str = "") -> dict:
    payload: dict[str, Any] = {"meta": {"source": "who-finder", **(meta or {})}}
    if table:
        payload["table"] = table
    payload["results"] = results
    return payload


def fail(code: int, message: str, *, fix: str = "", **extra: Any) -> dict:
    """Error envelope. `fix` is the next command to run, not an apology."""
    return {
        "meta": {"source": "who-finder", "ok": False},
        "error": {
            "code": code,
            "name": EXIT_CODES.get(code, "error"),
            "message": message,
            "fix": fix,
            **extra,
        },
    }


# --------------------------------------------------------------------------
# Field projection
# --------------------------------------------------------------------------


def _descend(node: Any, parts: list[str]) -> Any:
    if not parts:
        return node
    head, rest = parts[0], parts[1:]
    if isinstance(node, list):
        # Element-wise, so `results.entities.id` reads as "the id of each
        # entity" rather than requiring an index the caller cannot know.
        out = [_descend(item, parts) for item in node]
        return [v for v in out if v is not None]
    if isinstance(node, dict):
        if head not in node:
            return None
        return _descend(node[head], rest)
    return None


def _graft(dest: dict, parts: list[str], value: Any) -> None:
    head, rest = parts[0], parts[1:]
    if not rest:
        dest[head] = value
        return
    child = dest.setdefault(head, {})
    if isinstance(child, dict):
        _graft(child, rest, value)


def select(payload: dict, spec: str | None) -> dict:
    """Keep only the named dotted paths, preserving `meta` and `error`.

    `meta` always survives: it carries the credit count and the drift state,
    and a projection that silently dropped those would let a caller mistake a
    broken run for a thin one.
    """
    if not spec:
        return payload
    paths = [p.strip() for p in spec.split(",") if p.strip()]
    if not paths:
        return payload
    out: dict[str, Any] = {"meta": payload.get("meta", {})}
    if "error" in payload:
        out["error"] = payload["error"]
    for path in paths:
        parts = path.split(".")
        value = _descend(payload, parts)
        if value is None:
            continue
        if isinstance(value, list) and not value:
            continue
        _graft(out, parts, value)
    out.setdefault("results", {})
    return out


# --------------------------------------------------------------------------
# Delivery sinks
# --------------------------------------------------------------------------


class DeliveryError(RuntimeError):
    pass


def deliver(body: str, sink: str | None, *, content_type: str = "application/json") -> str:
    """Route output to a sink. Returns a short human note about what happened.

    An empty or `stdout` sink writes nothing here and leaves printing to the
    caller, so the default path stays a plain pipe.
    """
    if not sink or sink == "stdout":
        return ""
    if sink.startswith("file:"):
        target = Path(sink[5:]).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        # tmp + rename so a reader never sees a half-written file.
        tmp = target.with_suffix(target.suffix + f".tmp{os.getpid()}")
        tmp.write_text(body, encoding="utf-8")
        tmp.replace(target)
        return str(target)
    if sink.startswith("webhook:"):
        url = sink[8:]
        req = urllib.request.Request(
            url,
            data=body.encode("utf-8"),
            headers={"Content-Type": content_type},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return f"{url} {resp.status}"
        except urllib.error.HTTPError as exc:
            raise DeliveryError(f"{url} HTTP {exc.code}") from exc
        except Exception as exc:
            raise DeliveryError(f"{url} {exc}") from exc
    raise DeliveryError(
        f"unknown sink '{sink}'. supported: stdout, file:<path>, webhook:<url>"
    )


# --------------------------------------------------------------------------
# Profiles
# --------------------------------------------------------------------------


def profiles_path() -> Path:
    return home() / "profiles.json"


def _read_profiles() -> dict:
    path = profiles_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_profiles(data: dict) -> None:
    path = profiles_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


PROFILE_NAME = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$", re.I)


def save_profile(name: str, flags: dict) -> dict:
    if not PROFILE_NAME.match(name or ""):
        raise ValueError(f"bad profile name '{name}': letters, digits, . _ - only")
    data = _read_profiles()
    data[name] = {k: v for k, v in flags.items() if v is not None}
    _write_profiles(data)
    return data[name]


def load_profile(name: str) -> dict:
    data = _read_profiles()
    if name not in data:
        raise KeyError(name)
    return data[name]


def list_profiles() -> dict:
    return _read_profiles()


def delete_profile(name: str) -> bool:
    data = _read_profiles()
    if name not in data:
        return False
    del data[name]
    _write_profiles(data)
    return True


def apply_profile(args, name: str) -> list[str]:
    """Fill unset attributes from a saved profile. Explicit flags always win.

    Returns the names applied, so the run can report what it inherited — a
    profile that silently changed the scenario would make an odd result
    impossible to explain.
    """
    prof = load_profile(name)
    applied = []
    for key, value in prof.items():
        attr = key.replace("-", "_")
        if not hasattr(args, attr):
            continue
        current = getattr(args, attr)
        # argparse defaults are the "unset" signal: only fill falsy holes.
        if current in (None, "", False, 0) and value not in (None, "", False):
            setattr(args, attr, value)
            applied.append(key)
    return applied


# --------------------------------------------------------------------------
# Feedback
# --------------------------------------------------------------------------


def feedback_path() -> Path:
    return home() / "feedback.jsonl"


def record_feedback(text: str, *, context: str = "") -> Path:
    path = feedback_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "note": text.strip(),
        "context": context,
    }
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return path


def read_feedback(limit: int = 20) -> list[dict]:
    path = feedback_path()
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows[-limit:]


# --------------------------------------------------------------------------
# Emission
# --------------------------------------------------------------------------


def emit(payload: dict, *, agent: bool, sink: str | None = None, spec: str | None = None) -> int:
    """Print and/or route one envelope. Returns an exit code for delivery faults."""
    payload = select(payload, spec) if agent else payload
    if agent:
        body = json.dumps(payload, ensure_ascii=False)
    else:
        body = payload.get("table") or json.dumps(payload, indent=2, ensure_ascii=False)
    try:
        note = deliver(body, sink, content_type="application/json" if agent else "text/plain")
    except DeliveryError as exc:
        json.dump(fail(E_DELIVERY, str(exc), fix="use --deliver file:<path> or stdout"), sys.stdout)
        sys.stdout.write("\n")
        return E_DELIVERY
    if note:
        # Delivered elsewhere: stdout gets the receipt, not a second copy.
        if agent:
            json.dump({"meta": {"source": "who-finder"}, "results": {"delivered": note}}, sys.stdout)
            sys.stdout.write("\n")
        else:
            print(f"delivered -> {note}")
        return OK
    sys.stdout.write(body + "\n")
    return OK
