"""JSON GET. ScrapeCreators: x-api-key header."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


class HTTPError(RuntimeError):
    def __init__(self, status: int, url: str, body: str = ""):
        super().__init__(f"HTTP {status} {url}")
        self.status = status
        self.url = url
        self.body = body[:800]


def get(url: str, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None, timeout: int = 45) -> dict[str, Any]:
    if params:
        qs = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None and v != ""})
        url = url + ("&" if "?" in url else "?") + qs
    req = urllib.request.Request(url, headers=headers or {}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        raise HTTPError(exc.code, url, body) from exc
    if not raw.strip():
        return {}
    data = json.loads(raw)
    return data if isinstance(data, dict) else {"data": data}


def sc_headers(token: str) -> dict[str, str]:
    return {"x-api-key": token, "Accept": "application/json"}


HTTPError = HTTPError
sc_headers = sc_headers
