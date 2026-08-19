"""Apollo people-match. Seed pool and ABM only — never a full engager dump."""

from __future__ import annotations

from .. import auth, http
from .base import Collector


class ApolloCollector(Collector):
    name = "apollo"
    cost_per_profile = 0.0  # credits, not USD; we still count units in spend_log

    def __init__(self, token: str | None = None):
        self._token = token if token is not None else auth.token("apollo")

    def available(self) -> bool:
        return bool(self._token)

    def match(self, linkedin_url: str) -> dict | None:
        """Match one LinkedIn URL. Returns enrichment fields or None."""
        if not self._token:
            return None
        try:
            data = http.post(
                "https://api.apollo.io/api/v1/people/match",
                payload={"linkedin_url": linkedin_url},
                headers={"X-Api-Key": self._token, "Content-Type": "application/json"},
                timeout=30,
            )
        except Exception:
            return None
        person = data.get("person") if isinstance(data, dict) else None
        if not isinstance(person, dict):
            return None
        org = person.get("organization") if isinstance(person.get("organization"), dict) else {}
        return {
            "seniority": person.get("seniority") or "",
            "function": (person.get("departments") or [None])[0] or person.get("title") or "",
            "industry": org.get("industry") or "",
            "geo": person.get("country") or "",
            "company": org.get("name") or "",
            "company_size": org.get("estimated_num_employees"),
            "headline": person.get("title") or "",
            "source": "apollo",
        }
