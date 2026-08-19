"""Keyless backends parse real HTML/JSON. They never invent an identity."""

from urllib.parse import quote

from lib import providers
from lib.identity import parse_identity

DDG_HTML = """
<html><body>
<div class="result results_links">
  <a rel="nofollow" class="result__a" href="//duckduckgo.com/l/?uddg={uddg}">
    Jane Doe - Founder at Acme - LinkedIn
  </a>
  <a class="result__snippet">We build AI video tools at Acme.</a>
</div>
<div class="result results_links">
  <a class="result__a" href="https://www.youtube.com/@adlab">Ad Lab</a>
  <a class="result__snippet">AI video ads tutorials</a>
</div>
</body></html>
""".format(uddg=quote("https://www.linkedin.com/in/jane-doe", safe=""))


def test_ddg_html_unwraps_redirects_into_real_urls():
    rows = providers.parse_ddg_html(DDG_HTML)
    urls = [r["url"] for r in rows]
    assert "https://www.linkedin.com/in/jane-doe" in urls
    assert "https://www.youtube.com/@adlab" in urls
    jane = next(r for r in rows if "linkedin.com" in r["url"])
    assert "Jane Doe" in jane["title"]
    assert "AI video" in jane["snippet"]


def test_ddg_hits_become_identities_the_engine_already_knows():
    rows = providers.parse_ddg_html(DDG_HTML)
    jane = next(r for r in rows if "linkedin.com" in r["url"])
    ent = parse_identity(jane["url"], jane["title"], jane["snippet"], source="linkedin_people")
    assert ent is not None
    assert ent["kind"] == "person"
    assert ent["platform"] == "linkedin"
    assert ent["handle"] == "jane-doe"
    assert ent.get("name")


def test_ddg_empty_html_is_no_identities_not_a_guess():
    assert providers.parse_ddg_html("") == []
    assert providers.parse_ddg_html("<html><body>no results</body></html>") == []


def test_unwrap_ddg_passthrough_for_plain_urls():
    assert providers.unwrap_ddg("https://example.com/x") == "https://example.com/x"
    assert providers.unwrap_ddg("") == ""
