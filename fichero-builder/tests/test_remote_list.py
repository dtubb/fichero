"""dev-workflows.run.remote-list (manager 2026-11-03): [check].remote may be a LIST tried in order, one alert per runner that is down,
and a red that appears only because the runner changed is retried once on a runner it did not run on before it counts."""
from __future__ import annotations

import subprocess

import pytest

from fichero_builder import check_tool, journal, queue
from fichero_builder.check_tool import Config

GREEN = {"name": "pytest", "ok": True, "exit_code": 0}
RED = {"name": "pytest", "ok": False, "exit_code": 1}


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "STATE", tmp_path / "s")
    check_tool._DOWN.clear(), check_tool._DEAD.clear(), check_tool._ALERTED.clear()
    ran, alerts = [], []
    state = {"down": set(), "local": GREEN, "back": set(), "remote_res": {}}

    def remote_run(name, argv, root, t, cfg, extra, cwd, remote=""):
        if remote in state["down"]:
            return check_tool._remote_down(cfg, "ssh timeout", remote)
        ran.append(remote)
        return {**state["remote_res"].get(remote, GREEN), "remote": remote}

    monkeypatch.setattr(check_tool, "_remote_run", remote_run)
    monkeypatch.setattr(check_tool, "_local", lambda *a, **k: ran.append("here") or state["local"])
    monkeypatch.setattr(check_tool, "_ssh", lambda host, script, t, stdin=None: subprocess.CompletedProcess([], 0 if host in state["back"] else 255, b"", b""))
    monkeypatch.setattr(queue, "alert", lambda lane, step, why, ev, acts: alerts.append(why) or "a1")
    return ran, alerts, state


CFG = Config(remote="imac:~/g", remotes=("imac:~/g", "air:~/g"))


def test_the_remote_key_reads_a_list_and_a_string(tmp_path):
    t = tmp_path / "harness.toml"
    t.write_text('[check]\nremote = ["imac:~/g", "air:~/g"]\n')
    c = check_tool.load(tmp_path)
    assert c.remotes == ("imac:~/g", "air:~/g") and c.remote == "imac:~/g"
    t.write_text('[check]\nremote = "imac:~/g"\n')
    assert check_tool.load(tmp_path).remote == "imac:~/g" and check_tool._runners(check_tool.load(tmp_path)) == ("imac:~/g",)


def test_the_first_reachable_runner_runs_it_one_alert_per_runner_that_is_down(world, tmp_path):
    ran, alerts, state = world
    assert check_tool._run("pytest", ["x"], tmp_path, 5, CFG, remote=True)["remote"] == "imac:~/g"
    state["down"] = {"imac:~/g"}
    check_tool._DEAD.clear()
    assert check_tool._run("pytest", ["x"], tmp_path, 5, CFG, remote=True)["remote"] == "air:~/g"
    assert len(alerts) == 1 and "imac:~/g is unreachable; trying air:~/g" in alerts[0]
    check_tool._run("pytest", ["x"], tmp_path, 5, CFG, remote=True)
    assert len(alerts) == 1, "a dead runner is not tried (or alerted) again in the ladder"
    state["down"] = {"imac:~/g", "air:~/g"}
    check_tool._DEAD.clear()
    check_tool._run("pytest", ["x"], tmp_path, 5, CFG, remote=True)
    assert ran[-1] == "here" and "the tests ran here" in alerts[-1]


def test_a_red_after_a_runner_change_is_retried_once_on_the_runner_that_is_back_and_a_green_there_counts(world, tmp_path):
    ran, alerts, state = world
    state.update(down={"imac:~/g", "air:~/g"}, local=RED, back={"imac"})
    state["down"] = {"imac:~/g", "air:~/g"}
    res = check_tool._run("pytest", ["x"], tmp_path, 5, CFG, remote=True)
    assert res["ok"] is False, "both down: the local red stands (nothing to compare with)"
    assert len(alerts) == 2, "one alert per runner; the retry pass finds imac 'back' (ssh true) and its run fails again: no second alert"
    state["down"] = {"imac:~/g"}
    check_tool._DEAD.clear()
    state["remote_res"] = {"air:~/g": RED}  # the Air runs it red; the iMac is back
    state["down"] = set()
    check_tool._DEAD.update({"imac:~/g"})
    ran.clear()
    res = check_tool._run("pytest", ["x"], tmp_path, 5, CFG, remote=True)
    assert res["ok"] is True and res["remote"] == "imac:~/g" and ran == ["air:~/g", "imac:~/g"]
    row = next(r for r in journal.read() if r["event"] == "runner-retry")
    assert row["first"] == "air:~/g" and row["retried"] == "imac:~/g" and row["ok"] is True
