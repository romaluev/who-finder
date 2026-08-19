import json

from lib import icp


def _d(**kw):
    base = {
        "id": "person/linkedin/x",
        "kind": "person",
        "platform": "linkedin",
        "handle": "x",
        "name": "X",
        "headline": "",
        "bio": "",
        "topics": [],
        "recent": [],
        "signals": [],
        "company": {},
        "audience": 0,
        "location": "",
        "country": "",
        "enriched": True,
    }
    base.update(kw)
    return base


CFG = {
    "name": "test",
    "must_any": ["ai video"],
    "boost": {"founder": 15, "head of": 12},
    "penalty": {"student": -20},
    "audience": {"min": 1000, "sweet_min": 10000, "sweet_max": 2000000, "weight": 20},
    "geo": {"prefer": ["united states"], "weight": 8},
    "signals": {"hiring": 10, "funded": 12},
}


def test_strong_fit_stacks_reasons():
    f = icp.fit(
        _d(
            headline="Founder at an ai video studio",
            bio="We make ai video ads",
            audience=24_000,
            location="Austin, United States",
            signals=["hiring"],
        ),
        CFG,
    )
    assert f["band"] == "strong"
    assert f["score"] >= 70
    joined = " ".join(f["reasons"])
    assert "topic match" in joined
    assert "founder" in joined
    assert "audience 24k in target band" in joined
    assert "geo match" in joined


def test_penalty_terms_push_a_row_down():
    f = icp.fit(_d(headline="Student, aspiring ai video editor", bio="ai video", audience=200), CFG)
    assert f["score"] < 60
    assert any("student" in r for r in f["reasons"])


def test_missing_topic_caps_the_band_even_with_boosts():
    f = icp.fit(_d(headline="Founder at a dog grooming brand", bio="we groom dogs", audience=50_000), CFG)
    assert f["band"] in {"weak", "off"}
    assert any("no topic keyword" in r for r in f["reasons"])


def test_unenriched_row_is_unknown_not_off():
    """Absence of evidence must never rank as a hard no."""
    f = icp.fit(_d(enriched=False, headline="", bio=""), CFG)
    assert f["band"] == "unknown"
    assert any("provisional" in g for g in f["gaps"])


def test_gaps_name_what_is_missing():
    f = icp.fit(_d(headline="founder of an ai video tool", audience=0), CFG)
    assert any("audience" in g for g in f["gaps"])


def test_topic_terms_prefer_the_whole_phrase():
    terms = icp.topic_terms("people making ai video ads")
    assert terms[0] == "making ai video ads"
    assert "ai" in terms


def test_generic_config_is_seeded_from_the_topic(tmp_path, monkeypatch):
    monkeypatch.setenv("WHO_FINDER_HOME", str(tmp_path))
    monkeypatch.delenv("WHO_FINDER_ICP", raising=False)
    cfg = icp.load(None, topic="ai video ads")
    assert cfg["_path"] == ""
    assert "ai video ads" in cfg["must_any"]


def test_explicit_config_file_wins(tmp_path):
    path = tmp_path / "icp.json"
    path.write_text(json.dumps({"name": "mine", "boost": {"cto": 5}}), encoding="utf-8")
    cfg = icp.load(str(path))
    assert cfg["name"] == "mine"
    assert cfg["_path"] == str(path)


def test_reach_points_are_log_scaled():
    assert icp.reach_points(0) == 0
    assert 25 < icp.reach_points(1_000) < 35
    assert 45 < icp.reach_points(10_000) < 55
    assert icp.reach_points(10_000_000) == 100


def test_priority_rewards_new_names_and_penalises_unknown():
    d = _d(audience=10_000)
    strong = {"score": 80, "band": "strong"}
    p_new = icp.priority(d, strong, "new")
    p_known = icp.priority(d, strong, "known")
    assert p_new > p_known
    p_unknown = icp.priority(d, {"score": 80, "band": "unknown"}, "new")
    assert p_unknown < p_new


def test_rank_sorts_by_priority():
    rows = [{"priority": 10, "fit_score": 90}, {"priority": 80, "fit_score": 10}]
    assert icp.rank(rows)[0]["priority"] == 80
