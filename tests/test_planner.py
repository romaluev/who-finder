from lib.planner import core_topic, detect_scenario, plan


def test_detect_creators_not_people():
    assert detect_scenario("find creators posting about Kling AI") == "creators"


def test_detect_hiring_beats_people():
    assert detect_scenario("who is hiring for AI video editors") == "hiring"


def test_detect_press():
    assert detect_scenario("journalists covering text-to-video") == "press"


def test_people_at_companies_is_people():
    assert detect_scenario("people at AI video companies") == "people"


def test_companies_alone():
    assert detect_scenario("companies building AI video ads") == "companies"


def test_compare_vs():
    p = plan("Runway vs Kling for ads")
    assert p.scenario == "compare"
    assert p.topic
    assert p.side_b
    sides = {s.side for s in p.steps}
    assert "a" in sides and "b" in sides


def test_people_plan_uses_linkedin_in_operator():
    p = plan("founders of AI video tools")
    assert p.scenario == "people"
    queries = " ".join(s.query for s in p.steps)
    assert "site:linkedin.com/in" in queries
    assert "find" not in p.topic.lower()
    assert "founders" not in p.topic.lower()


def test_quoted_topic_kept():
    assert core_topic('find people posting "text to video"') == "text to video"


def test_forced_scenario():
    p = plan("Kling AI", scenario="creators")
    assert p.scenario == "creators"
    assert any(s.source == "youtube" for s in p.steps)


def test_extra_sources_adds_step():
    p = plan("Kling AI", scenario="people", extra_sources=["reddit"])
    assert any(s.source == "reddit" for s in p.steps)
