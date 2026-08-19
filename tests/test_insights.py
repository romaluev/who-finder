from lib import insights


def _d(i, topics, **kw):
    base = {
        "id": f"person/linkedin/{i}",
        "enriched": True,
        "topics": topics,
        "signals": [],
        "audience": 0,
        "masked": False,
    }
    base.update(kw)
    return base


def test_coverage_distinguishes_empty_from_broken():
    """'We found nothing' and 'the source failed' are different claims."""
    cov = insights.coverage(
        [
            {"source": "youtube", "label": "yt", "state": "ok", "n": 12},
            {"source": "x", "label": "x", "state": "no-results", "n": 0},
            {"source": "web", "label": "w", "state": "error", "n": 0},
        ]
    )
    assert "youtube:yt ok(12)" in cov
    assert "x:x no-results" in cov
    assert "web:w ERROR" in cov


def test_clusters_name_recurring_themes():
    dossiers = [
        _d(1, ["agency", "video", "ads"]),
        _d(2, ["agency", "video", "brand"]),
        _d(3, ["agency", "saas"]),
        _d(4, ["photography"]),
    ]
    themes = insights.clusters(dossiers, min_members=2)
    names = [t["theme"] for t in themes]
    assert "agency" in names
    top = next(t for t in themes if t["theme"] == "agency")
    assert top["n"] == 3


def test_clusters_ignore_a_term_everyone_shares():
    dossiers = [_d(i, ["video", f"unique{i}"]) for i in range(5)]
    themes = insights.clusters(dossiers, min_members=2)
    assert "video" not in [t["theme"] for t in themes]


def test_findings_report_audience_and_masking():
    dossiers = [
        _d(1, ["ai"], audience=10_000),
        _d(2, ["ai"], audience=30_000),
        _d(3, ["ai"], audience=0, masked=True),
    ]
    rows = [
        {"id": "person/linkedin/1", "name": "Ada", "platform": "linkedin", "fit_band": "strong",
         "fit_reasons": ["topic match: ai (+18)"]},
        {"id": "person/linkedin/2", "name": "Bea", "platform": "linkedin", "fit_band": "possible"},
        {"id": "person/linkedin/3", "name": "Cee", "platform": "linkedin", "fit_band": "unknown"},
    ]
    out = " ".join(
        insights.findings(rows, dossiers, scenario="people", topic="ai", n_new=3, n_known=0)
    )
    assert "3 people" in out or "3 person" in out
    assert "median" in out
    assert "hides job history" in out


def test_findings_use_singular_grammar_for_one_row():
    out = " ".join(
        insights.findings(
            [{"platform": "linkedin", "fit_band": "strong"}],
            [_d(1, ["ai"], audience=5000)],
            scenario="people",
            topic="ai",
            n_new=1,
            n_known=0,
        )
    )
    assert "1 person" in out
    assert "1 people" not in out
    assert "1 entities" not in out


def test_findings_on_empty_result_say_so():
    out = insights.findings([], [], scenario="people", topic="x", n_new=0, n_known=0)
    assert "No entities matched" in out[0]


def test_gaps_surface_dead_and_silent_sources():
    g = insights.gaps(
        [_d(1, ["a"], audience=0)],
        [
            {"source": "web", "label": "w", "state": "error"},
            {"source": "x", "label": "x", "state": "no-results"},
        ],
        ["youtube: HTTP 500"],
    )
    joined = " ".join(g)
    assert "errored" in joined
    assert "returned nothing" in joined
    assert "HTTP 500" in joined


def test_build_returns_all_four_sections():
    out = insights.build(
        [{"platform": "linkedin", "fit_band": "strong"}],
        [_d(1, ["ai", "video"], audience=5000)],
        scenario="people",
        topic="ai video",
        n_new=1,
        n_known=0,
        source_status=[{"source": "youtube", "label": "yt", "state": "ok", "n": 3}],
        errors=[],
    )
    assert set(out) == {"coverage", "findings", "clusters", "gaps"}
