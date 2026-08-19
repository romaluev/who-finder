"""Reports, reframing and pagination.

The report is the artifact a person actually reads, so these tests care less
about internal shapes and more about whether the document tells the truth: that
a PDF is a PDF, that an unverified name is not presented as a verified one, and
that the file says which query found each person.
"""

import pytest

from lib import cli, db, frames, http, pdf, planner, report
from test_deep import fake_get


# --------------------------------------------------------------------------
# Reframing
# --------------------------------------------------------------------------


def test_a_frame_is_derived_for_each_way_of_asking():
    got = {f.label: f.topic for f in frames.derive("ai video ads", "people")}
    assert got["literal"] == "ai video ads"
    assert got["exact"] == '"ai video ads"'
    assert got["broad"] == "video ads"


def test_the_quoted_frame_survives_deduplication():
    """`ai video ads` and `"ai video ads"` are different queries to an index."""
    topics = [f.topic for f in frames.derive("ai video ads", "people")]
    assert "ai video ads" in topics and '"ai video ads"' in topics


def test_broadening_needs_something_left_to_search():
    # Dropping the modifier from two words leaves one, which is not a search.
    assert frames.broaden("video ads") == ""
    assert frames.broaden("ai video ads") == "video ads"


def test_a_frame_that_collapses_to_a_filler_word_is_dropped():
    labels = [f.label for f in frames.derive("ai video", "people")]
    assert "broad" not in labels


def test_the_caller_can_add_meaning_the_engine_cannot_derive():
    got = [f.topic for f in frames.derive("ai video ads", "people",
                                          extra=["generative creative"])]
    assert "generative creative" in got


def test_frames_are_capped_so_the_bill_is_bounded():
    fr = frames.derive("ai video ads for consumer brands", "people",
                       extra=["a", "b", "c", "d", "e"], limit=3)
    assert len(fr) == 3


def test_extra_frames_cost_one_search_each_not_a_whole_angle_set():
    """Crossing every frame with every angle would multiply the bill."""
    one = planner.plan("people making ai video ads", n_frames=1)
    three = planner.plan("people making ai video ads", n_frames=3)
    assert len(three.steps) == len(one.steps) + 2


def test_frames_are_built_from_the_topic_not_the_raw_brief():
    p = planner.plan("find me people making ai video ads", n_frames=3)
    assert all("find me" not in s.query for s in p.steps)


# --------------------------------------------------------------------------
# Document rendering
# --------------------------------------------------------------------------

ROWS = [
    {"id": "person/linkedin/jane", "kind": "person", "platform": "linkedin",
     "handle": "jane", "name": "Jane Doe", "fit_band": "strong", "priority": 88,
     "fit_score": 91, "enriched": True, "audience": 24000,
     "fit_reasons": ["topic match: ai video (+18)"], "novelty": "new"},
    {"id": "person/linkedin/sam", "kind": "person", "platform": "linkedin",
     "handle": "sam", "name": "Sam Smith", "fit_band": "possible", "priority": 40,
     "fit_score": 55, "enriched": False, "novelty": "known"},
]
DOSS = {
    "person/linkedin/jane": {"headline": "Head of Content at Acme", "audience": 24000,
                             "audience_kind": "followers", "bio": "I make ai video ads.",
                             "location": "Austin", "signals": ["posting"]},
    "person/linkedin/sam": {"headline": "", "audience": 0},
}
INS = {"findings": ["2 entities (1 new)."], "clusters": [], "gaps": []}


def blocks(**kw):
    base = dict(brief="people making ai video ads", scenario="people",
                topic="ai video ads", n_new=1, n_known=1,
                steps=["linkedin_people:li-in"], frames=["literal: ai video ads — as asked"],
                icp_name="generic", credits=7)
    base.update(kw)
    return report.build(ROWS, DOSS, INS, **base)


def test_markdown_gives_every_person_their_own_section():
    md = report.to_markdown(blocks())
    assert "#### 1. Jane Doe" in md and "#### 2. Sam Smith" in md


def test_the_summary_comes_before_the_people():
    md = report.to_markdown(blocks())
    assert md.index("## Summary") < md.index("## The people")


def test_an_unfetched_profile_is_flagged_rather_than_dressed_up():
    md = report.to_markdown(blocks())
    assert "Profile could not be fetched" in md


def test_the_report_says_which_slice_of_the_ranking_it_covers():
    assert "the top 2 of 2 found" in report.to_markdown(blocks())
    assert "ranked 11-12 of 2 found" in report.to_markdown(blocks(offset=10))


def test_a_continued_report_keeps_the_original_rank_numbers():
    md = report.to_markdown(blocks(offset=10))
    assert "#### 11. Jane Doe" in md


def test_the_method_section_records_how_the_question_was_reframed():
    md = report.to_markdown(blocks())
    assert "How the question was asked" in md
    assert "ai video ads" in md
    assert "Exactly as asked" in md or "literal" in md


def test_html_is_a_standalone_file_with_no_external_requests():
    out = report.to_html(blocks())
    assert out.startswith("<!doctype html>")
    assert "<style>" in out and "http://" not in out.split("<body>")[0]


def test_html_escapes_names_so_a_profile_cannot_inject_markup():
    rows = [dict(ROWS[0], name="<script>alert(1)</script>")]
    out = report.to_html(report.build(rows, {}, INS, brief="x", scenario="people",
                                      topic="x", n_new=1, n_known=0, steps=[]))
    assert "<script>alert(1)</script>" not in out
    assert "&lt;script&gt;" in out


def test_consecutive_bullets_render_as_one_list():
    out = report.to_html(blocks())
    assert out.count("<ul>") < 4


def test_pdf_output_is_a_pdf_a_reader_will_open():
    raw = report.to_pdf(blocks())
    assert raw.startswith(b"%PDF-1.4")
    assert raw.rstrip().endswith(b"%%EOF")
    assert b"xref" in raw and b"/Type /Catalog" in raw


def test_pdf_paginates_instead_of_running_off_the_page():
    many = [dict(ROWS[0], id=f"person/linkedin/p{i}", handle=f"p{i}", name=f"Person {i}")
            for i in range(40)]
    doss = {r["id"]: DOSS["person/linkedin/jane"] for r in many}
    raw = report.to_pdf(report.build(many, doss, INS, brief="x", scenario="people",
                                     topic="x", n_new=40, n_known=0, steps=[]))
    assert raw.count(b"/Type /Page ") > 3


def test_an_unknown_format_is_refused_by_name():
    with pytest.raises(ValueError, match="docx"):
        report.render(blocks(), "docx")


def test_empty_sections_are_left_out_entirely():
    md = report.to_markdown(blocks())
    assert "What they are talking about" not in md


def test_a_theme_section_appears_when_there_are_themes():
    ins = dict(INS, clusters=[{"term": "creative testing", "n": 3}])
    md = report.to_markdown(report.build(ROWS, DOSS, ins, brief="x", scenario="people",
                                         topic="x", n_new=1, n_known=1, steps=[]))
    assert "What they are talking about" in md and "creative testing" in md


def test_corroboration_is_reported_when_several_framings_agree():
    md = report.to_markdown(blocks(found_by={"person/linkedin/jane": ["q1", "q2", "q3"]}))
    assert "3 different phrasings" in md


def test_one_framing_is_not_dressed_up_as_corroboration():
    md = report.to_markdown(blocks(found_by={"person/linkedin/jane": ["q1"]}))
    assert "different framings" not in md


def test_search_operators_are_stripped_from_the_displayed_query():
    md = report.to_markdown(blocks(found_by={"person/linkedin/jane":
                                             ["site:linkedin.com/in ai video ads"]}))
    assert "`ai video ads`" in md and "site:linkedin.com" not in md


# --------------------------------------------------------------------------
# The PDF writer itself
# --------------------------------------------------------------------------


def test_line_breaking_respects_the_column():
    lines = pdf.wrap("word " * 60, 10, 300)
    assert len(lines) > 1
    assert all(pdf.text_width(l, 10) <= 300 for l in lines)


def test_a_word_wider_than_the_column_is_broken_not_looped_forever():
    lines = pdf.wrap("x" * 400, 10, 100)
    assert len(lines) > 1
    assert all(pdf.text_width(l, 10) <= 100 for l in lines)


def test_bold_is_measured_with_bold_metrics():
    assert pdf.text_width("Handling", 10, bold=True) > pdf.text_width("Handling", 10)


def test_characters_outside_the_font_do_not_corrupt_the_file():
    raw = pdf.sanitize("em—dash “quotes” and 日本語")
    assert "—" not in raw and "-dash" in raw
    raw.encode("latin-1")


def test_parentheses_in_a_name_cannot_break_the_content_stream():
    c = pdf.Canvas()
    c.para("Jane (Acme) \\ Doe")
    raw = c.render()
    assert raw.startswith(b"%PDF")


# --------------------------------------------------------------------------
# End to end through the CLI
# --------------------------------------------------------------------------


@pytest.fixture
def wired(monkeypatch, tmp_path):
    monkeypatch.setattr(http, "get", fake_get)
    monkeypatch.setenv("SCRAPECREATORS_API_KEY", "test-key")
    monkeypatch.setenv("WHO_FINDER_HOME", str(tmp_path))
    monkeypatch.delenv("WHO_FINDER_ICP", raising=False)
    return tmp_path


def test_find_writes_every_requested_format_from_one_run(wired, tmp_path, capsys):
    out = tmp_path / "out" / "shortlist"
    rc = cli.main(["find", "people making ai video ads", "--deep", "2",
                   "--format", "md,html,pdf", "--out", str(out)])
    assert rc == 0
    assert (tmp_path / "out" / "shortlist.md").exists()
    assert (tmp_path / "out" / "shortlist.html").exists()
    assert (tmp_path / "out" / "shortlist.pdf").read_bytes().startswith(b"%PDF")
    assert "Wrote 3 files" in capsys.readouterr().out


def test_the_report_names_the_people_it_covers(wired, tmp_path):
    out = tmp_path / "r"
    cli.main(["find", "people making ai video ads", "--deep", "2",
              "--format", "md", "--out", str(out)])
    assert "Jane Doe" in (tmp_path / "r.md").read_text()


def test_a_bad_format_is_refused_before_anything_is_written(wired, tmp_path, capsys):
    rc = cli.main(["find", "people making ai video ads", "--deep", "1",
                   "--format", "docx", "--out", str(tmp_path / "x"), "--agent"])
    assert rc == 2
    assert not list(tmp_path.glob("x.*"))


def test_a_report_can_be_rebuilt_from_the_roster_for_free(wired, tmp_path, monkeypatch):
    cli.main(["find", "people making ai video ads", "--deep", "2"])

    def explode(*a, **k):
        raise AssertionError("report must not touch the network")

    monkeypatch.setattr(http, "get", explode)
    rc = cli.main(["report", "--limit", "2", "--format", "md", "--out", str(tmp_path / "x")])
    assert rc == 0 and (tmp_path / "x.md").exists()


def test_paging_past_the_first_report_returns_different_people(wired, tmp_path):
    cli.main(["find", "people making ai video ads", "--deep", "3"])
    cli.main(["report", "--limit", "1", "--format", "md", "--out", str(tmp_path / "a")])
    cli.main(["report", "--limit", "1", "--offset", "1", "--format", "md",
              "--out", str(tmp_path / "b")])
    first, second = (tmp_path / "a.md").read_text(), (tmp_path / "b.md").read_text()
    assert first.split("## The people")[1] != second.split("## The people")[1]


def test_more_costs_nothing_when_the_profiles_are_already_stored(wired, tmp_path,
                                                                 monkeypatch, capsys):
    cli.main(["find", "people making ai video ads", "--deep", "3"])
    capsys.readouterr()

    def explode(*a, **k):
        raise AssertionError("already enriched — must not refetch")

    monkeypatch.setattr(http, "get", explode)
    rc = cli.main(["more", "--offset", "1", "--limit", "2", "--agent"])
    assert rc == 0
    assert '"credits_spent": 0' in capsys.readouterr().out


def test_more_enriches_the_rows_that_were_never_paid_for(wired, capsys):
    """`--deep 1` leaves the rest of the ranking discovered but unenriched."""
    cli.main(["find", "people making ai video ads", "--deep", "1"])
    capsys.readouterr()
    rc = cli.main(["more", "--offset", "1", "--limit", "3", "--agent"])
    out = capsys.readouterr().out
    assert rc == 0
    import json
    body = json.loads(out)
    assert body["meta"]["credits_spent"] > 0
    assert any(e.get("enriched") for e in body["results"]["entities"])


def test_more_can_write_the_continued_report(wired, tmp_path):
    cli.main(["find", "people making ai video ads", "--deep", "1"])
    rc = cli.main(["more", "--offset", "1", "--limit", "2",
                   "--format", "md", "--out", str(tmp_path / "next")])
    assert rc == 0
    assert "#### 2." in (tmp_path / "next.md").read_text()


def test_more_refuses_rather_than_crashing_without_a_key(wired, monkeypatch, capsys):
    cli.main(["find", "people making ai video ads", "--deep", "1"])
    capsys.readouterr()
    monkeypatch.delenv("SCRAPECREATORS_API_KEY", raising=False)
    rc = cli.main(["more", "--offset", "1", "--limit", "3", "--agent"])
    assert rc == 4
    assert "report --offset" in capsys.readouterr().out


def test_more_says_so_when_the_ranking_is_exhausted(wired, capsys):
    cli.main(["find", "people making ai video ads", "--deep", "1"])
    capsys.readouterr()
    rc = cli.main(["more", "--offset", "999", "--agent"])
    assert rc == 3
    assert "nothing left below rank 999" in capsys.readouterr().out


def test_a_run_records_which_query_found_each_person(wired, tmp_path):
    out = tmp_path / "q"
    cli.main(["find", "people making ai video ads", "--deep", "2",
              "--frames", "3", "--format", "md", "--out", str(out)])
    assert "**Found by:**" in (tmp_path / "q.md").read_text()


def test_a_caller_supplied_framing_reaches_the_searches(wired, tmp_path, capsys):
    cli.main(["find", "people making ai video ads", "--frames", "4",
              "--frame", "generative advertising creative", "--dry-run", "--agent"])
    assert "generative advertising creative" in capsys.readouterr().out


def test_dry_run_prices_the_extra_framings_before_they_are_bought(wired, capsys):
    cli.main(["find", "people making ai video ads", "--frames", "1", "--dry-run", "--agent"])
    one = capsys.readouterr().out
    cli.main(["find", "people making ai video ads", "--frames", "4", "--dry-run", "--agent"])
    four = capsys.readouterr().out
    import json
    a = json.loads(one)["results"]["estimate"]["total_max"]
    b = json.loads(four)["results"]["estimate"]["total_max"]
    assert b > a
