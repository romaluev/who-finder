"""Orchestrate collect → classify → score → price for stored creators."""

from __future__ import annotations

from . import auth, calibration, capabilities, classifiers, db, economy, icp, overlap, playbook
from . import portfolio as portfoliom
from . import pricing, scoring
from .classifiers import agent as agentclf
from .classifiers import llm as llmclf
from .classifiers import rules
from .collectors import brightdata, clay, public, unipile
from .features import compute as compute_features
from .features.provenance import pack


def _store_profile_posts(conn, cid: str, url: str, prof, posts, ts: str) -> int:
    if prof:
        db.upsert_creator(conn, {**prof, "url": url}, ts)
    n = 0
    for p in posts or []:
        p["creator_id"] = cid
        db.upsert_post(conn, p, ts)
        n += 1
    return n


def collect_lite(conn, cid: str, ts: str, *, max_spend: float | None = None,
                 cheap: bool = False) -> dict:
    """Public → Clay → Bright Data. Paid scrapers only when posts are still missing."""
    creator = db.get_creator(conn, cid)
    if not creator:
        return {"ok": False, "error": "not found"}
    url = creator["url"]
    existing = db.posts_for(conn, cid, limit=80)
    has_posts = bool(existing)
    has_video = any((p.get("source") or "") in {"who-finder", "ytdlp", "public"} for p in existing)
    plan = economy.lite_plan(url, cheap=cheap, has_posts=has_posts, has_video=has_video)
    used = []
    skipped = []
    n_posts = len(existing)
    spent = db.spend_total(conn)

    for step in plan:
        backend = step["backend"]
        if backend == "public":
            col = public.PublicCollector()
            prof = col.profile(url)
            posts = [] if has_posts else col.posts(url, n=20)
            added = _store_profile_posts(conn, cid, url, prof, posts, ts)
            if prof or added:
                used.append("public")
                n_posts += added
                has_posts = has_posts or bool(added)
                has_video = has_video or any((p.get("source") == "ytdlp") for p in posts)
                db.save_raw(conn, "collect-lite", "public",
                            {"n_posts": added, "profile": bool(prof)}, ts, cid)
            continue
        if backend == "clay":
            col = clay.ClayCollector()
            if not col.available():
                continue
            prof = col.profile(url)
            if prof:
                db.upsert_creator(conn, {**prof, "url": url}, ts)
                used.append("clay")
                db.save_raw(conn, "collect-lite", "clay", {"profile": True}, ts, cid)
            continue
        if backend == "brightdata":
            if has_posts:
                skipped.append({"backend": "brightdata", "why": "posts already stored"})
                continue
            col = brightdata.BrightDataCollector()
            if not col.available():
                skipped.append({"backend": "brightdata", "why": "no key"})
                continue
            cost = col.estimate(n_profiles=1, n_posts=40)
            if max_spend is not None and spent + cost > max_spend:
                from .collectors.base import BudgetError
                raise BudgetError(
                    f"collect-lite for {cid} would cost ${cost:.3f} and exceed --max-spend ${max_spend}"
                )
            prof = col.profile(url)
            posts = col.posts(url, n=40)
            added = _store_profile_posts(conn, cid, url, prof, posts, ts)
            if posts or prof:
                db.log_spend(conn, "brightdata", "lite", 1 + len(posts), cost, ts, cid)
                db.save_raw(conn, "collect-lite", "brightdata",
                            {"profile": prof, "n_posts": len(posts)}, ts, cid)
                used.append("brightdata")
                n_posts += added
            continue

    return {
        "ok": True,
        "backend": used[0] if used else None,
        "backends": used,
        "skipped": skipped,
        "n_posts": n_posts,
        "plan": plan,
        "cheap": cheap,
        "note": None if used else "nothing new collected — ingest a sheet or connect a source",
    }


def collect_deep(conn, cid: str, ts: str, *, i_understand: bool = False,
                 max_spend: float | None = None, sleep: bool = True) -> dict:
    unipile.assert_rails(i_understand=i_understand, conn=conn)
    posts = db.posts_for(conn, cid, limit=12)
    if not posts:
        return {"ok": False, "error": "no posts to attach engagers to"}
    col = unipile.UnipileCollector(sleep=sleep)
    n = 0
    for p in posts:
        rows = col.engagers(p.get("url") or p["id"], cap=200, conn=conn, i_understand=True)
        for e in rows:
            db.insert_engagement(conn, {
                "post_id": p["id"],
                "engager_hash": e["hash"],
                "type": e.get("type") or "reaction",
                "word_count": e.get("word_count") or 0,
                "latency_sec": e.get("latency_sec"),
                "generic": False,
                "ai_flag": False,
            }, ts)
            if e.get("headline"):
                from . import icp as icpmod
                enr = icpmod.classify_headline(e["headline"])
                db.upsert_enrichment(conn, {"hash": e["hash"], **enr, "source": "rules"}, ts)
            n += 1
    return {"ok": True, "n_engagers": n, "n_posts": len(posts)}


def ingest_engager_dump(conn, cid: str, rows: list[dict], ts: str) -> int:
    from .collectors.unipile import ingest_hashed_dump
    posts = db.posts_for(conn, cid, limit=12)
    post_ids = [p["id"] for p in posts] or [f"{cid}:unknown"]
    hashed = ingest_hashed_dump(rows)
    n = 0
    for i, e in enumerate(hashed):
        pid = e.get("post_id") or post_ids[i % len(post_ids)]
        db.insert_engagement(conn, {
            "post_id": pid,
            "engager_hash": e["hash"],
            "type": e.get("type") or "reaction",
            "word_count": e.get("word_count") or 0,
            "latency_sec": e.get("latency_sec"),
            "generic": False,
            "ai_flag": False,
        }, ts)
        if e.get("headline"):
            from . import icp as icpmod
            enr = icpmod.classify_headline(e["headline"])
            db.upsert_enrichment(conn, {"hash": e["hash"], **enr, "source": "rules"}, ts)
        n += 1
    return n


def classify_creator(conn, cid: str, ts: str, *, use_llm: bool = False, brief: str = "") -> int:
    cfg = icp.load()
    brief = brief or cfg.get("brief") or ""
    n = 0
    for p in db.posts_for(conn, cid, limit=80):
        existing = db.topic_for(conn, p["id"])
        if existing and existing.get("classifier") in {"llm", "agent"}:
            continue
        result = rules.classify_post(p.get("text") or "", brief=brief)
        if use_llm:
            overlay = llmclf.classify_post(p.get("text") or "", brief=brief)
            if overlay:
                result.update({k: overlay[k] for k in overlay if overlay[k] is not None})
                result["classifier"] = "llm"
        result["post_id"] = p["id"]
        db.upsert_topic(conn, result, ts)
        n += 1
    return n


def score_creator(conn, cid: str, ts: str, *, preset: str = "awareness+leads",
                  fitted: dict | None = None) -> dict:
    creator = db.get_creator(conn, cid)
    if not creator:
        raise KeyError(cid)
    posts = db.posts_for(conn, cid, limit=80)
    engagements = db.engagements_for(conn, cid)
    hashes = {g["engager_hash"] for g in engagements}
    enrichment = db.enrichment_map(conn, hashes)
    topics = {p["id"]: db.topic_for(conn, p["id"]) or {} for p in posts}
    # Classify on the fly if posts exist without topics (rung 0 still uses headline).
    cfg = icp.load()
    brief = cfg.get("brief") or ""
    for p in posts:
        if not topics[p["id"]].get("topic"):
            t = rules.classify_post(p.get("text") or "", brief=brief)
            db.upsert_topic(conn, {**t, "post_id": p["id"]}, ts)
            topics[p["id"]] = t

    pilots = [p for p in db.list_pilots(conn) if p["creator_id"] == cid]
    consented = {}
    if pilots:
        last = pilots[0]
        if last.get("impressions") is not None:
            consented["impressions"] = last["impressions"]
        if last.get("icp_share") is not None:
            consented["icp_share"] = last["icp_share"]

    all_creators = {c["id"]: c for c in db.list_creators(conn, limit=500)}
    posts_by = {c["id"]: db.posts_for(conn, c["id"], limit=40) for c in all_creators.values()}
    calib = calibration.from_pilots(db.list_pilots(conn), all_creators, posts_by)
    k = (fitted or {}).get("k") or calib.get("k") or 20
    imp_src = calib.get("impressions_label") or "estimated"

    metrics = compute_features(
        creator, posts, engagements, enrichment, topics,
        icp_cfg=cfg, abm=db.abm_names(conn), brief=brief,
        consented=consented or None, k_format=k, impressions_source=imp_src,
    )
    n_engager_posts = len({g["post_id"] for g in engagements})
    caps = auth.capabilities()
    result = scoring.score(
        metrics, preset_name=preset, n_posts=len(posts),
        n_engagers=len(engagements), n_engager_posts=n_engager_posts, caps=caps,
    )
    priced = pricing.price(metrics, creator, posts, fitted_k=calib.get("k_by_tier"))
    result["price"] = priced
    result["creator_id"] = cid
    result["stage"] = "v2" if engagements else "v1"
    result["n_posts"] = len(posts)
    result["n_engagers"] = len(engagements)
    result["calibration"] = {"k": k, "label": imp_src, "r2": calib.get("r2"), "n": calib.get("n")}
    db.save_score(conn, {
        "creator_id": cid,
        "preset": preset,
        "stage": result["stage"],
        "social": result["social"],
        "engagement": result["engagement"],
        "interest": result["interest"],
        "creator_score": result["creator_score"],
        "confidence": result["confidence"],
        "tier": result["tier"],
        "next_action": result["next_action"],
        "gates": result["gates"],
        "metrics": pack(metrics),
    }, ts)
    if priced:
        # stash price next to metrics so report/export can find it
        result["metrics_packed"] = pack(metrics)
    else:
        result["metrics_packed"] = pack(metrics)
    return result


def score_all(conn, ts: str, *, preset: str = "awareness+leads", limit: int = 500) -> list[dict]:
    out = []
    for c in db.list_creators(conn, limit=limit):
        out.append(score_creator(conn, c["id"], ts, preset=preset))
    return out


def shortlist(conn, *, threshold: float = 60, decile: float = 0.1) -> list[str]:
    rows = db.list_scores(conn)
    rows = [r for r in rows if r.get("creator_score") is not None]
    rows.sort(key=lambda r: -float(r["creator_score"]))
    n = max(1, int(len(rows) * decile))
    picked = []
    for i, r in enumerate(rows):
        if i < n or float(r["creator_score"]) >= threshold:
            db.set_status(conn, r["creator_id"], "shortlist")
            picked.append(r["creator_id"])
    return picked


def assemble_report_rows(conn, *, preset: str = "awareness+leads", limit: int = 50) -> list[dict]:
    scores = db.list_scores(conn, preset=preset, limit=limit)
    out = []
    for s in scores:
        creator = db.get_creator(conn, s["creator_id"]) or {}
        posts = db.posts_for(conn, s["creator_id"], limit=12)
        metrics = {}
        raw = s.get("metrics") or {}
        from .features.provenance import unpack
        from . import scales
        metrics = unpack(raw)
        scales.apply(metrics)
        priced = pricing.price(metrics, creator, posts)
        used = sum(
            scoring.flatten(scoring.get_preset(s.get("preset") or "awareness+leads")).get(name, 0)
            for name, m in metrics.items()
            if m.present and m.scaled is not None
        )
        out.append({
            **creator,
            **s,
            "metrics": metrics,
            "price": priced,
            "fair": (priced or {}).get("fair"),
            "cpm_icp": (priced or {}).get("cpm_icp"),
            "used_points": used,
            "icp_impressions": (priced or {}).get("icp_impressions") or _metric(metrics, "est_icp_impressions_per_post"),
        })
    return out


def _metric(metrics: dict, name: str):
    m = metrics.get(name)
    if m is None:
        return None
    return m.value if hasattr(m, "value") else (m.get("value") if isinstance(m, dict) else m)


def overlap_pairs(conn, rows: list[dict]) -> tuple[list[dict], str]:
    sets = {r["id"]: db.engager_hashes_for(conn, r["id"]) for r in rows}
    if any(sets.values()):
        return overlap.matrix(sets, kind="jaccard"), "jaccard"
    proxy = overlap.proxy_sets([{**r, "id": r["id"], "topic_mix": _topic_mix(r)} for r in rows])
    return overlap.matrix(proxy, kind="proxy"), "proxy"


def _topic_mix(row: dict):
    m = (row.get("metrics") or {}).get("topic_mix")
    if m is None:
        return {}
    return m.value if hasattr(m, "value") else (m.get("value") if isinstance(m, dict) else m)
