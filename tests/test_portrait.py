"""Portraits have to be sentences a person would say, derived from fields we have."""

from lib import portrait


def test_scoring_arithmetic_becomes_english():
    assert portrait.english_reason("topic match: ai (+18)") == "their profile talks about ai"
    assert portrait.english_reason("match 'founder' (+12)") == "described as founder"
    assert "in the size you asked for" in portrait.english_reason("audience 41k in target band (+18)")
    assert portrait.english_reason("signal hiring (+10)") == "they're hiring"


def test_internal_search_labels_become_places():
    assert portrait.english_step("linkedin_people:li-in") == "LinkedIn profiles"
    assert "exact phrase" in portrait.english_step("linkedin_people:li-in~exact")
    assert "YouTube" in portrait.english_step("youtube:yt-talks")


def test_lede_uses_the_bio_not_a_word_bag():
    r = {"name": "Jane Doe", "audience": 24000, "audience_kind": "followers"}
    d = {"headline": "Head of Content at Acme", "bio": "I lead content at Acme. We build ai video ads.",
         "location": "Austin", "audience": 24000, "audience_kind": "followers"}
    out = portrait.lede(r, d)
    assert "Jane Doe is Head of Content at Acme" in out
    assert "Austin" in out
    assert "24k" in out
    assert "I lead content at Acme" in out


def test_lede_does_not_invent_a_role_when_there_is_none():
    out = portrait.lede({"name": "Sam"}, {"bio": ""})
    assert "is " not in out
    assert out.startswith("Sam")


def test_outreach_angle_prefers_hiring_over_a_generic_line():
    r = {"signals": ["hiring", "posting"]}
    d = {"signals": ["hiring", "posting"], "recent": [{"title": "We're growing the team"}]}
    assert "hiring" in portrait.angle(r, d).lower()


def test_landscape_names_who_to_talk_to_first():
    rows = [
        {"id": "p/1", "name": "Jane", "platform": "linkedin", "kind": "person",
         "fit_band": "strong", "fit_reasons": ["match 'founder' (+12)"], "audience": 10000},
        {"id": "p/2", "name": "Sam", "platform": "linkedin", "kind": "person",
         "fit_band": "off", "audience": 200},
    ]
    doss = [
        {"id": "p/1", "name": "Jane", "headline": "Founder", "audience": 10000, "signals": ["hiring"]},
        {"id": "p/2", "name": "Sam", "audience": 200, "signals": []},
    ]
    out = " ".join(portrait.landscape(rows, doss, topic="ai video", n_new=2, n_known=0))
    assert "Talk to first" in out and "Jane" in out
    assert "hiring" in out
    assert "weak or off fit" in out
    assert "ai video" in out


def test_landscape_calls_out_a_skewed_audience():
    rows = [
        {"id": "a", "name": "Big", "platform": "youtube", "kind": "person",
         "fit_band": "strong", "audience": 310000},
        {"id": "b", "name": "Small", "platform": "linkedin", "kind": "person",
         "fit_band": "strong", "audience": 8000},
    ]
    doss = [
        {"id": "a", "name": "Big", "audience": 310000},
        {"id": "b", "name": "Small", "audience": 8000},
    ]
    out = " ".join(portrait.landscape(rows, doss, topic="x", n_new=2, n_known=0))
    assert "skewed" in out and "Big" in out
