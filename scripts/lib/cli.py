"""CLI. The skill runs this; the agent does not reimplement HTTP or ranking.

Two depths:
  find "brief"              discovery only, cheap, one credit per query angle
  find "brief" --deep 10    + a dossier, ICP fit and priority for the top 10

`report` re-renders the deep brief from the local roster for zero credits.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import __version__, db, emit, enrich, icp, insights, sources
from .identity import parse_id
from .planner import detect_scenario, plan as make_plan
from .scenarios import SCENARIOS, SOURCES
from .which import resolve as which_resolve

ENV_KEY = "SCRAPECREATORS_API_KEY"

COMPACT_KEYS = (
    "novelty",
    "status",
    "kind",
    "platform",
    "handle",
    "name",
    "url",
    "score",
    "previous_score",
    "hit_count",
    "views",
    "likes",
    "comments",
    "sample",
    "sample_url",
    "side",
    "flags",
    "headline",
    "audience",
    "audience_kind",
    "fit_score",
    "fit_band",
    "fit_reasons",
    "fit_gaps",
    "priority",
    "signals",
    "enriched",
)

SIGNALS = {
    "hiring": "profile or recent posts mention hiring / open roles",
    "funding-talk": "recent posts mention raising or a round",
    "funded": "LinkedIn company page lists at least one funding round",
    "recent-round": "last round dated 2024 or later",
    "verified": "platform verification badge",
    "posting": "has recent public posts",
    "masked-profile": "LinkedIn hid job history; role came from the search snippet",
    "smb": "under 200 employees",
    "midmarket": "200-1999 employees",
    "enterprise": "2000+ employees",
    "small-audience": "under 10k followers/subscribers",
    "mid-audience": "10k-100k",
    "large-audience": "100k+",
}


def _token() -> str:
    return os.environ.get(ENV_KEY, "").strip()


def _emit(payload: dict, agent: bool) -> None:
    if agent:
        json.dump(payload, sys.stdout, ensure_ascii=False)
        sys.stdout.write("\n")
        return
    if payload.get("table"):
        print(payload["table"])
        return
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def _db(args: argparse.Namespace):
    return db.connect(Path(args.db) if getattr(args, "db", None) else None)


def _compact(row: dict) -> dict:
    out = {k: row.get(k) for k in COMPACT_KEYS}
    out["id"] = f"{row.get('kind')}/{row.get('platform')}/{row.get('handle')}"
    out["sample"] = row.get("sample") or row.get("sample_title")
    out["sample_url"] = row.get("sample_url")
    out["flags"] = row.get("flags") or []
    return out


def _ident(row: dict) -> str:
    return f"{row.get('kind')}/{row.get('platform')}/{row.get('handle')}"


def _ingest(conn, query: str, entities: list[dict], hits: list[dict], ts: str, scenario: str):
    n_new = n_known = 0
    out = []
    for h in hits:
        db.upsert_hit(conn, h, query, ts, scenario)
    for e in entities:
        novelty = db.upsert_entity(conn, e, query, ts, scenario)
        if novelty == "new":
            n_new += 1
        else:
            n_known += 1
        row = db.get_entity(conn, e["kind"], e["platform"], e["handle"]) or e
        row["novelty"] = novelty
        row["sample"] = e.get("sample")
        row["sample_url"] = e.get("sample_url") or row.get("sample_url")
        row["flags"] = e.get("flags") or []
        row["side"] = e.get("side") or ""
        out.append(row)
    return out, n_new, n_known


def _parse_sources(raw: str | None) -> list[str] | None:
    if not raw:
        return None
    srcs = [s.strip() for s in raw.split(",") if s.strip()]
    bad = [s for s in srcs if s not in SOURCES]
    if bad:
        raise SystemExit(f"unknown sources: {bad}. want {list(SOURCES)}")
    return srcs


def _score_rows(conn, rows: list[dict], dossiers: dict[str, dict], cfg: dict, ts: str) -> dict[str, dict]:
    """Attach fit + priority to every row and persist the dossier. Costs nothing."""
    full: dict[str, dict] = {}
    for r in rows:
        ident = _ident(r)
        d = dossiers.get(ident) or enrich.shallow(r)
        f = icp.fit(d, cfg)
        pr = icp.priority(d, f, r.get("novelty") or "known", int(r.get("score") or 0))
        r["headline"] = d.get("headline")
        r["audience"] = d.get("audience")
        r["audience_kind"] = d.get("audience_kind")
        r["signals"] = d.get("signals")
        r["enriched"] = bool(d.get("enriched"))
        r["fit_score"] = f["score"]
        r["fit_band"] = f["band"]
        r["fit_reasons"] = f["reasons"]
        r["fit_gaps"] = f["gaps"]
        r["priority"] = pr
        db.upsert_dossier(conn, d, f, pr, ts)
        d = dict(d)
        d["fit_score"] = f["score"]
        d["fit_band"] = f["band"]
        d["fit_reasons"] = f["reasons"]
        d["signals"] = d.get("signals") or []
        full[ident] = d
    return full


def cmd_doctor(args: argparse.Namespace) -> int:
    token = _token()
    path = Path(args.db) if args.db else db.default_db()
    icp_path = icp.config_path(getattr(args, "icp", None))
    payload = {
        "meta": {"source": "who-finder", "version": __version__},
        "results": {
            "state": "skipped-unconfigured" if not token else "ready",
            "key": "set" if token else "missing",
            "env": ENV_KEY,
            "db": str(path),
            "db_exists": path.exists(),
            "icp": str(icp_path),
            "icp_exists": icp_path.exists(),
            "scenarios": list(SCENARIOS),
            "sources": list(SOURCES),
        },
    }
    if not token:
        payload["results"]["fix"] = (
            f"export {ENV_KEY}=...  (recipient's own key from https://scrapecreators.com)"
        )
        payload["results"]["api"] = "untested"
        _emit(payload, args.agent)
        return 4
    try:
        credits = sources.http.get(
            f"{sources.SC}/v1/credit-balance",
            headers=sources.http.sc_headers(token),
            timeout=20,
        )
        payload["results"]["credits"] = credits
        payload["results"]["api"] = "ok"
        payload["results"]["state"] = "ready"
    except sources.http.HTTPError as exc:
        payload["results"]["credits_error"] = str(exc)
        payload["results"]["api"] = "auth-failed" if exc.status in {401, 403} else "error"
        payload["results"]["state"] = payload["results"]["api"]
        _emit(payload, args.agent)
        return 5
    except Exception as exc:
        payload["results"]["credits_error"] = str(exc)
        payload["results"]["api"] = "error"
        payload["results"]["state"] = "error"
        _emit(payload, args.agent)
        return 5
    if getattr(args, "probe", False):
        try:
            hits = sources.youtube(token, "youtube", 3, "month")
            payload["results"]["probe"] = {"youtube_hits": len(hits), "ok": True}
        except Exception as exc:
            payload["results"]["probe"] = {"ok": False, "error": str(exc)}
            payload["results"]["state"] = "error"
            _emit(payload, args.agent)
            return 5
    _emit(payload, args.agent)
    return 0


def cmd_which(args: argparse.Namespace) -> int:
    hit = which_resolve(args.capability)
    payload = {
        "meta": {"source": "who-finder", "version": __version__},
        "results": {
            "capability": args.capability,
            "run": hit["run"],
            "scenario": hit.get("scenario"),
            "note": hit.get("note") or "",
        },
    }
    _emit(payload, True)
    return 0 if hit.get("matched") else 2


def cmd_find(args: argparse.Namespace) -> int:
    token = _token()
    if not token:
        print(f"missing {ENV_KEY}", file=sys.stderr)
        return 4
    forced = None if args.scenario in {None, "auto"} else args.scenario
    if forced and forced not in SCENARIOS:
        print(f"unknown scenario {forced}. want {list(SCENARIOS)}", file=sys.stderr)
        return 2
    extra = _parse_sources(args.sources)
    p = make_plan(args.brief, scenario=forced, extra_sources=extra)
    if not p.steps:
        print("planner produced zero steps", file=sys.stderr)
        return 2

    entities, hits, errors, source_status = sources.run_plan(token, p, args.limit, args.freshness)
    depth = max(0, int(args.deep or 0))
    dossiers: dict[str, dict] = {}
    spent = len(p.steps)

    conn = _db(args)
    ts = db.now()
    try:
        out, n_new, n_known = _ingest(conn, args.brief, entities, hits, ts, p.scenario)
        db.record_search(
            conn, args.brief, sorted({s.source for s in p.steps}), n_new, n_known, ts, p.scenario
        )
        if args.new_only:
            out = [r for r in out if r.get("novelty") == "new" or r.get("status") == "new"]
            n_new, n_known = len(out), 0

        if depth:
            queue = out[:depth] if not args.new_only else [r for r in out if r.get("novelty") == "new"][:depth]
            dossiers, enrich_errors, enrich_spent = enrich.enrich_many(
                token, queue, limit=depth, cache=args.cache
            )
            errors.extend(enrich_errors)
            spent += enrich_spent

        cfg = icp.load(args.icp, topic=p.topic)
        full = _score_rows(conn, out, dossiers, cfg, ts)
        conn.commit()
    finally:
        conn.close()

    rows = icp.rank(out)
    step_labels = [f"{s.source}:{s.label}" for s in p.steps]
    ins = insights.build(
        rows,
        [full[_ident(r)] for r in rows if _ident(r) in full],
        scenario=p.scenario,
        topic=p.topic,
        n_new=n_new,
        n_known=n_known,
        source_status=source_status,
        errors=errors,
    )
    if depth:
        table = emit.brief(
            rows,
            full,
            ins,
            scenario=p.scenario,
            topic=p.topic,
            n_new=n_new,
            n_known=n_known,
            steps=step_labels,
            icp_name=cfg.get("name", "generic"),
            enriched_n=sum(1 for d in dossiers.values() if d.get("enriched")),
            credits=spent,
            side_b=p.side_b,
            show=args.show,
        )
    else:
        table = emit.table(
            rows,
            scenario=p.scenario,
            n_new=n_new,
            n_known=n_known,
            topic=p.topic,
            errors=errors,
            steps=step_labels,
            side_b=p.side_b,
        )
    payload = {
        "meta": {
            "source": "who-finder",
            "version": __version__,
            "brief": args.brief,
            "ran_at": ts,
            "scenario": p.scenario,
            "kind": p.kind,
            "freshness": args.freshness,
            "depth": depth,
            "icp": cfg.get("name", "generic"),
            "icp_path": cfg.get("_path", ""),
            "credits_spent": spent,
        },
        "plan": p.as_dict(),
        "table": table,
        "results": {
            "n_new": n_new,
            "n_known": n_known,
            "errors": errors,
            "source_status": source_status,
            "insights": ins,
            "entities": [_compact(r) for r in rows],
            "dossiers": full if args.full else {},
        },
    }
    _emit(payload, args.agent)
    return 0


def cmd_enrich(args: argparse.Namespace) -> int:
    token = _token()
    if not token:
        print(f"missing {ENV_KEY}", file=sys.stderr)
        return 4
    conn = _db(args)
    ts = db.now()
    try:
        if args.identity:
            targets = []
            for ident in args.identity:
                kind, platform, handle = parse_id(ident)
                row = db.get_entity(conn, kind, platform, handle)
                if not row:
                    row = {"kind": kind, "platform": platform, "handle": handle, "name": handle}
                row["novelty"] = "new" if row.get("status") == "new" else "known"
                targets.append(row)
        else:
            targets = db.list_entities(
                conn, status=args.status, kind=args.kind, query=args.query, limit=args.limit
            )
            for r in targets:
                r["novelty"] = "new" if r.get("status") == "new" else "known"
        if not targets:
            print("nothing to enrich", file=sys.stderr)
            return 3
        dossiers, errors, spent = enrich.enrich_many(
            token, targets, limit=args.limit, cache=args.cache
        )
        cfg = icp.load(args.icp, topic=args.query or "")
        full = _score_rows(conn, targets, dossiers, cfg, ts)
        conn.commit()
    finally:
        conn.close()
    rows = icp.rank(targets)
    ins = insights.build(
        rows,
        list(full.values()),
        scenario="enrich",
        topic=args.query or "roster",
        n_new=sum(1 for r in rows if r.get("novelty") == "new"),
        n_known=sum(1 for r in rows if r.get("novelty") != "new"),
        source_status=[],
        errors=errors,
    )
    payload = {
        "meta": {"source": "who-finder", "version": __version__, "credits_spent": spent},
        "table": emit.brief(
            rows,
            full,
            ins,
            scenario="enrich",
            topic=args.query or "roster",
            n_new=sum(1 for r in rows if r.get("novelty") == "new"),
            n_known=sum(1 for r in rows if r.get("novelty") != "new"),
            steps=[],
            icp_name=cfg.get("name", "generic"),
            enriched_n=sum(1 for d in dossiers.values() if d.get("enriched")),
            credits=spent,
            show=args.show,
        ),
        "results": {
            "errors": errors,
            "insights": ins,
            "entities": [_compact(r) for r in rows],
            "dossiers": full if args.full else {},
        },
    }
    _emit(payload, args.agent)
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    """Re-render the deep brief from the roster. Zero credits, zero network."""
    conn = _db(args)
    try:
        rows = db.list_ranked(
            conn,
            status=args.status,
            kind=args.kind,
            query=args.query,
            band=args.band,
            limit=args.limit,
        )
    finally:
        conn.close()
    full = {}
    for r in rows:
        d = dict(r.get("payload") or {})
        d.setdefault("id", _ident(r))
        d["headline"] = r.get("headline") or d.get("headline")
        d["headline_source"] = r.get("headline_source") or d.get("headline_source")
        d["audience"] = r.get("audience") or d.get("audience")
        d["audience_kind"] = r.get("audience_kind") or d.get("audience_kind")
        d["signals"] = r.get("signals") or d.get("signals") or []
        d["topics"] = r.get("topics") or d.get("topics") or []
        d["enriched"] = bool(r.get("enriched"))
        d["fit_score"] = r.get("fit_score")
        d["fit_band"] = r.get("fit_band")
        d["fit_reasons"] = r.get("fit_reasons") or []
        full[_ident(r)] = d
    n_new = sum(1 for r in rows if r.get("novelty") == "new")
    ins = insights.build(
        rows,
        list(full.values()),
        scenario="report",
        topic=args.query or (args.status or "roster"),
        n_new=n_new,
        n_known=len(rows) - n_new,
        source_status=[],
        errors=[],
    )
    ins["coverage"] = ["(from roster — no live search was run)"]
    payload = {
        "meta": {"source": "who-finder", "version": __version__, "credits_spent": 0},
        "table": emit.brief(
            rows,
            full,
            ins,
            scenario="report",
            topic=args.query or (args.status or "roster"),
            n_new=n_new,
            n_known=len(rows) - n_new,
            steps=[],
            icp_name=(rows[0].get("icp") if rows else "") or "generic",
            enriched_n=sum(1 for r in rows if r.get("enriched")),
            credits=0,
            show=args.show,
        ),
        "results": {
            "insights": ins,
            "entities": [_compact(r) for r in rows],
            "dossiers": full if args.full else {},
        },
    }
    _emit(payload, args.agent)
    return 0


def cmd_expand(args: argparse.Namespace) -> int:
    """Lateral growth from an existing dossier's similar/employee lists.

    LinkedIn already returned these names inside the profile payload, so this
    adds candidates without paying for another search.
    """
    kind, platform, handle = parse_id(args.identity)
    conn = _db(args)
    ts = db.now()
    spent = 0
    try:
        stored = db.get_dossier(conn, kind, platform, handle)
        d = (stored or {}).get("payload") or {}
        if not d:
            token = _token()
            if not token:
                print(f"no stored dossier and missing {ENV_KEY}", file=sys.stderr)
                return 4
            row = db.get_entity(conn, kind, platform, handle) or {
                "kind": kind, "platform": platform, "handle": handle, "name": handle,
            }
            d = enrich.enrich(token, row, cache=args.cache)
            spent = 0 if d.get("cached") else 1
            f = icp.fit(d, icp.load(args.icp))
            db.upsert_dossier(conn, d, f, icp.priority(d, f), ts)
        candidates = enrich.similar_identities(d) + enrich.people_identities(d)
        if not candidates:
            print("no similar profiles or employees in this dossier", file=sys.stderr)
            return 3
        for c in candidates:
            c["sample"] = c.get("title") or c.get("sample_title") or ""
            c["sample_url"] = c.get("url")
        query = f"expand:{args.identity}"
        out, n_new, n_known = _ingest(conn, query, candidates, [], ts, "expand")
        cfg = icp.load(args.icp)
        full = _score_rows(conn, out, {}, cfg, ts)
        conn.commit()
    finally:
        conn.close()
    rows = icp.rank(out)
    ins = insights.build(
        rows, list(full.values()), scenario="expand", topic=args.identity,
        n_new=n_new, n_known=n_known, source_status=[], errors=[],
    )
    ins["coverage"] = [f"expanded from {args.identity} (no new search)"]
    payload = {
        "meta": {"source": "who-finder", "version": __version__, "credits_spent": spent},
        "table": emit.brief(
            rows, full, ins, scenario="expand", topic=args.identity,
            n_new=n_new, n_known=n_known, steps=[], icp_name=cfg.get("name", "generic"),
            enriched_n=0, credits=spent, show=args.show,
        ),
        "results": {"n_new": n_new, "n_known": n_known, "entities": [_compact(r) for r in rows]},
    }
    _emit(payload, args.agent)
    return 0


def cmd_icp(args: argparse.Namespace) -> int:
    if args.action == "init":
        path = icp.write_template(args.icp)
        _emit(
            {"meta": {"source": "who-finder"}, "results": {"path": str(path), "created": True}},
            args.agent,
        )
        return 0
    cfg = icp.load(args.icp)
    _emit(
        {
            "meta": {"source": "who-finder"},
            "results": {
                "path": cfg.get("_path") or "(none — using built-in generic rules)",
                "name": cfg.get("name"),
                "config": {k: v for k, v in cfg.items() if not k.startswith("_")},
            },
        },
        args.agent,
    )
    return 0


def cmd_signals(args: argparse.Namespace) -> int:
    _emit({"meta": {"source": "who-finder"}, "results": {"signals": SIGNALS}}, args.agent)
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    """One raw keyword, one source. Debug hatch — find is the primary verb."""
    token = _token()
    if not token:
        print(f"missing {ENV_KEY}", file=sys.stderr)
        return 4
    srcs = _parse_sources(args.sources) or ["youtube"]
    scenario = detect_scenario(args.query, None)
    hits, err = sources.search_step(
        token, srcs[0], args.query, args.limit, args.freshness, scenario
    )
    errors = [err] if err else []
    entities = sources.rollup_entities(hits, scenario)
    conn = _db(args)
    ts = db.now()
    try:
        out, n_new, n_known = _ingest(conn, args.query, entities, hits, ts, scenario)
        db.record_search(conn, args.query, srcs, n_new, n_known, ts, scenario)
        conn.commit()
    finally:
        conn.close()
    payload = {
        "meta": {
            "source": "who-finder",
            "version": __version__,
            "query": args.query,
            "scenario": scenario,
        },
        "table": emit.table(
            out,
            scenario=scenario,
            n_new=n_new,
            n_known=n_known,
            topic=args.query,
            errors=errors,
            steps=[srcs[0]],
        ),
        "results": {
            "n_new": n_new,
            "n_known": n_known,
            "errors": errors,
            "entities": [_compact(r) for r in out],
        },
    }
    _emit(payload, args.agent)
    return 0


def cmd_new(args: argparse.Namespace) -> int:
    conn = _db(args)
    try:
        rows = db.list_entities(
            conn, status="new", query=args.query, kind=args.kind, limit=args.limit
        )
        for r in rows:
            r["novelty"] = "new"
    finally:
        conn.close()
    _emit({"meta": {"source": "who-finder"}, "results": {"entities": rows}}, args.agent)
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    conn = _db(args)
    try:
        rows = db.list_entities(
            conn,
            status=args.status,
            query=args.query,
            kind=args.kind,
            scenario=args.scenario,
            limit=args.limit,
        )
        for r in rows:
            r["novelty"] = "new" if r.get("status") == "new" else "known"
    finally:
        conn.close()
    _emit({"meta": {"source": "who-finder"}, "results": {"entities": rows}}, args.agent)
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    kind, platform, handle = parse_id(args.identity)
    conn = _db(args)
    try:
        ent = db.get_entity(conn, kind, platform, handle)
        if not ent:
            print("not found", file=sys.stderr)
            return 3
        hits = db.hits_for(conn, kind, platform, handle)
        snaps = db.snapshots_for(conn, kind, platform, handle)
        dos = db.get_dossier(conn, kind, platform, handle)
    finally:
        conn.close()
    ent["novelty"] = "new" if ent.get("status") == "new" else "known"
    payload = {
        "meta": {"source": "who-finder"},
        "results": {"entity": ent, "dossier": dos, "hits": hits, "snapshots": snaps},
    }
    if dos:
        dos = dict(dos)
        dos["id"] = f"{kind}/{platform}/{handle}"
        dos["name"] = ent.get("name")
        payload["table"] = emit.dossier_card(dos, ent)
    _emit(payload, args.agent)
    return 0


def cmd_mark(args: argparse.Namespace) -> int:
    kind, platform, handle = parse_id(args.identity)
    conn = _db(args)
    try:
        ok = db.mark(conn, kind, platform, handle, args.status)
        conn.commit()
    finally:
        conn.close()
    if not ok:
        print("not found", file=sys.stderr)
        return 3
    _emit(
        {"meta": {"source": "who-finder"}, "results": {"ok": True, "status": args.status}},
        args.agent,
    )
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    conn = _db(args)
    try:
        rows = db.list_ranked(
            conn,
            status=args.status,
            query=args.query,
            kind=args.kind,
            band=args.band,
            limit=args.limit,
        )
        text = db.export_csv(rows)
    finally:
        conn.close()
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        if args.agent:
            json.dump(
                {"meta": {"source": "who-finder"}, "results": {"path": args.out, "n": len(rows)}},
                sys.stdout,
            )
            sys.stdout.write("\n")
        else:
            print(args.out)
        return 0
    sys.stdout.write(text)
    return 0


def cmd_import(args: argparse.Namespace) -> int:
    text = Path(args.csv).read_text(encoding="utf-8")
    conn = _db(args)
    ts = db.now()
    try:
        n = db.import_csv(conn, text, ts)
        conn.commit()
    finally:
        conn.close()
    _emit({"meta": {"source": "who-finder"}, "results": {"imported": n}}, args.agent)
    return 0


def cmd_scenarios(args: argparse.Namespace) -> int:
    rows = [
        {
            "name": name,
            "kind": spec["kind"],
            "blurb": spec["blurb"],
            "default_sources": list(spec["default_sources"]),
        }
        for name, spec in SCENARIOS.items()
    ]
    _emit({"meta": {"source": "who-finder"}, "results": {"scenarios": rows}}, args.agent)
    return 0


def main(argv: list[str] | None = None) -> int:
    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument("--agent", action="store_true", help="JSON on stdout")
    shared.add_argument("--db", default=None, help="sqlite path (default: .who-finder/roster.sqlite)")

    deep = argparse.ArgumentParser(add_help=False)
    deep.add_argument("--icp", default=None, help="ICP json path (default: .who-finder/icp.json)")
    deep.add_argument("--cache", default="7d", choices=list(enrich.CACHE_CHOICES),
                      help="reuse a cached profile this old for 0 credits")
    deep.add_argument("--show", type=int, default=12, help="cards in the printed brief")
    deep.add_argument("--full", action="store_true", help="include whole dossiers in --agent JSON")

    p = argparse.ArgumentParser(prog="who-finder", description=__doc__, parents=[shared])
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("doctor", parents=[shared], help="key, roster path, credits, four-state health")
    d.add_argument("--probe", action="store_true", help="spend 1 credit on a YouTube smoke search")
    d.add_argument("--icp", default=None)
    d.set_defaults(fn=cmd_doctor)

    w = sub.add_parser("which", parents=[shared], help="map a capability phrase to a command")
    w.add_argument("capability")
    w.set_defaults(fn=cmd_which)

    sc = sub.add_parser("scenarios", parents=[shared], help="list engine-owned search types")
    sc.set_defaults(fn=cmd_scenarios)

    sg = sub.add_parser("signals", parents=[shared], help="signal names you can score in icp.json")
    sg.set_defaults(fn=cmd_signals)

    f = sub.add_parser("find", parents=[shared, deep], help="detect scenario, plan queries, search, ingest")
    f.add_argument("brief")
    f.add_argument("--scenario", default="auto", help="auto|people|companies|creators|hiring|press|compare")
    f.add_argument("--sources", default=None, help="comma list; default is the scenario's set")
    f.add_argument("--limit", type=int, default=40)
    f.add_argument("--freshness", default="month", choices=list(sources.FRESHNESS))
    f.add_argument("--new-only", action="store_true")
    f.add_argument("--deep", type=int, default=0, metavar="N",
                   help="enrich the top N (1 credit each) and produce the full brief")
    f.set_defaults(fn=cmd_find)

    en = sub.add_parser("enrich", parents=[shared, deep], help="dossier + ICP fit for stored entities")
    en.add_argument("identity", nargs="*", help="kind/platform/handle; omit to use --status")
    en.add_argument("--status", default="new")
    en.add_argument("--kind", default=None, choices=["person", "company"])
    en.add_argument("--query", default=None)
    en.add_argument("--limit", type=int, default=10)
    en.set_defaults(fn=cmd_enrich)

    rp = sub.add_parser("report", parents=[shared, deep], help="re-render the deep brief from the roster (0 credits)")
    rp.add_argument("--status", default=None)
    rp.add_argument("--kind", default=None, choices=["person", "company"])
    rp.add_argument("--query", default=None)
    rp.add_argument("--band", default=None, choices=list(icp.BANDS))
    rp.add_argument("--limit", type=int, default=25)
    rp.set_defaults(fn=cmd_report)

    ex = sub.add_parser("expand", parents=[shared, deep], help="pull similar profiles / employees out of a dossier")
    ex.add_argument("identity")
    ex.set_defaults(fn=cmd_expand)

    ic = sub.add_parser("icp", parents=[shared], help="show or create the fit config")
    ic.add_argument("action", choices=["show", "init"])
    ic.add_argument("--icp", default=None)
    ic.set_defaults(fn=cmd_icp)

    s = sub.add_parser("search", parents=[shared], help="one raw keyword, no planner (debug)")
    s.add_argument("query")
    s.add_argument("--sources", default="youtube")
    s.add_argument("--limit", type=int, default=40)
    s.add_argument("--freshness", default="month", choices=list(sources.FRESHNESS))
    s.set_defaults(fn=cmd_search)

    n = sub.add_parser("new", parents=[shared], help="entities still marked new")
    n.add_argument("--query", default=None)
    n.add_argument("--kind", default=None, choices=["person", "company"])
    n.add_argument("--limit", type=int, default=50)
    n.set_defaults(fn=cmd_new)

    l = sub.add_parser("list", parents=[shared], help="list stored entities")
    l.add_argument("--status", default=None)
    l.add_argument("--query", default=None)
    l.add_argument("--kind", default=None, choices=["person", "company"])
    l.add_argument("--scenario", default=None)
    l.add_argument("--limit", type=int, default=50)
    l.set_defaults(fn=cmd_list)

    sh = sub.add_parser("show", parents=[shared], help="one entity + dossier + hits + snapshots")
    sh.add_argument("identity", help="kind/platform/handle")
    sh.set_defaults(fn=cmd_show)

    m = sub.add_parser("mark", parents=[shared], help="new|watched|outreached|skip|customer")
    m.add_argument("identity")
    m.add_argument("--status", required=True)
    m.set_defaults(fn=cmd_mark)

    e = sub.add_parser("export", parents=[shared], help="CSV handoff (does not send)")
    e.add_argument("--status", default="new")
    e.add_argument("--query", default=None)
    e.add_argument("--kind", default=None, choices=["person", "company"])
    e.add_argument("--band", default=None, choices=list(icp.BANDS))
    e.add_argument("--limit", type=int, default=200)
    e.add_argument("--out", default=None)
    e.set_defaults(fn=cmd_export)

    i = sub.add_parser("import", parents=[shared], help="seed skip/customer/outreached from CSV")
    i.add_argument("csv")
    i.set_defaults(fn=cmd_import)

    args = p.parse_args(argv)
    return int(args.fn(args) or 0)
