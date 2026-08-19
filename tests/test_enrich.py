from lib.enrich import (
    _headline_from_snippet,
    _linkedin_company,
    _linkedin_person,
    _youtube,
    enrich,
    enrichable,
    people_identities,
    profile_url,
    shallow,
    similar_identities,
)
from lib.util import clean, human, is_masked, keywords, to_int


def _blankish(kind="person", platform="linkedin", handle="x"):
    from lib.enrich import _blank

    return _blank(kind, platform, handle)


def test_to_int_handles_text_counts():
    assert to_int("2.75M subscribers") == 2_750_000
    assert to_int("9,221 videos") == 9221
    assert to_int("2,170,355,382 views") == 2_170_355_382
    assert to_int(None) == 0


def test_masked_linkedin_strings_are_dropped():
    masked = "******* ** * ****** ****** ********** *********"
    assert is_masked(masked) is True
    assert clean(masked) == ""
    assert is_masked("C++ dev *not* for hire") is False


def test_human_reads_like_a_person_wrote_it():
    assert human(2_750_000) == "2.8M"
    assert human(24_000) == "24k"
    assert human(950) == "950"


def test_keywords_skip_stopwords():
    kw = keywords("We build generative video ads for the brands of the world")
    assert "generative" in kw
    assert "the" not in kw
    assert "build" not in kw


def test_keywords_strip_sentence_punctuation():
    """`brands.` and `brands` are one theme, not two."""
    kw = keywords("ai video for brands. Great brands deserve ai video")
    assert "brands" in kw
    assert "brands." not in kw


def test_profile_url_splits_person_and_company():
    assert profile_url("person", "linkedin", "ada") == "https://www.linkedin.com/in/ada/"
    assert profile_url("company", "linkedin", "acme") == "https://www.linkedin.com/company/acme/"


def test_only_platforms_with_a_profile_endpoint_are_enrichable():
    assert enrichable("person", "linkedin") is True
    assert enrichable("company", "web") is False
    assert enrichable("person", "reddit") is False


def test_headline_from_snippet_strips_name_and_site_suffix():
    got = _headline_from_snippet("Jane Doe - Head of Content at Acme - LinkedIn", "Jane Doe")
    assert got == "Head of Content at Acme"


def test_shallow_dossier_keeps_snippet_headline():
    d = shallow(
        {
            "kind": "person",
            "platform": "linkedin",
            "handle": "jane",
            "name": "Jane Doe",
            "sample_title": "Jane Doe - Head of Content at Acme | LinkedIn",
        }
    )
    assert d["enriched"] is False
    assert d["headline"] == "Head of Content at Acme"
    assert d["headline_source"] == "search-snippet"


def test_linkedin_person_masked_experience_does_not_leak_asterisks():
    d = _blankish()
    _linkedin_person(
        d,
        {
            "name": "Sam Parr",
            "location": "Westport, Connecticut, United States",
            "followers": 64803,
            "about": "I founded The Hustle, a business news media company.",
            "experience": [{"name": "******* ** ******", "member": {"description": "*** ***"}}],
            "recentPosts": [{"title": "We are hiring a video lead", "link": "https://x"}],
            "similarProfiles": [{"name": "Steve Cody", "link": "https://ca.linkedin.com/in/stevemcody"}],
        },
    )
    assert "*" not in d["headline"]
    assert d["masked"] is True
    assert d["audience"] == 64803
    assert d["audience_kind"] == "followers"
    assert d["headline_source"] == "linkedin-about"
    assert d["similar"][0]["name"] == "Steve Cody"


def test_linkedin_person_uses_real_experience_when_public():
    d = _blankish()
    _linkedin_person(d, {"name": "Ada", "experience": [{"name": "Hampton", "url": "https://li/company/x"}]})
    assert d["headline"] == "at Hampton"
    assert d["headline_source"] == "linkedin-experience"


def test_linkedin_company_extracts_funding_and_employees():
    d = _blankish("company", "linkedin", "shopify")
    _linkedin_company(
        d,
        {
            "name": "Shopify",
            "description": "Commerce platform.",
            "employeeCount": 23591,
            "industry": "Software Development",
            "size": "10,001+ employees",
            "founded": 2006,
            "headquarters": "Ottawa, ON",
            "specialties": ["ecommerce", "payments"],
            "funding": {
                "numberOfRounds": 4,
                "lastRound": {"type": "Series C", "date": "2024-01-11T00:00:00.000Z", "amount": "US$ 100.0M"},
                "investors": [{"name": "Insight Partners"}],
            },
            "employees": [{"name": "Joseph Smarr", "title": "Principal Engineer @ Shopify", "link": "https://www.linkedin.com/in/jsmarr"}],
            "similarPages": [{"name": "Airbnb", "link": "https://www.linkedin.com/company/airbnb"}],
        },
    )
    assert d["audience"] == 23591
    assert d["audience_kind"] == "employees"
    assert d["company"]["funding_rounds"] == 4
    assert d["company"]["investors"] == ["Insight Partners"]
    assert "Software Development" in d["headline"]
    assert d["people"][0]["title"] == "Principal Engineer @ Shopify"


def test_youtube_channel_maps_subscribers_and_links():
    d = _blankish("person", "youtube", "pat")
    _youtube(
        d,
        {
            "name": "The Pat McAfee Show",
            "description": "Daily sports show",
            "subscriberCount": 2750000,
            "videoCountText": "9,221 videos",
            "viewCountText": "2,170,355,382 views",
            "country": "United States",
            "twitter": "https://twitter.com/PatMcAfeeShow",
            "links": ["https://store.patmcafeeshow.com"],
        },
    )
    assert d["audience"] == 2_750_000
    assert d["audience_detail"]["videos"] == 9221
    assert "https://twitter.com/PatMcAfeeShow" in d["links"]


def test_signals_derive_from_text_and_numbers():
    d = enrich.__globals__["_derive_signals"](
        {
            "bio": "We are hiring a creative lead",
            "headline": "",
            "recent": [{"title": "we raised a Series A"}],
            "audience": 250_000,
            "audience_kind": "followers",
            "verified": True,
            "company": {"funding_rounds": 2, "last_round_date": "2025-01-01", "employees": 40},
        }
    )
    assert "hiring" in d
    assert "funded" in d
    assert "recent-round" in d
    assert "verified" in d
    assert "large-audience" in d
    assert "smb" in d


def test_headcount_is_not_described_as_an_audience():
    """A 120-person company is `smb`, never `small-audience`."""
    d = enrich.__globals__["_derive_signals"](
        {
            "bio": "AI video tooling",
            "headline": "",
            "recent": [],
            "audience": 120,
            "audience_kind": "employees",
            "company": {"employees": 120},
        }
    )
    assert "smb" in d
    assert not any(s.endswith("-audience") for s in d)


def test_similar_and_employee_lists_become_candidate_rows():
    d = {
        "id": "company/linkedin/acme",
        "kind": "company",
        "similar": [{"name": "Airbnb", "url": "https://www.linkedin.com/company/airbnb"}],
        "people": [{"name": "Jo", "title": "Head of Video", "url": "https://www.linkedin.com/in/jo"}],
    }
    sim = similar_identities(d)
    assert sim[0]["platform"] == "linkedin"
    assert sim[0]["handle"] == "airbnb"
    assert sim[0]["via"] == "company/linkedin/acme"
    ppl = people_identities(d)
    assert ppl[0]["kind"] == "person"
    assert ppl[0]["handle"] == "jo"
    assert ppl[0]["sample_title"] == "Head of Video"


def test_enrich_returns_error_row_for_unenrichable_platform():
    d = enrich("tok", {"kind": "company", "platform": "web", "handle": "acme", "sample_title": "Acme - AI video studio"})
    assert d["enriched"] is False
    assert "no profile endpoint" in d["error"]
    assert d["headline"]
