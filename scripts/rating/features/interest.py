"""Interest graph I1–I10."""

from __future__ import annotations

from collections import Counter

from .. import icp as icpmod
from ..classifiers import rules
from ..util import median, shannon
from .provenance import Metric


def compute(creator: dict, posts: list[dict], topics: dict[str, dict],
            engagements: list[dict], enrichment: dict[str, dict],
            *, icp_cfg: dict, brief: str) -> dict[str, Metric]:
    out: dict[str, Metric] = {}
    n = len(posts)
    headline = creator.get("headline") or ""
    about = creator.get("about") or ""

    if n == 0:
        head = rules.classify_headline_topics(headline, about=about, brief=brief)
        out["topic_mix"] = Metric.estimated("topic_mix", head.get("topic") or "Other",
                                            "no posts; topic guessed from headline/about")
        # Single-document concentration is 1.0 if we could classify, else insufficient.
        topic = head.get("topic") or "Other"
        if topic != "Other" or head.get("relevance", 0) > 0:
            out["topic_concentration"] = Metric.estimated(
                "topic_concentration", 1.0 if topic != "Other" else 0.0,
                "single headline/about document",
            )
            out["topic_entropy"] = Metric.estimated("topic_entropy", 0.0, "one document")
            out["brand_topic_fit"] = Metric.estimated(
                "brand_topic_fit", float(head.get("relevance") or 0),
                f"headline/about vs brief; relevance={head.get('relevance')}",
            )
            out["headline_alignment"] = Metric.estimated(
                "headline_alignment", float(head.get("headline_alignment") or head.get("relevance") or 0),
                "headline vs brief (no post topics to align to)",
            )
        else:
            for name in ("topic_concentration", "topic_entropy", "brand_topic_fit", "headline_alignment"):
                out[name] = Metric.missing(name, "no posts and headline did not match the taxonomy")
        for name in ("fit_engagement_lift", "audience_interest_alignment",
                     "competitor_mentions", "brand_safety", "language_mix"):
            why = "no posts" if name != "audience_interest_alignment" else "no engager rows"
            out[name] = Metric.missing(name, why)
        return out

    primaries = []
    relevances = []
    safeties = []
    langs = []
    bait = 0
    for p in posts:
        t = topics.get(p["id"]) or {}
        if not t.get("topic"):
            t = rules.classify_post(p.get("text") or "", brief=brief)
        primaries.append(t.get("topic") or "Other")
        if t.get("relevance") is not None:
            relevances.append(float(t["relevance"]))
        safeties.append(t.get("safety") or "ok")
        langs.append(t.get("language") or "en")
        if t.get("bait"):
            bait += 1

    counts = Counter(primaries)
    mix = dict(counts)
    out["topic_mix"] = Metric.measured("topic_mix", mix, f"{n} classified posts")
    top2 = sum(c for _, c in counts.most_common(2))
    out["topic_concentration"] = Metric.measured(
        "topic_concentration", top2 / n, f"top-2 {counts.most_common(2)} of {n}"
    )
    out["topic_entropy"] = Metric.measured("topic_entropy", shannon(list(counts.values())), f"{len(counts)} topics")
    if relevances:
        out["brand_topic_fit"] = Metric.measured(
            "brand_topic_fit", sum(relevances) / len(relevances), f"mean relevance over {len(relevances)} posts"
        )
    else:
        out["brand_topic_fit"] = Metric.missing("brand_topic_fit", "no relevance scores")

    # fit_engagement_lift
    high, all_w = [], []
    for p in posts:
        w = int(p.get("reactions") or 0) + 2 * int(p.get("comments") or 0) + 3 * int(p.get("reposts") or 0)
        all_w.append(float(w))
        rel = (topics.get(p["id"]) or {}).get("relevance")
        if rel is not None and float(rel) >= 0.6:
            high.append(float(w))
    med_all = median(all_w)
    med_high = median(high) if high else None
    if med_all and med_high is not None and med_all > 0:
        out["fit_engagement_lift"] = Metric.measured(
            "fit_engagement_lift", med_high / med_all, f"{len(high)} high-relevance posts vs {n}"
        )
    else:
        out["fit_engagement_lift"] = Metric.missing("fit_engagement_lift", "need high-relevance posts with counts")

    head_rel = rules.relevance_to_brief(f"{headline} {about}", brief=brief)
    top_topics = " ".join(t for t, _ in counts.most_common(3))
    align = rules.relevance_to_brief(f"{headline} {about} {top_topics}", brief=top_topics or brief)
    out["headline_alignment"] = Metric.measured(
        "headline_alignment", max(head_rel, align),
        f"headline vs top topics {counts.most_common(2)}",
    )

    if engagements and enrichment:
        hits = 0
        for g in engagements:
            e = enrichment.get(g["engager_hash"]) or {}
            if icpmod.is_marketing(e, icp_cfg) or icpmod.is_icp(e, icp_cfg):
                hits += 1
        out["audience_interest_alignment"] = Metric.measured(
            "audience_interest_alignment", hits / len(engagements),
            f"{hits} of {len(engagements)} engager rows in target functions",
        )
    else:
        out["audience_interest_alignment"] = Metric.missing(
            "audience_interest_alignment", "need engager headlines"
        )

    competitors = [c.lower() for c in (icp_cfg.get("competitors") or [])]
    mentions = 0
    if competitors:
        for p in posts:
            blob = (p.get("text") or "").lower()
            if any(c in blob for c in competitors):
                mentions += 1
        out["competitor_mentions"] = Metric.measured(
            "competitor_mentions", mentions / n, f"{mentions} of {n} mention a competitor"
        )
    else:
        out["competitor_mentions"] = Metric.missing("competitor_mentions", "no competitor list in icp.json")

    if "fail" in safeties:
        safety = "fail"
    elif "caution" in safeties:
        safety = "caution"
    else:
        safety = "ok"
    out["brand_safety"] = Metric.measured("brand_safety", safety, f"{safeties.count('fail')} fail / {n}")

    campaign = set(icp_cfg.get("campaign_languages") or ["en"])
    lang_ok = sum(1 for lang in langs if lang in campaign)
    out["language_mix"] = Metric.measured("language_mix", lang_ok / n, f"{lang_ok} of {n} in {sorted(campaign)}")
    return out
