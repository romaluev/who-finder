"""Collector protocol. Swap a vendor without touching a metric."""

from __future__ import annotations

from typing import Any


class CollectorError(RuntimeError):
    pass


class HygieneError(CollectorError):
    """A hard rail fired. The CLI maps this to exit 11."""


class BudgetError(CollectorError):
    """Would exceed --max-spend. The CLI maps this to exit 8."""


class Profile(dict):
    """url, name, handle, headline, about, followers, connections, location, platform."""


class Post(dict):
    """id, url, text, posted_at, reactions, comments, reposts, impressions, format."""


class Engager(dict):
    """hash (required), type, word_count, latency_sec, headline — never a raw URL after ingest."""


class Collector:
    name = "base"
    cost_per_profile = 0.0
    cost_per_post = 0.0
    cost_per_engager = 0.0

    def available(self) -> bool:
        return True

    def profile(self, url: str) -> Profile | None:
        return None

    def posts(self, url: str, n: int = 40) -> list[Post]:
        return []

    def engagers(self, post_url: str, cap: int = 200) -> list[Engager]:
        return []

    def search(self, query: str, limit: int = 50) -> list[Profile]:
        return []

    def estimate(self, n_profiles: int = 0, n_posts: int = 0, n_engagers: int = 0) -> float:
        return (
            n_profiles * self.cost_per_profile
            + n_posts * self.cost_per_post
            + n_engagers * self.cost_per_engager
        )
