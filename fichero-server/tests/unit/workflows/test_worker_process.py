"""The engine starts a worker process, watches it, records it as a job row Activity shows, and stops it.

(dev-workflows.node.worker, #6116.) Kinds: `claude` (today's cli_agent command) and `fake` (replays a
scripted scenario, no model, no money). The worker runs in its own process group in a scratch workdir;
its row follows it: running -> done / failed (exit code, timeout) / cancelled (stop).
"""

from __future__ import annotations

import json

import pytest

from fichero_server.workflows import worker_process as wp


def _row(db, job_id):
    return db.execute_fetchone("SELECT kind, state, reason, detail FROM jobs WHERE id = ?", [job_id])


def test_a_fake_worker_runs_in_its_workdir_and_its_row_is_done(db, tmp_path):
    job = wp.start(db, kind="fake", brief="build #1", workdir=tmp_path, timeout_s=20,
                   scenario={"lines": ["working", "sha abc123"], "exit": 0})
    assert wp.wait(job, 20) == "done"
    kind, state, reason, detail = _row(db, job)
    assert (kind, state) == ("worker", "done")
    out = json.loads(detail)
    assert out["exit_code"] == 0 and out["tail"][-1] == "sha abc123" and out["worker"] == "fake"
    assert out["cwd"] == str(tmp_path)


def test_a_failing_worker_is_failed_with_its_exit_code(db, tmp_path):
    job = wp.start(db, kind="fake", brief="x", workdir=tmp_path, timeout_s=20, scenario={"lines": ["boom"], "exit": 3})
    assert wp.wait(job, 20) == "failed"
    assert "3" in _row(db, job)[2]


def test_the_row_says_what_the_worker_last_said_while_it_runs(db, tmp_path):
    job = wp.start(db, kind="fake", brief="x", workdir=tmp_path, timeout_s=20,
                   scenario={"lines": ["step one"], "hang": True})
    assert wp.wait_for_line(job, "step one", 20)
    assert _row(db, job)[1:3] == ("running", "step one")
    wp.stop(db, job)
    assert wp.wait(job, 20) == "cancelled"


def test_stop_kills_the_whole_process_group(db, tmp_path):
    job = wp.start(db, kind="fake", brief="x", workdir=tmp_path, timeout_s=60,
                   scenario={"lines": ["up"], "hang": True, "child": True})
    assert wp.wait_for_line(job, "up", 20)
    pids = wp.pids(job)
    wp.stop(db, job)
    assert wp.wait(job, 20) == "cancelled"
    assert pids and not wp.any_alive(pids)


def test_a_worker_past_its_timeout_is_failed(db, tmp_path):
    job = wp.start(db, kind="fake", brief="x", workdir=tmp_path, timeout_s=1, scenario={"hang": True})
    assert wp.wait(job, 20) == "failed"
    assert "timed out" in _row(db, job)[2]


def test_a_missing_program_and_a_bad_workdir_are_refused(db, tmp_path):
    with pytest.raises(ValueError, match="workdir"):
        wp.start(db, kind="fake", brief="x", workdir=tmp_path / "nope", timeout_s=5, scenario={})
    with pytest.raises(ValueError, match="kind"):
        wp.start(db, kind="gpt", brief="x", workdir=tmp_path, timeout_s=5)
    with pytest.raises(ValueError, match="timeout"):
        wp.start(db, kind="fake", brief="x", workdir=tmp_path, timeout_s=0, scenario={})
