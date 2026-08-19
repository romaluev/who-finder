from lib.identity import parse_id, parse_identity


def test_linkedin_person():
    ent = parse_identity("https://www.linkedin.com/in/jane-doe", "Jane Doe | LinkedIn")
    assert ent["kind"] == "person"
    assert ent["platform"] == "linkedin"
    assert ent["handle"] == "jane-doe"


def test_linkedin_company():
    ent = parse_identity("https://www.linkedin.com/company/openai", "OpenAI")
    assert ent["kind"] == "company"
    assert ent["handle"] == "openai"


def test_linkedin_job_becomes_company():
    ent = parse_identity(
        "https://www.linkedin.com/jobs/view/123",
        "AI Video Editor | Higgsfield | LinkedIn",
        source="linkedin_jobs",
        scenario_kind="company",
    )
    assert ent["kind"] == "company"
    assert ent["handle"] == "Higgsfield" or ent["handle"].lower() == "higgsfield"


def test_youtube_at_handle():
    ent = parse_identity("https://www.youtube.com/@mkbhd", "MKBHD")
    assert ent["platform"] == "youtube"
    assert ent["handle"] == "mkbhd"


def test_parse_id_three_and_two_part():
    assert parse_id("person/youtube/mkbhd") == ("person", "youtube", "mkbhd")
    assert parse_id("youtube/mkbhd") == ("person", "youtube", "mkbhd")
