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
    assert f"mkdir -p {own}/tmp" in cmd and f"[ -O {own} ]" in cmd, "the directory is made by the worker and its owner is checked"
    assert f"cd {own} &&" in cmd and f"cd {wr} &&" not in cmd, "never the world-writable workroot itself"
    assert f"TMPDIR={own}/tmp" in cmd and f"--basetemp={own}/tmp/pytest" in cmd
