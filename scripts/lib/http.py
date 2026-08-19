"""HTTP GET. JSON for APIs; text for the keyless HTML floor.

Retry lives here so every caller gets the same 429/5xx policy: try once more,
then raise. The search waterfall decides whether to fall through to another
backend; this module only knows how to fetch.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

RETRYABLE = frozenset({429, 500, 502, 503, 504})
UA = "Mozilla/5.0 (compatible; who-finder/3.6; +https://github.com/romaluev/who-finder)"


class HTTPError(RuntimeError):
    def __init__(self, status: int, url: str, body: str = ""):
        super().__init__(f"HTTP {status} {url}")
        self.status = status
        self.url = url
        self.body = body[:800]


def _url(url: str, params: dict[str, Any] | None) -> str:
    if not params:
        return url
    qs = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None and v != ""})
    return url + ("&" if "?" in url else "?") + qs


def _fetch(url: str, headers: dict[str, str] | None, timeout: int) -> str:
    hdrs = {"User-Agent": UA, "Accept": "*/*"}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, headers=hdrs, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        raise HTTPError(exc.code, url, body) from exc


def _with_retry(fn, retries: int = 1):
    last = None
    for attempt in range(max(0, retries) + 1):
        try:
            return fn()
        except HTTPError as exc:
            last = exc
            if exc.status not in RETRYABLE or attempt >= retries:
                raise
            time.sleep(0.4 * (attempt + 1))
    raise last  # pragma: no cover


def get(
    url: str,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 45,
    retries: int = 1,
) -> dict[str, Any]:
    target = _url(url, params)

    def once() -> dict[str, Any]:
        raw = _fetch(target, headers, timeout)
        if not raw.strip():
            return {}
        data = json.loads(raw)
        return data if isinstance(data, dict) else {"data": data}

    return _with_retry(once, retries=retries)


def get_text(
    url: str,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 30,
    retries: int = 1,
) -> str:
    target = _url(url, params)
    return _with_retry(lambda: _fetch(target, headers, timeout), retries=retries)


def sc_headers(token: str) -> dict[str, str]:
    return {"x-api-key": token, "Accept": "application/json"}
