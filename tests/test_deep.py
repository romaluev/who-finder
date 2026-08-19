"""End-to-end deep run with the network faked.

Covers the whole pipeline in one pass: plan -> search -> identity -> roster ->
enrich -> ICP fit -> priority -> brief. If this test passes, `find --deep`
works against real responses in the shape ScrapeCreators documents.
"""

import json

import pytest

from lib import cli, db, http


GOOGLE_PEOPLE = {
    "results": [
        {
            "url": "https://www.linkedin.com/in/jane-doe",
            "title": "Jane Doe - Head of Content at Acme - LinkedIn",
            "description": "Head of Content at Acme. We make ai video ads at scale.",
        },
        {
            "url": "https://www.linkedin.com/in/sam-smith",
            "title": "Sam Smith - Student - LinkedIn",
            "description": "Aspiring editor, student at Film School.",
        },
    ]
}

YOUTUBE_SEARCH = {
    "videos": [
        {
            "id": "vid1",
            "title": "How we make ai video ads",
            "url": "https://www.youtube.com/watch?v=vid1",
            "viewCountInt": 120000,
            "likeCount": 4000,
            "commentCount": 300,
            "channel": {"handle": "@adlab", "name": "Ad Lab", "url": "https://www.youtube.com/@adlab"},
        }
    ]
}

LINKEDIN_PROFILE = {
    "success": True,
    "name": "Jane Doe",
    "location": "Austin, Texas, United States",
    "followers": 24000,
    "about": "I lead content at Acme. We build ai video ads for consumer brands.",
    "experience": [{"name": "******* ** ******", "member": {"description": "****"}}],
    "recentPosts": [{"title": "We are hiring a senior video producer", "link": "https://li/post/1"}],
    "similarProfiles": [{"name": "Rae Kim", "link": "https://www.linkedin.com/in/raekim"}],
}

SAM_PROFILE = {
    "success": True,
    "name": "Sam Smith",
    "location": "Manchester, United Kingdom",
    "followers": 180,
    "about": "Student at Film School. Aspiring editor looking for my first role.",
    "experience": [],
}

YOUTUBE_CHANNEL = {
    "success": True,
    "name": "Ad Lab",
    "description": "We teach ai video ads production.",
    "subscriberCount": 310000,
    "videoCountText": "412 videos",
    "viewCountText": "48,000,000 views",
    "country": "United States",
    "links": ["https://adlab.example"],
}


def fake_get(url, params=None, headers=None, timeout=45):
    if "/v1/google/search" in url:
        q = (params or {}).get("query", "")
        return GOOGLE_PEOPLE if "linkedin.com/in" in q else {"results": []}
    if "/v1/youtube/search" in url:
        return YOUTUBE_SEARCH
    if "/v1/linkedin/profile" in url:
        return SAM_PROFILE if "sam-smith" in (params or {}).get("url", "") else LINKEDIN_PROFILE
    if "/v1/youtube/channel" in url:
        return YOUTUBE_CHANNEL
    if "/v1/credit-balance" in url:
        return {"credits_remaining": 999}
    raise AssertionError(f"unexpected call: {url}")


@pytest.fixture
def wired(monkeypatch, tmp_path):
    monkeypatch.setattr(http, "get", fake_get)
    monkeypatch.setenv("SCRAPECREATORS_API_KEY", "test-key")
    monkeypatch.setenv("WHO_FINDER_HOME", str(tmp_path))
    monkeypatch.delenv("WHO_FINDER_ICP", raising=False)
    icp_path = tmp_path / "icp.json"
    icp_path.write_text(
        json.dumps(
            {
                "name": "test-icp",
                "must_any": ["ai video"],
                "boost": {"head of": 12, "founder": 15},
                "penalty": {"student": -20, "aspiring": -12},
                "audience": {"min": 1000, "sweet_min": 10000, "sweet_max": 2000000, "weight": 20},
                "geo": {"prefer": ["united states"], "weight": 8},
                "signals": {"hiring": 10},
            }
        ),
        encoding="utf-8",
    )
    return tmp_path


def _run(capsys, argv):
    assert cli.main(argv) == 0
    return json.loads(capsys.readouterr().out)


def test_deep_find_produces_a_ranked_brief(wired, capsys):
    payload = _run(
        capsys,
        ["find", "people making ai video ads", "--scenario", "people", "--deep", "5", "--agent", "--full"],
    )
    table = payload["table"]
    results = payload["results"]

    assert payload["meta"]["depth"] == 5
    assert payload["meta"]["icp"] == "test-icp"

    ids = [e["id"] for e in results["entities"]]
    assert "person/linkedin/jane-doe" in ids
    assert "person/youtube/adlab" in ids

    jane = next(e for e in results["entities"] if e["id"] == "person/linkedin/jane-doe")
    sam = next(e for e in results["entities"] if e["id"] == "person/linkedin/sam-smith")

    assert jane["audience"] == 24000
    assert "hiring" in jane["signals"]
    assert jane["fit_band"] == "strong"
    assert jane["priority"] > sam["priority"]
    assert any("head of" in r for r in jane["fit_reasons"])

    # The masked LinkedIn experience block must never reach the report.
    assert "*****" not in table
    assert "WHAT I FOUND" in table
    assert "WHO TO CONTACT" in table
    assert "person/linkedin/jane-doe" in table
    assert "hiring" in table

    assert results["insights"]["findings"]
    assert any("ok(" in c for c in results["insights"]["coverage"])


def test_a_name_stays_new_until_you_act_on_it(wired, capsys):
    """Re-finding an untouched name is still the outreach queue, not old news."""
    _run(capsys, ["find", "people making ai video ads", "--scenario", "people", "--deep", "2", "--agent"])
    second = _run(
        capsys, ["find", "people making ai video ads", "--scenario", "people", "--deep", "2", "--agent"]
    )
    assert second["results"]["n_new"] > 0

    assert cli.main(["mark", "person/linkedin/jane-doe", "--status", "outreached", "--agent"]) == 0
    capsys.readouterr()
    third = _run(
        capsys, ["find", "people making ai video ads", "--scenario", "people", "--deep", "2", "--agent"]
    )
    jane = next(e for e in third["results"]["entities"] if e["id"] == "person/linkedin/jane-doe")
    assert jane["novelty"] == "known"
    assert third["results"]["n_known"] >= 1


def test_report_rebuilds_the_brief_without_spending_credits(wired, capsys, monkeypatch):
    _run(capsys, ["find", "people making ai video ads", "--scenario", "people", "--deep", "5", "--agent"])

    def explode(*a, **k):
        raise AssertionError("report must not hit the network")

    monkeypatch.setattr(http, "get", explode)
    payload = _run(capsys, ["report", "--agent"])
    assert payload["meta"]["credits_spent"] == 0
    assert "person/linkedin/jane-doe" in payload["table"]
    assert "Head of Content" in payload["table"] or "content at Acme" in payload["table"]


def test_expand_pulls_similar_profiles_without_a_new_search(wired, capsys, monkeypatch):
    _run(capsys, ["find", "people making ai video ads", "--scenario", "people", "--deep", "5", "--agent"])

    def explode(*a, **k):
        raise AssertionError("expand must reuse the stored dossier")

    monkeypatch.setattr(http, "get", explode)
    payload = _run(capsys, ["expand", "person/linkedin/jane-doe", "--agent"])
    ids = [e["id"] for e in payload["results"]["entities"]]
    assert "person/linkedin/raekim" in ids
    assert payload["meta"]["credits_spent"] == 0


def test_export_carries_the_research_into_csv(wired, capsys, tmp_path):
    _run(capsys, ["find", "people making ai video ads", "--scenario", "people", "--deep", "5", "--agent"])
    out = tmp_path / "handoff.csv"
    assert cli.main(["export", "--status", "new", "--out", str(out), "--agent"]) == 0
    text = out.read_text(encoding="utf-8")
    header = text.splitlines()[0]
    for col in ("headline", "audience", "fit_score", "fit_band", "priority", "signals"):
        assert col in header
    assert "person/linkedin/jane-doe" in text
    assert "strong" in text


def test_shallow_find_still_emits_the_compact_table(wired, capsys):
    payload = _run(capsys, ["find", "people making ai video ads", "--scenario", "people", "--agent"])
    assert payload["meta"]["depth"] == 0
    assert "WHO TO CONTACT" not in payload["table"]
    assert "scenario=people" in payload["table"]


def test_enrich_command_scores_stored_rows(wired, capsys):
    _run(capsys, ["find", "people making ai video ads", "--scenario", "people", "--agent"])
    payload = _run(capsys, ["enrich", "person/linkedin/jane-doe", "--agent", "--full"])
    dossier = payload["results"]["dossiers"]["person/linkedin/jane-doe"]
    assert dossier["enriched"] is True
    assert dossier["audience"] == 24000
    assert payload["meta"]["credits_spent"] == 1


def test_dossier_survives_a_roundtrip_through_sqlite(wired, capsys):
    _run(capsys, ["find", "people making ai video ads", "--scenario", "people", "--deep", "5", "--agent"])
    conn = db.connect(db.default_db())
    try:
        stored = db.get_dossier(conn, "person", "linkedin", "jane-doe")
    finally:
        conn.close()
    assert stored["audience"] == 24000
    assert stored["fit_band"] == "strong"
    assert isinstance(stored["signals"], list)
    assert stored["payload"]["recent"][0]["title"].startswith("We are hiring")


def test_enrichment_failure_degrades_to_the_search_snippet(monkeypatch, wired, capsys):
    def flaky(url, params=None, headers=None, timeout=45):
        if "/v1/linkedin/profile" in url:
            raise http.HTTPError(500, url, "boom")
        return fake_get(url, params, headers, timeout)

    monkeypatch.setattr(http, "get", flaky)
    payload = _run(
        capsys,
        ["find", "people making ai video ads", "--scenario", "people", "--deep", "5", "--agent", "--full"],
    )
    jane = payload["results"]["dossiers"]["person/linkedin/jane-doe"]
    assert jane["enriched"] is False
    assert jane["headline"]
    assert any("HTTP 500" in e for e in payload["results"]["errors"])
    # A row we could not verify must not be presented as a confident answer.
    assert jane["fit_band"] != "strong"
