"""Coercion and small helpers. Nothing here invents a number."""

from __future__ import annotations

import math
import re
from typing import Any
from urllib.parse import urlparse

_NUM_SUFFIX = {None: 1, "k": 1_000, "m": 1_000_000, "b": 1_000_000_000}


def to_int(v: Any) -> int:
    if isinstance(v, bool):
        return 0
    if isinstance(v, (int, float)):
        return int(v)
    if isinstance(v, str):
        s = v.lower().replace(",", "").strip()
        m = re.match(r"^([\d.]+)\s*([kmb])?\b", s)
        if m:
            return int(float(m.group(1)) * _NUM_SUFFIX[m.group(2)])
        digits = re.sub(r"[^\d]", "", s)
        return int(digits) if digits else 0
    if isinstance(v, dict):
        for k in ("count", "value", "text", "followers", "audience"):
            if k in v:
                return to_int(v[k])
    return 0


def to_float(v: Any) -> float | None:
    if v is None or v == "":
        return None
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        s = v.lower().replace(",", "").replace("%", "").strip()
        try:
            return float(s)
        except ValueError:
            return None
    return None


def to_str(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, dict):
        for k in ("name", "title", "text", "description", "headline"):
            if k in v:
                return to_str(v[k])
        return ""
    if isinstance(v, list):
        return " ".join(to_str(x) for x in v if x)
    return str(v).strip()


def clean(text: Any, limit: int = 0) -> str:
    s = re.sub(r"<[^>]+>", " ", to_str(text))
    s = re.sub(r"\s+", " ", s).strip()
    return s[:limit] if limit else s


def human(n: int | float) -> str:
    n = int(n or 0)
    for cutoff, suffix, div in (
        (1_000_000_000, "B", 1_000_000_000),
        (1_000_000, "M", 1_000_000),
        (1_000, "k", 1_000),
    ):
        if n >= cutoff:
            val = n / div
            return f"{val:.1f}".rstrip("0").rstrip(".") + suffix
    return str(n)


def money(n: float | None) -> str:
    if n is None:
        return "—"
    if n >= 1000:
        return f"${n:,.0f}"
    if n >= 10:
        return f"${n:,.0f}"
    return f"${n:,.2f}"


def plural(n: int, one: str, many: str = "") -> str:
    return one if n == 1 else (many or one + "s")


def clamp(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else hi if v > hi else v


def safe_div(num: float, den: float, default: float | None = None) -> float | None:
    if den == 0:
        return default
    return num / den


def median(values: list[float]) -> float | None:
    xs = sorted(v for v in values if v is not None)
    if not xs:
        return None
    mid = len(xs) // 2
    if len(xs) % 2:
        return float(xs[mid])
    return (xs[mid - 1] + xs[mid]) / 2.0


def mean(values: list[float]) -> float | None:
    xs = [v for v in values if v is not None]
    if not xs:
        return None
    return sum(xs) / len(xs)


def percentile(values: list[float], p: float) -> float | None:
    xs = sorted(v for v in values if v is not None)
    if not xs:
        return None
    if len(xs) == 1:
        return float(xs[0])
    k = (len(xs) - 1) * (p / 100.0)
    lo = int(math.floor(k))
    hi = int(math.ceil(k))
    if lo == hi:
        return float(xs[lo])
    return xs[lo] * (hi - k) + xs[hi] * (k - lo)


def shannon(counts: list[int]) -> float:
    total = sum(counts)
    if total <= 0:
        return 0.0
    h = 0.0
    for c in counts:
        if c <= 0:
            continue
        p = c / total
        h -= p * math.log2(p)
    return h


def linreg_slope(xs: list[float], ys: list[float]) -> float | None:
    n = min(len(xs), len(ys))
    if n < 2:
        return None
    x = xs[:n]
    y = ys[:n]
    mx = sum(x) / n
    my = sum(y) / n
    num = sum((a - mx) * (b - my) for a, b in zip(x, y))
    den = sum((a - mx) ** 2 for a in x)
    if den == 0:
        return 0.0
    return num / den


def r_squared(xs: list[float], ys: list[float], slope: float, intercept: float) -> float | None:
    n = min(len(xs), len(ys))
    if n < 2:
        return None
    y = ys[:n]
    pred = [slope * xs[i] + intercept for i in range(n)]
    my = sum(y) / n
    ss_tot = sum((yi - my) ** 2 for yi in y)
    ss_res = sum((yi - pi) ** 2 for yi, pi in zip(y, pred))
    if ss_tot == 0:
        return 1.0 if ss_res == 0 else 0.0
    return 1.0 - ss_res / ss_tot


def jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def norm_url(url: str) -> str:
    raw = (url or "").strip()
    if not raw:
        return ""
    if not re.match(r"^https?://", raw, re.I):
        raw = "https://" + raw.lstrip("/")
    try:
        p = urlparse(raw)
    except ValueError:
        return raw.lower().rstrip("/")
    host = (p.netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    path = (p.path or "").rstrip("/").lower()
    return f"https://{host}{path}"


def linkedin_handle(url: str) -> str:
    m = re.search(r"linkedin\.com/(?:in|company|school)/([^/?#]+)", url or "", re.I)
    return (m.group(1) if m else "").strip("/").lower()


def handle_from(url: str, name: str = "") -> str:
    h = linkedin_handle(url)
    if h:
        return h
    slug = re.sub(r"[^a-z0-9-]+", "-", (name or "").lower()).strip("-")
    return slug or "unknown"


def platform_of(url: str) -> str:
    host = ""
    try:
        host = (urlparse(url).hostname or "").lower()
    except ValueError:
        pass
    if "linkedin" in host:
        return "linkedin"
    if "youtube" in host or "youtu.be" in host:
        return "youtube"
    if "tiktok" in host:
        return "tiktok"
    if "instagram" in host:
        return "instagram"
    if host in {"x.com", "twitter.com"}:
        return "x"
    return "web"
