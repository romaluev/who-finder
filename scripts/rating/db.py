"""SQLite store. Default: <cwd>/.creator-rating/rating.sqlite

Nine tables from the spec plus raw_payloads (reprocess without refetching),
spend_log (--max-spend), pace_log (daily caps), and session_ack (rails).
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS creators (
  id         TEXT PRIMARY KEY,
  url        TEXT NOT NULL UNIQUE,
  handle     TEXT,
  name       TEXT,
  platform   TEXT NOT NULL DEFAULT 'linkedin',
  source     TEXT,
  headline   TEXT,
  about      TEXT,
  followers  INTEGER NOT NULL DEFAULT 0,
  connections INTEGER NOT NULL DEFAULT 0,
  location   TEXT,
  status     TEXT NOT NULL DEFAULT 'longlist',
  first_seen TEXT NOT NULL,
  last_seen  TEXT NOT NULL,
  extra      TEXT
);

CREATE TABLE IF NOT EXISTS creator_snapshots (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  creator_id TEXT NOT NULL,
  taken_at   TEXT NOT NULL,
  followers  INTEGER NOT NULL DEFAULT 0,
  connections INTEGER NOT NULL DEFAULT 0,
  headline   TEXT,
  source     TEXT
);

CREATE TABLE IF NOT EXISTS posts (
  id         TEXT PRIMARY KEY,
  creator_id TEXT NOT NULL,
  url        TEXT,
  text       TEXT,
  posted_at  TEXT,
  reactions  INTEGER NOT NULL DEFAULT 0,
  comments   INTEGER NOT NULL DEFAULT 0,
  reposts    INTEGER NOT NULL DEFAULT 0,
  impressions INTEGER,
  format     TEXT,
  source     TEXT,
  fetched_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS post_topics (
  post_id     TEXT NOT NULL,
  classifier  TEXT NOT NULL,
  version     TEXT NOT NULL,
  topic       TEXT,
  secondary   TEXT,
  relevance   REAL,
  bait        INTEGER NOT NULL DEFAULT 0,
  ai_likelihood REAL,
  safety      TEXT,
  language    TEXT,
  generic     INTEGER NOT NULL DEFAULT 0,
  classified_at TEXT NOT NULL,
  PRIMARY KEY (post_id, classifier, version)
);

CREATE TABLE IF NOT EXISTS engagements (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  post_id      TEXT NOT NULL,
  engager_hash TEXT NOT NULL,
  type         TEXT NOT NULL,
  word_count   INTEGER NOT NULL DEFAULT 0,
  latency_sec  INTEGER,
  generic      INTEGER NOT NULL DEFAULT 0,
  ai_flag      INTEGER NOT NULL DEFAULT 0,
  fetched_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS engagers (
  hash       TEXT PRIMARY KEY,
  first_seen TEXT NOT NULL,
  last_seen  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS engager_enrichment (
  hash         TEXT PRIMARY KEY,
  seniority    TEXT,
  function     TEXT,
  industry     TEXT,
  geo          TEXT,
  company      TEXT,
  company_size INTEGER,
  headline     TEXT,
  source       TEXT,
  enriched_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scores (
  creator_id   TEXT NOT NULL,
  taken_at     TEXT NOT NULL,
  preset       TEXT NOT NULL,
  stage        TEXT NOT NULL,
  social       REAL,
  engagement   REAL,
  interest     REAL,
  creator_score REAL,
  confidence   REAL,
  tier         TEXT,
  next_action  TEXT,
  gates        TEXT,
  metrics      TEXT,
  PRIMARY KEY (creator_id, taken_at, preset, stage)
);

CREATE TABLE IF NOT EXISTS pilots (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  creator_id  TEXT NOT NULL,
  kind        TEXT NOT NULL,
  taken_at    TEXT NOT NULL,
  impressions INTEGER,
  icp_share   REAL,
  leads       INTEGER,
  comments_icp INTEGER,
  paid        REAL,
  format      TEXT,
  notes       TEXT,
  payload     TEXT
);

CREATE TABLE IF NOT EXISTS raw_payloads (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  creator_id TEXT,
  kind       TEXT NOT NULL,
  source     TEXT NOT NULL,
  fetched_at TEXT NOT NULL,
  payload    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS spend_log (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  collector TEXT NOT NULL,
  kind      TEXT NOT NULL,
  units     INTEGER NOT NULL DEFAULT 1,
  usd       REAL NOT NULL DEFAULT 0,
  at        TEXT NOT NULL,
  note      TEXT
);

CREATE TABLE IF NOT EXISTS pace_log (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  collector TEXT NOT NULL,
  at        TEXT NOT NULL,
  units     INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS session_ack (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS abm_accounts (
  name     TEXT PRIMARY KEY,
  domain   TEXT,
  added_at TEXT NOT NULL
);
"""

STATUSES = ("longlist", "shortlist", "pilot", "contracted", "pass", "watch")


def home() -> Path:
    raw = os.environ.get("CREATOR_RATING_HOME")
    return Path(raw).expanduser() if raw else Path.cwd() / ".creator-rating"


def default_db() -> Path:
    raw = os.environ.get("CREATOR_RATING_DB")
    return Path(raw).expanduser() if raw else home() / "rating.sqlite"


def connect(path: Path | None = None) -> sqlite3.Connection:
    db_path = Path(path) if path else default_db()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False)


def upsert_creator(conn: sqlite3.Connection, row: dict, ts: str) -> str:
    """Insert or refresh. Returns 'new' or 'known'. Dedupe key is the profile URL."""
    from .util import handle_from, norm_url, platform_of

    url = norm_url(row.get("url") or "")
    if not url:
        raise ValueError("creator needs a profile url")
    handle = row.get("handle") or handle_from(url, row.get("name") or "")
    cid = row.get("id") or f"{row.get('platform') or platform_of(url)}/{handle}"
    existing = conn.execute("SELECT id, url FROM creators WHERE url=?", (url,)).fetchone()
    if existing:
        cid = existing["id"]
        conn.execute(
            """UPDATE creators SET
                 handle=COALESCE(?, handle), name=COALESCE(?, name),
                 platform=COALESCE(?, platform), source=COALESCE(?, source),
                 headline=COALESCE(?, headline), about=COALESCE(?, about),
                 followers=MAX(?, followers), connections=MAX(?, connections),
                 location=COALESCE(?, location), last_seen=?
               WHERE id=?""",
            (
                row.get("handle") or handle,
                row.get("name"),
                row.get("platform") or platform_of(url),
                row.get("source"),
                row.get("headline"),
                row.get("about"),
                int(row.get("followers") or 0),
                int(row.get("connections") or 0),
                row.get("location"),
                ts,
                cid,
            ),
        )
        _snapshot(conn, cid, row, ts)
        return "known"
    conn.execute(
        """INSERT INTO creators (
             id, url, handle, name, platform, source, headline, about,
             followers, connections, location, status, first_seen, last_seen, extra
           ) VALUES (?,?,?,?,?,?,?,?,?,?,?,'longlist',?,?,?)""",
        (
            cid,
            url,
            handle,
            row.get("name") or handle,
            row.get("platform") or platform_of(url),
            row.get("source") or "manual",
            row.get("headline") or "",
            row.get("about") or "",
            int(row.get("followers") or 0),
            int(row.get("connections") or 0),
            row.get("location") or "",
            ts,
            ts,
            _dumps(row.get("extra") or {}),
        ),
    )
    _snapshot(conn, cid, row, ts)
    return "new"


def _snapshot(conn: sqlite3.Connection, cid: str, row: dict, ts: str) -> None:
    conn.execute(
        """INSERT INTO creator_snapshots (creator_id, taken_at, followers, connections, headline, source)
           VALUES (?,?,?,?,?,?)""",
        (
            cid,
            ts,
            int(row.get("followers") or 0),
            int(row.get("connections") or 0),
            row.get("headline") or "",
            row.get("source") or "",
        ),
    )


def get_creator(conn: sqlite3.Connection, cid: str) -> dict | None:
    row = conn.execute("SELECT * FROM creators WHERE id=?", (cid,)).fetchone()
    if row:
        return dict(row)
    row = conn.execute("SELECT * FROM creators WHERE url=?", (cid,)).fetchone()
    return dict(row) if row else None


def get_by_url(conn: sqlite3.Connection, url: str) -> dict | None:
    from .util import norm_url

    row = conn.execute("SELECT * FROM creators WHERE url=?", (norm_url(url),)).fetchone()
    return dict(row) if row else None


def list_creators(
    conn: sqlite3.Connection,
    status: str | None = None,
    limit: int = 200,
) -> list[dict]:
    sql = "SELECT * FROM creators WHERE 1=1"
    args: list = []
    if status:
        sql += " AND status=?"
        args.append(status)
    sql += " ORDER BY last_seen DESC LIMIT ?"
    args.append(limit)
    return [dict(r) for r in conn.execute(sql, args)]


def set_status(conn: sqlite3.Connection, cid: str, status: str) -> bool:
    if status not in STATUSES:
        raise ValueError(f"status must be one of {STATUSES}")
    cur = conn.execute("UPDATE creators SET status=? WHERE id=?", (status, cid))
    return cur.rowcount > 0


def upsert_post(conn: sqlite3.Connection, post: dict, ts: str) -> str:
    pid = post.get("id") or post.get("url") or ""
    if not pid:
        raise ValueError("post needs an id or url")
    conn.execute(
        """INSERT INTO posts (
             id, creator_id, url, text, posted_at, reactions, comments, reposts,
             impressions, format, source, fetched_at
           ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(id) DO UPDATE SET
             reactions=excluded.reactions, comments=excluded.comments,
             reposts=excluded.reposts, impressions=COALESCE(excluded.impressions, posts.impressions),
             text=COALESCE(NULLIF(excluded.text,''), posts.text),
             fetched_at=excluded.fetched_at, source=excluded.source
        """,
        (
            pid,
            post["creator_id"],
            post.get("url") or "",
            post.get("text") or "",
            post.get("posted_at") or "",
            int(post.get("reactions") or 0),
            int(post.get("comments") or 0),
            int(post.get("reposts") or 0),
            post.get("impressions"),
            post.get("format") or "",
            post.get("source") or "",
            ts,
        ),
    )
    return pid


def posts_for(conn: sqlite3.Connection, cid: str, limit: int = 40) -> list[dict]:
    return [
        dict(r)
        for r in conn.execute(
            "SELECT * FROM posts WHERE creator_id=? ORDER BY posted_at DESC, fetched_at DESC LIMIT ?",
            (cid, limit),
        )
    ]


def upsert_topic(conn: sqlite3.Connection, row: dict, ts: str) -> None:
    conn.execute(
        """INSERT INTO post_topics (
             post_id, classifier, version, topic, secondary, relevance, bait,
             ai_likelihood, safety, language, generic, classified_at
           ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(post_id, classifier, version) DO UPDATE SET
             topic=excluded.topic, secondary=excluded.secondary,
             relevance=excluded.relevance, bait=excluded.bait,
             ai_likelihood=excluded.ai_likelihood, safety=excluded.safety,
             language=excluded.language, generic=excluded.generic,
             classified_at=excluded.classified_at
        """,
        (
            row["post_id"],
            row.get("classifier") or "rules",
            row.get("version") or "1",
            row.get("topic") or "",
            _dumps(row.get("secondary") or []),
            row.get("relevance"),
            1 if row.get("bait") else 0,
            row.get("ai_likelihood"),
            row.get("safety") or "ok",
            row.get("language") or "",
            1 if row.get("generic") else 0,
            ts,
        ),
    )


def topic_for(conn: sqlite3.Connection, post_id: str) -> dict | None:
    row = conn.execute(
        """SELECT * FROM post_topics WHERE post_id=?
           ORDER BY CASE classifier WHEN 'llm' THEN 0 WHEN 'agent' THEN 1 ELSE 2 END
           LIMIT 1""",
        (post_id,),
    ).fetchone()
    if not row:
        return None
    out = dict(row)
    try:
        out["secondary"] = json.loads(out["secondary"]) if out.get("secondary") else []
    except (TypeError, ValueError):
        out["secondary"] = []
    return out


def topics_for_creator(conn: sqlite3.Connection, cid: str) -> dict[str, dict]:
    posts = posts_for(conn, cid, limit=200)
    return {p["id"]: topic_for(conn, p["id"]) or {} for p in posts}


def insert_engagement(conn: sqlite3.Connection, row: dict, ts: str) -> None:
    conn.execute(
        """INSERT INTO engagements (
             post_id, engager_hash, type, word_count, latency_sec, generic, ai_flag, fetched_at
           ) VALUES (?,?,?,?,?,?,?,?)""",
        (
            row["post_id"],
            row["engager_hash"],
            row.get("type") or "reaction",
            int(row.get("word_count") or 0),
            row.get("latency_sec"),
            1 if row.get("generic") else 0,
            1 if row.get("ai_flag") else 0,
            ts,
        ),
    )
    existing = conn.execute("SELECT hash FROM engagers WHERE hash=?", (row["engager_hash"],)).fetchone()
    if existing:
        conn.execute("UPDATE engagers SET last_seen=? WHERE hash=?", (ts, row["engager_hash"]))
    else:
        conn.execute(
            "INSERT INTO engagers (hash, first_seen, last_seen) VALUES (?,?,?)",
            (row["engager_hash"], ts, ts),
        )


def engagements_for(conn: sqlite3.Connection, cid: str) -> list[dict]:
    return [
        dict(r)
        for r in conn.execute(
            """SELECT e.* FROM engagements e
               JOIN posts p ON p.id=e.post_id
               WHERE p.creator_id=?""",
            (cid,),
        )
    ]


def engager_hashes_for(conn: sqlite3.Connection, cid: str) -> set[str]:
    return {
        r["engager_hash"]
        for r in conn.execute(
            """SELECT DISTINCT e.engager_hash FROM engagements e
               JOIN posts p ON p.id=e.post_id WHERE p.creator_id=?""",
            (cid,),
        )
    }


def upsert_enrichment(conn: sqlite3.Connection, row: dict, ts: str) -> None:
    conn.execute(
        """INSERT INTO engager_enrichment (
             hash, seniority, function, industry, geo, company, company_size, headline, source, enriched_at
           ) VALUES (?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(hash) DO UPDATE SET
             seniority=COALESCE(excluded.seniority, engager_enrichment.seniority),
             function=COALESCE(excluded.function, engager_enrichment.function),
             industry=COALESCE(excluded.industry, engager_enrichment.industry),
             geo=COALESCE(excluded.geo, engager_enrichment.geo),
             company=COALESCE(excluded.company, engager_enrichment.company),
             company_size=COALESCE(excluded.company_size, engager_enrichment.company_size),
             headline=COALESCE(excluded.headline, engager_enrichment.headline),
             source=excluded.source, enriched_at=excluded.enriched_at
        """,
        (
            row["hash"],
            row.get("seniority") or "",
            row.get("function") or "",
            row.get("industry") or "",
            row.get("geo") or "",
            row.get("company") or "",
            row.get("company_size"),
            row.get("headline") or "",
            row.get("source") or "rules",
            ts,
        ),
    )


def enrichment_map(conn: sqlite3.Connection, hashes: set[str]) -> dict[str, dict]:
    if not hashes:
        return {}
    out = {}
    for h in hashes:
        row = conn.execute("SELECT * FROM engager_enrichment WHERE hash=?", (h,)).fetchone()
        if row:
            out[h] = dict(row)
    return out


def save_score(conn: sqlite3.Connection, row: dict, ts: str) -> None:
    conn.execute(
        """INSERT INTO scores (
             creator_id, taken_at, preset, stage, social, engagement, interest,
             creator_score, confidence, tier, next_action, gates, metrics
           ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(creator_id, taken_at, preset, stage) DO UPDATE SET
             social=excluded.social, engagement=excluded.engagement,
             interest=excluded.interest, creator_score=excluded.creator_score,
             confidence=excluded.confidence, tier=excluded.tier,
             next_action=excluded.next_action, gates=excluded.gates, metrics=excluded.metrics
        """,
        (
            row["creator_id"],
            ts,
            row.get("preset") or "awareness+leads",
            row.get("stage") or "v1",
            row.get("social"),
            row.get("engagement"),
            row.get("interest"),
            row.get("creator_score"),
            row.get("confidence"),
            row.get("tier"),
            row.get("next_action"),
            _dumps(row.get("gates") or []),
            _dumps(row.get("metrics") or {}),
        ),
    )


def latest_score(conn: sqlite3.Connection, cid: str, preset: str | None = None) -> dict | None:
    sql = "SELECT * FROM scores WHERE creator_id=?"
    args: list = [cid]
    if preset:
        sql += " AND preset=?"
        args.append(preset)
    sql += " ORDER BY taken_at DESC LIMIT 1"
    row = conn.execute(sql, args).fetchone()
    if not row:
        return None
    out = dict(row)
    for col in ("gates", "metrics"):
        try:
            out[col] = json.loads(out[col]) if out.get(col) else ([] if col == "gates" else {})
        except (TypeError, ValueError):
            out[col] = [] if col == "gates" else {}
    return out


def list_scores(conn: sqlite3.Connection, preset: str | None = None, limit: int = 200) -> list[dict]:
    sql = """SELECT s.*, c.name, c.url, c.handle, c.followers, c.headline, c.platform, c.source, c.status
             FROM scores s JOIN creators c ON c.id=s.creator_id
             WHERE 1=1"""
    args: list = []
    if preset:
        sql += " AND s.preset=?"
        args.append(preset)
    sql += " ORDER BY s.taken_at DESC, s.creator_score DESC"
    rows = [dict(r) for r in conn.execute(sql, args)]
    # Keep the latest score per creator.
    seen, out = set(), []
    for r in rows:
        if r["creator_id"] in seen:
            continue
        seen.add(r["creator_id"])
        for col in ("gates", "metrics"):
            try:
                r[col] = json.loads(r[col]) if r.get(col) else ([] if col == "gates" else {})
            except (TypeError, ValueError):
                r[col] = [] if col == "gates" else {}
        out.append(r)
        if len(out) >= limit:
            break
    return out


def insert_pilot(conn: sqlite3.Connection, row: dict, ts: str) -> int:
    cur = conn.execute(
        """INSERT INTO pilots (
             creator_id, kind, taken_at, impressions, icp_share, leads, comments_icp,
             paid, format, notes, payload
           ) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (
            row["creator_id"],
            row.get("kind") or "consented",
            ts,
            row.get("impressions"),
            row.get("icp_share"),
            row.get("leads"),
            row.get("comments_icp"),
            row.get("paid"),
            row.get("format") or "",
            row.get("notes") or "",
            _dumps(row.get("payload") or {}),
        ),
    )
    return int(cur.lastrowid)


def list_pilots(conn: sqlite3.Connection) -> list[dict]:
    return [dict(r) for r in conn.execute("SELECT * FROM pilots ORDER BY taken_at DESC")]


def save_raw(conn: sqlite3.Connection, kind: str, source: str, payload, ts: str, creator_id: str = "") -> None:
    conn.execute(
        "INSERT INTO raw_payloads (creator_id, kind, source, fetched_at, payload) VALUES (?,?,?,?,?)",
        (creator_id, kind, source, ts, _dumps(payload)),
    )


def log_spend(conn: sqlite3.Connection, collector: str, kind: str, units: int, usd: float, ts: str, note: str = "") -> None:
    conn.execute(
        "INSERT INTO spend_log (collector, kind, units, usd, at, note) VALUES (?,?,?,?,?,?)",
        (collector, kind, units, usd, ts, note),
    )


def spend_total(conn: sqlite3.Connection, since: str | None = None) -> float:
    if since:
        row = conn.execute("SELECT COALESCE(SUM(usd),0) AS s FROM spend_log WHERE at>=?", (since,)).fetchone()
    else:
        row = conn.execute("SELECT COALESCE(SUM(usd),0) AS s FROM spend_log").fetchone()
    return float(row["s"] if row else 0)


def log_pace(conn: sqlite3.Connection, collector: str, ts: str, units: int = 1) -> None:
    conn.execute("INSERT INTO pace_log (collector, at, units) VALUES (?,?,?)", (collector, ts, units))


def pace_today(conn: sqlite3.Connection, collector: str, day: str) -> int:
    row = conn.execute(
        "SELECT COALESCE(SUM(units),0) AS n FROM pace_log WHERE collector=? AND at LIKE ?",
        (collector, day + "%"),
    ).fetchone()
    return int(row["n"] if row else 0)


def set_ack(conn: sqlite3.Connection, key: str, value: str, ts: str) -> None:
    conn.execute(
        "INSERT INTO session_ack (key, value, at) VALUES (?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value, at=excluded.at",
        (key, value, ts),
    )


def get_ack(conn: sqlite3.Connection, key: str) -> str:
    row = conn.execute("SELECT value FROM session_ack WHERE key=?", (key,)).fetchone()
    return row["value"] if row else ""


def add_abm(conn: sqlite3.Connection, name: str, domain: str, ts: str) -> None:
    conn.execute(
        "INSERT INTO abm_accounts (name, domain, added_at) VALUES (?,?,?) ON CONFLICT(name) DO UPDATE SET domain=excluded.domain",
        (name.strip(), (domain or "").strip().lower(), ts),
    )


def abm_names(conn: sqlite3.Connection) -> set[str]:
    return {r["name"].lower() for r in conn.execute("SELECT name FROM abm_accounts") if r["name"]}


def prune_engagers(conn: sqlite3.Connection, before: str) -> int:
    """Drop raw engager rows older than `before`. Keep aggregates already in scores."""
    hashes = [
        r["engager_hash"]
        for r in conn.execute("SELECT DISTINCT engager_hash FROM engagements WHERE fetched_at < ?", (before,))
    ]
    conn.execute("DELETE FROM engagements WHERE fetched_at < ?", (before,))
    gone = 0
    for h in hashes:
        still = conn.execute("SELECT 1 FROM engagements WHERE engager_hash=? LIMIT 1", (h,)).fetchone()
        if still:
            continue
        conn.execute("DELETE FROM engager_enrichment WHERE hash=?", (h,))
        conn.execute("DELETE FROM engagers WHERE hash=?", (h,))
        gone += 1
    return gone


def engager_pii_columns() -> frozenset:
    """Columns that must never appear on an export. The exporter checks this set."""
    return frozenset({
        "engager_hash", "engager_url", "engager_name", "email", "emails",
        "first_name", "last_name", "phone", "raw_url", "comment_text",
        "engager_headline",
    })
