"""CLI. The skill runs this; the agent does not reimplement HTTP or ranking.

Two depths:
  find "brief"              discovery only, cheap, one credit per query angle
  find "brief" --deep 10    + a dossier, ICP fit and priority for the top 10

`report` re-renders the deep brief from the local roster for zero credits.

Because every search costs money, the cost gates come before the network:
`--dry-run` prints the planned queries and the ceiling without spending or
even needing a key, and `--max-credits` refuses an over-budget plan at exit 8
rather than reporting the overspend afterwards.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

from . import __version__, agentio, db, emit, enrich, icp, insights, sources
from .agentio import E_API, E_AUTH, E_BUDGET, E_CONFIG, E_NOTFOUND, E_USAGE
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


COMMAND_HELP = {
    "find": ("detect scenario, plan queries, search, ingest, rank", "1/angle + 1/enriched"),
    "report": ("re-render the deep brief from the roster", "0"),
    "enrich": ("dossier + ICP fit for stored entities", "1/entity, 0 cached"),
    "expand": ("similar profiles / employees out of a stored dossier", "0"),
    "doctor": ("key, roster path, credits, four-state health", "0, or 1 with --probe"),
    "agent-context": ("machine-readable description of this whole CLI", "0"),
    "which": ("map a capability phrase to a command", "0"),
    "scenarios": ("list engine-owned search types", "0"),
    "signals": ("signal names you can score in icp.json", "0"),
    "icp": ("show or create the fit config", "0"),
    "search": ("one raw keyword, no planner (debug hatch)", "1"),
    "new": ("entities still marked new", "0"),
    "list": ("list stored entities", "0"),
    "show": ("one entity + dossier + hits + snapshots", "0"),
    "mark": ("new|watched|outreached|skip|customer", "0"),
    "export": ("CSV handoff (does not send)", "0"),
    "import": ("seed skip/customer/outreached from CSV", "0"),
    "profile": ("save/list/show/delete a reusable flag set", "0"),
    "feedback": ("record what surprised you about this CLI", "0"),
}


def _command_index() -> list[dict]:
    return [
        {"command": name, "does": does, "credits": cost}
        for name, (does, cost) in COMMAND_HELP.items()
    ]


def _token() -> str:
    return os.environ.get(ENV_KEY, "").strip()


def _emit(payload: dict, agent: bool, args: argparse.Namespace | None = None) -> int:
    return agentio.emit(
        payload,
        agent=agent,
        sink=getattr(args, "deliver", None),
        spec=getattr(args, "select", None),
    )


def _die(args: argparse.Namespace, code: int, message: str, fix: str = "", **extra) -> int:
    """Emit a branchable error envelope and return its exit code.

    Errors go to stdout in `--agent` mode for the same reason results do: a
    caller that has to correlate stderr with stdout to learn why a run failed
    will skip the step and guess instead.
    """
    payload = agentio.fail(code, message, fix=fix, **extra)
    if getattr(args, "agent", False):
        json.dump(payload, sys.stdout, ensure_ascii=False)
        sys.stdout.write("\n")
    else:
        print(f"error [{code}] {message}", file=sys.stderr)
        if fix:
            print(f"fix: {fix}", file=sys.stderr)
    return code


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
        raise ValueError(f"unknown sources: {bad}. want {list(SOURCES)}")
    return srcs


def _estimate(plan, depth: int) -> dict:
    """Credit cost of a plan before any of it is spent.

    Discovery is one credit per query angle; enrichment is one per entity, and
    only up to the number of entities discovery can actually return. Cached
    profile reads cost nothing, so this is a ceiling rather than a forecast.
    """
    discovery = len(plan.steps)
    enrichment = max(0, int(depth or 0))
    return {
        "discovery": discovery,
        "enrichment_max": enrichment,
        "total_max": discovery + enrichment,
        "note": "enrichment is a ceiling: cached profiles cost 0",
    }


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
        # `table` is what a human sees; agents read `results`. Rendered at the
        # end of the command so it reflects the probe and credit results.
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
        payload["table"] = emit.doctor_card(payload["results"])
        _emit(payload, args.agent, args)
        return E_AUTH
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
        payload["table"] = emit.doctor_card(payload["results"])
        _emit(payload, args.agent, args)
        return E_API
    except Exception as exc:
        payload["results"]["credits_error"] = str(exc)
        payload["results"]["api"] = "error"
        payload["results"]["state"] = "error"
        payload["table"] = emit.doctor_card(payload["results"])
        _emit(payload, args.agent, args)
        return E_API
    if getattr(args, "probe", False):
        try:
            hits = sources.youtube(token, "youtube", 3, "month")
            payload["results"]["probe"] = {"youtube_hits": len(hits), "ok": True}
        except Exception as exc:
            payload["results"]["probe"] = {"ok": False, "error": str(exc)}
            payload["results"]["state"] = "error"
            payload["table"] = emit.doctor_card(payload["results"])
            _emit(payload, args.agent, args)
            return E_API
    payload["table"] = emit.doctor_card(payload["results"])
    return _emit(payload, args.agent, args)


def cmd_which(args: argparse.Namespace) -> int:
    hit = which_resolve(args.capability)
    lines = []
    if hit.get("matched"):
        lines.append("Run this:")
    else:
        lines.append(f"No confident match for \"{args.capability}\". Closest thing:")
    lines.append(f"  {_invocation()} {hit['run']}")
    if hit.get("note"):
        lines.append(f"\n  {hit['note']}")
    if not hit.get("matched"):
        lines.append(f"\nOr see everything:  {_invocation()} help")
    payload = {
        "meta": {"source": "who-finder", "version": __version__},
        "table": "\n".join(lines),
        "results": {
            "capability": args.capability,
            "matched": bool(hit.get("matched")),
            "run": hit["run"],
            "scenario": hit.get("scenario"),
            "note": hit.get("note") or "",
        },
    }
    _emit(payload, args.agent, args)
    return 0 if hit.get("matched") else 2


def cmd_find(args: argparse.Namespace) -> int:
    dry = bool(getattr(args, "dry_run", False))
    # Argument validation precedes the auth check on purpose. Both can be wrong
    # at once, and reporting the missing key first sends the user away to fetch
    # one only to hit the typo on the next run.
    forced = None if args.scenario in {None, "auto"} else args.scenario
    if forced and forced not in SCENARIOS:
        return _die(args, E_USAGE, f"unknown scenario '{forced}'",
                    fix=f"drop --scenario to let the engine detect, or pick one of {list(SCENARIOS)}",
                    allowed=list(SCENARIOS))
    try:
        extra = _parse_sources(args.sources)
    except ValueError as exc:
        return _die(args, E_USAGE, str(exc), fix=f"pick from {list(SOURCES)}", allowed=list(SOURCES))
    token = _token()
    if not token and not dry:
        return _die(args, E_AUTH, f"missing {ENV_KEY}",
                    fix=f"export {ENV_KEY}=... — the recipient supplies their own key "
                        "from https://scrapecreators.com")
    p = make_plan(args.brief, scenario=forced, extra_sources=extra)
    if not p.steps:
        return _die(args, E_USAGE, "planner produced zero steps for this brief",
                    fix="give a brief with a topic in it, or force one with --scenario")

    depth = max(0, int(args.deep or 0))
    est = _estimate(p, depth)

    # Cost gates run before the first request, because a budget check that
    # fires after the spend is just a receipt.
    cap = getattr(args, "max_credits", None)
    if cap is not None and est["total_max"] > cap:
        return _die(
            args, E_BUDGET,
            f"plan needs up to {est['total_max']} credits, --max-credits is {cap}",
            fix=f"raise --max-credits, lower --deep, or narrow --sources",
            estimate=est, plan=p.as_dict(),
        )
    if dry:
        return _emit(
            {
                "meta": {"source": "who-finder", "version": __version__, "dry_run": True,
                         "scenario": p.scenario, "kind": p.kind, "credits_spent": 0},
                "plan": p.as_dict(),
                "table": emit.plan_card(p, est, depth=depth, icp_name=icp.load(args.icp, topic=p.topic).get("name", "generic")),
                "results": {"estimate": est, "steps": p.as_dict()["steps"]},
            },
            args.agent, args,
        )

    entities, hits, errors, source_status = sources.run_plan(token, p, args.limit, args.freshness)
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
    return _emit(payload, args.agent, args)


def cmd_enrich(args: argparse.Namespace) -> int:
    token = _token()
    if not token:
        return _die(args, E_AUTH, f"missing {ENV_KEY}",
                    fix=f"export {ENV_KEY}=... — the recipient supplies their own key "
                        "from https://scrapecreators.com")
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
            return _die(args, E_NOTFOUND, "nothing to enrich",
                        fix="run find first, or widen with --status any")
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
    return _emit(payload, args.agent, args)


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
    return _emit(payload, args.agent, args)


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
                return _die(args, E_AUTH, f"no stored dossier and missing {ENV_KEY}",
                            fix=f"export {ENV_KEY}=... or run enrich on this id first")
            row = db.get_entity(conn, kind, platform, handle) or {
                "kind": kind, "platform": platform, "handle": handle, "name": handle,
            }
            d = enrich.enrich(token, row, cache=args.cache)
            spent = 0 if d.get("cached") else 1
            f = icp.fit(d, icp.load(args.icp))
            db.upsert_dossier(conn, d, f, icp.priority(d, f), ts)
        candidates = enrich.similar_identities(d) + enrich.people_identities(d)
        if not candidates:
            return _die(args, E_NOTFOUND,
                        "no similar profiles or employees in this dossier",
                        fix="this platform exposes no lateral links; run a fresh find instead")
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
    return _emit(payload, args.agent, args)


def cmd_icp(args: argparse.Namespace) -> int:
    if args.action == "init":
        path = icp.write_template(args.icp)
        return _emit(
            {"meta": {"source": "who-finder"}, "results": {"path": str(path), "created": True}},
            args.agent,
            args,
        )
    cfg = icp.load(args.icp)
    return _emit(
        {
            "meta": {"source": "who-finder"},
            "results": {
                "path": cfg.get("_path") or "(none — using built-in generic rules)",
                "name": cfg.get("name"),
                "config": {k: v for k, v in cfg.items() if not k.startswith("_")},
            },
        },
        args.agent,
        args,
    )


def cmd_agent_context(args: argparse.Namespace) -> int:
    """Everything a caller needs to drive this CLI without reading the docs.

    Emitted from the same constants the commands use, so it cannot drift from
    the real behaviour the way a hand-written command list does.
    """
    token = _token()
    icp_path = icp.config_path(getattr(args, "icp", None))
    return _emit(
        {
            "meta": {"source": "who-finder", "version": __version__},
            "results": {
                "version": __version__,
                "key_present": bool(token),
                "env": {"key": ENV_KEY, "home": "WHO_FINDER_HOME", "db": "WHO_FINDER_DB",
                        "icp": "WHO_FINDER_ICP"},
                "paths": {
                    "db": str(db.default_db()),
                    "icp": str(icp_path),
                    "profiles": str(agentio.profiles_path()),
                    "feedback": str(agentio.feedback_path()),
                },
                "primary_verb": "find",
                "commands": _command_index(),
                "scenarios": {n: s["blurb"] for n, s in SCENARIOS.items()},
                "sources": list(SOURCES),
                "signals": SIGNALS,
                "bands": list(icp.BANDS),
                "statuses": list(db.STATUSES),
                "exit_codes": agentio.EXIT_CODES,
                "available_profiles": sorted(agentio.list_profiles()),
                "global_flags": {
                    "--agent": "JSON envelope on stdout",
                    "--select": "comma-separated dotted paths; meta always survives",
                    "--deliver": "stdout | file:<path> | webhook:<url>",
                    "--profile": "apply a saved flag set; explicit flags still win",
                    "--db": "override the roster path",
                },
                "cost_model": {
                    "discovery_per_query_angle": 1,
                    "enrichment_per_entity": 1,
                    "cached_profile": 0,
                    "report_expand_show_export_mark": 0,
                    "preview": "find <brief> --dry-run --agent",
                },
            },
        },
        args.agent, args,
    )


def cmd_profile(args: argparse.Namespace) -> int:
    if args.action == "list":
        return _emit(
            {"meta": {"source": "who-finder"}, "results": {"profiles": agentio.list_profiles()}},
            args.agent, args,
        )
    if args.action == "show":
        if not args.name:
            return _die(args, E_USAGE, "profile show needs a name", fix="profile list --agent")
        try:
            prof = agentio.load_profile(args.name)
        except KeyError:
            return _die(args, E_NOTFOUND, f"no profile '{args.name}'", fix="profile list --agent")
        return _emit(
            {"meta": {"source": "who-finder"}, "results": {"name": args.name, "flags": prof}},
            args.agent, args,
        )
    if args.action == "delete":
        if not args.name:
            return _die(args, E_USAGE, "profile delete needs a name", fix="profile list --agent")
        gone = agentio.delete_profile(args.name)
        if not gone:
            return _die(args, E_NOTFOUND, f"no profile '{args.name}'", fix="profile list --agent")
        return _emit(
            {"meta": {"source": "who-finder"}, "results": {"deleted": args.name}}, args.agent, args
        )
    # save
    if not args.name:
        return _die(args, E_USAGE, "profile save needs a name",
                    fix='profile save nightly --set scenario=people --set deep=10')
    flags: dict[str, object] = {}
    for pair in args.set or []:
        if "=" not in pair:
            return _die(args, E_USAGE, f"--set wants key=value, got '{pair}'",
                        fix="--set deep=10 --set scenario=people")
        key, _, raw = pair.partition("=")
        flags[key.strip()] = _coerce(raw.strip())
    try:
        saved = agentio.save_profile(args.name, flags)
    except ValueError as exc:
        return _die(args, E_USAGE, str(exc), fix="use letters, digits, dot, underscore or hyphen")
    return _emit(
        {"meta": {"source": "who-finder"},
         "results": {"saved": args.name, "flags": saved, "path": str(agentio.profiles_path())}},
        args.agent, args,
    )


def _coerce(raw: str):
    low = raw.lower()
    if low in {"true", "yes", "on"}:
        return True
    if low in {"false", "no", "off"}:
        return False
    if re.fullmatch(r"-?\d+", raw):
        return int(raw)
    return raw


def cmd_feedback(args: argparse.Namespace) -> int:
    words = list(args.words or [])
    if words[:1] == ["list"]:
        return _emit(
            {"meta": {"source": "who-finder"},
             "results": {"feedback": agentio.read_feedback(args.limit),
                         "path": str(agentio.feedback_path())}},
            args.agent, args,
        )
    text = " ".join(words).strip()
    if not text and not sys.stdin.isatty():
        text = sys.stdin.read().strip()
    if not text:
        return _die(args, E_USAGE, "feedback needs a note",
                    fix='feedback "the compare scenario ranked side b too low"')
    path = agentio.record_feedback(text, context=args.context or "")
    return _emit(
        {"meta": {"source": "who-finder"}, "results": {"recorded": True, "path": str(path)}},
        args.agent, args,
    )


def cmd_signals(args: argparse.Namespace) -> int:
    return _emit({"meta": {"source": "who-finder"}, "results": {"signals": SIGNALS}}, args.agent, args)


def cmd_search(args: argparse.Namespace) -> int:
    """One raw keyword, one source. Debug hatch — find is the primary verb."""
    token = _token()
    if not token:
        return _die(args, E_AUTH, f"missing {ENV_KEY}",
                    fix=f"export {ENV_KEY}=... — the recipient supplies their own key "
                        "from https://scrapecreators.com")
    srcs = _parse_sources(args.sources) or ["youtube"]
    scenario = detect_scenario(args.query, None)
    hits, err, _ = sources.search_step(
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
    return _emit(payload, args.agent, args)


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
    return _emit({"meta": {"source": "who-finder"}, "results": {"entities": rows}}, args.agent, args)


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
    return _emit({"meta": {"source": "who-finder"}, "results": {"entities": rows}}, args.agent, args)


def cmd_show(args: argparse.Namespace) -> int:
    kind, platform, handle = parse_id(args.identity)
    conn = _db(args)
    try:
        ent = db.get_entity(conn, kind, platform, handle)
        if not ent:
            return _die(args, E_NOTFOUND, f"{args.identity} is not in the roster",
                        fix="run list --agent to see stored ids")
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
    return _emit(payload, args.agent, args)


def cmd_mark(args: argparse.Namespace) -> int:
    kind, platform, handle = parse_id(args.identity)
    conn = _db(args)
    try:
        ok = db.mark(conn, kind, platform, handle, args.status)
        conn.commit()
    finally:
        conn.close()
    if not ok:
        return _die(args, E_NOTFOUND, f"{args.identity} is not in the roster",
                    fix="run list --agent to see stored ids")
    return _emit(
        {"meta": {"source": "who-finder"}, "results": {"ok": True, "status": args.status}},
        args.agent,
        args,
    )


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
    # CSV is the payload here, not a JSON envelope, so --deliver routes the
    # sheet itself; --out stays as the plain-file shorthand.
    sink = args.deliver or (f"file:{args.out}" if args.out else None)
    if sink:
        try:
            note = agentio.deliver(text, sink, content_type="text/csv")
        except agentio.DeliveryError as exc:
            return _die(args, agentio.E_DELIVERY, str(exc),
                        fix="use --out <path> or --deliver file:<path>")
        return _emit(
            {"meta": {"source": "who-finder"},
             "results": {"path": note, "rows": len(rows), "format": "csv"}},
            args.agent, argparse.Namespace(agent=args.agent, deliver=None, select=args.select),
        )
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
    return _emit({"meta": {"source": "who-finder"}, "results": {"imported": n}}, args.agent, args)


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
    return _emit({"meta": {"source": "who-finder"}, "results": {"scenarios": rows}}, args.agent, args)


GLOBAL_FLAGS = ("agent", "db", "select", "deliver", "profile")

HELP_WORDS = {"help", "start", "setup", "hello", "hi", "?", "-h", "--help", "usage", "guide"}


VALUE_FLAGS = {"--db", "--select", "--deliver", "--profile", "--icp"}


def _invocation() -> str:
    """How the caller actually reached us, so printed examples are copy-pasteable."""
    script = sys.argv[0] if sys.argv else ""
    if "who_finder" not in script:  # imported, or run under a test harness
        return "who-finder"
    return f"python3 {script}"


def _first_word(raw: list[str]) -> str:
    """First bare word, skipping flags and the values they consume.

    Without the skip, `--profile ghost list` reads 'ghost' as the command.
    """
    skip = False
    for tok in raw:
        if skip:
            skip = False
            continue
        if tok.startswith("-"):
            if tok in VALUE_FLAGS:
                skip = True
            continue
        return tok
    return ""


def _welcome(agent: bool = False) -> int:
    if agent:
        return cmd_agent_context(argparse.Namespace(
            agent=True, select=None, deliver=None, db=None, icp=None
        ))
    print(emit.welcome(
        invocation=_invocation(),
        python=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        key_set=bool(_token()),
        db_path=str(db.default_db()),
        db_exists=db.default_db().exists(),
    ))
    return 0


def _did_you_mean(token: str) -> int:
    """An unrecognised first word is usually a brief someone typed directly.

    argparse's answer is a list of nineteen subcommands and a note that the
    choice was invalid, which does not tell a first-time user that the thing
    they typed is nearly right.
    """
    if " " in token or len(token.split()) > 1:
        print(f'"{token}" looks like what you are searching for, not a command.\n')
        print("Try:")
        print(f'  {_invocation()} find "{token}" --deep 10 --dry-run')
        print("\n(--dry-run previews the searches and their cost without spending anything.)")
        return E_USAGE
    print(f"'{token}' is not a command.\n")
    print(f'Ask in your own words:  {_invocation()} which "{token}"')
    print(f"Or see everything:      {_invocation()} help")
    return E_USAGE


def _restore_leading_globals(args: argparse.Namespace, argv: list[str], commands: set[str]) -> None:
    """Let global flags work before the subcommand as well as after it.

    argparse gives the subparser its own copy of every shared flag, and those
    defaults overwrite whatever the top level already parsed — so
    `--profile x find ...` silently loses the profile. Re-reading only the
    tokens ahead of the subcommand restores them without touching anything the
    subparser genuinely set.
    """
    cut = next((i for i, tok in enumerate(argv) if tok in commands), None)
    if not cut:
        return
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--agent", action="store_true")
    pre.add_argument("--db", default=None)
    pre.add_argument("--select", default=None)
    pre.add_argument("--deliver", default=None)
    pre.add_argument("--profile", default=None)
    leading, _ = pre.parse_known_args(argv[:cut])
    for name in GLOBAL_FLAGS:
        found = getattr(leading, name, None)
        if found in (None, False):
            continue
        if getattr(args, name, None) in (None, False):
            setattr(args, name, found)


def main(argv: list[str] | None = None) -> int:
    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument("--agent", action="store_true", help="JSON envelope on stdout")
    shared.add_argument("--db", default=None, help="sqlite path (default: .who-finder/roster.sqlite)")
    shared.add_argument("--select", default=None, metavar="PATHS",
                        help="comma-separated dotted paths to keep, e.g. "
                             "results.entities.id,results.entities.priority")
    shared.add_argument("--deliver", default=None, metavar="SINK",
                        help="stdout | file:<path> | webhook:<url>")
    shared.add_argument("--profile", default=None, metavar="NAME",
                        help="apply a saved flag set; explicit flags still win")

    deep = argparse.ArgumentParser(add_help=False)
    deep.add_argument("--icp", default=None, help="ICP json path (default: .who-finder/icp.json)")
    deep.add_argument("--cache", default="7d", choices=list(enrich.CACHE_CHOICES),
                      help="reuse a cached profile this old for 0 credits")
    deep.add_argument("--show", type=int, default=12, help="cards in the printed brief")
    deep.add_argument("--full", action="store_true", help="include whole dossiers in --agent JSON")

    p = argparse.ArgumentParser(prog="who-finder", description=__doc__, parents=[shared])
    p.add_argument("--version", action="version", version=f"who-finder {__version__}")
    # Not required: a bare invocation should teach, not raise.
    sub = p.add_subparsers(dest="cmd", required=False)

    ac = sub.add_parser("agent-context", parents=[shared],
                        help="machine-readable description of this whole CLI")
    ac.add_argument("--icp", default=None)
    ac.set_defaults(fn=cmd_agent_context)

    pf = sub.add_parser("profile", parents=[shared], help="save/list/show/delete a flag set")
    pf.add_argument("action", choices=["save", "list", "show", "delete"])
    pf.add_argument("name", nargs="?")
    pf.add_argument("--set", action="append", metavar="KEY=VALUE",
                    help="repeatable; e.g. --set deep=10 --set scenario=people")
    pf.set_defaults(fn=cmd_profile)

    fb = sub.add_parser("feedback", parents=[shared], help="record what surprised you")
    # Free-form words, not a choices= subcommand: `feedback "the note"` is the
    # common call and argparse would otherwise reject the note as a bad choice.
    fb.add_argument("words", nargs="*", metavar="list | NOTE")
    fb.add_argument("--context", default=None, help="the command or brief it happened on")
    fb.add_argument("--limit", type=int, default=20)
    fb.set_defaults(fn=cmd_feedback)

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
    f.add_argument("--dry-run", action="store_true",
                   help="print the exact queries and the credit ceiling, spend nothing")
    f.add_argument("--max-credits", type=int, default=None, metavar="N",
                   help="refuse (exit 8) if the plan could cost more than N")
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

    raw = list(argv if argv is not None else sys.argv[1:])

    # Intercept before argparse: an unknown first word is a teaching moment,
    # not a parse error. Only when no real subcommand appears anywhere.
    if not any(tok in sub.choices for tok in raw):
        first = _first_word(raw)
        if not first or first.lower() in HELP_WORDS:
            return _welcome(agent="--agent" in raw)
        if "--version" not in raw and "-h" not in raw and "--help" not in raw:
            return _did_you_mean(first)

    args = p.parse_args(argv)
    if not getattr(args, "cmd", None):
        return _welcome(agent=getattr(args, "agent", False))
    _restore_leading_globals(args, raw, set(sub.choices))
    if getattr(args, "profile", None):
        try:
            applied = agentio.apply_profile(args, args.profile)
        except KeyError:
            return _die(args, E_NOTFOUND, f"no profile '{args.profile}'",
                        fix="who-finder profile list --agent")
        args._profile_applied = applied
    try:
        return int(args.fn(args) or 0)
    except icp.ConfigError as exc:
        return _die(args, E_CONFIG, str(exc), fix="fix or delete the file, then re-run")
    except sources.http.HTTPError as exc:
        code = E_AUTH if exc.status in {401, 403} else E_API
        return _die(args, code, str(exc),
                    fix="who-finder doctor --agent" if code == E_AUTH else "retry; if it persists the vendor is down")
    except BrokenPipeError:
        return 0
