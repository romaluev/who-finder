"""Public contacts are extracted. Work emails are never invented."""

from lib import contacts, notices, report
from lib.enrich import _blank, _linkedin_person, _twitter, _derive_signals


def test_harvest_takes_an_email_off_the_profile_and_nothing_else():
    d = {
        "bio": "Write me at hello@studio.com — we make ads.",
        "links": ["https://calendly.com/jane/30min", "https://studio.com"],
        "url": "https://www.linkedin.com/in/jane",
    }
    c = contacts.harvest(d)
    assert c["emails"] == ["hello@studio.com"]
    assert c["takes_meetings"] is True
    assert c["has_personal_site"] is True
    kinds = {l["kind"] for l in c["links"]}
    assert "calendly" in kinds and "website" in kinds


def test_harvest_does_not_invent_first_last_at_company():
    d = {
        "name": "Jane Doe",
        "headline": "Founder at Acme",
        "company": {"current": "Acme", "website": "https://acme.com"},
        "bio": "Building the future of video.",
    }
    c = contacts.harvest(d)
    assert c["emails"] == []
    assert "jane@acme.com" not in str(c)


def test_obfuscated_email_is_reassembled():
    c = contacts.harvest({"bio": "ping me at jane [at] studio [dot] com"})
    assert "jane@studio.com" in c["emails"]


def test_throwaway_domains_are_dropped():
    c = contacts.harvest({"bio": "schema at example.com wait user@sentry.io"})
    # example.com is throw-away; sentry.io too. "schema at example.com" is not
    # a well-formed address in the first place.
    assert all(e.split("@")[-1] not in contacts.THROW_AWAY for e in c["emails"])


def test_personal_gmail_is_flagged_as_personal():
    c = contacts.harvest({"bio": "jane@gmail.com"})
    assert c["personal_emails"] == ["jane@gmail.com"]


def test_linkedin_person_harvests_a_website_the_vendor_sent():
    d = _blank("person", "linkedin", "jane")
    _linkedin_person(d, {
        "name": "Jane Doe",
        "about": "I make ads.",
        "website": "https://janedoe.com",
        "twitter": "https://x.com/janedoe",
        "email": "hello@janedoe.com",
        "headline": "Founder at Acme",
    })
    assert "https://janedoe.com" in d["links"]
    assert "https://x.com/janedoe" in d["links"]
    assert "hello@janedoe.com" in d["links"]
    assert d["headline"] == "Founder at Acme"
    assert d["headline_source"] == "linkedin-headline"


def test_twitter_profile_urls_become_links():
    d = _blank("person", "x", "jane")
    _twitter(d, {
        "user": {
            "legacy": {
                "name": "Jane",
                "description": "ads",
                "followers_count": 12,
                "entities": {
                    "url": {"urls": [{"expanded_url": "https://janedoe.com"}]},
                },
            }
        }
    })
    assert "https://janedoe.com" in d["links"]


def test_calendly_becomes_a_books_meetings_signal():
    sig = _derive_signals({
        "bio": "", "headline": "", "recent": [],
        "links": ["https://calendly.com/jane/30"],
        "audience": 0, "company": {},
    })
    assert "books-meetings" in sig


def test_same_name_on_two_platforms_is_one_person():
    rows = [
        {"id": "person/linkedin/jane-doe", "name": "Jane Doe", "platform": "linkedin",
         "kind": "person", "handle": "jane-doe"},
        {"id": "person/youtube/janedoe", "name": "Jane Doe", "platform": "youtube",
         "kind": "person", "handle": "janedoe"},
    ]
    doss = [
        {"id": "person/linkedin/jane-doe", "name": "Jane Doe"},
        {"id": "person/youtube/janedoe", "name": "Jane Doe"},
    ]
    texts = " ".join(n["text"] for n in notices.of_set(rows, doss))
    assert "same person" in texts
    assert "Jane Doe" in texts


def test_no_notice_when_the_set_has_nothing_surprising():
    rows = [
        {"id": "a", "name": "Ada Lovelace", "platform": "linkedin", "kind": "person", "handle": "ada"},
        {"id": "b", "name": "Sam Altman", "platform": "linkedin", "kind": "person", "handle": "sam"},
    ]
    doss = [{"id": "a", "name": "Ada Lovelace"}, {"id": "b", "name": "Sam Altman"}]
    assert notices.of_set(rows, doss) == []


def test_hub_notice_when_similar_points_into_the_set():
    rows = [
        {"id": "person/linkedin/jane", "name": "Jane Doe", "platform": "linkedin",
         "kind": "person", "handle": "jane",
         "url": "https://www.linkedin.com/in/jane"},
        {"id": "person/linkedin/sam", "name": "Sam Smith", "platform": "linkedin",
         "kind": "person", "handle": "sam",
         "url": "https://www.linkedin.com/in/sam"},
    ]
    doss = [
        {"id": "person/linkedin/jane", "name": "Jane Doe",
         "url": "https://www.linkedin.com/in/jane",
         "similar": [{"name": "Sam Smith", "url": "https://www.linkedin.com/in/sam"}]},
        {"id": "person/linkedin/sam", "name": "Sam Smith",
         "url": "https://www.linkedin.com/in/sam"},
    ]
    texts = " ".join(n["text"] for n in notices.of_set(rows, doss))
    assert "Sam Smith" in texts and "similar" in texts.lower()


def test_same_employer_is_a_cluster_not_three_leads():
    rows = [
        {"id": "1", "name": "Jane Doe", "platform": "linkedin", "kind": "person",
         "handle": "j", "headline": "Head of Content at Acme"},
        {"id": "2", "name": "Sam Smith", "platform": "linkedin", "kind": "person",
         "handle": "s", "headline": "Designer at Acme"},
    ]
    doss = [
        {"id": "1", "name": "Jane Doe", "headline": "Head of Content at Acme"},
        {"id": "2", "name": "Sam Smith", "headline": "Designer at Acme"},
    ]
    texts = " ".join(n["text"] for n in notices.of_set(rows, doss))
    assert "Acme" in texts and "cluster" in texts


def test_person_notice_names_a_published_email_and_a_personal_inbox():
    r = {"id": "p/1", "name": "Jane", "platform": "linkedin"}
    d = {"id": "p/1", "name": "Jane", "bio": "jane@gmail.com"}
    texts = " ".join(n["text"] for n in notices.of_one(r, d))
    assert "jane@gmail.com" in texts
    assert "personal" in texts


def test_person_notice_omits_when_there_is_nothing_to_say():
    r = {"id": "p/1", "name": "Jane", "platform": "linkedin"}
    d = {"id": "p/1", "name": "Jane", "bio": "I make ads."}
    assert notices.of_one(r, d) == []


def test_report_surfaces_easy_to_miss_and_how_to_reach():
    rows = [
        {"id": "person/linkedin/jane", "kind": "person", "platform": "linkedin",
         "handle": "jane", "name": "Jane Doe", "fit_band": "strong", "priority": 80,
         "fit_score": 90, "enriched": True, "url": "https://www.linkedin.com/in/jane"},
        {"id": "person/youtube/janedoe", "kind": "person", "platform": "youtube",
         "handle": "janedoe", "name": "Jane Doe", "fit_band": "possible",
         "priority": 40, "fit_score": 50, "enriched": True},
    ]
    doss = {
        "person/linkedin/jane": {
            "name": "Jane Doe", "headline": "Founder at Acme",
            "bio": "Write hello@acme.com", "enriched": True,
            "links": ["https://calendly.com/jane"],
        },
        "person/youtube/janedoe": {"name": "Jane Doe", "enriched": True},
    }
    ins = {"findings": ["two people"], "notices": ["**Jane Doe** on linkedin and **Jane Doe** on youtube look like the same person — count them once, not twice."],
           "clusters": [], "gaps": []}
    md = report.to_markdown(report.build(
        rows, doss, ins, brief="x", scenario="people", topic="x",
        n_new=2, n_known=0, steps=[],
    ))
    assert "Easy to miss" in md
    assert "same person" in md
    assert "hello@acme.com" in md
    assert "How to reach them" in md
