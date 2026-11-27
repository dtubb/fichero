"""local.run.worker-cli-current: the worker's Claude Code kept at the manager's version and signed in; a model it refuses, a revoked
sign-in and a sign-in about to end are each one alert."""
import datetime as dt
import json
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
    assert alerts[0].startswith("the worker's Claude sign-in is revoked: save a `claude setup-token` to ") and "owned by fichero-worker" in alerts[0]
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


def test_the_loops_job_probes_the_models_of_the_real_harness_toml_and_queue_roles_from_a_readable_dir_and_holds_on_a_revoked_sign_in(tmp_path, monkeypatch):
    """2026-11-27 09:05: live, worker-cli.json said {"models": {"2.1.332": {}}}, nothing held, code-audit-1 'gone' 3 times. The probe ran
    in the loop's cwd, unreadable to the worker ("Can't read the current directory (EACCES)"), and read as nothing."""
    from fichero_builder import models, queue, start_tool
    from fichero_builder import jail as jail_mod
    repo = Path(__file__).resolve().parents[2]
    mdl = models.load(repo)
    roles = ["", "haiku-trial", "maintainer-fable", "qwen-trial", "no-such-role"]
    want = worker_cli.wanted_models(mdl, roles)
    assert {"sonnet", "haiku", models.for_role(mdl, "maintainer-fable").model} <= want
    assert all(models.for_role(mdl, r).provider == "claude-code" for r in ("builder", "haiku-trial", "maintainer-fable"))
    work_root = tmp_path / "wr"
    (work_root / "bin").mkdir(parents=True)
    calls = tmp_path / "calls"
    worker = work_root / "bin" / "claude"
    worker.write_text(f'#!/bin/sh\n[ "$1" = --version ] && {{ echo "2.1.332 (Claude Code)"; exit 0; }}\necho "$PWD $*" >> "{calls}"\n'
                      '[ "$PWD" = /tmp ] || [ "$PWD" = /private/tmp ] || { echo "Can\'t read the current directory (EACCES)." >&2; exit 1; }\n'
                      'echo "Failed to authenticate: OAuth token revoked" >&2; exit 1\n')
    worker.chmod(0o755)
    monkeypatch.setattr(start_tool, "find_claude", lambda *h: str(worker))
    monkeypatch.setattr(jail_mod, "load", lambda root: None)
    monkeypatch.setattr(queue, "load", lambda: [{"id": f"l{i}", "role": r, "steps": []} for i, r in enumerate(roles)])
    job = queue.worker_cli_job(repo, {"jail": {"user": "fichero-worker", "workroot": str(work_root)}}, mdl)
    job()
    assert worker_cli.HELD[0], "a revoked sign-in holds new sessions"
    alerts = [r for r in journal.read() if r.get("event") == "alert"]
    assert len(alerts) == 1 and "sign-in is revoked" in json.dumps(alerts[0]) and f"setup-token` to {work_root}/.claude-token" in json.dumps(alerts[0])
    assert calls.read_text().split()[0] in ("/tmp", "/private/tmp") and "--model" in calls.read_text()


def test_a_probe_that_is_neither_signed_in_nor_refused_is_a_row_never_silence(tmp_path):
    worker = fake(tmp_path / "w" / "claude", "2.1.332", say="something else went wrong", rc=1)
    worker_cli.check(worker, str(worker), {"sonnet"}, lambda *a: None)
    assert [r["state"] for r in journal.read() if r.get("event") == "worker-cli"] == ["probe-failed"]


def test_the_probe_reads_the_workers_token_file_in_the_workers_own_shell_and_never_puts_the_token_in_argv(tmp_path, monkeypatch):
    """owner 2026-11-27: `auth login` fails under sudo (no keychain); a setup-token in <workroot>/.claude-token, read as the worker."""
    import subprocess as sp
    worker = tmp_path / "w" / "bin"
    worker.mkdir()
    cli = worker / "claude"
    cli.write_text('#!/bin/sh\n[ "$1" = --version ] && { echo "2.1.332 (Claude Code)"; exit 0; }\n'
                   'if [ -n "$CLAUDE_CODE_OAUTH_TOKEN" ]; then echo "token: set"; else echo "token: unset"; fi\n')
    cli.chmod(0o755)
    tok = tmp_path / "w" / ".claude-token"
    seen = []
    real = sp.run
    monkeypatch.setattr(worker_cli.subprocess, "run", lambda argv, **k: seen.append(list(argv)) or real(argv, **k))
    as_user = ("/usr/bin/env",)  # stands in for `sudo -n -H -u fichero-worker`
    assert worker_cli.probe(cli, "sonnet", as_user, tok) == ("ok", "token: unset"), "no file: the worker's own sign-in"
    tok.write_text("sk-ant-oat-SECRET\n")
    tok.chmod(0o600)
    assert worker_cli.probe(cli, "sonnet", as_user, tok) == ("ok", "token: set")
    assert worker_cli.probe(cli, "sonnet", (), tok) == ("ok", "token: unset"), "unjailed, this process never reads it"
    assert not any("SECRET" in " ".join(a) for a in seen) and "CLAUDE_CODE_OAUTH_TOKEN" not in __import__("os").environ
    assert str(tok) in seen[1] and seen[1][:2] == ["/usr/bin/env", "/bin/sh"]
    m = fake(tmp_path / "manager", "2.1.400")
    worker_cli.sync(cli, str(m))
    assert tok.read_text() == "sk-ant-oat-SECRET\n" and worker_cli.version(cli) == "2.1.400", "the sync replaces bin/claude only"
