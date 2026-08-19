"""The key has to survive a new terminal. Env still wins."""

from pathlib import Path

from lib import auth, cli


def test_placeholder_keys_are_refused(tmp_path, monkeypatch):
    monkeypatch.setenv("WHO_FINDER_HOME", str(tmp_path))
    try:
        auth.save("your-key")
        raise AssertionError("placeholders must not be written")
    except ValueError as exc:
        assert "scrapecreators.com" in str(exc)
    assert not auth.key_file().exists()


def test_setup_writes_a_file_doctor_can_see(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("WHO_FINDER_HOME", str(tmp_path))
    monkeypatch.delenv("SCRAPECREATORS_API_KEY", raising=False)
    assert auth.token() == ""
    assert cli.main(["setup", "sk_live_testkey_12345"]) == 0
    out = capsys.readouterr().out
    assert "Key saved" in out
    assert auth.token() == "sk_live_testkey_12345"
    source = auth.read()[1]
    assert source.startswith("file:")
    assert Path(source.split(":", 1)[1]).exists()


def test_env_wins_over_the_file(tmp_path, monkeypatch):
    monkeypatch.setenv("WHO_FINDER_HOME", str(tmp_path))
    auth.save("sk_live_fromfile_123")
    monkeypatch.setenv("SCRAPECREATORS_API_KEY", "sk_live_fromenv_123")
    token, source = auth.read()
    assert token == "sk_live_fromenv_123"
    assert source == "env"


def test_setup_without_a_key_teaches(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("WHO_FINDER_HOME", str(tmp_path))
    monkeypatch.delenv("SCRAPECREATORS_API_KEY", raising=False)
    assert cli.main(["setup"]) == 0
    out = capsys.readouterr().out
    assert "not set yet" in out
    assert "scrapecreators.com" in out
    assert "setup YOUR_KEY" in out


def test_setup_clear_removes_only_the_file(tmp_path, monkeypatch):
    monkeypatch.setenv("WHO_FINDER_HOME", str(tmp_path))
    monkeypatch.delenv("SCRAPECREATORS_API_KEY", raising=False)
    auth.save("sk_live_testkey_12345")
    assert cli.main(["setup", "--clear"]) == 0
    assert auth.token() == ""


def test_who_finder_home_hides_the_real_home_key(tmp_path, monkeypatch):
    """A developer with ~/.who-finder/key must not leak it into tests."""
    monkeypatch.setenv("WHO_FINDER_HOME", str(tmp_path))
    monkeypatch.delenv("SCRAPECREATORS_API_KEY", raising=False)
    assert auth.token() == ""
    assert auth.key_file() == tmp_path / "key"
