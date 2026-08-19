"""Compose with who-finder. Never impersonate it — we only ingest its JSON."""

from __future__ import annotations

from .base import Collector
from .csv_import import parse_who_finder_json


class WhoFinderCollector(Collector):
    name = "who_finder"

    def available(self) -> bool:
        return True

    def ingest(self, data) -> list:
        return parse_who_finder_json(data)
