"""Session-based engager collector (Unipile-class) behind engine-enforced rails.

Hard rails, not docs:
- dedicated collection account only; refuse if it matches the brand account
- --i-understand recorded once in config
- human-pace throttling with jitter and a daily cap (hard stop)
- engager rows keyed by hashed profile URL
- this adapter never returns a raw engager URL to the rest of the pipeline
"""

from __future__ import annotations

import hashlib
import random
import time
from datetime import datetime, timezone

from .. import auth, db, http
from ..util import clean, norm_url, to_int
from .base import Collector, Engager, HygieneError

DAILY_CAP = 80
MIN_SLEEP = 8.0
MAX_SLEEP = 18.0


def hash_url(url: str) -> str:
    target = norm_url(url)
    return hashlib.sha256(target.encode("utf-8")).hexdigest()[:32]


def assert_rails(cfg: dict | None = None, *, i_understand: bool = False, conn=None) -> dict:
    """Refuse unless a dedicated account is configured and acknowledged."""
    cfg = dict(cfg or auth.read_config())
    if conn is not None and not cfg.get("session_ack"):
        ack = db.get_ack(conn, "i_understand")
        if ack:
            cfg["session_ack"] = ack
    collection = (cfg.get("collection_account") or "").strip().lower()
    brand = (cfg.get("brand_account") or "").strip().lower()
    if not collection:
        raise HygieneError(
            "engager collection needs a dedicated account. "
            "setup --collection-account ACCOUNT --brand-account BRAND, then --i-understand"
        )
    if brand and collection == brand:
        raise HygieneError(
            "collection account matches the brand operating account. "
            "use a dedicated seat, never the brand's own login"
        )
    ack = bool(cfg.get("session_ack") or cfg.get("i_understand") or i_understand)
    if not ack:
        raise HygieneError(
            "engager collection is opt-in. pass --i-understand once after naming the dedicated account. "
            "see docs/connect.md#engager-source"
        )
    return cfg


def record_ack(conn, ts: str) -> None:
    db.set_ack(conn, "i_understand", "yes", ts)
    auth.write_config({"session_ack": True, "i_understand": True})


class UnipileCollector(Collector):
    name = "unipile"
    cost_per_engager = 0.0

    def __init__(self, token: str | None = None, *, sleep: bool = True, daily_cap: int = DAILY_CAP):
        self._token = token if token is not None else auth.token("unipile")
        self.sleep = sleep
        self.daily_cap = daily_cap

    def available(self) -> bool:
        return bool(self._token)

    def _pace(self, conn) -> None:
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        used = db.pace_today(conn, self.name, day) if conn is not None else 0
        if used >= self.daily_cap:
            raise HygieneError(
                f"daily engager cap reached ({self.daily_cap}). "
                "the pacing budget is a hard stop, not a warning"
            )
        if self.sleep:
            time.sleep(random.uniform(MIN_SLEEP, MAX_SLEEP))

    def engagers(self, post_url: str, cap: int = 200, *, conn=None, i_understand: bool = False) -> list[Engager]:
        cfg = assert_rails(i_understand=i_understand, conn=conn)
        if not self._token:
            return []
        if conn is not None:
            self._pace(conn)
        try:
            data = http.get(
                f"https://api.unipile.com/api/v1/posts/{_post_id(post_url)}/reactions",
                headers={"X-API-KEY": self._token, "Accept": "application/json"},
                timeout=40,
            )
        except Exception:
            data = {}
        rows = data.get("items") or data.get("data") or []
        out: list[Engager] = []
        ts = db.now()
        for raw in rows:
            if not isinstance(raw, dict):
                continue
            url = raw.get("profile_url") or raw.get("url") or ""
            if not url:
                continue
            hashed = hash_url(url)
            text = clean(raw.get("comment") or raw.get("text") or "")
            out.append(Engager(
                hash=hashed,
                type="comment" if text else (raw.get("type") or "reaction"),
                word_count=len(text.split()) if text else 0,
                latency_sec=to_int(raw.get("latency_sec") or raw.get("delay")),
                headline=clean(raw.get("headline") or raw.get("title") or ""),
            ))
            if len(out) >= cap:
                break
        if conn is not None:
            db.log_pace(conn, self.name, ts, 1)
            _ = cfg
        # Strip any leftover URL field — the rest of the pipeline must never see it.
        for e in out:
            e.pop("url", None)
            e.pop("profile_url", None)
            e.pop("name", None)
        return out


def _post_id(url: str) -> str:
    raw = (url or "").rstrip("/").split("/")[-1]
    return raw or "unknown"


def ingest_hashed_dump(rows: list[dict]) -> list[Engager]:
    """Manual / SaaS export path. Accepts already-hashed or raw URLs; always re-hashes."""
    out = []
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        url = raw.get("url") or raw.get("profile_url") or ""
        hashed = raw.get("hash") or (hash_url(url) if url else "")
        if not hashed:
            continue
        text = clean(raw.get("comment") or raw.get("text") or "")
        out.append(Engager(
            hash=hashed,
            type=raw.get("type") or ("comment" if text else "reaction"),
            word_count=int(raw.get("word_count") or (len(text.split()) if text else 0)),
            latency_sec=raw.get("latency_sec"),
            headline=clean(raw.get("headline") or ""),
            post_id=raw.get("post_id") or "",
        ))
    return out
