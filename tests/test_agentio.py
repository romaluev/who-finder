"""The agent-facing contract: projection, sinks, profiles, budgets, exit codes.

These are the surfaces a caller writes code against, so each test pins a
promise rather than an implementation detail. If one breaks, someone's script
breaks with it.
"""

import json

import pytest

from lib import agentio, cli


# --------------------------------------------------------------------------
# Projection
# --------------------------------------------------------------------------

PAYLOAD = {
    "meta": {"credits_spent": 7, "scenario": "people"},
    "table": "a rendered brief",
    "results": {
        "n_new": 2,
        "entities": [
            {"id": "person/linkedin/jane", "priority": 82, "fit_band": "strong", "bio": "x" * 400},
            {"id": "person/youtube/adlab", "priority": 77, "fit_band": "strong", "bio": "y" * 400},
        ],
    },
}


def test_select_keeps_only_the_named_paths():
    out = agentio.select(PAYLOAD, "results.entities.id")
    assert out["results"]["entities"]["id"] == [
        "person/linkedin/jane",
        "person/youtube/adlab",
    ]
    assert "table" not in out


def test_select_traverses_lists_element_wise():
    out = agentio.select(PAYLOAD, "results.entities.priority")
    assert out["results"]["entities"]["priority"] == [82, 77]


def test_meta_always_survives_projection():
    """Credits and scenario must not be projectable away — a caller that lost
    them could mistake an expensive run for a cheap one."""
    out = agentio.select(PAYLOAD, "results.n_new")
    assert out["meta"]["credits_spent"] == 7


def test_error_survives_projection():
    payload = agentio.fail(agentio.E_AUTH, "no key", fix="export ...")
    out = agentio.select(payload, "results.entities.id")
    assert out["error"]["code"] == agentio.E_AUTH


def test_no_select_spec_is_a_passthrough():
    assert agentio.select(PAYLOAD, None) is PAYLOAD
    assert agentio.select(PAYLOAD, "  ") is PAYLOAD


def test_unknown_paths_are_dropped_not_nulled():
    out = agentio.select(PAYLOAD, "results.nope,results.n_new")
    assert "nope" not in out["results"]
    assert out["results"]["n_new"] == 2


# --------------------------------------------------------------------------
# Delivery
# --------------------------------------------------------------------------


def test_file_sink_writes_atomically(tmp_path):
    target = tmp_path / "nested" / "out.json"
    note = agentio.deliver('{"a":1}', f"file:{target}")
    assert target.read_text() == '{"a":1}'
    assert note == str(target)
    assert not list(target.parent.glob("*.tmp*"))


def test_stdout_sink_is_a_noop():
    assert agentio.deliver("body", None) == ""
    assert agentio.deliver("body", "stdout") == ""


def test_unknown_sink_names_the_supported_set():
    with pytest.raises(agentio.DeliveryError) as exc:
        agentio.deliver("body", "s3://bucket/key")
    assert "file:<path>" in str(exc.value)


# --------------------------------------------------------------------------
# Profiles
# --------------------------------------------------------------------------


@pytest.fixture
def home(monkeypatch, tmp_path):
    monkeypatch.setenv("WHO_FINDER_HOME", str(tmp_path))
    monkeypatch.delenv("WHO_FINDER_ICP", raising=False)
    return tmp_path


def test_profile_round_trip(home):
    agentio.save_profile("nightly", {"deep": 10, "scenario": "people"})
    assert agentio.load_profile("nightly")["deep"] == 10
    assert "nightly" in agentio.list_profiles()
    assert agentio.delete_profile("nightly") is True
    assert agentio.delete_profile("nightly") is False


def test_profile_rejects_a_path_shaped_name(home):
    with pytest.raises(ValueError):
        agentio.save_profile("../../etc/passwd", {"deep": 1})


def test_explicit_flags_beat_the_profile(home):
    import argparse

    agentio.save_profile("p", {"deep": 10, "scenario": "people"})
    args = argparse.Namespace(deep=3, scenario=None)
    applied = agentio.apply_profile(args, "p")
    assert args.deep == 3, "an explicit --deep must not be overwritten"
    assert args.scenario == "people"
    assert applied == ["scenario"]


def test_corrupt_profiles_file_does_not_crash(home):
    agentio.profiles_path().write_text("{not json", encoding="utf-8")
    assert agentio.list_profiles() == {}


# --------------------------------------------------------------------------
# CLI wiring
# --------------------------------------------------------------------------


def _run(capsys, argv, expect=0):
    code = cli.main(argv)
    assert code == expect, capsys.readouterr()
    return json.loads(capsys.readouterr().out)


def test_dry_run_spends_nothing_and_shows_the_ceiling(home, capsys, monkeypatch):
    monkeypatch.setenv("SCRAPECREATORS_API_KEY", "k")
    monkeypatch.setattr(
        cli.sources.http, "get", lambda *a, **k: pytest.fail("dry run must not call the network")
    )
    payload = _run(capsys, ["find", "founders of ai video tools", "--deep", "5", "--dry-run", "--agent"])
    est = payload["results"]["estimate"]
    assert payload["meta"]["credits_spent"] == 0
    assert est["total_max"] == est["discovery"] + 5
    assert "DRY RUN" in payload["table"]


def test_dry_run_works_without_a_key(home, capsys, monkeypatch):
    """Planning is free, so previewing cost must not require credentials."""
    monkeypatch.delenv("SCRAPECREATORS_API_KEY", raising=False)
    payload = _run(capsys, ["find", "ai video companies", "--dry-run", "--agent"])
    assert payload["meta"]["dry_run"] is True


def test_budget_refuses_before_spending(home, capsys, monkeypatch):
    monkeypatch.setenv("SCRAPECREATORS_API_KEY", "k")
    monkeypatch.setattr(
        cli.sources.http, "get", lambda *a, **k: pytest.fail("must refuse before any request")
    )
    cli.main(["find", "ai video", "--deep", "20", "--max-credits", "3", "--agent"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["error"]["code"] == agentio.E_BUDGET
    assert payload["error"]["estimate"]["total_max"] > 3


def test_budget_allows_a_plan_that_fits(home, capsys, monkeypatch):
    monkeypatch.setenv("SCRAPECREATORS_API_KEY", "k")
    payload = _run(capsys, ["find", "ai video", "--dry-run", "--max-credits", "99", "--agent"])
    assert payload["meta"]["dry_run"] is True


def test_missing_key_is_a_branchable_envelope(home, capsys, monkeypatch):
    monkeypatch.delenv("SCRAPECREATORS_API_KEY", raising=False)
    code = cli.main(["find", "ai video", "--agent"])
    payload = json.loads(capsys.readouterr().out)
    assert code == agentio.E_AUTH
    assert payload["error"]["code"] == agentio.E_AUTH
    assert "SCRAPECREATORS_API_KEY" in payload["error"]["fix"]


def test_malformed_icp_is_a_config_error_not_a_silent_fallback(home, capsys, monkeypatch):
    """A bad ICP file must stop the run: scoring against the wrong rules and
    reporting it as a result is worse than refusing."""
    monkeypatch.setenv("SCRAPECREATORS_API_KEY", "k")
    (home / "icp.json").write_text("{broken", encoding="utf-8")
    code = cli.main(["find", "ai video", "--dry-run", "--agent"])
    payload = json.loads(capsys.readouterr().out)
    assert code == agentio.E_CONFIG
    assert payload["error"]["code"] == agentio.E_CONFIG


def test_unknown_source_lists_the_allowed_set(home, capsys, monkeypatch):
    monkeypatch.setenv("SCRAPECREATORS_API_KEY", "k")
    code = cli.main(["find", "ai video", "--sources", "myspace", "--agent"])
    payload = json.loads(capsys.readouterr().out)
    assert code == agentio.E_USAGE
    assert "youtube" in payload["error"]["allowed"]


def test_a_bad_flag_is_reported_even_when_the_key_is_also_missing(home, capsys, monkeypatch):
    """Both can be wrong at once. Reporting the key first would send the user
    off to fetch one, only to hit the typo on the next run."""
    monkeypatch.delenv("SCRAPECREATORS_API_KEY", raising=False)
    assert cli.main(["find", "ai video", "--scenario", "alien", "--agent"]) == agentio.E_USAGE
    capsys.readouterr()
    assert cli.main(["find", "ai video", "--sources", "myspace", "--agent"]) == agentio.E_USAGE


def test_agent_context_describes_the_whole_cli(home, capsys):
    payload = _run(capsys, ["agent-context", "--agent"])
    r = payload["results"]
    assert r["primary_verb"] == "find"
    assert {c["command"] for c in r["commands"]} >= {"find", "report", "enrich", "doctor", "setup"}
    assert "8" in {str(k) for k in r["exit_codes"]}
    assert r["cost_model"]["cached_profile"] == 0


def test_agent_context_lists_saved_profiles(home, capsys):
    cli.main(["profile", "save", "nightly", "--set", "deep=10", "--agent"])
    capsys.readouterr()
    payload = _run(capsys, ["agent-context", "--agent"])
    assert "nightly" in payload["results"]["available_profiles"]


def test_global_flags_work_before_the_subcommand(home, capsys, monkeypatch):
    """argparse hands the subparser its own defaults; they must not clobber
    a flag the user put ahead of the verb."""
    monkeypatch.setenv("SCRAPECREATORS_API_KEY", "k")
    cli.main(["profile", "save", "deepen", "--set", "deep=7", "--agent"])
    capsys.readouterr()
    payload = _run(capsys, ["--profile", "deepen", "find", "ai video", "--dry-run", "--agent"])
    assert payload["results"]["estimate"]["enrichment_max"] == 7


def test_select_applies_through_the_cli(home, capsys, monkeypatch):
    monkeypatch.setenv("SCRAPECREATORS_API_KEY", "k")
    payload = _run(
        capsys,
        ["find", "ai video", "--dry-run", "--agent", "--select", "results.estimate.total_max"],
    )
    assert payload["results"]["estimate"]["total_max"]
    assert "steps" not in payload["results"]


def test_deliver_writes_the_envelope_and_prints_a_receipt(home, capsys, tmp_path):
    out = tmp_path / "ctx.json"
    payload = _run(capsys, ["agent-context", "--agent", "--deliver", f"file:{out}"])
    assert payload["results"]["delivered"] == str(out)
    assert json.loads(out.read_text())["results"]["primary_verb"] == "find"


def test_bad_sink_exits_nine(home, capsys):
    code = cli.main(["agent-context", "--agent", "--deliver", "carrier-pigeon:/x"])
    assert code == agentio.E_DELIVERY
    assert json.loads(capsys.readouterr().out)["error"]["code"] == agentio.E_DELIVERY


def test_feedback_takes_a_bare_note(home, capsys):
    payload = _run(capsys, ["feedback", "compare ranked side b too low", "--agent"])
    assert payload["results"]["recorded"] is True
    listed = _run(capsys, ["feedback", "list", "--agent"])
    assert listed["results"]["feedback"][-1]["note"] == "compare ranked side b too low"


def test_unknown_profile_is_not_found(home, capsys):
    code = cli.main(["--profile", "ghost", "list", "--agent"])
    assert code == agentio.E_NOTFOUND


# --------------------------------------------------------------------------
# First run
#
# A cold start is the only moment a new user decides whether this is usable.
# argparse's default answer to every one of these is a list of nineteen
# subcommands and "invalid choice", which names the mistake but not the fix.
# --------------------------------------------------------------------------


def test_no_arguments_teaches_instead_of_erroring(home, capsys):
    assert cli.main([]) == 0
    out = capsys.readouterr().out
    assert "you just ask" in out, "a non-technical reader should learn they can just ask"
    assert "--dry-run" in out, "the free, keyless path must be offered"
    assert "scrapecreators.com" in out, "they cannot start without knowing where the key comes from"


def test_help_words_reach_the_same_place(home, capsys):
    for word in ("help", "start", "guide", "?"):
        assert cli.main([word]) == 0
        assert "--dry-run" in capsys.readouterr().out


def test_a_typed_brief_is_redirected_to_find(home, capsys):
    """Someone who types what they want, rather than a subcommand, is close to
    right — say so and show the exact command."""
    code = cli.main(["find me AI video founders"])
    out = capsys.readouterr().out
    assert code == agentio.E_USAGE
    assert 'find "find me AI video founders"' in out
    assert "--dry-run" in out


def test_a_mistyped_command_points_at_which(home, capsys):
    code = cli.main(["serch"])
    out = capsys.readouterr().out
    assert code == agentio.E_USAGE
    assert 'which "serch"' in out


def test_doctor_prints_a_readable_card_for_humans(home, capsys, monkeypatch):
    monkeypatch.delenv("SCRAPECREATORS_API_KEY", raising=False)
    code = cli.main(["doctor"])
    out = capsys.readouterr().out
    assert code == agentio.E_AUTH
    assert "NOT SET UP" in out
    assert "setup YOUR_KEY" in out
    assert "scrapecreators.com" in out
    assert not out.lstrip().startswith("{"), "humans should not be shown raw JSON"


def test_doctor_still_gives_agents_structured_results(home, capsys, monkeypatch):
    monkeypatch.delenv("SCRAPECREATORS_API_KEY", raising=False)
    cli.main(["doctor", "--agent"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["results"]["state"] == "skipped-unconfigured"
    assert payload["table"], "the human card rides along as `table`"


def test_bare_agent_invocation_returns_the_context_map(home, capsys):
    """An agent that runs this with no command should get something machine
    readable, not a welcome poster."""
    assert cli.main(["--agent"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["results"]["primary_verb"] == "find"
