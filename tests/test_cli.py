from lib.cli import main
from lib.emit import table
from lib.which import resolve


def test_which_hiring():
    hit = resolve("who is hiring for AI video")
    assert hit["matched"] is True
    assert hit["scenario"] == "hiring"
    assert "find" in hit["run"]


def test_which_unknown_falls_back_to_find():
    hit = resolve("something totally novel")
    assert "find" in hit["run"]


def test_emit_people_table_lists_new_only():
    rows = [
        {
            "novelty": "new",
            "kind": "person",
            "platform": "linkedin",
            "handle": "ada",
            "score": 20,
            "hit_count": 2,
            "sample": "Ada Lovelace | LinkedIn",
            "flags": [],
        },
        {
            "novelty": "known",
            "kind": "person",
            "platform": "linkedin",
            "handle": "skip",
            "score": 99,
            "hit_count": 1,
            "sample": "already outreached",
            "flags": [],
        },
    ]
    text = table(
        rows,
        scenario="people",
        n_new=1,
        n_known=1,
        topic="AI video",
        errors=[],
        steps=["linkedin_people:li-in"],
    )
    assert "person/linkedin/ada" in text
    assert "person/linkedin/skip" not in text
    assert "scenario=people" in text


def test_cli_which_and_scenarios(capsys):
    assert main(["which", "find companies in AI video"]) == 0
    out = capsys.readouterr().out
    assert "companies" in out
    assert main(["scenarios", "--agent"]) == 0
    out = capsys.readouterr().out
    assert "hiring" in out
    assert "creators" in out


def test_cli_doctor_missing_key(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("SCRAPECREATORS_API_KEY", raising=False)
    monkeypatch.setenv("WHO_FINDER_HOME", str(tmp_path))
    code = main(["doctor", "--agent"])
    assert code == 4
    out = capsys.readouterr().out
    assert "missing" in out or "skipped" in out
