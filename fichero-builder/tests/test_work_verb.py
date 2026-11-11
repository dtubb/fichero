"""dev-workflows.tool.work: `builder work` chains run -> patches -> fetch -> check -> review -> land in ONE process, journals
every step, stops with `QUESTION: <why>` (exit 2) and never pushes. The steps are faked; the order, stops and rows are real."""
from __future__ import annotations

from pathlib import Path

import json
import shlex
import subprocess
import types

import pytest

from fichero_builder import __main__ as cli
from fichero_builder import journal, work

REAL_AS_WORKER = work.as_worker
REAL_DO_LAND = work.do_land
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
        "do_rebase": lambda a, branch: (calls.append(("rebase", branch)), "")[1],
        "do_export": lambda a, branch: (calls.append(("export", branch)), 2)[1],
        "do_fetch": lambda a, repo, branch: (calls.append(("fetch", repo)), HEAD)[1],
        "do_check": lambda a, repo, since, head, ladder: (calls.append(("check", since, head)), {"ok": True, "failed": ""})[1],
        "do_review": lambda a, repo, head, ladder, verdicts, model: (calls.append(("review", model, ladder.endswith(".json"))), (True, "READY"))[1],
        "do_land": lambda a, repo, head, verdicts, log: (calls.append(("land", head)), (True, PUSH))[1],
        "_base_moved": lambda a, branch, head: False,
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
    assert [c[0] for c in chain.calls] == ["run", "rebase", "export", "fetch", "check", "review", "land"]
    assert chain.calls[0][1] == "sonnet" and chain.calls[5][1] == "opus", "[models].builder and [models].reviewer"
    assert chain.calls[4][1] == "integration" and chain.calls[4][2] == HEAD
    assert PUSH in capsys.readouterr().out
    assert [(r["step"], r["ok"]) for r in rows()] == [(s, True) for s in ("run", "rebase", "patches", "fetch", "check", "review", "land")]
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
    assert [c[0] for c in chain.calls] == ["run", "rebase", "export", "fetch"]
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


def test_a_ready_range_whose_base_moved_before_the_land_gate_is_rebased_and_checked_again(chain, monkeypatch, capsys):
    """Manager 2026-11-02: when the landing branch moves, a ready range is rebased and re-checked by the chain, never
    refused for a person to rebase by hand; a base that never stops moving is still refused after three tries."""
    lands = iter([(False, "REFUSED: integration is not an ancestor"), (True, PUSH)])
    monkeypatch.setattr(work, "do_land", lambda *a: (chain.calls.append(("land",)), next(lands))[1])
    monkeypatch.setattr(work, "_base_moved", lambda a, branch, head: True)
    assert chain() == 0 and PUSH in capsys.readouterr().out
    assert [c[0] for c in chain.calls] == ["run"] + ["rebase", "export", "fetch", "check", "review", "land"] * 2
    assert any("moved under" in r["detail"] for r in rows() if r["step"] == "rebase")
    monkeypatch.setattr(work, "do_land", lambda *a: (False, "REFUSED: still moving"))
    chain.calls.clear()
    assert chain() == 2 and [c[0] for c in chain.calls].count("check") == 1 + work.MOVES


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


def test_a_rerun_after_the_worker_rewrote_its_branch_replaces_the_owners_ref(scratch):
    w = scratch.wt
    _commit(w, "one")
    first = work.do_fetch(scratch.a, str(scratch.engine), "integration")
    _g(w, "reset", "-q", "--hard", "HEAD~1")
    _commit(w, "other")  # a history the owner's work-n1 ref does not contain
    second = work.do_fetch(scratch.a, str(scratch.engine), "integration")
    assert first and second and second != first
    assert _g(scratch.engine, "rev-parse", "refs/heads/work-n1") == second


def test_fetch_brings_in_a_base_the_engine_mirror_has_not_seen_yet(scratch):
    up = scratch.tmp / "up"
    subprocess.run(["git", "clone", "-q", str(scratch.engine), str(up)], check=True)
    _commit(up, "newer")  # origin moved on; the worktree rebased onto it, the engine mirror did not fetch yet
    _g(scratch.engine, "remote", "add", "origin", str(up))
    _g(scratch.wt, "remote", "set-url", "origin", str(up)), _g(scratch.wt, "fetch", "-q", "origin")
    _g(scratch.wt, "reset", "-q", "--hard", "origin/integration")
    _commit(scratch.wt, "mine")
    head = work.do_fetch(scratch.a, str(scratch.engine), "integration")
    assert head and head == _g(scratch.wt, "rev-parse", "HEAD")


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
    monkeypatch.setattr(work.check_tool, "run_ladder", lambda *a, **k: (seen.append(a), kw.append(k), {"ok": True})[2])
    kw = []
    base = _g(scratch.engine, "rev-parse", "HEAD")
    _g(scratch.engine, "checkout", "-qb", "side")
    (scratch.engine / "g").write_text("1")
    _g(scratch.engine, "add", "g"), _g(scratch.engine, "commit", "-qm", "two")
    head = _g(scratch.engine, "rev-parse", "HEAD")
    a = types.SimpleNamespace(**vars(scratch.a), ids=["dev-workflows.tool.work"])
    work.do_check(a, str(scratch.engine), "integration", head, str(scratch.tmp / "ladder.json"))
    root, since, h, pinned, protected = seen[0]
    assert since == base and h == head and list(protected) == ["dev-workflows.tool.work"]
    assert kw[0].get("maintainer") is not True, "builder work can never set the maintainer flag"


@pytest.fixture
def real_chain(scratch, monkeypatch):
    """The real `work` main over a pinned rules file; only the sudo boundary is faked (what the worker leaves in the shared journal)."""
    monkeypatch.setattr(work.jail.Jail, "require", lambda self: None)
    pin = scratch.tmp / "pin"
    (pin / "harness.toml").write_text(RULES.replace('"/engine"', f'"{scratch.engine}"').replace("[check]\n", '[check]\npython = "/py/python"\n')
                                      + f'[jail]\nuser = "wuser"\nworkroot = "{scratch.tmp}/wr"\n')

    def go(worker_lines, toml=None):
        if toml:
            (pin / "harness.toml").write_text((pin / "harness.toml").read_text() + toml)

        def fake(a, script):
            if " rebase " in script:
                return subprocess.CompletedProcess(script, 0, "", "")  # the rebase step, faked green
            if "fichero_builder run" not in script:
                return subprocess.CompletedProcess(script, 1, "", "")
            with (scratch.tmp / "wr" / "state" / "journal.jsonl").open("a") as f:
                f.write(json.dumps({"event": "worker", "task": "n1", "worktree": str(scratch.wt)}) + "\n")
                f.write("".join(x + "\n" for x in worker_lines))
            return subprocess.CompletedProcess(script, 0, "", "")
        monkeypatch.setattr(work, "as_worker", fake)
        return cli.main(["work", "--brief", "b.txt", "--worktree", str(scratch.wt), "--name", "n1", "--issues", "7",
                         "--pinned", str(pin), "--state", str(scratch.tmp / "s")])
    return go


@pytest.mark.parametrize("line", ["{not json", "1", '["a"]', '{"task": "n1"}'])
def test_a_worker_written_journal_row_that_is_not_a_row_never_tracebacks(real_chain, capsys, line):
    done = json.dumps({"event": "cost", "task": "n1", "end": "done"})
    assert real_chain([line, done]) == 2  # skipped; the chain goes on and stops at patches (the fake worker made none)
    assert capsys.readouterr().out.startswith("QUESTION: ")
    assert rows()[-1]["step"] == "patches" and rows()[0]["step"] == "run" and rows()[0]["ok"] is True


def test_a_cost_row_with_no_end_is_not_an_end(real_chain, capsys):
    assert real_chain([json.dumps({"event": "cost", "task": "n1"})]) == 2
    assert capsys.readouterr().out.startswith("QUESTION: ") and "no end row" in rows()[-1]["detail"]
    assert rows()[-1]["step"] == "run" and rows()[-1]["ok"] is False


def test_a_misspelt_jail_key_is_a_question_row_not_a_traceback(real_chain, capsys):
    assert real_chain([], toml='usr = "x"\n') == 2
    assert capsys.readouterr().out.startswith("QUESTION: ")
    assert rows()[-1]["ok"] is False


def test_work_without_pinned_makes_the_pinned_worktree_for_the_briefs_base_and_reads_the_rules_from_it(scratch, monkeypatch):
    """Item 4: no --pinned: [land].pinned_dir/pinned-<base7> is made from the engine repo (base from the brief's first line)
    and the rules are read from THAT copy; a second run finds it and makes nothing."""
    e, root = scratch.engine, scratch.tmp / "root"
    (e / "harness.toml").write_text(RULES.replace('"/engine"', f'"{e}"') + f'[jail]\nuser = "wuser"\nworkroot = "{scratch.tmp}/wr"\n')
    _g(e, "add", "harness.toml"), _g(e, "commit", "-qm", "rules")
    base = _g(e, "rev-parse", "HEAD")
    root.mkdir()
    (root / "harness.toml").write_text(f'[land]\nbranch = "integration"\npinned_dir = "{scratch.tmp}/pins"\n[check]\nengine_repo = "{e}"\n')
    (scratch.tmp / "b.txt").write_text(f"You are a worker in the dev harness. Branch step-1.1 in this worktree (base {base}). No push.\nmore\n")
    seen = []
    for k in ("do_run", "do_export", "do_fetch", "do_check", "do_review", "do_land"):
        monkeypatch.setattr(work, k, lambda a, *r, _k=k: (seen.append((_k, a.pinned)), {"do_run": "done", "do_export": 1, "do_fetch": HEAD,
                            "do_check": {"ok": True, "failed": ""}, "do_review": (True, "READY"), "do_land": (True, PUSH)}[_k])[1])
    argv = ["work", "--brief", str(scratch.tmp / "b.txt"), "--worktree", str(scratch.wt), "--name", "n1", "--issues", "7",
            "--root", str(root), "--state", str(scratch.tmp / "s")]
    assert cli.main(argv) == 0
    dest = scratch.tmp / "pins" / f"pinned-{base[:7]}"
    assert (dest / "harness.toml").is_file()
    assert {p for _, p in seen} == {str(dest)}
    assert "pinned-" + base[:7] in _g(e, "branch", "--list", "pinned-*")
    rows = [json.loads(x) for x in (scratch.tmp / "s" / "journal.jsonl").read_text().splitlines()]
    assert [r["detail"] for r in rows if r.get("step") == "pinned"] == [str(dest)]
    mtime = dest.stat().st_mtime
    assert cli.main(argv) == 0  # found, not remade
    assert dest.stat().st_mtime == mtime


def test_work_without_pinned_and_no_base_in_the_brief_is_a_question(scratch, capsys):
    root = scratch.tmp / "root"
    root.mkdir()
    (root / "harness.toml").write_text(f'[land]\nbranch = "integration"\npinned_dir = "{scratch.tmp}/pins"\n[check]\nengine_repo = "{scratch.engine}"\n')
    (scratch.tmp / "b.txt").write_text("a brief with no base line\n")
    assert cli.main(["work", "--brief", str(scratch.tmp / "b.txt"), "--worktree", str(scratch.wt), "--name", "n1", "--issues", "7",
                     "--root", str(root), "--state", str(scratch.tmp / "s")]) == 2
    assert "base" in capsys.readouterr().out


def test_rebase_puts_the_worktree_on_top_of_the_branch_another_lane_moved(scratch):
    """Item 9: two lanes landing in turn. The other lane landed first (origin moved); the worktree is rebased as the worker
    before its patches are taken, so the check judges the range that will land."""
    _commit(scratch.wt, "mine")
    _commit(scratch.engine, "theirs")
    assert work.do_rebase(scratch.a, "integration") == ""
    assert _g(scratch.wt, "rev-parse", "HEAD^") == _g(scratch.engine, "rev-parse", "HEAD")
    assert _g(scratch.wt, "log", "--format=%s", "-1") == "mine"
    assert any("rebase -q origin/integration" in r for r in scratch.ran), "run as the worker (through as_worker), not as the owner"


def test_a_rebase_conflict_is_aborted_and_said_never_resolved(scratch):
    (scratch.wt / "f").write_text("mine"), _g(scratch.wt, "commit", "-qam", "mine")
    (scratch.engine / "f").write_text("theirs"), _g(scratch.engine, "commit", "-qam", "theirs")
    why = work.do_rebase(scratch.a, "integration")
    assert "conflict" in why.lower() or "could not" in why.lower()
    assert not (scratch.wt / ".git" / "rebase-merge").exists(), "aborted"
    assert _g(scratch.wt, "log", "--format=%s", "-1") == "mine"


def test_a_failed_rebase_is_a_question_before_patches(chain, monkeypatch, capsys):
    monkeypatch.setattr(work, "do_rebase", lambda a, branch: "conflict in f")
    assert chain() == 2
    assert [c[0] for c in chain.calls] == ["run"]
    assert "conflict in f" in capsys.readouterr().out
    assert [(r["step"], r["ok"]) for r in rows()][-1] == ("rebase", False)


def test_a_land_log_the_gate_cannot_write_is_a_question_not_a_traceback(chain, monkeypatch, capsys):
    """The chain runs the gate in-process now: an OSError from its log at the end of the ladder must stay a question."""
    monkeypatch.setattr(work.land_tool, "gate", lambda *a: (_ for _ in ()).throw(PermissionError("parent dir must be owned")))
    ok, why = REAL_DO_LAND(types.SimpleNamespace(pinned="/p"), "/r", HEAD, "/v", "/l")
    assert not ok and "parent dir must be owned" in why
    (journal.STATE).mkdir(parents=True, exist_ok=True)
    (journal.STATE / "land-n1.log").mkdir()
    assert chain() == 2 and "the land log" in capsys.readouterr().out, "before the worker runs, not after"
    assert not any(r.get("step") == "run" for r in rows())


def test_a_pinned_copy_removed_under_the_chain_is_a_question_not_a_traceback(chain, monkeypatch, capsys):
    """Another lane's landing removes this one's pinned copy, so the steps after the worker lose their rules: a row and a question."""
    from fichero_builder import jail

    def gone(a, branch):
        raise jail.JailMissing("no [jail] user and workroot in the rules file")
    monkeypatch.setattr(work, "do_rebase", gone)
    assert chain() == 2
    assert "QUESTION: " in capsys.readouterr().out and rows()[-1]["ok"] is False and "no [jail]" in rows()[-1]["detail"]


def test_a_worker_that_committed_and_never_said_done_goes_on_to_the_check(chain, monkeypatch):
    """`builder run` ends such a worker `done-unsaid` with exit 0: the branch has the work, so the check judges it, as for done."""
    monkeypatch.setattr(work, "do_run", lambda a, model: "done-unsaid")
    assert chain() == 0
    assert next(r for r in rows() if r["step"] == "run")["ok"] is True


def test_a_range_that_already_has_ready_is_not_reviewed_again(chain, monkeypatch, capsys):
    """Same input, same model: a queue restarted in `reviewing` must reuse the verdict, not pay for a second pass."""
    monkeypatch.setattr(work.land_tool, "unreviewed", lambda *a: [])
    monkeypatch.setattr(work, "do_review", lambda *a: pytest.fail("the model ran again"))
    assert chain() == 0


def test_a_red_guard_is_named_in_what_goes_back_to_the_worker():
    """A guards rung's detail is in its results, so the fix brief named the rung and not the guard."""
    r = {"rungs": [{"name": "guards", "ok": False, "results": [{"name": "check_a", "ok": True, "stderr_tail": "fine"}, {"name": "check_b", "ok": False, "stdout_tail": "b is wrong"}]}]}
    text = work._tail(r)
    assert "check_b" in text and "b is wrong" in text and "check_a" not in text


def test_run_makes_a_missing_worktree_as_the_jail_user_from_its_clone_and_leaves_an_existing_one(scratch, monkeypatch):
    """Maintainer's answer: the worker's worktree is made as the jail user when missing, from `<workroot>/root` at the base."""
    root = scratch.tmp / "wr" / "root"
    subprocess.run(["git", "clone", "-q", str(scratch.engine), str(root)], check=True)
    (scratch.tmp / "pin" / "harness.toml").write_text((scratch.tmp / "pin" / "harness.toml").read_text() + '[land]\nbranch = "integration"\n')
    wt = scratch.tmp / "wr" / "wt-n9"
    scratch.a.worktree, scratch.a.name = str(wt), "n9"
    assert work.ensure_worktree(scratch.a, "n9") == ""
    assert _g(wt, "rev-parse", "--abbrev-ref", "HEAD") == "n9" and (wt / "f").exists(), "a real worktree on a new branch, at origin's head"
    made = len(scratch.ran)
    assert work.ensure_worktree(scratch.a, "n9") == "" and len(scratch.ran) == made, "an existing one is left alone"
    scratch.a.worktree = str(scratch.tmp / "wr" / "wt-other")
    scratch.a.base = _g(root, "rev-parse", "HEAD")
    assert work.ensure_worktree(scratch.a, "other") == ""
    assert _g(scratch.a.worktree, "rev-parse", "HEAD") == scratch.a.base, "--base when one is given"
    scratch.a.worktree, scratch.a.base = str(scratch.tmp / "wr" / "wt-bad"), "0" * 40
    assert "could not be made" in work.ensure_worktree(scratch.a, "bad")


def test_do_run_refuses_with_the_reason_when_the_worktree_cannot_be_made(scratch, monkeypatch):
    monkeypatch.setattr(work.jail.Jail, "require", lambda self: None)
    monkeypatch.setattr(work, "ensure_worktree", lambda a, name: "the worktree could not be made: nope")
    with pytest.raises(RuntimeError, match="nope"):
        work.do_run(scratch.a, "sonnet")


def test_the_chain_finds_its_pinned_copy_again_inside_the_ladder_lock(chain, monkeypatch):
    """Another lane's landing may have removed the copy this lane started from; once the lock is held nothing can until the land gate is done."""
    seen = []
    a = types.SimpleNamespace(worktree="/w", name="n", pinned="/gone", issues=[1], repin=lambda: (seen.append("repin"), "/fresh")[1])
    monkeypatch.setattr(work, "do_check", lambda a_, *r: (seen.append(a_.pinned), {"ok": False, "failed": "x"})[1])
    assert work.after_run(a, "/r", "integration", "m")["kind"] == "red"
    assert seen == ["repin", "/fresh"]


def test_an_external_lanes_own_checkout_runs_its_chain_steps_as_the_owner(tmp_path):
    """Soak 2026-11-02: ie-batch2 waited in the owner's land-ie checkout, which the jail user cannot read; an external lane's
    tree outside the workroot runs its rebase, export and bundle as the owner, into the owner's own state dir."""
    import types

    from fichero_builder import work
    (tmp_path / "harness.toml").write_text(f'[jail]\nuser = "w"\nworkroot = "{tmp_path / "wr"}"\n')
    (tmp_path / "wr").mkdir()
    out = types.SimpleNamespace(pinned=str(tmp_path), worktree=str(tmp_path / "land-ie"), external=True)
    inside = types.SimpleNamespace(pinned=str(tmp_path), worktree=str(tmp_path / "wr" / "wt-x"), external=True)
    worker = types.SimpleNamespace(pinned=str(tmp_path), worktree=str(tmp_path / "land-ie"))
    assert work.owner_tree(out) and not work.owner_tree(inside) and not work.owner_tree(worker)
    (tmp_path / "land-ie").mkdir()
    r = work.as_worker(out, "pwd")
    assert r.returncode == 0 and r.stdout.strip().endswith("land-ie"), "as the owner, in the lane's own tree: no sudo"
    assert work.shared_state(out) == work.journal.STATE / "owner-trees"


def test_the_review_model_is_sonnet_unless_the_range_touches_harness_paths_or_it_is_the_milestones_last_step(tmp_path):
    """Manager 2026-11-02 (6a): sonnet by default; opus for harness, land or jail paths, and one opus pass per milestone."""
    import subprocess
    import types

    from fichero_builder import work

    def g(*a):
        return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *a], cwd=tmp_path, check=True, capture_output=True, text=True).stdout.strip()
    g("init", "-q", "-b", "integration"), (tmp_path / "a").write_text("a"), g("add", "."), g("commit", "-qm", "base")
    g("checkout", "-q", "-b", "lane")
    (tmp_path / "fichero").mkdir()
    (tmp_path / "fichero" / "View.swift").write_text("x")
    g("add", "."), g("commit", "-qm", "product")
    a = types.SimpleNamespace(reviewer_fast="sonnet", opus_paths=work.OPUS_PATHS, last_step=False)
    head = g("rev-parse", "HEAD")
    assert work.pick_reviewer(a, str(tmp_path), "integration", head, "opus") == "sonnet"
    a.last_step = True
    assert work.pick_reviewer(a, str(tmp_path), "integration", head, "opus") == "opus", "the milestone's last step: one opus pass"
    a.last_step = False
    (tmp_path / "fichero-builder").mkdir()
    (tmp_path / "fichero-builder" / "x.py").write_text("x")
    g("add", "."), g("commit", "-qm", "harness")
    assert work.pick_reviewer(a, str(tmp_path), "integration", g("rev-parse", "HEAD"), "opus") == "opus", "a harness path: opus"
    assert work.pick_reviewer(types.SimpleNamespace(), str(tmp_path), "integration", head, "opus") == "opus", "no fast reviewer set: the full one"


class _Waited(Exception):
    pass


def _stop(_s):
    raise _Waited


def test_two_disjoint_batches_check_at_once_and_a_batch_sharing_a_file_waits(scratch):
    """Speed 3 (manager 2026-11-02): [check].parallel ladders at once, never two whose batches share a file; an unknown file
    list shares every file; parallel 1 is the old single ladder."""
    with work.ladder_slot("a", ["x.py"], 2) as s1:
        with work.ladder_slot("b", ["y.py"], 2) as s2:
            assert {s1, s2} == {"ladder", "ladder-2"}
        for name, files, n in (("c", ["x.py", "z.py"], 2), ("d", [], 2), ("e", ["z.py"], 1)):
            with pytest.raises(_Waited):
                with work.ladder_slot(name, files, n, sleep=_stop):
                    pass
    with work.ladder_slot("c", ["x.py"], 2) as s:
        assert s == "ladder"
    assert not list(journal.STATE.glob("*.files")), "a slot's file list goes with its lock"


def test_a_ladders_rung_hook_and_key_are_its_own_threads():
    """Speed 3: two ladders at once in the loop's chain threads: one chain's ON_RUNG never fires for the other's rungs."""
    import threading
    work.check_tool.ON_RUNG[0], work.check_tool._KEY[0] = "mine", "k"
    seen = []
    t = threading.Thread(target=lambda: seen.append((work.check_tool.ON_RUNG[0], work.check_tool._KEY[0])))
    t.start(), t.join()
    assert seen == [(None, "")] and work.check_tool.ON_RUNG[0] == "mine"
    work.check_tool.ON_RUNG[0], work.check_tool._KEY[0] = None, ""


def _early_chain(chain, monkeypatch, later_red: bool):
    """A fake ladder that reports ready and red-on-base green, then the rest green (or a later rung red)."""
    import threading
    started, release = threading.Event(), threading.Event()
    killed = []

    def review(a, repo, head, ladder, verdicts, model, holder=None):
        chain.calls.append(("review", model, ladder.endswith(".partial")))
        part = json.loads(Path(ladder).read_text()) if ladder.endswith(".partial") else {}
        chain.pending = part.get("pending")
        chain.guard_results = [len(r.get("results") or []) for r in part.get("rungs", []) if r["name"] == "guards"]
        if holder is not None:
            holder["proc"] = type("P", (), {"kill": lambda self: (killed.append(True), release.set())})()
        started.set()
        release.wait(5)
        return True, "READY"

    def check(a, repo, since, head, ladder):
        chain.calls.append(("check", since, head))
        work.check_tool.ON_RUNG[0]("red-on-base", True, [{"name": "ready", "ok": True}, {"name": "red-on-base", "ok": True}])
        assert not (Path(ladder).parent / (Path(ladder).name + ".partial")).exists(), "not after red-on-base: no guard has run yet (reviews 199, 207, 263, 275)"
        cheap = [{"name": n, "ok": True} for n in ("ready", "diff-bound", "red-on-base")] + [
            {"name": "guards", "ok": True, "results": [{"name": "check_a", "ok": True}, {"name": "check_b", "ok": True}]},
            {"name": "contract-current", "ok": True}, {"name": "since-guards", "ok": True}]
        work.check_tool.ON_RUNG[0]("since-guards", True, cheap)
        assert started.wait(5), "the review started beside the ladder, before the check ended"
        if not later_red:
            release.set()
        return {"ok": not later_red, "failed": "pytest" if later_red else ""}
    monkeypatch.setattr(work, "do_review", review)
    monkeypatch.setattr(work, "do_check", check)
    monkeypatch.setattr(work.land_tool, "unreviewed", lambda *a: True)
    monkeypatch.setattr(work, "pick_reviewer", lambda *a: "opus")
    return killed


def test_the_review_starts_once_red_on_base_is_green_and_its_verdict_is_used(chain, monkeypatch):
    """Speed 2: the review runs beside the rest of the ladder over the partial ladder; a green check takes its verdict."""
    killed = _early_chain(chain, monkeypatch, later_red=False)
    assert chain() == 0
    assert [c[0] for c in chain.calls] == ["run", "rebase", "export", "fetch", "check", "review", "land"]
    assert chain.calls[5] == ("review", "opus", True) and not killed


def test_the_early_review_is_told_which_rungs_still_run_beside_it(chain, monkeypatch):
    """Reviews 199 and 207 (2026-11-03): the early review read a ladder of three rungs and answered 'no guards ran'; the partial
    file names the rungs still to come, in the ladder's order."""
    _early_chain(chain, monkeypatch, later_red=False)
    assert chain() == 0
    assert chain.pending == ["build"], "only the build runs beside the review"
    assert chain.guard_results == [2], "the reviewer reads every guard's result (the partial is written after since-guards)"


def test_a_later_red_rung_kills_the_early_review(chain, monkeypatch):
    """Speed 2: a rung after red-on-base goes red: the early review's process is killed and nothing lands."""
    killed = _early_chain(chain, monkeypatch, later_red=True)
    assert chain() != 0
    assert killed == [True] and "land" not in [c[0] for c in chain.calls]


def test_a_base_that_moved_during_the_check_is_rebased_before_the_review_and_a_disjoint_delta_keeps_the_green(chain, monkeypatch):
    """Manager 2026-11-02 (ie-batch2 lost 55 min): the chain never reviews a range whose base moved; it rebases first, and a
    base delta disjoint from the batch keeps the green check (a row names the new base) instead of a second ladder."""
    import types
    bases, moved = iter(["b" * 40, "c" * 40]), iter([True, False])
    monkeypatch.setattr(work, "r_since", lambda repo, branch: next(bases))
    monkeypatch.setattr(work, "_git", lambda repo, *args: types.SimpleNamespace(stdout="fichero-builder/x.py\n", returncode=0))
    monkeypatch.setattr(work, "_base_moved", lambda a, branch, head: next(moved))
    monkeypatch.setattr(work, "keep_green", lambda repo, ob, of, nb, f, cfg, oh="", h="": f"kept across rebase onto {nb[:9]}: base delta disjoint (1 file(s))"
                        if (ob, of, f) == ("b" * 40, ["fichero-builder/x.py"], ["fichero-builder/x.py"]) else "")
    assert chain() == 0
    assert [c[0] for c in chain.calls] == ["run", "rebase", "export", "fetch", "check", "rebase", "export", "fetch", "review", "land"]
    (kept,) = [r for r in journal.read() if r["event"] == "check" and r.get("kept")]
    assert kept["since"] == "c" * 40 and kept["ok"] is True and "ccccccccc" in kept["kept"]


def test_keep_green_only_for_a_base_delta_outside_the_batchs_dirs_check_files_and_guards(tmp_path):
    """The keep rule: the same batch files, an ancestor move, and a delta touching none of: the batch's files, the top-level
    dirs it changes, [check].check_paths, the guard glob."""
    g = lambda *a: _g(tmp_path, *a)  # noqa: E731
    g("init", "-q"), g("config", "user.email", "t@e"), g("config", "user.name", "t")
    for f in ("pkg/a.py", "other/b.py", "scripts/check_x.py", "harness.toml"):
        (tmp_path / f).parent.mkdir(exist_ok=True)
        (tmp_path / f).write_text("1\n")
    g("add", "."), g("commit", "-qm", "base")
    old = g("rev-parse", "HEAD")
    cfg = work.check_tool.Config(check_paths=("harness.toml",), guard_glob="scripts/check_*.py")
    batch = ["pkg/a.py"]

    def move(f):
        (tmp_path / f).write_text((tmp_path / f).read_text() + "2\n")
        g("commit", "-qam", f)
        return g("rev-parse", "HEAD")
    new = move("other/b.py")
    assert work.keep_green(str(tmp_path), old, batch, new, batch, cfg, old, new).startswith(f"kept across rebase onto {new[:9]}")
    assert work.keep_green(str(tmp_path), old, batch, new, batch, cfg) == "", "no heads: the patch cannot be compared"
    assert work.keep_green(str(tmp_path), old, batch, new, ["pkg/a.py", "pkg/c.py"], cfg, old, new) == "", "a different batch"
    # same file names, different content: the patch of the rebased head is not the one the ladder judged
    (tmp_path / "pkg" / "a.py").write_text("changed after the check\n")
    g("commit", "-qam", "new content in the batch file")
    assert work.keep_green(str(tmp_path), old, batch, new, batch, cfg, old, g("rev-parse", "HEAD")) == "", "new content rides no green"
    g("reset", "-q", "--hard", new)
    for f in ("pkg/a.py", "harness.toml", "scripts/check_x.py"):
        g("reset", "-q", "--hard", old)
        assert work.keep_green(str(tmp_path), old, batch, move(f), batch, cfg, old, old) == "", f
    g("reset", "-q", "--hard", old)
    (tmp_path / "pkg" / "z.py").write_text("1\n")
    g("add", "."), g("commit", "-qm", "same dir")
    assert work.keep_green(str(tmp_path), old, batch, g("rev-parse", "HEAD"), batch, cfg, old, old) == "", "a delta in the batch's own dir"


def test_every_reason_a_pinned_refusal_lists_maps_to_the_approval_that_excuses_it():
    """Manager 2026-11-02: four approves of a conftest.py batch did nothing: its reason matched no approval kind."""
    tail = ("pipeline/tests/conftest.py: conftest.py is pinned by name anywhere (it changes what pytest does)\n"
            "scripts/x.py: a new file under a pinned path (only a new guard may be added there)\nthe diff deletes or weakens existing tests (t.py)")
    assert work.pinned_approvals(tail) == ["maintainer", "approve_weakened", "approve_pinned_new"]
    assert work.pinned_approvals("a.py: conftest.py is pinned by name anywhere (x)") == ["maintainer"]


def test_the_alert_names_the_group_that_blocked_not_the_files_last_line():
    """Alert harness-gen3-batch-1-75 read 'the review is not READY: READY': the grouped review file ends with the last group's verdict."""
    text = ("[group 1 of 3: a..b]\nfine\nREADY\n[group 2 of 3: b..c]\nbody\nNOT READY: a send-back never reaches a live session\n"
            "[group 3 of 3: c..d]\nnotes\nREADY")
    assert work.blocking(text, "READY") == "[group 2 of 3: b..c] NOT READY: a send-back never reaches a live session"
    assert work.blocking("body\nNOT READY: x", "NOT READY: x") == "NOT READY: x"
    assert work.blocking("nothing structured", "nothing structured") == "nothing structured"


def test_a_guard_data_stop_the_added_routes_rule_clears_runs_the_ladder_again_with_heads_copy(chain, monkeypatch):
    """dev-workflows.run.auto-rules (guard-data-added-routes, manager 2026-11-03): no alert, one `auto` row, the ladder again with
    head's copy of exactly the data files under the pinned guards."""
    (chain.tmp / "harness.toml").write_text(RULES.replace('[check]\n', '[check]\ncheck_paths = ["scripts/"]\nauto = ["guard-data-added-routes"]\nroutes_file = "api.json"\n'))
    monkeypatch.setattr(work, "r_since", lambda repo, branch: "b" * 40)
    monkeypatch.setattr(work, "_git", lambda repo, *args: types.SimpleNamespace(stdout="scripts/check_x_known_gaps.json\n", returncode=0))
    monkeypatch.setattr(work.check_tool, "known_gaps_added_only", lambda *a: "")
    seen = []

    def check(a, repo, since, head, ladder):
        seen.append(tuple(getattr(a, "guard_data", ())))
        return {"ok": bool(seen[-1]), "failed": "" if seen[-1] else "guards", "rungs": []}
    monkeypatch.setattr(work, "do_check", check)
    assert chain() == 0
    assert seen == [(), ("scripts/check_x_known_gaps.json",)]
    assert [(r["rule"], r["file"]) for r in journal.read() if r["event"] == "auto"] == [("guard-data-added-routes", "scripts/check_x_known_gaps.json")]
    monkeypatch.setattr(work.check_tool, "known_gaps_added_only", lambda *a: "removes ['GET /x']")
    seen.clear()
    assert chain() != 0 and seen == [()], "anything else still stops for the manager"


BAKE = "import hashlib, pathlib; pathlib.Path('ident.txt').write_text(hashlib.sha256(pathlib.Path('contract.json').read_bytes()).hexdigest() + chr(10))"


def _generated_world(scratch):
    (scratch.tmp / "pin" / "harness.toml").write_text(
        f'[jail]\nuser = "wuser"\nworkroot = "{scratch.tmp}/wr"\n[check]\npython = "/py/python"\ngenerated = ["ident.txt"]\n'
        f'rebake = ["python3", "-c", "{BAKE}"]\nrebake_issue = "#4705"\n')

    def bake(w, contract):
        (w / "contract.json").write_text(contract)
        subprocess.run(["python3", "-c", BAKE], cwd=w, check=True)
    lines = "\n".join(f"line {i}" for i in range(20)) + "\n"
    bake(scratch.engine, lines)
    _g(scratch.engine, "add", "."), _g(scratch.engine, "commit", "-qm", "the contract")
    _g(scratch.wt, "pull", "-q")
    bake(scratch.wt, lines.replace("line 2\n", "line 2 mine\n"))
    _g(scratch.wt, "commit", "-qam", "mine: a route\n\nDirected-By: the maintainer\nCo-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>")
    bake(scratch.engine, lines.replace("line 17\n", "line 17 theirs\n"))
    _g(scratch.engine, "commit", "-qam", "theirs: another route")
    return bake


def test_a_rebase_whose_only_conflict_is_the_generated_identity_re_bakes_it_and_goes_on(scratch):
    """Manager 2026-11-04 (alerts 290, 291, 308): every landing made the other lanes conflict only on the contract identity."""
    _generated_world(scratch)
    assert work.do_rebase(scratch.a, "integration") == ""
    import hashlib
    contract = (scratch.wt / "contract.json").read_text()
    assert "line 2 mine" in contract and "line 17 theirs" in contract, "the sources merged"
    assert (scratch.wt / "ident.txt").read_text().strip() == hashlib.sha256(contract.encode()).hexdigest(), "the identity is of the merged contract"
    assert subprocess.run(["git", "-C", str(scratch.wt), "merge-base", "--is-ancestor", _g(scratch.engine, "rev-parse", "HEAD"), "HEAD"]).returncode == 0, "on top of origin"
    assert "mine: a route" in _g(scratch.wt, "log", "--format=%s", "-3"), "the lane's commit kept, with its message"
    assert _g(scratch.wt, "status", "--porcelain") == "" and not (scratch.wt / ".git" / "rebase-merge").exists()
    rows = [r for r in journal.read() if r["event"] == "rebake"]
    assert rows and rows[0]["files"] == ["ident.txt"] and rows[0]["lane"] == "n1"


def test_a_rebase_with_any_other_conflict_beside_the_identity_is_aborted_as_before(scratch):
    _generated_world(scratch)
    (scratch.wt / "f").write_text("mine"), _g(scratch.wt, "commit", "-qam", "mine f")
    (scratch.engine / "f").write_text("theirs"), _g(scratch.engine, "commit", "-qam", "theirs f")
    why = work.do_rebase(scratch.a, "integration")
    assert "could not finish" in why and not (scratch.wt / ".git" / "rebase-merge").exists()


def test_a_pinned_copy_removed_before_the_rebase_is_pinned_again_and_the_error_names_the_file_it_read(tmp_path):
    """batch-25, 2026-11-05 00:50: another lane's landing removed the older pinned copies while this chain held no ladder slot, and the
    rebase read [jail] from the gone copy. `_jail` pins again from the current base; with no way to, it names the file it read."""
    import types

    gone, fresh = tmp_path / "pinned-aaaaaaa", tmp_path / "pinned-bbbbbbb"
    fresh.mkdir()
    (fresh / "harness.toml").write_text('[jail]\nuser = "fichero-worker"\nworkroot = "/Users/Shared/fichero-worker"\n')
    a = types.SimpleNamespace(pinned=str(gone), repin=lambda: str(fresh))
    assert work._jail(a).user == "fichero-worker" and a.pinned == str(fresh)
    with pytest.raises(work.jail.JailMissing, match=f"{gone}/harness.toml is missing"):
        work._jail(types.SimpleNamespace(pinned=str(gone)))
    (gone).mkdir()
    (gone / "harness.toml").write_text("[check]\n")
    with pytest.raises(work.jail.JailMissing, match="harness.toml has no \\[jail\\] user and workroot"):
        work._jail(types.SimpleNamespace(pinned=str(gone)))


def test_a_review_that_never_reached_its_api_is_tried_again_and_then_is_an_alert_never_a_not_ready(chain, monkeypatch, capsys):
    """2026-11-07: an SSL error after the Mac woke came back as the review's text, read as NOT READY, and spent all three
    send-backs of a batch nobody had reviewed."""
    monkeypatch.setattr(work.time, "sleep", lambda s: None)
    said = iter([(False, "API Error: Unable to connect to API: SSL certificate hostname mismatch"), (True, "READY")])
    monkeypatch.setattr(work, "do_review", lambda *a: next(said))
    assert chain() == 0, "the second try reached the API and said READY: the batch goes on to land"
    assert "land" in [c[0] for c in chain.calls]
    monkeypatch.setattr(work, "do_review", lambda *a: (False, "API Error: Unable to connect to API: SSL certificate hostname mismatch"))
    chain.calls.clear()
    assert chain() == 2
    assert "could not reach its API" in capsys.readouterr().out and "land" not in [c[0] for c in chain.calls]
    assert work.unreachable("NOT READY: API Error: Unable to connect is mentioned in a finding") is False, "a verdict is a verdict"


def test_run_cmd_takes_the_package_from_the_pinned_copy_not_the_owners_checkout(scratch):
    """#6466: the jail user cannot read the owner's checkout, so `builder run` imports fichero_builder from the pinned copy
    (world-readable) when it holds one; a pinned copy without the package falls back to this one."""
    (scratch.tmp / "pin" / "fichero-builder" / "fichero_builder").mkdir(parents=True)
    cmd = work.run_cmd(scratch.a, "sonnet")
    assert f"PYTHONPATH={scratch.tmp}/pin/fichero-builder " in cmd, cmd
    (scratch.tmp / "pin" / "fichero-builder" / "fichero_builder").rmdir()
    assert f"PYTHONPATH={shlex.quote(str(Path(work.__file__).resolve().parents[1]))} " in work.run_cmd(scratch.a, "sonnet")  # quoted: the M4 gate path has a space


def test_run_cmd_puts_homebrew_on_the_path_the_jail_user_gets(scratch):
    """#6466: `sudo -H -u` resets PATH, and harness_start needs tmux (/opt/homebrew/bin): the first dispatched worker was 'gone' in a
    minute because tmux was not found and nobody saw the error."""
    cmd = work.run_cmd(scratch.a, "sonnet")
    assert "PATH=/opt/homebrew/bin:" in cmd, cmd


def test_ensure_worktree_bases_a_managed_tree_on_a_bundle_of_the_steps_head(scratch, tmp_path):
    """#6466: the worker's root clone sees only origin, so a retried batch's head (in the engine repo) travels as a bundle: the
    managed tree starts at that head, on its new branch."""
    e, wr = scratch.engine, scratch.tmp / "wr"
    _g(e, "checkout", "-q", "-b", "feat")
    _commit(e, "one")
    head = _g(e, "rev-parse", "HEAD")
    _g(e, "checkout", "-q", "integration")
    subprocess.run(["git", "clone", "-q", str(e), str(wr / "root")], check=True)
    bundle = tmp_path / "base.bundle"
    _g(e, "branch", "base-lane-x", head)  # the ref the managed tree is fetched from (the loop names it after the lane)
    _g(e, "bundle", "create", str(bundle), "integration..base-lane-x")
    a = types.SimpleNamespace(**{**vars(scratch.a), "worktree": str(wr / "wt-x"), "base_bundle": str(bundle)})
    (scratch.tmp / "pin" / "harness.toml").write_text((scratch.tmp / "pin" / "harness.toml").read_text() + '[land]\nbranch = "integration"\n')
    assert work.ensure_worktree(a, "lane-x") == ""
    assert _g(wr / "wt-x", "rev-parse", "HEAD") == head and _g(wr / "wt-x", "branch", "--show-current") == "lane-x"
