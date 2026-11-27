"""local.run.worker-cli-current: the worker's Claude Code kept at the manager's version and signed in; a model it refuses, a revoked
sign-in and a sign-in about to end are each one alert."""
import datetime as dt
from pathlib import Path

import pytest

from fichero_builder import journal, worker_cli


def fake(path: Path, ver: str, refuse: str = "", calls: Path | None = None, say: str = "", rc: int = 0) -> Path:
    log = f'echo "$*" >> "{calls}"; ' if calls else ""
    path.write_text(f'#!/bin/sh\n{log}[ "$1" = --version ] && {{ echo "{ver} (Claude Code)"; exit 0; }}\n'
                    f'[ "$3" = "{refuse}" ] && {{ echo "API Error: unrecognized_model {refuse}" >&2; exit 1; }}\n'
                    f'printf "%s\\n" "{say}" >&2\necho ok\nexit {rc}\n')
    path.chmod(0o755)
    return path


@pytest.fixture(autouse=True)
def state(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "STATE", tmp_path / "s")
    monkeypatch.setattr(worker_cli, "HELD", [False])
    (tmp_path / "w").mkdir()


def test_an_old_worker_cli_is_replaced_atomically_and_a_refused_model_is_one_alert_per_version(tmp_path):
    calls = tmp_path / "calls"
    worker = fake(tmp_path / "w" / "claude", "2.1.316", refuse="claude-fable-5-2[1m]")
    manager = fake(tmp_path / "manager-claude", "2.1.332", refuse="no-such-model", calls=calls)
    alerts = []
    say = lambda m, v, what, why: alerts.append((m, v, why))  # noqa: E731
    worker_cli.check(worker, str(manager), {"claude-fable-5-2[1m]", "no-such-model"}, say)
    assert worker_cli.version(worker) == "2.1.332" and not (tmp_path / "w" / "claude.new").exists()
    rows = [r for r in journal.read() if r.get("event") == "worker-cli"]
    assert [r["state"] for r in rows] == ["updated"] and "2.1.316 -> 2.1.332" in rows[0]["detail"]
    assert [(m, v) for m, v, _ in alerts] == [("no-such-model", "2.1.332")] and "unrecognized_model" in alerts[0][2]
    n = len(calls.read_text().splitlines())
    worker_cli.check(worker, str(manager), {"claude-fable-5-2[1m]", "no-such-model"}, say)
    assert len(alerts) == 1, "cached per model and version: one alert"
    assert len(calls.read_text().splitlines()) == n + 3, "the second time: two --version calls and the one sign-in probe"
    assert len([r for r in journal.read() if r.get("event") == "worker-cli"]) == 1, "same version: no copy, no row"


def test_a_revoked_sign_in_is_one_alert_and_holds_new_sessions_until_a_probe_passes(tmp_path):
    worker = tmp_path / "w" / "claude"
    fake(worker, "2.1.332", say="Failed to authenticate: OAuth token revoked", rc=1)
    alerts = []
    say = lambda m, v, what, why: alerts.append(what)  # noqa: E731
    for _ in range(2):
        worker_cli.check(worker, str(worker), {"claude-fable-5-2[1m]"}, say, user="fichero-worker")
    assert worker_cli.HELD[0] and len(alerts) == 1
    assert alerts[0].startswith("the worker's Claude sign-in is revoked: run `sudo -u fichero-worker -H ") and "claude auth login`" in alerts[0]
    fake(worker, "2.1.332")
    worker_cli.check(worker, str(worker), {"claude-fable-5-2[1m]"}, say)
    assert not worker_cli.HELD[0] and len(alerts) == 1


def test_a_sign_in_that_ends_soon_is_one_alert_two_days_before_it_ends(tmp_path):
    worker = fake(tmp_path / "w" / "claude", "2.1.332", say="Warning: this sign-in ends between 2026-12-05 and 2026-12-08.")
    alerts = []
    say = lambda m, v, what, why: alerts.append(what)  # noqa: E731
    worker_cli.check(worker, str(worker), {"sonnet"}, say, today=dt.date(2026, 12, 2))
    assert alerts == []
    for _ in range(2):
        worker_cli.check(worker, str(worker), {"sonnet"}, say, today=dt.date(2026, 12, 3))
    assert len(alerts) == 1 and "ends from 2026-12-05" in alerts[0]
    assert worker_cli.ends_at("this sign-in ends between Dec 5, 2026 and Dec 8, 2026") == dt.date(2026, 12, 5)


def test_the_loop_checks_at_start_then_hourly_and_every_few_minutes_while_held(monkeypatch):
    from fichero_builder import queue
    ran = []
    procs = queue.Procs.__new__(queue.Procs)
    procs.worker_cli = lambda: ran.append(1)
    clock = [10_000.0]
    monkeypatch.setattr(queue.time, "time", lambda: clock[0])
    monkeypatch.setattr(queue, "WORKER_CLI_AT", [0.0])
    queue.worker_cli_when_due(procs, None)
    clock[0] += 1800
    queue.worker_cli_when_due(procs, None)
    clock[0] += 1801
    queue.worker_cli_when_due(procs, None)
    assert ran == [1, 1]
    worker_cli.HELD[0] = True
    clock[0] += 301
    queue.worker_cli_when_due(procs, None)
    assert ran == [1, 1, 1]
