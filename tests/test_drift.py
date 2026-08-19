"""Zero hits must say *why* it was zero.

The parsers in this build were written against ScrapeCreators' documented
response shapes, never against a live key. If upstream moves a field, every
parser silently yields nothing — and a report that calls that "no results"
asserts an absence the run never established. These tests pin the distinction
so the first real call diagnoses itself instead of lying quietly.
"""

import json

import pytest

from lib import cli, http, insights, sources


EMPTY_GOOGLE = {"success": True, "credits_remaining": 10, "results": []}

# Same records, one level deeper than the parser reads: the realistic shape of
# an upstream envelope change.
DRIFTED_GOOGLE = {
    "success": True,
    "credits_remaining": 10,
    "data": {
        "organic": [
            {
                "url": "https://www.linkedin.com/in/jane-doe",
                "title": "Jane Doe - Head of Content - LinkedIn",
                "description": "We make ai video ads.",
            }
        ]
    },
}

DRIFTED_YOUTUBE = {"success": True, "videos": [{"unexpected": "shape"}]}


def test_probe_counts_records_the_parser_would_read():
    assert sources.probe({"results": [1, 2, 3]}, "linkedin_people")["raw_n"] == 3
    assert sources.probe({"videos": [1], "shorts": [2]}, "youtube")["raw_n"] == 2
    assert sources.probe({"search_item_list": [1]}, "tiktok")["raw_n"] == 1
    assert sources.probe({}, "web")["raw_n"] == 0


def test_probe_locates_records_that_moved_to_a_new_key():
    pr = sources.probe(DRIFTED_GOOGLE, "linkedin_people")
    assert pr["raw_n"] == 0
    assert pr["container"] == "absent"
    assert pr["stray_n"] == 1
    assert pr["stray_at"] == "data.organic"


def test_probe_treats_a_present_empty_container_as_a_real_absence():
    pr = sources.probe(EMPTY_GOOGLE, "linkedin_people")
    assert pr["container"] == "present"
    assert pr["stray_n"] == 0


def test_probe_survives_a_non_dict_response():
    for bad in (None, [1, 2], "nope"):
        pr = sources.probe(bad, "web")
        assert pr["raw_n"] == 0
        assert pr["container"] == "absent"


@pytest.fixture
def wired(monkeypatch, tmp_path):
    monkeypatch.setenv("SCRAPECREATORS_API_KEY", "test-key")
    monkeypatch.setenv("WHO_FINDER_HOME", str(tmp_path))
    monkeypatch.delenv("WHO_FINDER_ICP", raising=False)
    return tmp_path


def _run(capsys, argv):
    assert cli.main(argv) == 0
    return json.loads(capsys.readouterr().out)


def _empty_per_endpoint(url, params=None, headers=None, timeout=45):
    """Each endpoint's own empty shape — an empty container, not a missing one."""
    if "/youtube/" in url:
        return {"success": True, "videos": []}
    if "/tiktok/" in url:
        return {"success": True, "search_item_list": []}
    if "/instagram/" in url:
        return {"success": True, "items": []}
    return EMPTY_GOOGLE


def test_a_genuinely_empty_source_is_reported_as_no_results(wired, capsys, monkeypatch):
    monkeypatch.setattr(http, "get", _empty_per_endpoint)
    payload = _run(capsys, ["find", "nobody at all", "--scenario", "people", "--agent"])
    states = {s["state"] for s in payload["results"]["source_status"]}
    assert states == {"no-results"}


def test_a_response_missing_its_container_entirely_is_drift(wired, capsys, monkeypatch):
    """An endpoint answering 200 with no recognisable container is not 'empty'."""
    monkeypatch.setattr(http, "get", lambda *a, **k: {"success": True, "credits_remaining": 9})
    payload = _run(capsys, ["find", "nobody at all", "--scenario", "people", "--agent"])
    assert {s["state"] for s in payload["results"]["source_status"]} == {"unparsed"}


def test_unreadable_records_are_reported_as_drift_not_emptiness(wired, capsys, monkeypatch):
    monkeypatch.setattr(http, "get", lambda *a, **k: DRIFTED_GOOGLE)
    payload = _run(capsys, ["find", "people making ai video ads", "--scenario", "people", "--agent"])
    status = payload["results"]["source_status"]

    assert status, "planner produced no steps"
    assert {s["state"] for s in status} == {"unparsed"}
    drifted = status[0]
    assert drifted["n"] == 0
    assert drifted["stray_at"] == "data.organic"
    assert "data" in drifted["response_keys"]


def test_drift_is_called_out_in_the_gaps_section(wired, capsys, monkeypatch):
    monkeypatch.setattr(http, "get", lambda *a, **k: DRIFTED_YOUTUBE)
    payload = _run(
        capsys, ["find", "ai video ad creators", "--scenario", "creators", "--agent"]
    )
    blob = json.dumps(payload["results"]["insights"])
    assert "SCHEMA DRIFT" in blob
    assert "parser bug, not an absence" in blob


def test_total_drift_is_never_summarised_as_an_empty_market():
    """The headline must not contradict the GAPS section."""
    status = [{"source": "web", "label": "a", "state": "unparsed", "raw_n": 3}]
    out = insights.findings(
        [], [], scenario="people", topic="t", n_new=0, n_known=0, source_status=status
    )
    assert "parser failure" in out[0]
    assert "Widen freshness" not in out[0]


def test_partial_drift_is_flagged_as_partial():
    status = [
        {"source": "web", "label": "a", "state": "unparsed", "raw_n": 3},
        {"source": "youtube", "label": "b", "state": "no-results", "raw_n": 0},
    ]
    out = insights.findings(
        [], [], scenario="people", topic="t", n_new=0, n_known=0, source_status=status
    )
    assert "1 source drifted" in out[0]


def test_a_real_empty_result_still_gets_the_ordinary_advice():
    status = [{"source": "web", "label": "a", "state": "no-results", "raw_n": 0}]
    out = insights.findings(
        [], [], scenario="people", topic="t", n_new=0, n_known=0, source_status=status
    )
    assert "Widen freshness" in out[0]


def test_coverage_line_distinguishes_the_two_zero_states():
    lines = insights.coverage(
        [
            {"source": "web", "label": "a", "state": "no-results", "n": 0, "raw_n": 0},
            {"source": "x", "label": "b", "state": "unparsed", "n": 0, "raw_n": 7},
        ]
    )
    assert "web:a no-results" in lines
    assert "x:b UNPARSED(7 raw)" in lines


def test_youtube_records_that_parse_to_nothing_are_drift():
    """A list of records we skip one-by-one is still a response we misread."""
    hits = sources.parse_youtube(DRIFTED_YOUTUBE, 10)
    pr = sources.probe(DRIFTED_YOUTUBE, "youtube")
    assert hits == []
    assert pr["raw_n"] == 1
