"""The Lead-facing surface: find, rate, run — one repo."""

import json
from pathlib import Path

from lib.cli import main
from lib.which import resolve


def test_welcome_shows_three_commands(capsys):
    assert main([]) == 0
    out = capsys.readouterr().out
    assert "who-finder find" in out or 'find "CMO AI video ads"' in out
    assert " rate " in out
    assert " run " in out


def test_which_maps_rate_and_run():
    assert "rate" in resolve("rate these creators")["run"]
    assert "rate" in resolve("Rate this Clay export and write it up as a PDF")["run"]
    assert "run" in resolve("find and rate")["run"]
    assert "run" in resolve("tell me who to buy")["run"]
    assert "find" in resolve("find me people")["run"]


def test_rate_sample_csv(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("WHO_FINDER_HOME", str(tmp_path))
    monkeypatch.setenv("CREATOR_RATING_HOME", str(tmp_path))
    src = Path(__file__).resolve().parent / "fixtures" / "creators.csv"
    out = tmp_path / "rating"
    assert main(["rate", str(src), "--out", str(out), "--format", "md,html",
                 "--no-collect", "--agent"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["results"]["n"] == 3
    assert (tmp_path / "rating.md").exists()
    assert (tmp_path / "rating.html").exists()
    html = (tmp_path / "rating.html").read_text(encoding="utf-8")
    assert "Ada Lovelace" in html
    assert "creator-rating" not in html
