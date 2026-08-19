"""CLI. The skill runs this; the agent does not reimplement scoring or HTTP."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import (
    __version__, agentio, auth, calibration, capabilities, db, economy, emit, export,
    icp, longlist, pipeline, playbook, portfolio as portfoliom, report, scoring,
)
from .agentio import E_API, E_AUTH, E_BUDGET, E_CONFIG, E_HYGIENE, E_NOTFOUND, E_USAGE
from .classifiers import agent as agentclf
from .collectors.base import BudgetError, HygieneError
from .collectors.unipile import record_ack
from .which import resolve as which_resolve

COMMAND_HELP = {
    "ingest": ("longlist from CSV, Clay export, who-finder, public search, or a URL", "0, or Clay/BD"),
    "collect": ("lite (public → Clay → Bright Data) or deep (engagers); --cheap skips invoices", "0, or vendor"),
    "classify": ("rule floor; optional --llm or --emit-batch / --apply-batch", "0, or LLM"),
    "rate": ("classify + score + price whatever is stored; works at rung 0", "0"),
    "report": ("summary then a page per creator; --format md,html,pdf,json", "0"),
    "portfolio": ("pick a set under --budget, penalise overlap", "0"),
    "export": ("CSV handoff — cannot emit engager PII", "0"),
    "show": ("one creator + latest score + price assumptions", "0"),
    "list": ("stored creators", "0"),
    "pilot": ("ingest consented analytics or a paid-pilot readout", "0"),
    "calibrate": ("refit k; flip estimated→calibrated at R²≥0.6 over ≥30", "0"),
    "prune": ("drop raw engager rows older than 90 days", "0"),
    "setup": ("save a named key; record the dedicated collection account", "0"),
    "doctor": ("rung, backends, what to connect next", "0"),
    "which": ("map a capability phrase to a command", "0"),
    "agent-context": ("machine-readable description of this whole CLI", "0"),
    "icp": ("show or write the ICP file", "0"),
    "shortlist": ("promote top decile / above threshold to shortlist", "0"),
    "profile": ("save/list/show/delete a reusable flag set", "0"),
    "feedback": ("record what surprised you", "0"),
}

HELP_WORDS = {"help", "--help", "-h"}


def _invocation() -> str:
    return "creator-rating"


def _command_index() -> list[dict]:
    return [{"command": n, "does": d, "cost": c} for n, (d, c) in COMMAND_HELP.items()]


def _emit(payload: dict, agent: bool, args: argparse.Namespace | None = None) -> int:
    return agentio.emit(
        payload, agent=agent,
        sink=getattr(args, "deliver", None),
        spec=getattr(args, "select", None),
    )


def _die(args: argparse.Namespace, code: int, message: str, fix: str = "", **extra) -> int:
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


def _rung_state(conn) -> tuple[int, str, dict]:
    caps = auth.capabilities()
    n_posts = conn.execute("SELECT COUNT(*) AS n FROM posts").fetchone()["n"]
    n_eng = conn.execute("SELECT COUNT(*) AS n FROM engagements").fetchone()["n"]
    n_pil = conn.execute("SELECT COUNT(*) AS n FROM pilots").fetchone()["n"]
    n_video = conn.execute(
        "SELECT COUNT(*) AS n FROM posts WHERE source IN ('who-finder','ytdlp','public')"
    ).fetchone()["n"]
    rung = capabilities.detect_rung(
        caps, has_posts=n_posts > 0, has_engagers=n_eng > 0,
        has_pilots=n_pil > 0, has_video_hits=n_video > 0,
    )
    return rung, capabilities.rung_label(rung), caps


def cmd_doctor(args: argparse.Namespace) -> int:
    path = Path(args.db) if args.db else db.default_db()
    conn = _db(args)
    rung, label, caps = _rung_state(conn)
    rows = pipeline.assemble_report_rows(conn, limit=20)
    nxt = []
    if rows:
        nxt = rows[0].get("connect_next") or []
        # Recompute from first creator's metrics if stored
        from .features.provenance import unpack
        if rows[0].get("metrics"):
            nxt = capabilities.what_to_connect(rows[0]["metrics"], scoring.get_preset(), caps)
    else:
        nxt = capabilities.what_to_connect({}, scoring.get_preset(), caps)
    results = {
        "state": "ready" if rung >= 2 else "ready-thin",
        "rung": rung,
        "label": label,
        "thin_available": True,
        "db": str(path),
        "db_exists": path.exists(),
        "icp": str(icp.config_path(getattr(args, "icp", None))),
        "backends": caps,
        "next": nxt,
        "economy": economy.card(caps),
        "guides": {
            "start": "docs/start.md",
            "connect": "docs/connect.md",
            "no_keys": "docs/no-keys.md",
            "ask": "docs/ask.md",
            "economy": "docs/economy.md",
        },
    }
    payload = {
        "meta": {"source": "creator-rating", "version": __version__},
        "results": results,
        "table": emit.doctor_card(results),
    }
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
    payload = {
        "meta": {"source": "creator-rating", "version": __version__},
        "table": "\n".join(lines),
        "results": {
            "capability": args.capability,
            "matched": bool(hit.get("matched")),
            "run": hit["run"],
            "note": hit.get("note") or "",
        },
    }
    _emit(payload, args.agent, args)
    return 0 if hit.get("matched") else 2


def cmd_setup(args: argparse.Namespace) -> int:
    if getattr(args, "collection_account", None) or getattr(args, "brand_account", None):
        data = {}
        if args.collection_account:
            data["collection_account"] = args.collection_account
        if args.brand_account:
            data["brand_account"] = args.brand_account
        auth.write_config(data)
    if getattr(args, "i_understand", False):
        conn = _db(args)
        record_ack(conn, db.now())
        conn.commit()
    if getattr(args, "clear", False):
        name = args.backend or "brightdata"
        gone = auth.clear(name)
        return _emit({"meta": {"source": "creator-rating"}, "results": {"cleared": gone, "name": name},
                      "table": f"{'cleared' if gone else 'nothing to clear'} {name}"},
                     args.agent, args)
    if args.key:
        name = args.backend or "brightdata"
        try:
            path = auth.save(args.key, name)
        except ValueError as exc:
            return _die(args, E_USAGE, str(exc), fix="docs/connect.md")
        return _emit({"meta": {"source": "creator-rating"},
                      "results": {"saved": name, "path": str(path)},
                      "table": f"Key saved ({name}) → {path}"}, args.agent, args)
    if not args.key and not getattr(args, "i_understand", False) and not getattr(args, "collection_account", None):
        return _die(args, E_USAGE, "setup needs a key or --collection-account / --i-understand",
                    fix="setup KEY --backend clay")
    return _emit({"meta": {"source": "creator-rating"}, "results": {"ok": True},
                  "table": "config updated"}, args.agent, args)


def cmd_ingest(args: argparse.Namespace) -> int:
    conn = _db(args)
    ts = db.now()
    try:
        if args.csv:
            result = longlist.from_csv(conn, args.csv, ts, source=args.source or "csv")
        elif args.clay:
            result = longlist.from_clay(conn, args.clay, ts)
        elif args.who_finder:
            text = Path(args.who_finder).expanduser().read_text(encoding="utf-8")
            result = longlist.from_who_finder(conn, text, ts)
        elif args.url:
            result = longlist.from_manual(
                conn, url=args.url, name=args.name or "", headline=args.headline or "",
                followers=args.followers or 0, about=args.about or "", ts=ts,
            )
        elif args.search or args.keyword:
            result = longlist.from_search(
                conn, args.search or args.keyword, ts,
                limit=args.limit, cheap=bool(args.cheap) or not args.keyword,
            )
        else:
            return _die(args, E_USAGE,
                        "ingest needs --csv, --clay, --who-finder, --url, or --search",
                        fix="ingest --clay export.csv   or   ingest --csv creators.csv")
    except ValueError as exc:
        return _die(args, E_USAGE, str(exc), fix="pass a profile url")
    conn.commit()
    table = f"ingested {result['n']} ({result['n_new']} new, {result['n_known']} known)"
    return _emit({"meta": {"source": "creator-rating"}, "results": result, "table": table},
                 args.agent, args)


def cmd_collect(args: argparse.Namespace) -> int:
    conn = _db(args)
    ts = db.now()
    ids = list(args.identity or [])
    if not ids:
        ids = [c["id"] for c in db.list_creators(conn, status=args.status, limit=args.limit)]
    out = []
    try:
        for cid in ids:
            if args.deep:
                out.append(pipeline.collect_deep(
                    conn, cid, ts, i_understand=bool(args.i_understand),
                    max_spend=args.max_spend, sleep=not args.no_sleep,
                ))
            else:
                out.append(pipeline.collect_lite(
                    conn, cid, ts, max_spend=args.max_spend, cheap=bool(args.cheap),
                ))
    except HygieneError as exc:
        return _die(args, E_HYGIENE, str(exc), fix="docs/connect.md#engager-source")
    except BudgetError as exc:
        return _die(args, E_BUDGET, str(exc), fix="raise --max-spend or collect fewer")
    conn.commit()
    return _emit({"meta": {"source": "creator-rating"}, "results": {"runs": out},
                  "table": f"collected {len(out)} creators"}, args.agent, args)


def cmd_classify(args: argparse.Namespace) -> int:
    conn = _db(args)
    ts = db.now()
    if args.emit_batch:
        posts = []
        for c in db.list_creators(conn, limit=args.limit):
            posts.extend(db.posts_for(conn, c["id"], limit=40))
        path = agentclf.emit_batch(posts, args.emit_batch)
        return _emit({"meta": {"source": "creator-rating"},
                      "results": {"path": str(path), "n": len(posts)},
                      "table": f"wrote {len(posts)} items → {path}"}, args.agent, args)
    if args.apply_batch:
        items = agentclf.apply_batch(args.apply_batch)
        for item in items:
            db.upsert_topic(conn, item, ts)
        conn.commit()
        return _emit({"meta": {"source": "creator-rating"},
                      "results": {"n": len(items)},
                      "table": f"applied {len(items)} agent classifications"}, args.agent, args)
    n = 0
    for c in db.list_creators(conn, limit=args.limit):
        n += pipeline.classify_creator(conn, c["id"], ts, use_llm=bool(args.llm))
    conn.commit()
    return _emit({"meta": {"source": "creator-rating"}, "results": {"n": n},
                  "table": f"classified {n} posts"}, args.agent, args)


def _rate_rows(conn, args) -> list[dict]:
    ts = db.now()
    pipeline.score_all(conn, ts, preset=args.preset, limit=args.limit)
    conn.commit()
    return pipeline.assemble_report_rows(conn, preset=args.preset, limit=args.limit)


def cmd_rate(args: argparse.Namespace) -> int:
    conn = _db(args)
    ts = db.now()
    ids: list[str] = []
    if getattr(args, "csv", None):
        ids = longlist.from_csv(conn, args.csv, ts).get("ids") or []
        conn.commit()
    if getattr(args, "who_finder", None):
        text = Path(args.who_finder).expanduser().read_text(encoding="utf-8")
        ids = longlist.from_who_finder(conn, text, ts).get("ids") or []
        conn.commit()
    if not getattr(args, "no_collect", False):
        if not ids:
            ids = [c["id"] for c in db.list_creators(conn, limit=args.limit)]
        for cid in ids:
            pipeline.collect_lite(
                conn, cid, ts, cheap=bool(getattr(args, "cheap", False)),
            )
            pipeline.classify_creator(conn, cid, ts)
            conn.commit()
    rows = _rate_rows(conn, args)
    rung, label, _ = _rung_state(conn)
    table = emit.table(rows, preset=args.preset, rung_label=label, n=len(rows))
    if getattr(args, "format", "text") != "text":
        return _document(args, conn, rows)
    payload = {
        "meta": {"source": "creator-rating", "version": __version__, "rung": rung},
        "table": table,
        "results": {
            "n": len(rows),
            "rung": rung,
            "label": label,
            "creators": [_compact(r) for r in rows],
        },
    }
    return _emit(payload, args.agent, args)


def _compact(r: dict) -> dict:
    pr = r.get("price")
    return {
        "id": r.get("id"),
        "name": r.get("name"),
        "url": r.get("url"),
        "tier": r.get("tier"),
        "creator_score": r.get("creator_score"),
        "social": r.get("social"),
        "engagement": r.get("engagement"),
        "interest": r.get("interest"),
        "confidence": r.get("confidence"),
        "used_points": r.get("used_points"),
        "next_action": r.get("next_action"),
        "gates": r.get("gates"),
        "price": ({k: pr[k] for k in (
            "fair", "open", "walk_away", "cpm_icp", "icp_impressions",
            "assumptions", "source", "do_not_buy", "floor_driven", "interpret",
        ) if k in pr} if pr else None),
        "connect_next": r.get("connect_next") or [],
    }


def _document(args, conn, rows) -> int:
    fmts = [f.strip() for f in str(getattr(args, "format", "md")).split(",") if f.strip()]
    bad = [f for f in fmts if f not in report.FORMATS]
    if bad:
        return _die(args, E_USAGE, f"unknown report format {bad[0]!r}",
                    fix=f"use one of: {', '.join(report.FORMATS)}")
    rung, label, caps = _rung_state(conn)
    pairs, kind = pipeline.overlap_pairs(conn, rows)
    names = {r["id"]: r.get("name") or r["id"] for r in rows}
    notices = playbook.of_set(pairs, names)
    for r in rows:
        notices.extend(playbook.of_one(
            r.get("name") or r["id"], r["id"], r.get("metrics") or {},
            social=r.get("social"), engagement=r.get("engagement"), interest=r.get("interest"),
        ))
    picked = None
    if getattr(args, "budget", None):
        picked = portfoliom.pick(rows, pairs, budget=float(args.budget))
    nxt = []
    if rows:
        nxt = capabilities.what_to_connect(rows[0].get("metrics") or {}, scoring.get_preset(args.preset), caps)
    calib = calibration.from_pilots(
        db.list_pilots(conn),
        {c["id"]: c for c in db.list_creators(conn, limit=500)},
        {c["id"]: db.posts_for(conn, c["id"]) for c in db.list_creators(conn, limit=500)},
    )
    findings = report.findings_of(rows, label, picked)
    blocks = report.build(
        rows, brief=getattr(args, "brief", None) or "Creator rating",
        preset=args.preset, icp_name=icp.load().get("name") or "marketing-buyers",
        rung=rung, rung_label=label, findings=findings, notices=notices,
        portfolio=picked, connect_next=nxt, pairs=pairs, names=names,
        calibrated=bool(calib.get("calibrated")),
        economy=economy.card(caps),
    )
    out = getattr(args, "out", None) or "creator-rating-report"
    written = report.write(blocks, fmts, out, title=getattr(args, "brief", None) or "Creator rating")
    return _emit({
        "meta": {"source": "creator-rating", "version": __version__},
        "results": {"written": written, "n": len(rows), "rung": rung},
        "table": "wrote " + ", ".join(written),
    }, args.agent, args)


def cmd_report(args: argparse.Namespace) -> int:
    conn = _db(args)
    rows = pipeline.assemble_report_rows(conn, preset=args.preset, limit=args.limit)
    if getattr(args, "format", "text") == "text":
        rung, label, _ = _rung_state(conn)
        return _emit({
            "meta": {"source": "creator-rating"},
            "table": emit.table(rows, preset=args.preset, rung_label=label, n=len(rows)),
            "results": {"n": len(rows), "creators": [_compact(r) for r in rows]},
        }, args.agent, args)
    return _document(args, conn, rows)


def cmd_portfolio(args: argparse.Namespace) -> int:
    conn = _db(args)
    rows = pipeline.assemble_report_rows(conn, preset=args.preset, limit=args.limit)
    pairs, _ = pipeline.overlap_pairs(conn, rows)
    picked = portfoliom.pick(rows, pairs, budget=float(args.budget))
    table = (
        f"buy {picked['n']} for {picked['spend']:.0f} of {picked['budget']:.0f}; "
        f"ICP impressions {picked['icp_impressions']:.0f}"
    )
    return _emit({"meta": {"source": "creator-rating"}, "results": picked, "table": table},
                 args.agent, args)


def cmd_export(args: argparse.Namespace) -> int:
    conn = _db(args)
    rows = pipeline.assemble_report_rows(conn, preset=args.preset, limit=args.limit)
    payload_rows = [export.row_of(r, r, r.get("price")) for r in rows]
    text = export.render(payload_rows)
    if args.out:
        Path(args.out).expanduser().write_text(text, encoding="utf-8")
    return _emit({"meta": {"source": "creator-rating"},
                  "results": {"n": len(payload_rows), "path": args.out},
                  "table": text if not args.out else f"wrote {args.out}"},
                 args.agent, args)


def cmd_show(args: argparse.Namespace) -> int:
    conn = _db(args)
    c = db.get_creator(conn, args.identity)
    if not c:
        return _die(args, E_NOTFOUND, f"no creator '{args.identity}'", fix="list --agent")
    s = db.latest_score(conn, c["id"])
    rows = pipeline.assemble_report_rows(conn, limit=500)
    row = next((r for r in rows if r["id"] == c["id"]), {**c, **(s or {})})
    return _emit({"meta": {"source": "creator-rating"},
                  "results": _compact(row) | {"headline": c.get("headline"), "followers": c.get("followers")},
                  "table": emit.table([row], preset=args.preset, rung_label="", n=1)},
                 args.agent, args)


def cmd_list(args: argparse.Namespace) -> int:
    conn = _db(args)
    rows = db.list_creators(conn, status=args.status, limit=args.limit)
    table = "\n".join(f"{r['id']}\t{r.get('name')}\t{r.get('status')}\t{r.get('followers')}" for r in rows)
    return _emit({"meta": {"source": "creator-rating"},
                  "results": {"creators": rows, "n": len(rows)}, "table": table or "(empty)"},
                 args.agent, args)


def cmd_pilot(args: argparse.Namespace) -> int:
    conn = _db(args)
    c = db.get_creator(conn, args.creator)
    if not c:
        return _die(args, E_NOTFOUND, f"no creator '{args.creator}'", fix="list --agent")
    pid = db.insert_pilot(conn, {
        "creator_id": c["id"],
        "kind": args.kind,
        "impressions": args.impressions,
        "icp_share": args.icp_share,
        "leads": args.leads,
        "paid": args.paid,
        "format": args.format_name or "",
        "notes": args.notes or "",
    }, db.now())
    conn.commit()
    return _emit({"meta": {"source": "creator-rating"},
                  "results": {"pilot_id": pid, "creator_id": c["id"]},
                  "table": f"pilot {pid} stored for {c['id']}"}, args.agent, args)


def cmd_calibrate(args: argparse.Namespace) -> int:
    conn = _db(args)
    creators = {c["id"]: c for c in db.list_creators(conn, limit=500)}
    posts_by = {cid: db.posts_for(conn, cid) for cid in creators}
    # attach predicted icp share from latest scores
    for cid, cr in creators.items():
        s = db.latest_score(conn, cid)
        metrics = (s or {}).get("metrics") or {}
        share = metrics.get("icp_share_engagers") or {}
        cr["icp_share_pred"] = share.get("value") if isinstance(share, dict) else None
    result = calibration.from_pilots(db.list_pilots(conn), creators, posts_by)
    return _emit({"meta": {"source": "creator-rating"}, "results": result, "table": result.get("note") or ""},
                 args.agent, args)


def cmd_prune(args: argparse.Namespace) -> int:
    conn = _db(args)
    days = args.days if args.days is not None else 90
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    n = db.prune_engagers(conn, cutoff)
    conn.commit()
    return _emit({"meta": {"source": "creator-rating"},
                  "results": {"pruned": n, "before": cutoff},
                  "table": f"pruned {n} engager identities older than {days} days"},
                 args.agent, args)


def cmd_shortlist(args: argparse.Namespace) -> int:
    conn = _db(args)
    ids = pipeline.shortlist(conn, threshold=args.threshold, decile=args.decile)
    conn.commit()
    return _emit({"meta": {"source": "creator-rating"},
                  "results": {"ids": ids, "n": len(ids)},
                  "table": f"shortlisted {len(ids)}"}, args.agent, args)


def cmd_icp(args: argparse.Namespace) -> int:
    if args.action == "init":
        path = icp.write_template(getattr(args, "icp", None))
        return _emit({"meta": {"source": "creator-rating"},
                      "results": {"path": str(path)},
                      "table": f"wrote {path}"}, args.agent, args)
    cfg = icp.load(getattr(args, "icp", None))
    return _emit({"meta": {"source": "creator-rating"}, "results": cfg,
                  "table": json.dumps({k: v for k, v in cfg.items() if not k.startswith("_")}, indent=2)},
                 args.agent, args)


def cmd_agent_context(args: argparse.Namespace) -> int:
    return _emit({
        "meta": {"source": "creator-rating", "version": __version__},
        "results": {
            "version": __version__,
            "primary_verb": "rate",
            "commands": _command_index(),
            "exit_codes": agentio.EXIT_CODES,
            "presets": scoring.preset_names(),
            "rungs": capabilities.RUNG_LABELS,
            "guides": {
                "start": "docs/start.md",
                "connect": "docs/connect.md",
                "no_keys": "docs/no-keys.md",
                "ask": "docs/ask.md",
                "economy": "docs/economy.md",
            },
            "paths": {
                "db": str(db.default_db()),
                "keys": str(auth.keys_file()),
                "icp": str(icp.config_path()),
            },
            "env": {
                "home": "CREATOR_RATING_HOME",
                "db": "CREATOR_RATING_DB",
                "icp": "CREATOR_RATING_ICP",
            },
            "hygiene": {
                "engager_pii_export": False,
                "dedicated_account_required": True,
                "prune_days": 90,
            },
            "doctor_states": ["ready", "ready-thin"],
        },
    }, args.agent, args)


def cmd_profile(args: argparse.Namespace) -> int:
    if args.action == "list":
        return _emit({"meta": {"source": "creator-rating"},
                      "results": {"profiles": agentio.list_profiles()}}, args.agent, args)
    if args.action == "show":
        try:
            prof = agentio.load_profile(args.name)
        except KeyError:
            return _die(args, E_NOTFOUND, f"no profile '{args.name}'", fix="profile list")
        return _emit({"meta": {"source": "creator-rating"},
                      "results": {"name": args.name, "flags": prof}}, args.agent, args)
    if args.action == "delete":
        gone = agentio.delete_profile(args.name)
        if not gone:
            return _die(args, E_NOTFOUND, f"no profile '{args.name}'")
        return _emit({"meta": {"source": "creator-rating"}, "results": {"deleted": args.name}}, args.agent, args)
    flags = {}
    for item in args.set or []:
        if "=" in item:
            k, v = item.split("=", 1)
            flags[k] = v
    saved = agentio.save_profile(args.name, flags)
    return _emit({"meta": {"source": "creator-rating"},
                  "results": {"name": args.name, "flags": saved}}, args.agent, args)


def cmd_feedback(args: argparse.Namespace) -> int:
    words = args.words or []
    if words and words[0] == "list":
        rows = agentio.read_feedback(args.limit)
        return _emit({"meta": {"source": "creator-rating"}, "results": {"notes": rows}}, args.agent, args)
    note = " ".join(words).strip()
    if not note:
        return _die(args, E_USAGE, "feedback needs a note", fix='feedback "the surprising thing"')
    path = agentio.record_feedback(note, context=args.context or "")
    return _emit({"meta": {"source": "creator-rating"},
                  "results": {"path": str(path)}, "table": f"recorded → {path}"},
                 args.agent, args)


def _welcome(agent: bool = False) -> int:
    text = emit.welcome(invocation=_invocation(), python=sys.executable)
    if agent:
        json.dump({"meta": {"source": "creator-rating"}, "table": text, "results": {"help": True}}, sys.stdout)
        sys.stdout.write("\n")
    else:
        print(text)
    return 0


def _did_you_mean(word: str) -> int:
    hit = which_resolve(word)
    print(f"unknown command '{word}'. closest:")
    print(f"  {_invocation()} {hit['run']}")
    if hit.get("note"):
        print(f"  {hit['note']}")
    return 2


def _first_word(raw: list[str]) -> str:
    for tok in raw:
        if not tok.startswith("-"):
            return tok
    return ""


def main(argv: list[str] | None = None) -> int:
    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument("--agent", action="store_true")
    shared.add_argument("--db", default=None)
    shared.add_argument("--select", default=None)
    shared.add_argument("--deliver", default=None)
    shared.add_argument("--profile", default=None)
    shared.add_argument("--preset", default="awareness+leads")
    shared.add_argument("--icp", default=None)

    p = argparse.ArgumentParser(prog="creator-rating", description=__doc__, parents=[shared])
    p.add_argument("--version", action="version", version=f"creator-rating {__version__}")
    sub = p.add_subparsers(dest="cmd", required=False)

    ac = sub.add_parser("agent-context", parents=[shared])
    ac.set_defaults(fn=cmd_agent_context)

    su = sub.add_parser("setup", parents=[shared])
    su.add_argument("key", nargs="?")
    su.add_argument("--backend", default="clay",
                    choices=["clay", "brightdata", "unipile", "apollo", "llm", "scrapecreators", "brave"])
    su.add_argument("--clear", action="store_true")
    su.add_argument("--collection-account", default=None)
    su.add_argument("--brand-account", default=None)
    su.add_argument("--i-understand", action="store_true")
    su.set_defaults(fn=cmd_setup)

    d = sub.add_parser("doctor", parents=[shared])
    d.set_defaults(fn=cmd_doctor)

    w = sub.add_parser("which", parents=[shared])
    w.add_argument("capability")
    w.set_defaults(fn=cmd_which)

    ing = sub.add_parser("ingest", parents=[shared])
    ing.add_argument("--csv", default=None)
    ing.add_argument("--clay", default=None)
    ing.add_argument("--who-finder", default=None)
    ing.add_argument("--url", default=None)
    ing.add_argument("--name", default=None)
    ing.add_argument("--headline", default=None)
    ing.add_argument("--about", default=None)
    ing.add_argument("--followers", type=int, default=0)
    ing.add_argument("--search", default=None)
    ing.add_argument("--keyword", default=None)
    ing.add_argument("--source", default=None)
    ing.add_argument("--limit", type=int, default=50)
    ing.add_argument("--cheap", action="store_true")
    ing.set_defaults(fn=cmd_ingest)

    col = sub.add_parser("collect", parents=[shared])
    col.add_argument("identity", nargs="*")
    col.add_argument("--deep", action="store_true")
    col.add_argument("--status", default=None)
    col.add_argument("--limit", type=int, default=50)
    col.add_argument("--max-spend", type=float, default=None)
    col.add_argument("--cheap", action="store_true")
    col.add_argument("--i-understand", action="store_true")
    col.add_argument("--no-sleep", action="store_true")
    col.set_defaults(fn=cmd_collect)

    cl = sub.add_parser("classify", parents=[shared])
    cl.add_argument("--llm", action="store_true")
    cl.add_argument("--emit-batch", default=None)
    cl.add_argument("--apply-batch", default=None)
    cl.add_argument("--limit", type=int, default=200)
    cl.set_defaults(fn=cmd_classify)

    rt = sub.add_parser("rate", parents=[shared])
    rt.add_argument("--csv", default=None)
    rt.add_argument("--who-finder", default=None)
    rt.add_argument("--limit", type=int, default=200)
    rt.add_argument("--format", default="text")
    rt.add_argument("--out", default=None)
    rt.add_argument("--brief", default=None)
    rt.add_argument("--budget", type=float, default=None)
    rt.add_argument("--no-collect", action="store_true",
                    help="score what is already stored; do not search")
    rt.add_argument("--cheap", action="store_true")
    rt.set_defaults(fn=cmd_rate)

    rp = sub.add_parser("report", parents=[shared])
    rp.add_argument("--limit", type=int, default=50)
    rp.add_argument("--format", default="text")
    rp.add_argument("--out", default=None)
    rp.add_argument("--brief", default=None)
    rp.add_argument("--budget", type=float, default=None)
    rp.set_defaults(fn=cmd_report)

    pf = sub.add_parser("portfolio", parents=[shared])
    pf.add_argument("--budget", type=float, required=True)
    pf.add_argument("--limit", type=int, default=80)
    pf.set_defaults(fn=cmd_portfolio)

    ex = sub.add_parser("export", parents=[shared])
    ex.add_argument("--out", default=None)
    ex.add_argument("--limit", type=int, default=200)
    ex.set_defaults(fn=cmd_export)

    sh = sub.add_parser("show", parents=[shared])
    sh.add_argument("identity")
    sh.set_defaults(fn=cmd_show)

    ls = sub.add_parser("list", parents=[shared])
    ls.add_argument("--status", default=None)
    ls.add_argument("--limit", type=int, default=50)
    ls.set_defaults(fn=cmd_list)

    pi = sub.add_parser("pilot", parents=[shared])
    pi.add_argument("--creator", required=True)
    pi.add_argument("--kind", default="consented")
    pi.add_argument("--impressions", type=int, default=None)
    pi.add_argument("--icp-share", type=float, default=None)
    pi.add_argument("--leads", type=int, default=None)
    pi.add_argument("--paid", type=float, default=None)
    pi.add_argument("--format-name", default=None)
    pi.add_argument("--notes", default=None)
    pi.set_defaults(fn=cmd_pilot)

    ca = sub.add_parser("calibrate", parents=[shared])
    ca.set_defaults(fn=cmd_calibrate)

    pr = sub.add_parser("prune", parents=[shared])
    pr.add_argument("--days", type=int, default=90)
    pr.set_defaults(fn=cmd_prune)

    sl = sub.add_parser("shortlist", parents=[shared])
    sl.add_argument("--threshold", type=float, default=60)
    sl.add_argument("--decile", type=float, default=0.1)
    sl.set_defaults(fn=cmd_shortlist)

    ic = sub.add_parser("icp", parents=[shared])
    ic.add_argument("action", choices=["show", "init"])
    ic.set_defaults(fn=cmd_icp)

    pro = sub.add_parser("profile", parents=[shared])
    pro.add_argument("action", choices=["save", "list", "show", "delete"])
    pro.add_argument("name", nargs="?")
    pro.add_argument("--set", action="append")
    pro.set_defaults(fn=cmd_profile)

    fb = sub.add_parser("feedback", parents=[shared])
    fb.add_argument("words", nargs="*")
    fb.add_argument("--context", default=None)
    fb.add_argument("--limit", type=int, default=20)
    fb.set_defaults(fn=cmd_feedback)

    raw = list(argv if argv is not None else sys.argv[1:])
    if not any(tok in sub.choices for tok in raw):
        first = _first_word(raw)
        if not first or first.lower() in HELP_WORDS:
            return _welcome(agent="--agent" in raw)
        if "--version" not in raw and "-h" not in raw and "--help" not in raw:
            return _did_you_mean(first)

    args = p.parse_args(argv)
    if not getattr(args, "cmd", None):
        return _welcome(agent=getattr(args, "agent", False))
    if getattr(args, "profile", None):
        try:
            agentio.apply_profile(args, args.profile)
        except KeyError:
            return _die(args, E_NOTFOUND, f"no profile '{args.profile}'", fix="profile list --agent")
    try:
        return int(args.fn(args) or 0)
    except icp.ConfigError as exc:
        return _die(args, E_CONFIG, str(exc), fix="fix or delete the ICP file")
    except HygieneError as exc:
        return _die(args, E_HYGIENE, str(exc), fix="docs/connect.md#engager-source")
    except BudgetError as exc:
        return _die(args, E_BUDGET, str(exc), fix="raise --max-spend")
    except BrokenPipeError:
        return 0
