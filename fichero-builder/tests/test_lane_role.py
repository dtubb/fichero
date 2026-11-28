"""dev-workflows.models.by-config, per-lane role: `queue add --role` is checked at add time, the lane's worker starts on the
role's model, and the handoff successor stays on it."""
from __future__ import annotations

import json

import pytest

from fichero_builder import __main__ as cli
from fichero_builder import journal, queue, run

MODELS = ('[models]\nproviders = ["claude-code"]\nbuilder = { provider = "claude-code", model = "sonnet" }\nreviewer = { provider = "claude-code", model = "opus" }\n'
          'maintainer-fable = { provider = "claude-code", model = "claude-fable-5-1", context = 400000 }\n'
          'stray = { provider = "nowhere", model = "x" }\n')


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "STATE", tmp_path / "s")
    monkeypatch.setenv("FICHERO_HARNESS_REG", str(tmp_path / "reg"))
    (tmp_path / "brief").write_text("brief")
    (tmp_path / "harness.toml").write_text('[check]\nengine_repo = "/e"\n[land]\nbranch = "integration"\n[jail]\nuser = "wu"\nworkroot = "' + str(tmp_path / "wr") + '"\n'
                                           '[spend]\nsession_usd = 1\nday_usd = 5\nwindow = 1000\nprices = { sonnet = [3, 15], claude-fable-5-1 = [15, 75] }\n' + MODELS)
    (tmp_path / "wr").mkdir()
    return tmp_path


def add(state, *extra):
    return cli.main(["queue", "add", "--lane", "mf", "--worktree", "/w", "--step", "1.1", "--brief", str(state / "brief"),
                     "--root", str(state), "--state", str(state / "s"), *extra])


def test_add_refuses_a_role_missing_from_models_or_whose_provider_is_not_set_up(state, capsys):
    assert add(state, "--role", "nonesuch") == 1
    assert "nonesuch" in capsys.readouterr().out and queue.load() == []
    assert add(state, "--role", "stray") == 1
    assert "nowhere" in capsys.readouterr().out and queue.load() == []
    assert add(state, "--role", "maintainer-fable") == 0
    assert queue.load()[0]["role"] == "maintainer-fable"


def test_a_lane_with_a_role_starts_its_worker_on_that_roles_model_and_a_lane_without_one_on_the_builder(state, monkeypatch):
    popens = []
    monkeypatch.setattr(queue.work, "as_worker", lambda a, s: type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})())
    monkeypatch.setattr(queue.subprocess, "Popen", lambda argv, **k: popens.append(argv[-1]) or object())
    monkeypatch.setattr(queue, "tmux_as_worker", lambda j, *a: "")
    monkeypatch.setattr(queue.work, "ensure_pinned", lambda root, brief, base: str(state))
    monkeypatch.setattr(queue.land_tool, "resolve_branch", lambda repo, branch: "d" * 40)
    procs = queue.real_procs(state)
    for lane_id, extra in (("mf", {"role": "maintainer-fable"}), ("m2", {})):
        procs.start({"id": lane_id, "worktree": str(state / "wr" / f"wt-{lane_id}"), "seq": 0, **extra}, {"step": "1.1", "brief": str(state / "brief"), "issues": []})
    assert "--model claude-fable-5-1" in popens[0] and "--role maintainer-fable" in popens[0]
    assert "--model sonnet" in popens[1] and "--role" not in popens[1]
    assert "--kind claude" in popens[0] and "--kind claude" in popens[1]


def test_a_qwen_trial_lane_starts_pi_on_openrouter_with_the_owners_agent_dir(state, monkeypatch):
    """The Qwen3-Coder-Next trial: a lane on an openrouter role starts `builder run --kind pi --provider openrouter --agent-dir <dir>`
    (the queue started every worker as `--kind claude`); with no [models].pi_agent_dir it does not start."""
    toml = state / "harness.toml"
    toml.write_text(toml.read_text().replace('providers = ["claude-code"]', 'providers = ["claude-code", "openrouter"]')
                    + 'qwen-trial = { provider = "openrouter", model = "qwen/qwen3-coder-next", context = 262144 }\n')
    popens = []
    monkeypatch.setattr(queue.work, "as_worker", lambda a, s: type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})())
    monkeypatch.setattr(queue.subprocess, "Popen", lambda argv, **k: popens.append(argv[-1]) or object())
    monkeypatch.setattr(queue, "tmux_as_worker", lambda j, *a: "")
    monkeypatch.setattr(queue.work, "ensure_pinned", lambda root, brief, base: str(state))
    monkeypatch.setattr(queue.land_tool, "resolve_branch", lambda repo, branch: "d" * 40)
    lane = {"id": "qwen", "worktree": str(state / "wr" / "wt-qwen"), "seq": 0, "role": "qwen-trial"}
    with pytest.raises(RuntimeError, match="pi_agent_dir"):
        queue.real_procs(state).start(dict(lane), {"step": "1.1", "brief": str(state / "brief"), "issues": []})
    toml.write_text(toml.read_text().replace("[models]\n", '[models]\npi_agent_dir = "/Users/Shared/w/pi-agent"\n'))
    queue.real_procs(state).start(dict(lane), {"step": "1.1", "brief": str(state / "brief"), "issues": []})
    (cmd,) = popens
    assert "--kind pi" in cmd and "--provider openrouter" in cmd and "--agent-dir /Users/Shared/w/pi-agent" in cmd
    assert "--model qwen/qwen3-coder-next" in cmd and "--role qwen-trial" in cmd


def test_the_handoff_successor_keeps_the_role_its_window_and_its_label(state):
    from test_dry_run import HEALTHY, Fake  # the same fake session the handoff test uses

    (state / "wt").mkdir()
    fake = Fake([HEALTHY, {**HEALTHY, "idle": True, "last_text": "HANDOFF READY"}, HEALTHY, {**HEALTHY, "idle": True, "moved": True, "last_text": "DONE bbbb222"}])
    starts = []
    real = fake.start
    fake.procs.start = lambda *a: starts.append(a[4]) or real(*a)
    assert run.run(state, state / "wt", state / "b.txt", name="mf", model="claude-fable-5-1", role="maintainer-fable", procs=fake.procs, out=lambda s: None) == "done"
    assert starts == ["claude-fable-5-1", "claude-fable-5-1"]
    reg = json.loads((state / "reg" / "mf.json").read_text())
    assert reg["window"] == 400000 and reg["handoff_tokens"] == 340000, "85 % of the role's own window, not [spend]'s 175000 mark"
    rows = [e for e in journal.read() if e["event"] in ("worker", "cost")]
    assert len(rows) == 4 and all(e["role"] == "maintainer-fable" for e in rows)


def test_a_workers_command_starts_in_a_directory_it_made_with_tmpdir_and_pytest_basetemp_inside_it(state, monkeypatch):
    popens = []
    monkeypatch.setattr(queue.work, "as_worker", lambda a, s: type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})())
    monkeypatch.setattr(queue.subprocess, "Popen", lambda argv, **k: popens.append(argv[-1]) or object())
    monkeypatch.setattr(queue, "tmux_as_worker", lambda j, *a: "")
    monkeypatch.setattr(queue.work, "ensure_pinned", lambda root, brief, base: str(state))
    monkeypatch.setattr(queue.land_tool, "resolve_branch", lambda repo, branch: "d" * 40)
    queue.real_procs(state).start({"id": "mf", "worktree": str(state / "wr" / "wt-mf"), "seq": 0}, {"step": "1.1", "brief": str(state / "brief"), "issues": []})
    own, wr = str(state / "wr" / "work-mf"), str(state / "wr")
    cmd = popens[0]
    assert f"mkdir -p {own}/tmp" in cmd and f"[ ! -L {own} ] && [ -O {own} ]" in cmd, "the directory is made by the worker, is no link, and its owner is checked"
    assert f"cd {own} &&" in cmd and f"cd {wr} &&" not in cmd, "never the world-writable workroot itself"
    assert f"TMPDIR={own}/tmp" in cmd and f"--basetemp={own}/tmp/pytest" in cmd


def test_a_fix_round_closes_its_own_steps_last_session_and_starts_instead_of_alerting(state, monkeypatch):
    """2026-11-25 21:03-21:06, alerts 1933-1935: right after a red, app-bugs' fix round "in a new session" refused to start:
    "a tmux window named app-bugs holds a live session (@26, 2.1.332)" -- the step's own last session. A window of another step
    (one the loop did not send this step) still refuses."""
    popens, tmux = [], []
    monkeypatch.setattr(queue.work, "as_worker", lambda a, s: type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})())
    monkeypatch.setattr(queue.subprocess, "Popen", lambda argv, **k: popens.append(argv[-1]) or object())
    monkeypatch.setattr(queue, "tmux_as_worker", lambda j, *a: tmux.append(a) or "")
    monkeypatch.setattr(queue, "worker_windows", lambda j, name, with_command=False: [("@26", "2.1.332")])
    monkeypatch.setattr(queue.work, "ensure_pinned", lambda root, brief, base: str(state))
    monkeypatch.setattr(queue.land_tool, "resolve_branch", lambda repo, branch: "d" * 40)
    step = {"step": "nightly-green-1", "brief": str(state / "brief"), "issues": [], "rounds": 1}
    queue.real_procs(state).start({"id": "app-bugs", "worktree": str(state / "wr" / "wt-app-bugs"), "seq": 3, "session_step": "nightly-green-1"}, dict(step))
    assert ("kill-window", "-t", "@26") in tmux and len(popens) == 1
    (row,) = [r for r in journal.read() if r.get("state") == "window-closed"]
    assert "this step's own last session (@26, 2.1.332) was closed" in row["detail"]
    with pytest.raises(RuntimeError, match="holds a live session"):
        queue.real_procs(state).start({"id": "app-bugs", "worktree": str(state / "wr" / "wt-app-bugs"), "seq": 3, "session_step": "other-step"}, dict(step))


def test_a_retry_after_the_brief_was_rewritten_sends_the_new_brief_with_the_newest_addendum(state):
    """2026-11-26: a retry re-sent a stale retry-/question-/fix-<lane>-<step>.txt, made from the brief as it was before the manager
    rewrote it. The resume brief is made again from the current brief and its newest addendum (the findings, a stop, a send-back)."""
    import os
    brief, fix = state / "brief.md", state / "fix-l-1.2-1.txt"
    brief.write_text("# old brief\ndo X\n")
    fix.write_text(brief.read_text().rstrip("\n") + "\n\n" + queue.fix_text("1.2", "check", "test_a is red"))
    os.utime(brief, (1_000, 1_000))
    s = {"step": "1.2", "brief": str(brief), "resume_brief": str(fix)}
    assert queue.brief_of(s) == str(fix) and "old brief" in fix.read_text(), "the brief is older: the resume brief as it is"
    brief.write_text("# new brief\ndo Y instead\n")
    os.utime(fix, (1_000, 1_000))
    assert queue.brief_of(s) == str(fix)
    text = fix.read_text()
    assert text.startswith("# new brief\ndo Y instead\n\nStep 1.2: the check did not pass.") and "old brief" not in text and "test_a is red" in text
    assert [r["state"] for r in journal.read() if r.get("state") == "brief-renewed"] == ["brief-renewed"]
    q = state / "question-l-1.2.txt"  # an addendum with no known mark: the new brief alone
    q.write_text("# new brief\n\nsomething the old loop wrote\n")
    os.utime(q, (1_000, 1_000))
    assert queue.brief_of({"step": "1.2", "brief": str(brief), "resume_brief": str(q)}) == str(q) and q.read_text() == "# new brief\ndo Y instead\n"
    assert queue.brief_of({"step": "1.2", "brief": str(brief)}) == str(brief)


def test_a_landed_steps_live_session_is_closed_for_the_next_step_instead_of_alerting(state, monkeypatch):
    """2026-11-26 20:24: after soak-4 landed (by a train, the cleared path or `queue landed`), soak-5 refused to start on soak-4's live window."""
    popens, tmux = [], []
    monkeypatch.setattr(queue.work, "as_worker", lambda a, s: type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})())
    monkeypatch.setattr(queue.subprocess, "Popen", lambda argv, **k: popens.append(argv[-1]) or object())
    monkeypatch.setattr(queue, "tmux_as_worker", lambda j, *a: tmux.append(a) or "")
    monkeypatch.setattr(queue, "worker_windows", lambda j, name, with_command=False: [("@56", "2.1.332")])
    monkeypatch.setattr(queue.work, "ensure_pinned", lambda root, brief, base: str(state))
    monkeypatch.setattr(queue.land_tool, "resolve_branch", lambda repo, branch: "d" * 40)
    lane = {"id": "runner-soak", "worktree": str(state / "wr" / "wt-runner-soak"), "seq": 4, "session_step": "soak-4",
            "steps": [{"step": "soak-4", "state": "landed"}, {"step": "soak-5", "state": "queued"}]}
    queue.real_procs(state).start(lane, {"step": "soak-5", "brief": str(state / "brief"), "issues": [], "rounds": 0})
    assert ("kill-window", "-t", "@56") in tmux and len(popens) == 1
    assert "the landed step soak-4's session (@56, 2.1.332) was closed" in [r for r in journal.read() if r.get("state") == "window-closed"][0]["detail"]
    lane["steps"][0]["state"] = "train"
    with pytest.raises(RuntimeError, match="holds a live session"):
        queue.real_procs(state).start(lane, {"step": "soak-5", "brief": str(state / "brief"), "issues": [], "rounds": 0})


def test_a_start_reads_the_roles_model_from_the_live_rules_not_the_ones_the_loop_started_with(state, monkeypatch):
    """2026-11-28 08:20: builder and maintainer-fable went to sonnet in the live harness.toml; the 08:23 starts still ran
    claude-fable-5-2[1m], the [models] the loop read at its start. Each start (and model_of, which ends a kept session whose model
    changed) reads the live file."""
    popens = []
    monkeypatch.setattr(queue.work, "as_worker", lambda a, s: type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})())
    monkeypatch.setattr(queue.subprocess, "Popen", lambda argv, **k: popens.append(argv[-1]) or object())
    monkeypatch.setattr(queue, "tmux_as_worker", lambda j, *a: "")
    monkeypatch.setattr(queue.work, "ensure_pinned", lambda root, brief, base: str(state))
    monkeypatch.setattr(queue.land_tool, "resolve_branch", lambda repo, branch: "d" * 40)
    procs = queue.real_procs(state)
    lane = {"id": "mf", "worktree": str(state / "wr" / "wt-mf"), "seq": 0, "role": "maintainer-fable"}
    step = {"step": "1.1", "brief": str(state / "brief"), "issues": []}
    toml = state / "harness.toml"
    toml.write_text(toml.read_text().replace('model = "claude-fable-5-1", context = 400000', 'model = "sonnet", context = 200000'))
    procs.start(dict(lane), dict(step))
    assert "--model sonnet" in popens[-1] and procs.model_of(lane) == "sonnet"
