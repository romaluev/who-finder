"""Every derived number carries where it came from.

`source` is one of measured | estimated | assumed | consented | insufficient.
A composite inherits the weakest provenance of its inputs. Never upgrade.
"""

from __future__ import annotations

from typing import Any

SOURCES = ("consented", "measured", "estimated", "assumed", "insufficient")
RANK = {
    "consented": 4,
    "measured": 3,
    "estimated": 2,
    "assumed": 1,
    "insufficient": 0,
}
MEASURED_OR_BETTER = frozenset({"consented", "measured"})


def weakest(*sources: str) -> str:
    named = [s for s in sources if s in RANK]
    if not named:
        return "insufficient"
    return min(named, key=lambda s: RANK[s])


class Metric:
    __slots__ = ("name", "value", "source", "basis", "scaled")

    def __init__(
        self,
        name: str,
        value: Any,
        source: str,
        basis: str,
        scaled: float | None = None,
    ):
        if source not in RANK:
            source = "insufficient"
        self.name = name
        self.value = value
        self.source = source
        self.basis = basis
        self.scaled = scaled

    @property
    def present(self) -> bool:
        return self.value is not None and self.source != "insufficient"

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "value": self.value,
            "source": self.source,
            "basis": self.basis,
            "scaled": self.scaled,
        }

    @classmethod
    def missing(cls, name: str, why: str) -> "Metric":
        return cls(name, None, "insufficient", why)

    @classmethod
    def assumed(cls, name: str, value: Any, basis: str) -> "Metric":
        return cls(name, value, "assumed", basis)

    @classmethod
    def estimated(cls, name: str, value: Any, basis: str) -> "Metric":
        return cls(name, value, "estimated", basis)

    @classmethod
    def measured(cls, name: str, value: Any, basis: str) -> "Metric":
        return cls(name, value, "measured", basis)

    @classmethod
    def consented(cls, name: str, value: Any, basis: str) -> "Metric":
        return cls(name, value, "consented", basis)


def from_dict(d: dict) -> Metric:
    return Metric(
        d.get("name") or "",
        d.get("value"),
        d.get("source") or "insufficient",
        d.get("basis") or "",
        d.get("scaled"),
    )


def pack(metrics: dict[str, Metric]) -> dict:
    return {k: m.as_dict() for k, m in metrics.items()}


def unpack(raw: dict) -> dict[str, Metric]:
    out: dict[str, Metric] = {}
    for k, v in (raw or {}).items():
        if isinstance(v, Metric):
            out[k] = v
        elif isinstance(v, dict):
            row = dict(v)
            row.setdefault("name", k)
            out[k] = from_dict(row)
    return out
