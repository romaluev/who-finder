"""CLI. The skill runs this; the agent does not reimplement HTTP or ranking.

Two depths:
  find "brief"              discovery only, cheap, one credit per query angle
  find "brief" --deep 10    + a dossier, ICP fit and priority for the top 10

`report` re-renders the deep brief from the local roster for zero credits.

Missing ScrapeCreators is a thinner run, not a refusal. `--dry-run` prints
the planned queries, which backend each step would use, and the ceiling
(often $0). `--cheap` keeps one framing and saves paid credits for enrich.
`--max-credits` refuses an over-budget plan at exit 8 rather than reporting
the overspend afterwards.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import pathlib
import sys
from pathlib import Path

from . import __version__, agentio, auth, contacts, db, emit, enrich, icp, insights, notices, report, sources
from .agentio import E_API, E_AUTH, E_BUDGET, E_CONFIG, E_NOTFOUND, E_USAGE
from .identity import parse_id
from .planner import add_free_extras, apply_cheap, detect_scenario, plan as make_plan
from .scenarios import SCENARIOS, SOURCES
from .which import resolve as which_resolve

ENV_KEY = auth.ENV_KEY

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
    "books-meetings": "profile publishes a Calendly or cal.com link",
    "smb": "under 200 employees",
    "midmarket": "200-1999 employees",
    "enterprise": "2000+ employees",
    "small-audience": "under 10k followers/subscribers",
    "mid-audience": "10k-100k",
    "large-audience": "100k+",
}


COMMAND_HELP = {
    "find": ("detect scenario, plan queries, search, ingest, rank", "1/angle + 1/enriched"),
    "report": ("re-render from the roster; --format writes md/html/pdf/json files", "0"),
    "more": ("the next --limit down the ranking, enriched; no new search",
             "1/new profile, 0 discovery"),
    "enrich": ("dossier + ICP fit for stored entities", "1/entity, 0 cached"),
    "expand": ("similar profiles / employees out of a stored dossier", "0"),
    "setup": ("save ScrapeCreators and optional Brave keys so they survive a new terminal", "0"),
    "doctor": ("backends, roster path, credits; ready vs ready-thin", "0, or 1 with --probe"),
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
    "contacts": ("public emails and links already on stored profiles", "0"),
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
    return auth.token()


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
        db.upsert_hit(conn, h, h.get("found_by") or query, ts, scenario)
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


def _estimate(plan, depth: int, *, cheap: bool = False, has_sc: bool = False, has_brave: bool = False) -> dict:
    """Credit cost of a plan before any of it is spent.

    A ScrapeCreators angle is one credit; DuckDuckGo, Brave, HN, and yt-dlp
    are free. Enrichment is one per entity and only exists when ScrapeCreators
    is present. Cached profile reads cost nothing, so this is a ceiling.
    """
    steps = []
    discovery = 0
    for s in plan.steps:
        pred = sources.predict_backend(
            s.source, has_sc=has_sc, has_brave=has_brave, cheap=cheap
        )
        discovery += int(pred["credits"])
        steps.append(
            {
                "source": s.source,
                "label": s.label,
                "query": s.query,
                "weight": s.weight,
                "side": s.side,
                "backend": pred["backend"],
                "credits": pred["credits"],
            }
        )
    enrichment = max(0, int(depth or 0)) if has_sc else 0
    total = discovery + enrichment
    return {
        "discovery": discovery,
        "enrichment_max": enrichment,
        "total_max": total,
        "note": (
            "all free — public search only; no profile pages fetched"
            if total == 0
            else "enrichment is a ceiling: cached profiles cost 0"
        ),
        "steps": steps,
        "thin": not has_sc,
    }


def _already_enriched(conn, row: dict) -> bool:
    stored = db.get_dossier(conn, row["kind"], row["platform"], row["handle"])
    return bool(stored and stored.get("enriched"))


def _score_rows(conn, rows: list[dict], dossiers: dict[str, dict], cfg: dict, ts: str) -> dict[str, dict]:
    """Attach fit + priority to every row and persist the dossier. Costs nothing."""
    full: dict[str, dict] = {}
    for r in rows:
        ident = _ident(r)
        d = dossiers.get(ident) or enrich.shallow(r)
        contacts.attach(d)
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


def cmd_setup(args: argparse.Namespace) -> int:
    """Save a key to a file so the next terminal still works.

    `export` is forgotten when the window closes. That is the usual reason a
    clone looks broken the next morning. This writes ~/.who-finder/key (or
    $WHO_FINDER_HOME/key) at mode 0600 and never prints the secret back.
    Brave goes in keys.json via `--brave`.
    """
    which = "brave" if getattr(args, "brave", False) else "scrapecreators"
    if getattr(args, "clear", False):
        gone = auth.clear(which)
        label = "Brave key" if which == "brave" else "saved key"
        payload = {
            "meta": {"source": "who-finder", "version": __version__},
            "table": f"Removed the {label}." if gone else f"No {label} file to remove.",
            "results": {"cleared": gone, "name": which, "path": str(auth.keys_file() if which == "brave" else auth.key_file())},
        }
        return _emit(payload, args.agent, args)

    key = (args.key or "").strip()
    if not key:
        token, source = auth.read()
        brave, brave_src = auth.read_named("brave")
        lines = [
            "who-finder setup — keys are optional. Without one you still get a thinner shortlist.",
            "",
            f"  ScrapeCreators  {auth.key_file()}",
            f"  now             {'set (' + source + ')' if token else 'not set yet'}",
            f"  Brave           {'set (' + brave_src + ')' if brave else 'not set (optional)'}",
            "",
            "Full profiles and YouTube/TikTok engagement need ScrapeCreators:",
            f"  {_invocation()} setup YOUR_KEY",
            "  get one at https://scrapecreators.com (your own, not a teammate's).",
            "",
            "Optional, free-tier web search that spends no ScrapeCreators credits:",
            f"  {_invocation()} setup --brave YOUR_BRAVE_KEY",
            "",
            "The keys stay on this machine. Do not commit them, do not Slack them.",
        ]
        return _emit(
            {
                "meta": {"source": "who-finder", "version": __version__},
                "table": "\n".join(lines),
                "results": {
                    "key": "set" if token else "missing",
                    "key_source": source,
                    "brave": "set" if brave else "missing",
                    "brave_source": brave_src,
                    "path": str(auth.key_file()),
                    "url": "https://scrapecreators.com",
                },
            },
            args.agent, args,
        )
    try:
        path = auth.save(key, name=which)
    except ValueError as exc:
        hint = "https://brave.com/search/api/" if which == "brave" else "https://scrapecreators.com"
        return _die(args, E_USAGE, str(exc), fix=f"get a key at {hint} and paste the whole thing")
    label = "Brave key" if which == "brave" else "Key"
    lines = [
        f"{label} saved. It will still be here the next time you open a terminal.",
        f"  {path}",
        "",
        "Next:",
        f"  {_invocation()} doctor",
        f'  {_invocation()} find "founders of AI video tools" --deep 10 --dry-run',
        "",
        "Or just ask your assistant:  Find me the top 10 people building AI video tools.",
    ]
    return _emit(
        {
            "meta": {"source": "who-finder", "version": __version__},
            "table": "\n".join(lines),
            "results": {"saved": True, "name": which, "path": str(path), "key_source": f"file:{path}"},
        },
        args.agent, args,
    )


def cmd_doctor(args: argparse.Namespace) -> int:
    token = _token()
    path = Path(args.db) if args.db else db.default_db()
    icp_path = icp.config_path(getattr(args, "icp", None))
    caps = auth.capabilities()
    payload = {
        "meta": {"source": "who-finder", "version": __version__},
        # `table` is what a human sees; agents read `results`. Rendered at the
        # end of the command so it reflects the probe and credit results.
        "results": {
            "state": "ready" if token else "ready-thin",
            "key": "set" if token else "missing",
            "key_source": auth.read()[1],
            "env": ENV_KEY,
            "thin_available": True,
            "db": str(path),
            "db_exists": path.exists(),
            "icp": str(icp_path),
            "icp_exists": icp_path.exists(),
            "scenarios": list(SCENARIOS),
            "sources": list(SOURCES),
            "backends": caps,
            "contact_goat": {
                "installed": bool(contacts.contact_goat_bin()),
                "bin": contacts.contact_goat_bin(),
                "note": "optional. emails we print are only those published on a "
                        "public profile. guessed work emails are contact-goat's job, "
                        "and only if the user asked.",
            },
        },
    }
    if not token:
        payload["results"]["fix"] = (
            f"thin path is ready. for full profiles: "
            f"who-finder setup YOUR_KEY   or   export {ENV_KEY}=...  "
            "(your own key from https://scrapecreators.com)"
        )
        payload["results"]["api"] = "untested"
        payload["table"] = emit.doctor_card(payload["results"])
        return _emit(payload, args.agent, args)
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
        payload["results"]["state"] = "auth-failed" if exc.status in {401, 403} else "ready-thin"
        payload["results"]["thin_available"] = True
        payload["results"]["fix"] = (
            "ScrapeCreators rejected the key, but the thin public-search path "
            "is still available. setup a new key for full profiles, or run find anyway."
            if exc.status in {401, 403}
            else "ScrapeCreators is down; thin public-search path is still available."
        )
        payload["table"] = emit.doctor_card(payload["results"])
        return _emit(payload, args.agent, args)
    except Exception as exc:
        payload["results"]["credits_error"] = str(exc)
        payload["results"]["api"] = "error"
        payload["results"]["state"] = "ready-thin"
        payload["results"]["thin_available"] = True
        payload["results"]["fix"] = "ScrapeCreators could not be reached; thin path is still available."
        payload["table"] = emit.doctor_card(payload["results"])
        return _emit(payload, args.agent, args)
    if getattr(args, "probe", False):
        try:
            hits = sources.youtube(token, "youtube", 3, "month")
            payload["results"]["probe"] = {"youtube_hits": len(hits), "ok": True}
        except Exception as exc:
            payload["results"]["probe"] = {"ok": False, "error": str(exc)}
            payload["results"]["state"] = "ready-thin"
            payload["results"]["thin_available"] = True
            payload["table"] = emit.doctor_card(payload["results"])
            return _emit(payload, args.agent, args)
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
    brave = auth.brave_token()
    cheap = bool(getattr(args, "cheap", False))
    n_frames = 1 if cheap else max(1, int(getattr(args, "frames", 3) or 1))
    p = make_plan(
        args.brief,
        scenario=forced,
        extra_sources=extra,
        extra_frames=getattr(args, "frame", None),
        n_frames=n_frames,
    )
    if cheap:
        apply_cheap(p, extra)
    add_free_extras(p)
    if not p.steps:
        return _die(args, E_USAGE, "planner produced zero steps for this brief",
                    fix="give a brief with a topic in it, or force one with --scenario")

    depth = max(0, int(args.deep or 0))
    est = _estimate(p, depth, cheap=cheap, has_sc=bool(token), has_brave=bool(brave))

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
                         "scenario": p.scenario, "kind": p.kind, "credits_spent": 0,
                         "thin": est["thin"], "cheap": cheap},
                "plan": p.as_dict(),
                "table": emit.plan_card(p, est, depth=depth, icp_name=icp.load(args.icp, topic=p.topic).get("name", "generic")),
                "results": {"estimate": est, "steps": est["steps"]},
            },
            args.agent, args,
        )

    entities, hits, errors, source_status = sources.run_plan(
        token, p, args.limit, args.freshness, cheap=cheap, brave_token=brave
    )
    dossiers: dict[str, dict] = {}
    spent = sum(int(s.get("credits") or 0) for s in source_status)

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

        if depth and token:
            queue = out[:depth] if not args.new_only else [r for r in out if r.get("novelty") == "new"][:depth]
            if cheap:
                queue = [r for r in queue if not _already_enriched(conn, r)]
            if queue:
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
    thin = not token or not any(s.get("backend") == "scrapecreators" for s in source_status)
    ins = insights.build(
        rows,
        [full[_ident(r)] for r in rows if _ident(r) in full],
        scenario=p.scenario,
        topic=p.topic,
        n_new=n_new,
        n_known=n_known,
        source_status=source_status,
        errors=errors,
        thin=thin,
    )
    if getattr(args, "format", "text") != "text":
        # A file report covers exactly the rows that were enriched, since an
        # unenriched row has nothing to fill a page with.
        shown = rows[: depth or args.show]
        conn2 = _db(args)
        try:
            hits_by_id = {_ident(r): db.hits_for(conn2, r["kind"], r["platform"], r["handle"])
                          for r in shown}
        finally:
            conn2.close()
        found_by: dict[str, list[str]] = {}
        for h in hits:
            q = h.get("found_by")
            if q:
                found_by.setdefault(_ident(h), [])
                if q not in found_by[_ident(h)]:
                    found_by[_ident(h)].append(q)
        return _document(
            args, shown, full, ins,
            brief=args.brief, scenario=p.scenario, topic=p.topic,
            n_new=n_new, n_known=n_known, steps=step_labels,
            frames=[f"{f['label']}: {f['topic']} — {f['why']}" for f in (p.frames or [])],
            icp_name=cfg.get("name", "generic"), credits=spent,
            source_status=source_status, hits_by_id=hits_by_id, found_by=found_by,
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
            "thin": thin,
            "cheap": cheap,
            "mode": "thin" if thin else "full",
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
    """Re-render from the roster. Zero credits, zero network.

    Also the document generator: the same stored data becomes a terminal brief,
    a Markdown file, a styled HTML page, or a PDF, so a shortlist can be handed
    to someone who will never open a terminal.
    """
    offset = max(0, int(getattr(args, "offset", 0) or 0))
    conn = _db(args)
    try:
        rows = db.list_ranked(
            conn,
            status=args.status,
            kind=args.kind,
            query=args.query,
            band=args.band,
            limit=args.limit + offset,
        )
        hits_by_id = {}
        if getattr(args, "format", "text") != "text":
            for r in rows[offset:]:
                hits_by_id[_ident(r)] = db.hits_for(
                    conn, r.get("kind"), r.get("platform"), r.get("handle")
                )
    finally:
        conn.close()
    rows = rows[offset:]
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

    fmt = getattr(args, "format", "text")
    if fmt != "text":
        return _document(
            args, rows, full, ins,
            brief=args.query or f"Shortlist ({args.status or 'all'})",
            scenario="report", topic=args.query or "roster",
            n_new=n_new, n_known=len(rows) - n_new, steps=[], frames=[],
            icp_name=(rows[0].get("icp") if rows else "") or "generic",
            credits=0, source_status=[], hits_by_id=hits_by_id, offset=offset,
        )

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


def _document(args, rows, dossiers, ins, **kw) -> int:
    """Build the report document once and write every requested format.

    `--format md,pdf` writes both from one build, so the PDF can never describe
    a different shortlist than the Markdown beside it.
    """
    fmts = [f.strip() for f in str(getattr(args, "format", "md")).split(",") if f.strip()]
    bad = [f for f in fmts if f not in report.FORMATS]
    if bad:
        return _die(args, E_USAGE, f"unknown report format {bad[0]!r}",
                    fix=f"use one of: {', '.join(report.FORMATS)}, or text for the terminal")

    blocks = report.build(rows, dossiers, ins, **kw)
    title = kw.get("brief") or "who-finder report"
    stem = getattr(args, "out", None) or _slug(title)
    stem = re.sub(r"\.(md|html|pdf|json)$", "", str(stem))

    written = []
    for fmt in fmts:
        body = report.render(blocks, fmt, title=title)
        path = pathlib.Path(f"{stem}.{fmt}").expanduser()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(body, bytes):
                path.write_bytes(body)
            else:
                path.write_text(body, encoding="utf-8")
        except OSError as exc:
            return _die(args, E_DELIVERY, f"could not write {path}: {exc}",
                        fix="pick a writable --out path")
        written.append({"format": fmt, "path": str(path.resolve()),
                        "bytes": path.stat().st_size})

    lines = [f"Wrote {len(written)} file{'' if len(written) == 1 else 's'} "
             f"covering {len(rows)} {'person' if len(rows) == 1 else 'people'}:", ""]
    for w in written:
        lines.append(f"  {w['path']}   ({w['bytes'] // 1024 or 1} KB)")
    if any(w["format"] == "html" for w in written):
        lines += ["", "Open the .html in a browser and print to PDF if you want the",
                  "styled version — the .pdf here is generated without a browser."]
    return _emit(
        {
            "meta": {"source": "who-finder", "version": __version__, "credits_spent": 0},
            "table": "\n".join(lines),
            "results": {"written": written, "count": len(rows),
                        "offset": kw.get("offset", 0)},
        },
        args.agent, args,
    )


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")
    return f"who-finder-{s[:48] or 'report'}"


def cmd_more(args: argparse.Namespace) -> int:
    """Extend a shortlist without searching again.

    The roster usually holds far more candidates than the first report showed,
    because discovery returns everyone and enrichment only pays for the top
    slice. `more` walks further down that existing ranking and enriches the
    next batch, so asking for ten more costs enrichment only.
    """
    token = _token()
    offset = max(0, int(args.offset or 0))
    ts = db.now()
    conn = _db(args)
    try:
        rows = db.list_ranked(conn, status=args.status, kind=args.kind,
                              query=args.query, band=None, limit=offset + args.limit)
        batch = rows[offset:]
        if not batch:
            conn.close()
            return _die(args, E_NOTFOUND,
                        f"nothing left below rank {offset} for this filter",
                        fix="run find again with a wider brief, or drop --query")

        spent = 0
        errors: list[str] = []
        todo = [r for r in batch if not r.get("enriched")]
        if todo and not token:
            conn.close()
            return _die(args, E_AUTH,
                        f"{len(todo)} of these have no profile yet and {ENV_KEY} is unset",
                        fix=f"export {ENV_KEY}=... , or use `report --offset` to page "
                            "through what is already stored")
        cfg = icp.load(args.icp, topic=args.query or "")
        dossiers: dict[str, dict] = {}
        if todo:
            dossiers, errors, spent = enrich.enrich_many(
                token, todo, limit=len(todo), cache=args.cache
            )
        for r in batch:
            r["novelty"] = "new" if r.get("status") == "new" else "known"
        full = _score_rows(conn, batch, dossiers, cfg, ts)
        conn.commit()
        hits_by_id = {_ident(r): db.hits_for(conn, r["kind"], r["platform"], r["handle"])
                      for r in batch}
    finally:
        try:
            conn.close()
        except Exception:
            pass

    batch = icp.rank(batch)
    n_new = sum(1 for r in batch if r.get("novelty") == "new")
    ins = insights.build(batch, list(full.values()), scenario="report",
                         topic=args.query or "roster", n_new=n_new,
                         n_known=len(batch) - n_new, source_status=[], errors=errors)
    if getattr(args, "format", "text") != "text":
        return _document(
            args, batch, full, ins,
            brief=args.query or "Shortlist (continued)", scenario="report",
            topic=args.query or "roster", n_new=n_new, n_known=len(batch) - n_new,
            steps=[], frames=[], icp_name=cfg.get("name", "generic"),
            credits=spent, source_status=[], hits_by_id=hits_by_id, offset=offset,
        )
    return _emit(
        {
            "meta": {"source": "who-finder", "version": __version__,
                     "credits_spent": spent, "offset": offset},
            "table": emit.brief(batch, full, ins, scenario="report",
                                topic=args.query or "roster", n_new=n_new,
                                n_known=len(batch) - n_new, steps=[],
                                icp_name=cfg.get("name", "generic"),
                                enriched_n=sum(1 for r in batch if r.get("enriched")),
                                credits=spent, show=len(batch)),
            "results": {"insights": ins, "entities": [_compact(r) for r in batch]},
        },
        args.agent, args,
    )


def _merge_dossier(r: dict) -> dict:
    d = dict(r.get("payload") or {})
    d.setdefault("id", _ident(r))
    for k in ("headline", "headline_source", "audience", "audience_kind"):
        d[k] = r.get(k) or d.get(k)
    d["signals"] = r.get("signals") or d.get("signals") or []
    d["topics"] = r.get("topics") or d.get("topics") or []
    d["enriched"] = bool(r.get("enriched"))
    d["fit_score"] = r.get("fit_score")
    d["fit_band"] = r.get("fit_band")
    d["fit_reasons"] = r.get("fit_reasons") or []
    return d


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
                "key_file": str(auth.key_file()),
                "key_source": auth.read()[1],
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
                    "free_backends": ["ddg", "brave", "hn", "ytdlp"],
                    "enrichment_per_entity": 1,
                    "cached_profile": 0,
                    "report_expand_show_export_mark": 0,
                    "preview": "find <brief> --dry-run --agent",
                    "thin_without_key": True,
                },
                "doctor_states": ["ready", "ready-thin", "auth-failed", "error"],
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
    srcs = _parse_sources(args.sources) or ["youtube"]
    scenario = detect_scenario(args.query, None)
    hits, err, _ = sources.search_step(
        token, srcs[0], args.query, args.limit, args.freshness, scenario,
        brave_token=auth.brave_token(),
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
        for r in rows:
            c = contacts.harvest(contacts.from_row(r))
            r["emails"] = "; ".join(c["emails"])
            r["website"] = next((l["url"] for l in c["links"] if l["kind"] == "website"), "")
            r["calendly"] = next(
                (l["url"] for l in c["links"] if l["kind"] in {"calendly", "calendar"}), ""
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


def cmd_contacts(args: argparse.Namespace) -> int:
    """Public addresses already on stored profiles. Zero credits, no guessing."""
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
    finally:
        conn.close()
    people = []
    for r in rows:
        d = contacts.from_row(r)
        c = contacts.harvest(d)
        people.append({
            "id": _ident(r),
            "name": r.get("name") or d.get("name"),
            "emails": c["emails"],
            "links": c["links"],
            "reach": contacts.reach_line(c),
            "takes_meetings": c["takes_meetings"],
            "company": notices.employer(r, d),
        })
    goat = contacts.contact_goat_bin()
    handoff = []
    if goat and people:
        top = people[0]
        handoff = contacts.handoff_lines(top.get("name") or "", top.get("company") or "")
    payload = {
        "meta": {"source": "who-finder", "version": __version__, "credits_spent": 0},
        "table": emit.contacts_card(people, goat=goat),
        "results": {
            "n": len(people),
            "n_with_email": sum(1 for p in people if p["emails"]),
            "n_book_meetings": sum(1 for p in people if p["takes_meetings"]),
            "people": people,
            "contact_goat": {"installed": bool(goat), "bin": goat, "handoff": handoff},
            "note": "only addresses and URLs published on a public profile. "
                    "do not invent jane@acme.com. if the user wants a work email "
                    "or a warm intro and contact-goat is installed, ask before spending.",
        },
    }
    return _emit(payload, args.agent, args)


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

HELP_WORDS = {"help", "start", "hello", "hi", "?", "-h", "--help", "usage", "guide"}


VALUE_FLAGS = {"--db", "--select", "--deliver", "--profile", "--icp"}


def _invocation() -> str:
    """How the caller actually reached us, so printed examples are copy-pasteable."""
    script = sys.argv[0] if sys.argv else ""
    name = Path(script).name
    if name == "who-finder":
        return script if script.startswith(("./", "/")) else "./who-finder"
    if "who_finder" in script:
        return f"python3 {script}"
    return "who-finder"


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

    su = sub.add_parser("setup", parents=[shared],
                        help="save your API key so it survives a new terminal")
    su.add_argument("key", nargs="?", help="the key from scrapecreators.com (or Brave with --brave)")
    su.add_argument("--brave", action="store_true", help="save a Brave Search key instead")
    su.add_argument("--clear", action="store_true", help="forget the saved key file")
    su.set_defaults(fn=cmd_setup)

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
    f.add_argument("--frames", type=int, default=3, metavar="N",
                   help="ask the question N ways (default 3). each extra frame is 1 search")
    f.add_argument("--frame", action="append", default=None, metavar="PHRASE",
                   help="another way to say the topic, e.g. --frame 'generative creative'. repeatable")
    f.add_argument("--format", default="text",
                   help=f"text (default) or a file report: {', '.join(report.FORMATS)} (comma-separated)")
    f.add_argument("--out", default=None, metavar="PATH",
                   help="output path without extension; defaults to a slug of the brief")
    f.add_argument("--dry-run", action="store_true",
                   help="print the exact queries and the credit ceiling, spend nothing")
    f.add_argument("--max-credits", type=int, default=None, metavar="N",
                   help="refuse (exit 8) if the plan could cost more than N")
    f.add_argument("--cheap", action="store_true",
                   help="one framing, skip TikTok/Instagram unless named, save ScrapeCreators for enrich")
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
    rp.add_argument("--limit", type=int, default=25, help="how many to include (the 'top 10')")
    rp.add_argument("--offset", type=int, default=0,
                    help="skip the first N of the ranking, to page past a report already sent")
    rp.add_argument("--format", default="text",
                    help=f"text (default) or files: {', '.join(report.FORMATS)} (comma-separated)")
    rp.add_argument("--out", default=None, metavar="PATH", help="output path without extension")
    rp.set_defaults(fn=cmd_report)

    mo = sub.add_parser("more", parents=[shared, deep],
                        help="the next N down the ranking, enriched — no new search")
    mo.add_argument("--offset", type=int, default=10,
                    help="rank to resume from; pass the count you have already seen")
    mo.add_argument("--limit", type=int, default=10, help="how many more to add")
    mo.add_argument("--status", default=None)
    mo.add_argument("--kind", default=None, choices=["person", "company"])
    mo.add_argument("--query", default=None, help="restrict to a stored query, as in report")
    mo.add_argument("--format", default="text",
                    help=f"text (default) or files: {', '.join(report.FORMATS)}")
    mo.add_argument("--out", default=None, metavar="PATH")
    mo.set_defaults(fn=cmd_more)

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

    ct = sub.add_parser("contacts", parents=[shared],
                        help="public emails and links already on stored profiles")
    ct.add_argument("--status", default="new")
    ct.add_argument("--query", default=None)
    ct.add_argument("--kind", default=None, choices=["person", "company"])
    ct.add_argument("--band", default=None, choices=list(icp.BANDS))
    ct.add_argument("--limit", type=int, default=25)
    ct.set_defaults(fn=cmd_contacts)

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
