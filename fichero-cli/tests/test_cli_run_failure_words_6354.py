"""`run.fail.cli-says-the-fix` (#6354): `fichero workflow run --wait` and `fichero workflow status` say a failed run's words, `Fix: <fix>`
and each action as the command that does it; exit 1 for a failure; a bug in Fichero says so and names the bug-report command first;
never a traceback."""
from __future__ import annotations

from typer.testing import CliRunner

from fichero_cli import __main__ as cli
from fichero_cli import run_failure

NO_CREDIT = {"kind": "no-credit", "words": "OpenRouter has no credit left, so the run stopped at page 12 of 203.",
             "fix": "Add credit at OpenRouter, then run it again.",
             "actions": [{"kind": "open-settings", "control": "settings.ai.providers"}, {"kind": "choose-model"}, {"kind": "retry"}]}
BUG = {"kind": "unexpected", "words": "Something went wrong inside Fichero while it ran Read (RuntimeError).",
       "fix": "This is a bug in Fichero, not something you did. Send a bug report so it can be fixed.",
       "actions": [{"kind": "retry"}, {"kind": "report-bug"}]}
RATE = {"kind": "rate-limited", "words": "w", "fix": "f", "actions": [{"kind": "retry", "retry_after_seconds": 30.0}]}


def test_the_words_the_fix_and_each_action_as_a_command():
    text = run_failure.words(NO_CREDIT, "run-1")
    assert text.splitlines()[0].startswith("OpenRouter has no credit") and "Fix: Add credit at OpenRouter" in text
    assert "fichero providers set-api-key <provider>" in text and "--model <provider>/<model>" in text
    assert "fichero activity-api retry-job run-1" in text


def test_a_bug_in_fichero_says_so_and_names_the_bug_report_command_first():
    lines = run_failure.words(BUG, "run-2").splitlines()
    assert "a bug in Fichero" in lines[1]
    ways = [line for line in lines if line.startswith("  - ")]
    assert "post-job-bug-report run-2" in ways[0] and "retry-job run-2" in ways[1]


def test_a_retry_after_says_how_long_the_provider_asked_for():
    assert "30 seconds" in run_failure.words(RATE, "run-3")


def test_only_a_run_that_failed_has_a_failure_to_say():
    assert run_failure.of({"status": "failed", "failure": NO_CREDIT}) == NO_CREDIT
    assert run_failure.of({"status": "completed", "failure": NO_CREDIT}) is None
    assert run_failure.of({"status": "failed", "failure": None}) is None
    assert run_failure.of("not a payload") is None


class _Client:
    def __init__(self, status):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def run_workflow(self, workflow_id, inputs, **kw):
        return {"thread_id": "t1"}

    def execution_status(self, thread_id):
        return self.status


def _invoke(monkeypatch, status, *args):
    monkeypatch.setattr(cli, "_client", lambda ctx: _Client(status))
    monkeypatch.setattr(cli, "_resolve_workflow", lambda c, name: "wf")
    monkeypatch.setattr(cli, "_poll_until_terminal", lambda client, thread_id, **kw: status)
    return CliRunner().invoke(cli.app, list(args))


def test_run_wait_on_a_failed_run_prints_the_words_and_exits_1(monkeypatch):
    result = _invoke(monkeypatch, {"status": "failed", "failure": NO_CREDIT}, "workflow", "run", "W", "doc-1", "--wait")
    assert result.exit_code == run_failure.EXIT_CODE, result.output
    assert "Fix: Add credit at OpenRouter" in result.stderr and "Traceback" not in result.stderr


def test_run_wait_on_a_run_that_completed_exits_0_and_says_nothing_of_failure(monkeypatch):
    result = _invoke(monkeypatch, {"status": "completed", "failure": None}, "workflow", "run", "W", "doc-1", "--wait")
    assert result.exit_code == 0 and "Fix:" not in result.output


def test_status_of_a_failed_run_says_why_and_still_exits_0(monkeypatch):
    result = _invoke(monkeypatch, {"status": "failed", "failure": BUG}, "workflow", "status", "t1")
    assert result.exit_code == 0 and "a bug in Fichero" in result.stderr
