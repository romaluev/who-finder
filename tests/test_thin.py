"""Thin mode: no key is a usable shortlist, not exit 4."""

import json

from lib import auth, cli, http, providers, sources
from lib.agentio import E_AUTH


DDG_PEOPLE = [
    {
        "url": "https://www.linkedin.com/in/jane-doe",
        "title": "Jane Doe - Founder at Acme - LinkedIn",
        "snippet": "We build AI video tools at Acme.",
    }
]


def _home(monkeypatch, tmp_path):
    monkeypatch.setenv("WHO_FINDER_HOME", str(tmp_path))
    monkeypatch.delenv("SCRAPECREATORS_API_KEY", raising=False)
    monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    monkeypatch.delenv("WHO_FINDER_ICP", raising=False)
    return tmp_path


def _stub_floor(monkeypatch, items=None):
    rows = items if items is not None else DDG_PEOPLE
    monkeypatch.setattr(providers, "search_ddg", lambda q, limit: (rows, None))
    monkeypatch.setattr(providers, "search_brave", lambda *a, **k: ([], "no brave"))
    monkeypatch.setattr(providers, "search_hn", lambda q, limit: ([], None))
    monkeypatch.setattr(providers, "search_ytdlp", lambda q, limit: ([], "yt-dlp off"))
    monkeypatch.setattr(providers, "ytdlp_bin", lambda: "")


def _run(capsys, argv, expect=0):
    code = cli.main(argv)
    assert code == expect, capsys.readouterr()
    return json.loads(capsys.readouterr().out)


def test_find_without_a_key_does_not_exit_4(monkeypatch, tmp_path, capsys):
    _home(monkeypatch, tmp_path)
    _stub_floor(monkeypatch)
    payload = _run(capsys, ["find", "founders of AI video tools", "--agent"])
    assert payload["meta"].get("thin") is True
    assert payload["meta"]["credits_spent"] == 0
    ids = [e["id"] for e in payload["results"]["entities"]]
    assert "person/linkedin/jane-doe" in ids
    assert "error" not in payload


def test_deep_without_scrape_creators_uses_snippets(monkeypatch, tmp_path, capsys):
    _home(monkeypatch, tmp_path)
    _stub_floor(monkeypatch)
    payload = _run(capsys, ["find", "founders of AI video tools", "--deep", "10", "--agent"])
    assert payload["meta"]["thin"] is True
    gaps = " ".join(payload["results"]["insights"]["gaps"])
    assert "public search only" in gaps
    bands = {e.get("fit_band") for e in payload["results"]["entities"]}
    assert "strong" not in bands


def test_scrape_creators_500_falls_through_to_ddg(monkeypatch, tmp_path, capsys):
    _home(monkeypatch, tmp_path)
    monkeypatch.setenv("SCRAPECREATORS_API_KEY", "test-key")
    _stub_floor(monkeypatch)

    def boom(url, params=None, headers=None, timeout=45, **kw):
        raise http.HTTPError(500, url, "upstream down")

    monkeypatch.setattr(http, "get", boom)
    payload = _run(capsys, ["find", "founders of AI video tools", "--scenario", "people", "--agent"])
    status = payload["results"]["source_status"]
    assert status
    assert any(s.get("fell_back") for s in status)
    assert any(s.get("backend") == "ddg" for s in status)
    assert "person/linkedin/jane-doe" in [e["id"] for e in payload["results"]["entities"]]
    findings = " ".join(payload["results"]["insights"]["findings"])
    assert "nobody" not in findings.lower() or "empty market" not in findings.lower()


def test_total_backend_failure_is_an_error_not_an_empty_market(monkeypatch, tmp_path, capsys):
    _home(monkeypatch, tmp_path)
    monkeypatch.setattr(providers, "search_ddg", lambda q, limit: ([], "ddg down"))
    monkeypatch.setattr(providers, "search_brave", lambda *a, **k: ([], "no brave"))
    monkeypatch.setattr(providers, "search_hn", lambda q, limit: ([], "hn down"))
    monkeypatch.setattr(providers, "search_ytdlp", lambda q, limit: ([], "off"))
    monkeypatch.setattr(providers, "ytdlp_bin", lambda: "")
    payload = _run(capsys, ["find", "founders of AI video tools", "--scenario", "people", "--frames", "1", "--agent"])
    states = {s["state"] for s in payload["results"]["source_status"]}
    assert states == {"error"}
    findings = payload["results"]["insights"]["findings"][0]
    assert "outage" in findings or "failed" in findings
    assert "empty market" in findings


def test_cheap_dry_run_is_zero_without_a_paid_key(monkeypatch, tmp_path, capsys):
    _home(monkeypatch, tmp_path)
    payload = _run(
        capsys,
        ["find", "founders of AI video tools", "--cheap", "--deep", "10", "--dry-run", "--agent"],
    )
    est = payload["results"]["estimate"]
    assert est["total_max"] == 0
    assert est["discovery"] == 0
    assert est["thin"] is True
    assert "$0" in payload["table"]
    assert all(s["credits"] == 0 for s in est["steps"])
    assert all(s["backend"] in {"ddg", "brave", "hn", "ytdlp"} for s in est["steps"])


def test_cheap_saves_scrape_creators_for_native_and_enrich(monkeypatch, tmp_path, capsys):
    _home(monkeypatch, tmp_path)
    monkeypatch.setenv("SCRAPECREATORS_API_KEY", "test-key")
    payload = _run(
        capsys,
        ["find", "founders of AI video tools", "--cheap", "--deep", "10", "--dry-run", "--agent"],
    )
    est = payload["results"]["estimate"]
    by_source = {}
    for s in est["steps"]:
        by_source.setdefault(s["source"], []).append(s)
    assert "tiktok" not in by_source
    assert "instagram" not in by_source
    for s in by_source.get("linkedin_people", []):
        assert s["backend"] in {"brave", "ddg"}
        assert s["credits"] == 0
    for s in by_source.get("youtube", []):
        assert s["backend"] == "scrapecreators"
        assert s["credits"] == 1
    assert est["enrichment_max"] == 10
    assert est["discovery"] == sum(s["credits"] for s in est["steps"])


def test_doctor_ready_thin_is_usable(monkeypatch, tmp_path, capsys):
    _home(monkeypatch, tmp_path)
    payload = _run(capsys, ["doctor", "--agent"])
    assert payload["results"]["state"] == "ready-thin"
    assert payload["results"]["thin_available"] is True
    assert payload["results"]["backends"]["ddg"]["available"] is True
    assert "thinner" in payload["table"].lower() or "public search" in payload["table"].lower()


def test_doctor_rejected_key_still_offers_thin(monkeypatch, tmp_path, capsys):
    _home(monkeypatch, tmp_path)
    monkeypatch.setenv("SCRAPECREATORS_API_KEY", "test-key")

    def reject(url, params=None, headers=None, timeout=45, **kw):
        raise http.HTTPError(401, url, "bad key")

    monkeypatch.setattr(http, "get", reject)
    # doctor uses sources.http.get
    monkeypatch.setattr(sources.http, "get", reject)
    payload = _run(capsys, ["doctor", "--agent"])
    assert payload["results"]["state"] == "auth-failed"
    assert payload["results"]["thin_available"] is True
    assert "thin" in payload["table"].lower()


def test_enrich_without_a_key_is_still_exit_4(monkeypatch, tmp_path, capsys):
    _home(monkeypatch, tmp_path)
    code = cli.main(["enrich", "--agent"])
    payload = json.loads(capsys.readouterr().out)
    assert code == E_AUTH
    assert payload["error"]["code"] == E_AUTH


def test_setup_brave_round_trip(monkeypatch, tmp_path, capsys):
    _home(monkeypatch, tmp_path)
    assert cli.main(["setup", "--brave", "BSA_test_brave_key_12345"]) == 0
    capsys.readouterr()
    assert auth.brave_token() == "BSA_test_brave_key_12345"
    monkeypatch.setenv("BRAVE_API_KEY", "from-env-brave-key")
    assert auth.brave_token() == "from-env-brave-key"
