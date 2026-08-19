"""Clay — already-paid enrichment. Prefer a table export over a new vendor.

Clay does people search, title/company/size, and seniority. It does not
return LinkedIn post reactions or engager lists. A CSV/JSON export from a
table you already ran is the cheap path: no extra credits. The Public API
is optional and uses the same credits as the Clay UI.

https://developers.clay.com
"""

from __future__ import annotations

import csv
import io
import json
import re
from pathlib import Path

from .. import auth, http
from ..util import clean, handle_from, norm_url, platform_of, to_int
from .base import Collector, Profile

CLAY_API = "https://api.clay.com/public/v0"

URL_KEYS = (
    "linkedin url", "linkedin profile", "linkedin profile url",
    "person linkedin url", "linkedin", "profile url", "profile",
    "url", "person url", "linkedin permalink",
)
NAME_KEYS = (
    "full name", "name", "person name", "full_name", "fullname",
)
FIRST_KEYS = ("first name", "first", "firstname")
LAST_KEYS = ("last name", "last", "lastname")
TITLE_KEYS = (
    "job title", "title", "headline", "current title", "person title",
    "position", "role",
)
ABOUT_KEYS = ("about", "bio", "description", "headline", "summary")
COMPANY_KEYS = (
    "company name", "company", "organization", "org", "account",
    "current company",
)
SIZE_KEYS = (
    "company size", "# employees", "employees", "number of employees",
    "estimated num employees", "employee count", "company employees",
    "size",
)
FOLLOWER_KEYS = ("followers", "follower count", "audience", "linkedin followers")
LOC_KEYS = ("location", "person location", "city", "country", "geo")


def _norm_key(k) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(k or "").lower()).strip()


def _lookup(row: dict, keys: tuple[str, ...]):
    lower = {_norm_key(k): v for k, v in row.items()}
    for k in keys:
        v = lower.get(k)
        if v not in (None, ""):
            return v
    return None


def parse_company_size(v) -> int:
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return int(v)
    s = str(v or "")
    m = re.search(r"(\d[\d,]*)\s*[-–]\s*(\d[\d,]*)", s)
    if m:
        a = int(m.group(1).replace(",", ""))
        b = int(m.group(2).replace(",", ""))
        return (a + b) // 2
    return to_int(s)


def row_to_profile(row: dict, source: str = "clay") -> Profile | None:
    if not isinstance(row, dict):
        return None
    url = norm_url(str(_lookup(row, URL_KEYS) or ""))
    first = clean(str(_lookup(row, FIRST_KEYS) or ""))
    last = clean(str(_lookup(row, LAST_KEYS) or ""))
    name = clean(str(_lookup(row, NAME_KEYS) or "")) or " ".join(p for p in (first, last) if p)
    if not url and not name:
        return None
    if not url:
        slug = handle_from("", name)
        url = f"https://www.linkedin.com/in/{slug}"
    title = clean(str(_lookup(row, TITLE_KEYS) or ""))
    company = clean(str(_lookup(row, COMPANY_KEYS) or ""))
    headline = title
    if company and title and company.lower() not in title.lower():
        headline = f"{title} at {company}"
    about = clean(str(_lookup(row, ABOUT_KEYS) or ""))
    return Profile(
        url=url,
        name=name or handle_from(url),
        handle=handle_from(url, name),
        headline=headline or about[:180],
        about=about,
        followers=to_int(_lookup(row, FOLLOWER_KEYS)),
        location=clean(str(_lookup(row, LOC_KEYS) or "")),
        platform=platform_of(url) or "linkedin",
        source=source,
        company=company,
        company_size=parse_company_size(_lookup(row, SIZE_KEYS)),
        extra={
            "company": company,
            "company_size": parse_company_size(_lookup(row, SIZE_KEYS)),
            "title": title,
        },
    )


def _records_from_json(data) -> list[dict]:
    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict)]
    if not isinstance(data, dict):
        return []
    for key in ("rows", "records", "data", "results", "people"):
        val = data.get(key)
        if isinstance(val, list):
            return [r for r in val if isinstance(r, dict)]
        if isinstance(val, dict):
            inner = val.get("records") or val.get("rows") or val.get("items")
            if isinstance(inner, list):
                return [r for r in inner if isinstance(r, dict)]
    if any(_norm_key(k) in URL_KEYS or _norm_key(k) in NAME_KEYS for k in data):
        return [data]
    return []


def parse_table(text: str, source: str = "clay") -> list[Profile]:
    """CSV or JSON Clay table export. No network."""
    raw = (text or "").lstrip()
    if not raw:
        return []
    rows: list[dict] = []
    if raw[:1] in "{[":
        try:
            rows = _records_from_json(json.loads(raw))
        except ValueError:
            rows = []
    if not rows:
        reader = csv.DictReader(io.StringIO(text))
        rows = [dict(r) for r in reader]
    out = []
    seen = set()
    for row in rows:
        p = row_to_profile(row, source=source)
        if not p:
            continue
        key = p["url"]
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


def parse_path(path: str | Path, source: str = "clay") -> list[Profile]:
    return parse_table(Path(path).expanduser().read_text(encoding="utf-8"), source=source)


def _people_from_search(data: dict) -> list[Profile]:
    rows = _records_from_json(data)
    out = []
    for raw in rows:
        # Clay search records nest person fields.
        person = raw.get("person") if isinstance(raw.get("person"), dict) else raw
        linkedin = (
            person.get("linkedin_url")
            or person.get("linkedinUrl")
            or raw.get("linkedin_url")
            or ""
        )
        name = clean(person.get("full_name") or person.get("name") or "")
        if not name:
            name = " ".join(
                p for p in (person.get("first_name"), person.get("last_name")) if p
            )
        title = clean(person.get("title") or person.get("job_title") or "")
        org = person.get("company") or person.get("organization") or {}
        if isinstance(org, str):
            company = org
            size = 0
        else:
            company = clean((org or {}).get("name") or "")
            size = parse_company_size((org or {}).get("size") or (org or {}).get("employee_count"))
        url = norm_url(str(linkedin or ""))
        if not url and not name:
            continue
        if not url:
            url = f"https://www.linkedin.com/in/{handle_from('', name)}"
        out.append(Profile(
            url=url,
            name=name or handle_from(url),
            handle=handle_from(url, name),
            headline=(f"{title} at {company}" if title and company else (title or company)),
            about="",
            followers=0,
            location=clean(person.get("location") or ""),
            platform="linkedin",
            source="clay",
            company=company,
            company_size=size,
        ))
    return out


class ClayCollector(Collector):
    name = "clay"
    cost_per_profile = 0.0  # already-subscribed credits, not a new invoice

    def __init__(self, token: str | None = None):
        self._token = token if token is not None else auth.token("clay")

    def available(self) -> bool:
        return bool(self._token)

    def headers(self) -> dict[str, str]:
        return {"clay-api-key": self._token, "Content-Type": "application/json",
                "Accept": "application/json"}

    def ping(self) -> dict:
        if not self._token:
            return {}
        try:
            return http.get(f"{CLAY_API}/me", headers=self.headers(), timeout=20)
        except Exception:
            return {}

    def load(self, path: str | Path) -> list[Profile]:
        return parse_path(path)

    def search(self, query: str, limit: int = 25) -> list[Profile]:
        """People search. Empty list on any API miss — never invents rows."""
        if not self._token:
            return []
        try:
            data = http.post(
                f"{CLAY_API}/searches",
                payload={"source": "people", "query": query, "limit": min(max(int(limit), 1), 50)},
                headers=self.headers(),
                timeout=45,
            )
        except Exception:
            return []
        return _people_from_search(data if isinstance(data, dict) else {})[:limit]

    def profile(self, url: str) -> Profile | None:
        """Best-effort: search for this LinkedIn URL. Table ingest is preferred."""
        url = norm_url(url)
        if not url or not self._token:
            return None
        rows = self.search(url, limit=5)
        for p in rows:
            if norm_url(p.get("url") or "") == url:
                return p
        return rows[0] if rows else None
