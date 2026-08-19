"""Feature computation. Every metric carries provenance."""

from __future__ import annotations

from . import engagement, interest, social
from .provenance import Metric, pack, unpack


def compute(creator: dict, posts: list[dict], engagements: list[dict],
            enrichment: dict[str, dict], topics: dict[str, dict],
            *, icp_cfg: dict, abm: set[str], brief: str,
            consented: dict | None = None, k_format: float = 20.0,
            impressions_source: str = "estimated") -> dict[str, Metric]:
    metrics: dict[str, Metric] = {}
    metrics.update(social.compute(creator, engagements, enrichment, icp_cfg=icp_cfg, abm=abm,
                                  consented=consented))
    metrics.update(engagement.compute(creator, posts, engagements, topics,
                                      k_format=k_format, consented=consented,
                                      impressions_source=impressions_source))
    metrics.update(interest.compute(creator, posts, topics, engagements, enrichment,
                                    icp_cfg=icp_cfg, brief=brief))
    metrics["est_icp_impressions_per_post"] = social.icp_impressions(
        metrics.get("median_impressions_est"),
        metrics.get("icp_share_engagers"),
    )
    return metrics
