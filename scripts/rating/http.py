"""HTTP GET/POST. JSON for APIs. Retry lives here so every collector shares it."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

RETRYABLE = frozenset({429, 500, 502, 503, 504})
UA = "Mozilla/5.0 (compatible; who-finder/4.0; +https://github.com/romaluev/who-finder)"


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


def _fetch(url: str, headers: dict[str, str] | None, timeout: int, data: bytes | None = None) -> str:
    hdrs = {"User-Agent": UA, "Accept": "*/*"}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, headers=hdrs, data=data, method="POST" if data else "GET")
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


def get_text(
    url: str,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 30,
    retries: int = 1,
) -> str:
    """HTML / XML / plain text. Same retry policy as get()."""
    target = _url(url, params)
    hdrs = {"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}
    if headers:
        hdrs.update(headers)
    return _with_retry(lambda: _fetch(target, hdrs, timeout), retries=retries)


def get(
    url: str,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 45,
    retries: int = 1,
) -> dict[str, Any]:
    target = _url(url, params)
    hdrs = {"Accept": "application/json"}
    if headers:
        hdrs.update(headers)

    def once() -> dict[str, Any]:
        raw = _fetch(target, hdrs, timeout)
        if not raw.strip():
            return {}
        data = json.loads(raw)
        return data if isinstance(data, dict) else {"data": data}

    return _with_retry(once, retries=retries)


def post(
    url: str,
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 45,
    retries: int = 1,
) -> dict[str, Any]:
    body = json.dumps(payload or {}).encode("utf-8")
    hdrs = {"Content-Type": "application/json"}
    if headers:
        hdrs.update(headers)

    def once() -> dict[str, Any]:
        raw = _fetch(url, hdrs, timeout, data=body)
        if not raw.strip():
            return {}
        data = json.loads(raw)
        return data if isinstance(data, dict) else {"data": data}

    return _with_retry(once, retries=retries)
