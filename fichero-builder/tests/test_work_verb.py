"""dev-workflows.tool.work: `builder work` chains run -> patches -> fetch -> check -> review -> land in ONE process, journals
every step, stops with `QUESTION: <why>` (exit 2) and never pushes. The steps are faked; the order, stops and rows are real."""
from __future__ import annotations

import json
import subprocess
import types

import pytest

from fichero_builder import __main__ as cli
from fichero_builder import journal, work

REAL_AS_WORKER = work.as_worker
RULES = '[land]\nbranch = "integration"\n[check]\nengine_repo = "/engine"\n[models]\nproviders = ["claude-code"]\n' \
        'builder = { provider = "claude-code", model = "sonnet" }\nreviewer = { provider = "claude-code", model = "opus" }\n'
HEAD = "c" * 40
PUSH = f"READY TO LAND: git {'pu' + 'sh'} origin {HEAD}:refs/heads/integration"  # the land script's own line


@pytest.fixture
def chain(tmp_path, monkeypatch):
    (tmp_path / "harness.toml").write_text(RULES)
    monkeypatch.setattr(journal, "STATE", tmp_path / "s")
    calls = []
    fakes = {
        "do_run": lambda a, model: (calls.append(("run", model)), "done")[1],
        "do_export": lambda a, branch: (calls.append(("export", branch)), 2)[1],
        "do_fetch": lambda a, repo, branch: (calls.append(("fetch", repo)), HEAD)[1],
        "do_check": lambda a, repo, since, head, ladder: (calls.append(("check", since, head)), {"ok": True, "failed": ""})[1],
        "do_review": lambda a, repo, head, ladder, verdicts, model: (calls.append(("review", model, ladder.endswith(".json"))), (True, "READY"))[1],
        "do_land": lambda a, repo, head, verdicts, log: (calls.append(("land", head)), (True, PUSH))[1],
    }
    for k, v in fakes.items():
        monkeypatch.setattr(work, k, v)

    def go(*extra):
        return cli.main(["work", "--brief", "b.txt", "--worktree", str(tmp_path / "wt"), "--name", "n1", "--issues", "7", "8",
                         "--pinned", str(tmp_path), "--state", str(tmp_path / "s"), *extra])
    go.calls, go.tmp = calls, tmp_path
    return go


def rows():
    return [r for r in journal.read() if r["event"] == "work"]


def test_the_chain_runs_in_order_with_the_roles_models_prints_the_push_and_never_pushes(chain, capsys):
    assert chain() == 0
    assert [c[0] for c in chain.calls] == ["run", "export", "fetch", "check", "review", "land"]
    assert chain.calls[0][1] == "sonnet" and chain.calls[4][1] == "opus", "[models].builder and [models].reviewer"
    assert chain.calls[3][1] == "integration" and chain.calls[3][2] == HEAD
    assert PUSH in capsys.readouterr().out
    assert [(r["step"], r["ok"]) for r in rows()] == [(s, True) for s in ("run", "patches", "fetch", "check", "review", "land")]
    assert all(r["name"] == "n1" and r["issues"] == [7, 8] and "detail" in r for r in rows())


@pytest.mark.parametrize("end", ["parked", "gone"])
def test_a_worker_that_did_not_finish_is_a_question(chain, monkeypatch, capsys, end):
    monkeypatch.setattr(work, "do_run", lambda a, model: end)
    assert chain() == 2
    out = capsys.readouterr().out
    assert out.startswith("QUESTION: ") and end in out
    assert chain.calls == [] and [(r["step"], r["ok"]) for r in rows()] == [("run", False)]


def test_a_red_check_stops_before_review(chain, monkeypatch, capsys):
    monkeypatch.setattr(work, "do_check", lambda a, repo, since, head, ladder: {"ok": False, "failed": "pytest"})
    assert chain() == 2
    out = capsys.readouterr().out
    assert out.startswith("QUESTION: ") and "pytest" in out
    assert [c[0] for c in chain.calls] == ["run", "export", "fetch"]
    assert rows()[-1]["step"] == "check" and rows()[-1]["ok"] is False


def test_a_not_ready_review_stops_before_land(chain, monkeypatch, capsys):
    monkeypatch.setattr(work, "do_review", lambda *a: (False, "NOT READY: a test is missing"))
    assert chain() == 2
    assert "NOT READY: a test is missing" in capsys.readouterr().out
    assert "land" not in [c[0] for c in chain.calls]
    assert rows()[-1]["step"] == "review" and rows()[-1]["ok"] is False


def test_a_refused_land_is_a_question_and_prints_no_push_line(chain, monkeypatch, capsys):
    monkeypatch.setattr(work, "do_land", lambda *a: (False, "REFUSED: boundary"))
    assert chain() == 2
    out = capsys.readouterr().out
    assert "QUESTION: " in out and "REFUSED: boundary" in out and "READY TO LAND" not in out
    assert rows()[-1]["step"] == "land" and rows()[-1]["ok"] is False


def test_no_patches_is_a_question(chain, monkeypatch):
    monkeypatch.setattr(work, "do_export", lambda a, branch: 0)
    assert chain() == 2 and rows()[-1]["step"] == "patches"


def test_a_role_with_no_model_is_a_question_before_anything_starts(chain, capsys):
    (chain.tmp / "harness.toml").write_text(RULES.replace('reviewer = { provider = "claude-code", model = "opus" }', ""))
    assert chain() == 2
    assert chain.calls == [] and "reviewer" in capsys.readouterr().out


def _g(repo, *args):
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True)
    return r.stdout.strip()


@pytest.fixture
def scratch(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "STATE", tmp_path / "s")
    (tmp_path / "s").mkdir()
    (tmp_path / "pin").mkdir()
    (tmp_path / "pin" / "harness.toml").write_text(f'[jail]\nuser = "wuser"\nworkroot = "{tmp_path}/wr"\n[check]\npython = "/py/python"\n')
    (tmp_path / "wr" / "state").mkdir(parents=True)
    ran = []

    def local(a, script):  # the sudo boundary, faked: the same shell command, run here
        ran.append(script)
        return subprocess.run(["sh", "-c", script], capture_output=True, text=True)
    monkeypatch.setattr(work, "as_worker", local)
    e, w = tmp_path / "engine", tmp_path / "wt"
    e.mkdir()
    env = {"GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null", "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@e",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@e"}
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    _g(e, "init", "-q", "-b", "integration")
    (e / "f").write_text("0")
    _g(e, "add", "f"), _g(e, "commit", "-qm", "base")
    subprocess.run(["git", "clone", "-q", str(e), str(w)], check=True)
    return types.SimpleNamespace(engine=e, wt=w, ran=ran, tmp=tmp_path, a=types.SimpleNamespace(
        worktree=str(w), name="n1", pinned=str(tmp_path / "pin"), brief="b", root="r", kind="claude", session="h", tick=1.0))


def _commit(w, name):
    (w / name).write_text(name)
    _g(w, "add", name), _g(w, "commit", "-qm", name)


def test_fetch_never_passes_the_workers_branch_name_to_git(scratch, tmp_path):
    w = scratch.wt
    _commit(w, "one"), _commit(w, "two")
    hook = tmp_path / "hook.sh"
    hook.write_text(f"#!/bin/sh\ntouch {tmp_path}/PWNED\n")
    hook.chmod(0o755)
    evil = f"refs/heads/--upload-pack={hook}"
    _g(w, "update-ref", evil, "HEAD")
    _g(w, "symbolic-ref", "HEAD", evil)
    head = work.do_fetch(scratch.a, str(scratch.engine), "integration")
    assert head == _g(w, "rev-parse", "HEAD") and head
    assert _g(scratch.engine, "rev-parse", "refs/heads/work-n1") == head
    assert not (tmp_path / "PWNED").exists()


def test_export_counts_the_real_commits_over_the_base(scratch):
    _commit(scratch.wt, "one"), _commit(scratch.wt, "two")
    assert work.do_export(scratch.a, "integration") == 2
    assert len(list((scratch.tmp / "wr" / "state" / "patches-n1").glob("*.patch"))) == 2
    assert work.do_export(types.SimpleNamespace(**{**vars(scratch.a), "worktree": str(scratch.engine), "name": "n2"}), "integration") == 0


def test_the_worker_side_goes_through_sudo_as_the_jail_user_from_the_workroot(scratch, monkeypatch):
    seen = []
    monkeypatch.setattr(work.subprocess, "run", lambda argv, **kw: (seen.append(argv), subprocess.CompletedProcess(argv, 0, "", ""))[1])
    REAL_AS_WORKER(scratch.a, "echo hi")
    assert seen[0][:7] == ["sudo", "-n", "-H", "-u", "wuser", "sh", "-c"]
    assert seen[0][7] == f"cd {scratch.tmp}/wr && echo hi"


def _journal_rows(scratch, *rows):
    p = scratch.tmp / "wr" / "state" / "journal.jsonl"
    with p.open("a") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def test_run_starts_the_worker_as_the_jail_user_and_reads_its_end_from_the_shared_journal(scratch, monkeypatch):
    monkeypatch.setattr(work.jail.Jail, "require", lambda self: None)
    _journal_rows(scratch, {"event": "cost", "task": "n1", "end": "parked"})  # an older run of the same name: not this one

    def fake(a, script):
        scratch.ran.append(script)
        _journal_rows(scratch, {"event": "worker", "task": "n1", "worktree": a.worktree},
                      {"event": "cost", "task": "n1", "end": "handoff"}, {"event": "cost", "task": "n1", "end": "done"})
        return subprocess.CompletedProcess(script, 0, "n1: done\n", "")
    monkeypatch.setattr(work, "as_worker", fake)
    assert work.do_run(scratch.a, "sonnet") == "done"
    cmd = scratch.ran[0]
    assert "/py/python -m fichero_builder run" in cmd and "--name n1" in cmd and "--model sonnet" in cmd
    assert f"--state {scratch.tmp}/wr/state" in cmd and "PYTHONPATH=" in cmd


def test_run_with_no_worker_row_raises_with_the_workers_words(scratch, monkeypatch):
    monkeypatch.setattr(work.jail.Jail, "require", lambda self: None)
    monkeypatch.setattr(work, "as_worker", lambda a, s: subprocess.CompletedProcess(s, 1, "", "sudo: a password is required"))
    with pytest.raises(RuntimeError, match="password is required"):
        work.do_run(scratch.a, "sonnet")


@pytest.mark.parametrize("which", ["do_run", "do_check"])
@pytest.mark.parametrize("exc", [RuntimeError("harness_start failed"), work.jail.JailMissing("no [jail] in the rules file")])
def test_a_raised_step_is_a_question_row_and_exit_2_never_a_traceback(chain, monkeypatch, capsys, which, exc):
    def boom(*a, **k):
        raise exc
    monkeypatch.setattr(work, which, boom)
    assert chain() == 2
    out = capsys.readouterr().out
    assert out.startswith("QUESTION: ") and str(exc) in out
    assert rows()[-1]["step"] == which[3:] and rows()[-1]["ok"] is False and str(exc) in rows()[-1]["detail"]


def test_work_check_refuses_an_empty_range_like_builder_check(scratch, monkeypatch):
    monkeypatch.setattr(work.check_tool, "run_ladder", lambda *a, **k: pytest.fail("the ladder ran on an empty range"))
    head = _g(scratch.engine, "rev-parse", "HEAD")
    _g(scratch.engine, "branch", "work-n1", head)
    with pytest.raises(RuntimeError, match="empty"):
        work.do_check(scratch.a, str(scratch.engine), "integration", head, str(scratch.tmp / "ladder.json"))


def test_work_check_passes_a_resolved_sha_as_since_and_the_items_ids_as_protected(scratch, monkeypatch):
    seen = []
    monkeypatch.setattr(work.check_tool, "run_ladder", lambda *a, **k: (seen.append(a), {"ok": True})[1])
    base = _g(scratch.engine, "rev-parse", "HEAD")
    _g(scratch.engine, "checkout", "-qb", "side")
    (scratch.engine / "g").write_text("1")
    _g(scratch.engine, "add", "g"), _g(scratch.engine, "commit", "-qm", "two")
    head = _g(scratch.engine, "rev-parse", "HEAD")
    a = types.SimpleNamespace(**vars(scratch.a), ids=["dev-workflows.tool.work"])
    work.do_check(a, str(scratch.engine), "integration", head, str(scratch.tmp / "ladder.json"))
    root, since, h, pinned, protected = seen[0]
    assert since == base and h == head and list(protected) == ["dev-workflows.tool.work"]


def test_builder_check_and_work_check_share_the_empty_range_refusal():
    from fichero_builder import check_tool
    assert issubclass(check_tool.EmptyRange, RuntimeError) and callable(check_tool.ladder_over)
