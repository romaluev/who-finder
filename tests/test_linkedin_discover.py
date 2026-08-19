"""LinkedIn URLs are researched on the public web, never fetched."""

from rating.collectors.public import parse_linkedin_search_hit, PublicCollector
from rating.economy import lite_plan


def test_parse_linkedin_search_hit_reads_name_not_invents():
    name, headline, followers, connections = parse_linkedin_search_hit(
        "Jamie Zetz - Founder at Example | LinkedIn",
        "Jamie Zetz · 12k followers · 500+ connections · Helping CMOs ship ads",
    )
    assert name == "Jamie Zetz"
    assert "Founder" in headline
    assert followers == 12000
    assert connections == 500


def test_parse_linkedin_search_hit_empty_when_unread():
    name, headline, followers, _ = parse_linkedin_search_hit("LinkedIn", "")
    assert name == ""
    assert followers == 0
    assert headline == ""


def test_discover_linkedin_never_fetches_linkedin(monkeypatch):
    hits = [{
        "url": "https://www.linkedin.com/in/jamiezetz",
        "title": "Jamie Zetz - CMO | LinkedIn",
        "snippet": "CMO building AI video ads · 18k followers",
    }]
    fetched = []

    def fake_search(query, limit=8):
        return hits, "ddg"

    def fake_get_text(url, **kwargs):
        fetched.append(url)
        raise AssertionError(f"must not fetch {url}")

    def boom(*_a, **_k):
        raise AssertionError("YouTube is not the LinkedIn path")

    monkeypatch.setattr("rating.collectors.public.search_web", fake_search)
    monkeypatch.setattr("rating.collectors.public.http.get_text", fake_get_text)
    monkeypatch.setattr("rating.collectors.public.ytdlp_search", boom)

    prof, posts = PublicCollector().discover_linkedin("https://www.linkedin.com/in/jamiezetz")
    assert fetched == []
    assert prof["name"] == "Jamie Zetz"
    assert prof["url"].endswith("linkedin.com/in/jamiezetz")
    assert prof["followers"] == 18000
    assert posts == []


def test_lite_plan_includes_public_for_linkedin():
    plan = lite_plan("https://www.linkedin.com/in/jamiezetz", cheap=True)
    assert plan[0]["backend"] == "public"


def test_channel_fits_handle():
    from rating.collectors.public import channel_fits_handle
    assert channel_fits_handle("scottdclary", "Scott D. Clary - Success Story Podcast")
    assert channel_fits_handle("chris-tottman", "Chris Tottman")
    assert not channel_fits_handle("jamiezetz", "Jamie Oliver")
    assert not channel_fits_handle("jamiezetz", "jamiezetz@yahoo.com")
