"""Collector adapters. csv, who-finder, and public always work; the rest need keys."""

from __future__ import annotations

from . import apollo, brightdata, clay, csv_import, public, unipile, who_finder
from .base import BudgetError, Collector, CollectorError, Engager, HygieneError, Post, Profile

REGISTRY = {
    "csv": csv_import.CSVCollector,
    "who_finder": who_finder.WhoFinderCollector,
    "public": public.PublicCollector,
    "clay": clay.ClayCollector,
    "brightdata": brightdata.BrightDataCollector,
    "unipile": unipile.UnipileCollector,
    "apollo": apollo.ApolloCollector,
}


def get(name: str) -> Collector:
    cls = REGISTRY.get(name)
    if cls is None:
        raise CollectorError(f"unknown collector '{name}'. want {list(REGISTRY)}")
    return cls()


def available() -> dict[str, bool]:
    return {name: cls().available() for name, cls in REGISTRY.items()}
