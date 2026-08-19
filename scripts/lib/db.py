"""Portable sqlite roster. Default: <cwd>/.who-finder/roster.sqlite

'new' means first insert, and stays new until someone marks another status.
Re-finding a still-new entity is still the outreach queue (novelty=new).
Re-finding after outreached/skip/customer/watched is novelty=known.

Identity is kind/platform/handle. A person and a company with the same
LinkedIn slug are two rows.
"""

from __future__ import annotations

import csv
import io
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS entities (
  kind     TEXT NOT NULL,
  platform TEXT NOT NULL,
  handle   TEXT NOT NULL,
  name     TEXT,
  url      TEXT,
  status   TEXT NOT NULL DEFAULT 'new',
  first_seen TEXT NOT NULL,
  last_seen  TEXT NOT NULL,
  last_query TEXT,
  last_scenario TEXT,
  score    INTEGER NOT NULL DEFAULT 0,
  previous_score INTEGER NOT NULL DEFAULT 0,
  hit_count INTEGER NOT NULL DEFAULT 0,
  views    INTEGER NOT NULL DEFAULT 0,
  likes    INTEGER NOT NULL DEFAULT 0,
  comments INTEGER NOT NULL DEFAULT 0,
  shares   INTEGER NOT NULL DEFAULT 0,
  sample_title TEXT,
  sample_url TEXT,
  extra    TEXT,
  PRIMARY KEY (kind, platform, handle)
);

CREATE TABLE IF NOT EXISTS hits (
  kind       TEXT NOT NULL,
  platform   TEXT NOT NULL,
  handle     TEXT NOT NULL,
  content_id TEXT NOT NULL,
  url        TEXT,
  title      TEXT,
  posted_at  TEXT,
  query      TEXT,
  scenario   TEXT,
  fetched_at TEXT NOT NULL,
  views      INTEGER NOT NULL DEFAULT 0,
  likes      INTEGER NOT NULL DEFAULT 0,
  comments   INTEGER NOT NULL DEFAULT 0,
  shares     INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (platform, content_id)
);

CREATE TABLE IF NOT EXISTS searches (
  id     INTEGER PRIMARY KEY AUTOINCREMENT,
  query  TEXT NOT NULL,
  scenario TEXT,
  ran_at TEXT NOT NULL,
  sources TEXT,
  n_new  INTEGER NOT NULL DEFAULT 0,
  n_known INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS snapshots (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  kind TEXT NOT NULL,
  platform TEXT NOT NULL,
  handle   TEXT NOT NULL,
  taken_at TEXT NOT NULL,
  query    TEXT,
  scenario TEXT,
  score    INTEGER NOT NULL DEFAULT 0,
  views    INTEGER NOT NULL DEFAULT 0,
  likes    INTEGER NOT NULL DEFAULT 0,
  comments INTEGER NOT NULL DEFAULT 0,
  hit_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS dossiers (
  kind     TEXT NOT NULL,
  platform TEXT NOT NULL,
  handle   TEXT NOT NULL,
  fetched_at TEXT NOT NULL,
  headline TEXT,
  headline_source TEXT,
  bio      TEXT,
  location TEXT,
  audience INTEGER NOT NULL DEFAULT 0,
  audience_kind TEXT,
  topics   TEXT,
  signals  TEXT,
  enriched INTEGER NOT NULL DEFAULT 0,
  fit_score INTEGER NOT NULL DEFAULT 0,
  fit_band  TEXT,
  fit_reasons TEXT,
  fit_gaps  TEXT,
  priority  REAL NOT NULL DEFAULT 0,
  icp       TEXT,
  payload   TEXT,
  PRIMARY KEY (kind, platform, handle)
);
"""

STATUSES = ("new", "watched", "outreached", "skip", "customer")

HANDOFF_FIELDS = (
    "kind",
    "platform",
    "handle",
    "id",
    "name",
    "url",
    "headline",
    "location",
    "audience",
    "audience_kind",
    "fit_score",
    "fit_band",
    "priority",
    "signals",
    "status",
    "novelty",
    "score",
    "previous_score",
    "hit_count",
    "views",
    "likes",
    "comments",
    "shares",
    "last_query",
    "last_scenario",
    "first_seen",
    "last_seen",
    "sample_title",
    "sample_url",
    "emails",
    "website",
    "calendly",
    "notes",
)


def home() -> Path:
    raw = os.environ.get("WHO_FINDER_HOME")
    return Path(raw).expanduser() if raw else Path.cwd() / ".who-finder"


def default_db() -> Path:
    raw = os.environ.get("WHO_FINDER_DB")
    return Path(raw).expanduser() if raw else home() / "roster.sqlite"


def connect(path: Path | None = None) -> sqlite3.Connection:
    db_path = Path(path) if path else default_db()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _key(row: dict) -> tuple[str, str, str]:
    return row["kind"], row["platform"], row["handle"]


def upsert_entity(conn: sqlite3.Connection, row: dict, query: str, ts: str, scenario: str = "") -> str:
    """Insert or refresh. Returns 'new' if still in the outreach queue, else 'known'."""
    kind, platform, handle = _key(row)
    cur = conn.execute(
        "SELECT status, score FROM entities WHERE kind=? AND platform=? AND handle=?",
        (kind, platform, handle),
    )
    existing = cur.fetchone()
    extra = json.dumps(row.get("extra") or {}, ensure_ascii=False)
    score = int(row.get("score") or 0)
    if existing is None:
        conn.execute(
            """INSERT INTO entities (
                 kind, platform, handle, name, url, status, first_seen, last_seen,
                 last_query, last_scenario, score, previous_score, hit_count, views, likes,
                 comments, shares, sample_title, sample_url, extra
               ) VALUES (?,?,?,?,?, 'new', ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                kind,
                platform,
                handle,
                row.get("name") or handle,
                row.get("url"),
                ts,
                ts,
                query,
                scenario,
                score,
                row.get("hit_count") or 0,
                row.get("views") or 0,
                row.get("likes") or 0,
                row.get("comments") or 0,
                row.get("shares") or 0,
                row.get("sample") or row.get("sample_title"),
                row.get("sample_url"),
                extra,
            ),
        )
        _snapshot(conn, row, query, ts, scenario)
        return "new"
    conn.execute(
        """UPDATE entities SET
             name=COALESCE(?, name), url=COALESCE(?, url),
             last_seen=?, last_query=?, last_scenario=?,
             previous_score=score, score=?,
             hit_count=?, views=?, likes=?, comments=?, shares=?,
             sample_title=COALESCE(?, sample_title),
             sample_url=COALESCE(?, sample_url), extra=?
           WHERE kind=? AND platform=? AND handle=?""",
        (
            row.get("name"),
            row.get("url"),
            ts,
            query,
            scenario,
            score,
            row.get("hit_count") or 0,
            row.get("views") or 0,
            row.get("likes") or 0,
            row.get("comments") or 0,
            row.get("shares") or 0,
            row.get("sample") or row.get("sample_title"),
            row.get("sample_url"),
            extra,
            kind,
            platform,
            handle,
        ),
    )
    _snapshot(conn, row, query, ts, scenario)
    return "known" if existing["status"] != "new" else "new"


def _snapshot(conn: sqlite3.Connection, row: dict, query: str, ts: str, scenario: str) -> None:
    conn.execute(
        """INSERT INTO snapshots (
             kind, platform, handle, taken_at, query, scenario, score, views, likes, comments, hit_count
           ) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (
            row["kind"],
            row["platform"],
            row["handle"],
            ts,
            query,
            scenario,
            row.get("score") or 0,
            row.get("views") or 0,
            row.get("likes") or 0,
            row.get("comments") or 0,
            row.get("hit_count") or 0,
        ),
    )


def upsert_hit(conn: sqlite3.Connection, hit: dict, query: str, ts: str, scenario: str = "") -> None:
    cid = hit.get("content_id")
    if not cid:
        return
    conn.execute(
        """INSERT INTO hits (
             kind, platform, handle, content_id, url, title, posted_at, query,
             scenario, fetched_at, views, likes, comments, shares
           ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(platform, content_id) DO UPDATE SET
             views=excluded.views, likes=excluded.likes,
             comments=excluded.comments, shares=excluded.shares,
             fetched_at=excluded.fetched_at, query=excluded.query,
             handle=excluded.handle, kind=excluded.kind,
             title=COALESCE(excluded.title, hits.title),
             scenario=excluded.scenario
        """,
        (
            hit["kind"],
            hit["platform"],
            hit["handle"],
            cid,
            hit.get("hit_url") or hit.get("url"),
            hit.get("title"),
            hit.get("posted_at"),
            query,
            scenario,
            ts,
            hit.get("views") or 0,
            hit.get("likes") or 0,
            hit.get("comments") or 0,
            hit.get("shares") or 0,
        ),
    )


def record_search(
    conn: sqlite3.Connection,
    query: str,
    sources: list[str],
    n_new: int,
    n_known: int,
    ts: str,
    scenario: str = "",
) -> None:
    conn.execute(
        "INSERT INTO searches (query, scenario, ran_at, sources, n_new, n_known) VALUES (?,?,?,?,?,?)",
        (query, scenario, ts, ",".join(sources), n_new, n_known),
    )


def list_entities(
    conn: sqlite3.Connection,
    status: str | None = None,
    query: str | None = None,
    kind: str | None = None,
    scenario: str | None = None,
    limit: int = 50,
) -> list[dict]:
    sql = "SELECT * FROM entities WHERE 1=1"
    args: list = []
    if status:
        sql += " AND status=?"
        args.append(status)
    if kind:
        sql += " AND kind=?"
        args.append(kind)
    if query:
        sql += " AND last_query LIKE ?"
        args.append(f"%{query}%")
    if scenario:
        sql += " AND last_scenario=?"
        args.append(scenario)
    sql += " ORDER BY score DESC LIMIT ?"
    args.append(limit)
    return [dict(r) for r in conn.execute(sql, args)]


def get_entity(conn: sqlite3.Connection, kind: str, platform: str, handle: str) -> dict | None:
    row = conn.execute(
        "SELECT * FROM entities WHERE kind=? AND platform=? AND handle=?",
        (kind, platform, handle),
    ).fetchone()
    return dict(row) if row else None


def hits_for(
    conn: sqlite3.Connection, kind: str, platform: str, handle: str, limit: int = 20
) -> list[dict]:
    return [
        dict(r)
        for r in conn.execute(
            """SELECT * FROM hits WHERE kind=? AND platform=? AND handle=?
               ORDER BY views DESC, likes DESC LIMIT ?""",
            (kind, platform, handle, limit),
        )
    ]


def snapshots_for(
    conn: sqlite3.Connection, kind: str, platform: str, handle: str, limit: int = 12
) -> list[dict]:
    return [
        dict(r)
        for r in conn.execute(
            """SELECT * FROM snapshots WHERE kind=? AND platform=? AND handle=?
               ORDER BY taken_at DESC LIMIT ?""",
            (kind, platform, handle, limit),
        )
    ]


def upsert_dossier(conn: sqlite3.Connection, d: dict, f: dict, priority: float, ts: str) -> None:
    conn.execute(
        """INSERT INTO dossiers (
             kind, platform, handle, fetched_at, headline, headline_source, bio, location,
             audience, audience_kind, topics, signals, enriched,
             fit_score, fit_band, fit_reasons, fit_gaps, priority, icp, payload
           ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(kind, platform, handle) DO UPDATE SET
             fetched_at=excluded.fetched_at,
             headline=COALESCE(NULLIF(excluded.headline,''), dossiers.headline),
             headline_source=excluded.headline_source,
             bio=COALESCE(NULLIF(excluded.bio,''), dossiers.bio),
             location=COALESCE(NULLIF(excluded.location,''), dossiers.location),
             audience=MAX(excluded.audience, dossiers.audience),
             audience_kind=COALESCE(NULLIF(excluded.audience_kind,''), dossiers.audience_kind),
             topics=excluded.topics, signals=excluded.signals,
             enriched=MAX(excluded.enriched, dossiers.enriched),
             fit_score=excluded.fit_score, fit_band=excluded.fit_band,
             fit_reasons=excluded.fit_reasons, fit_gaps=excluded.fit_gaps,
             priority=excluded.priority, icp=excluded.icp, payload=excluded.payload
        """,
        (
            d["kind"],
            d["platform"],
            d["handle"],
            ts,
            d.get("headline") or "",
            d.get("headline_source") or "",
            d.get("bio") or "",
            d.get("location") or "",
            int(d.get("audience") or 0),
            d.get("audience_kind") or "",
            json.dumps(d.get("topics") or [], ensure_ascii=False),
            json.dumps(d.get("signals") or [], ensure_ascii=False),
            1 if d.get("enriched") else 0,
            int(f.get("score") or 0),
            f.get("band") or "",
            json.dumps(f.get("reasons") or [], ensure_ascii=False),
            json.dumps(f.get("gaps") or [], ensure_ascii=False),
            float(priority or 0),
            f.get("icp") or "",
            json.dumps(d, ensure_ascii=False),
        ),
    )


def get_dossier(conn: sqlite3.Connection, kind: str, platform: str, handle: str) -> dict | None:
    row = conn.execute(
        "SELECT * FROM dossiers WHERE kind=? AND platform=? AND handle=?",
        (kind, platform, handle),
    ).fetchone()
    return _hydrate(dict(row)) if row else None


def _hydrate(row: dict) -> dict:
    for col in ("topics", "signals", "fit_reasons", "fit_gaps"):
        raw = row.get(col)
        try:
            row[col] = json.loads(raw) if raw else []
        except (TypeError, ValueError):
            row[col] = []
    try:
        row["payload"] = json.loads(row["payload"]) if row.get("payload") else {}
    except (TypeError, ValueError):
        row["payload"] = {}
    return row


def dossier_map(conn: sqlite3.Connection, keys: list[tuple[str, str, str]]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for kind, platform, handle in keys:
        row = get_dossier(conn, kind, platform, handle)
        if row:
            out[f"{kind}/{platform}/{handle}"] = row
    return out


def list_ranked(
    conn: sqlite3.Connection,
    status: str | None = None,
    kind: str | None = None,
    query: str | None = None,
    band: str | None = None,
    limit: int = 25,
) -> list[dict]:
    """Roster rows joined to their dossier, ordered by priority. Costs no credits."""
    sql = """SELECT e.*, d.headline, d.headline_source, d.bio, d.location, d.audience,
                    d.audience_kind, d.topics, d.signals, d.enriched, d.fit_score,
                    d.fit_band, d.fit_reasons, d.fit_gaps, d.priority, d.icp, d.payload
             FROM entities e
             LEFT JOIN dossiers d
               ON d.kind=e.kind AND d.platform=e.platform AND d.handle=e.handle
             WHERE 1=1"""
    args: list = []
    if status:
        sql += " AND e.status=?"
        args.append(status)
    if kind:
        sql += " AND e.kind=?"
        args.append(kind)
    if query:
        sql += " AND e.last_query LIKE ?"
        args.append(f"%{query}%")
    if band:
        sql += " AND d.fit_band=?"
        args.append(band)
    sql += " ORDER BY COALESCE(d.priority, 0) DESC, e.score DESC LIMIT ?"
    args.append(limit)
    rows = []
    for r in conn.execute(sql, args):
        row = _hydrate(dict(r))
        row["novelty"] = "new" if row.get("status") == "new" else "known"
        rows.append(row)
    return rows


def mark(conn: sqlite3.Connection, kind: str, platform: str, handle: str, status: str) -> bool:
    if status not in STATUSES:
        raise ValueError(f"status must be one of {STATUSES}")
    cur = conn.execute(
        "UPDATE entities SET status=? WHERE kind=? AND platform=? AND handle=?",
        (status, kind, platform, handle),
    )
    return cur.rowcount > 0


def seed(conn: sqlite3.Connection, row: dict, ts: str) -> None:
    status = row.get("status") or "skip"
    if status not in STATUSES:
        raise ValueError(f"status must be one of {STATUSES}")
    extra = json.dumps({}, ensure_ascii=False)
    conn.execute(
        """INSERT INTO entities (
             kind, platform, handle, name, url, status, first_seen, last_seen,
             last_query, last_scenario, score, previous_score, extra
           ) VALUES (?,?,?,?,?,?,?,?,?,?,0,0,?)
           ON CONFLICT(kind, platform, handle) DO UPDATE SET
             status=excluded.status,
             name=COALESCE(excluded.name, entities.name),
             url=COALESCE(excluded.url, entities.url)
        """,
        (
            row.get("kind") or "person",
            row["platform"],
            row["handle"],
            row.get("name") or row["handle"],
            row.get("url"),
            status,
            ts,
            ts,
            row.get("last_query") or "import",
            row.get("last_scenario") or "",
            extra,
        ),
    )


def _row_id(r: dict) -> str:
    return f"{r.get('kind')}/{r.get('platform')}/{r.get('handle')}"


def export_csv(rows: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=HANDOFF_FIELDS, extrasaction="ignore")
    w.writeheader()
    for r in rows:
        out = {k: r.get(k, "") for k in HANDOFF_FIELDS}
        out["id"] = _row_id(r)
        out["notes"] = r.get("notes") or ""
        out["novelty"] = r.get("novelty") or ("new" if r.get("status") == "new" else "known")
        sig = r.get("signals")
        out["signals"] = " ".join(sig) if isinstance(sig, list) else (sig or "")
        w.writerow(out)
    return buf.getvalue()


def import_csv(conn: sqlite3.Connection, text: str, ts: str) -> int:
    reader = csv.DictReader(io.StringIO(text))
    n = 0
    for raw in reader:
        platform = (raw.get("platform") or "").strip().lower()
        handle = (raw.get("handle") or "").strip().lstrip("@")
        kind = (raw.get("kind") or "").strip().lower()
        if not kind and raw.get("id"):
            bits = [p for p in raw["id"].split("/") if p]
            if len(bits) == 3:
                kind, platform, handle = bits[0], bits[1], bits[2]
        if not platform or not handle:
            continue
        seed(
            conn,
            {
                "kind": kind or "person",
                "platform": platform,
                "handle": handle,
                "name": (raw.get("name") or "").strip(),
                "url": (raw.get("url") or "").strip(),
                "status": (raw.get("status") or "skip").strip() or "skip",
            },
            ts,
        )
        n += 1
    return n
