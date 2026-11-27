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
    check_tool._DEAD.update({"imac:~/g": __import__("time").time()})
    ran.clear()
    res = check_tool._run("pytest", ["x"], tmp_path, 5, CFG, remote=True)
    assert res["ok"] is True and res["remote"] == "imac:~/g" and ran == ["air:~/g", "imac:~/g"]
    row = next(r for r in journal.read() if r["event"] == "runner-retry")
    assert row["first"] == "air:~/g" and row["retried"] == "imac:~/g" and row["ok"] is True


def test_one_alert_per_outage_across_ladders_and_the_runner_back_answers_it(world, tmp_path):
    """speed batch 4 (manager 2026-11-03): 40 'unreachable' alerts in a day, one per ladder, while the iMac was off."""
    ran, alerts, state = world
    state["down"] = {"imac:~/g"}
    for _ladder in range(3):  # each ladder starts with clean per-ladder sets, as _jail_exit leaves them
        check_tool._DOWN.clear(), check_tool._DEAD.clear(), check_tool._ALERTED.clear()
        check_tool._run("pytest", ["x"], tmp_path, 5, CFG, remote=True)
    assert len(alerts) == 1, "one alert for the whole outage"
    check_tool._remote_back("imac:~/g")
    assert [(r["id"], r["action"]) for r in journal.read() if r["event"] == "alert-answer"] == [("a1", "runner-back")]
    check_tool._remote_back("imac:~/g")
    assert len([r for r in journal.read() if r["event"] == "alert-answer"]) == 1, "back twice is one answer"
    check_tool._DOWN.clear(), check_tool._DEAD.clear(), check_tool._ALERTED.clear()
    check_tool._run("pytest", ["x"], tmp_path, 5, CFG, remote=True)
    assert len(alerts) == 2, "the next outage alerts anew"


FOUR = Config(remote="air:~/g", remotes=("air:~/g", "imac:~/g", "imac:~/g2", "m4:~/g"))


def test_each_ladder_slot_starts_at_its_own_runner_and_the_base_runs_at_the_next(world, tmp_path):
    """2026-11-27 14:00-16:10: four ladder slots, four runners, and every remote run named the iMac: each ladder tried the list
    in the same order, so all queued behind the first runner's heavy lock while imac:~/g2 and m4 ran nothing."""
    ran, alerts, state = world
    firsts = []
    for i in range(4):
        check_tool.SLOT[0] = i
        firsts.append(check_tool._run("pytest", ["x"], tmp_path, 5, FOUR, remote=True)["remote"])
    assert firsts == ["air:~/g", "imac:~/g", "imac:~/g2", "m4:~/g"]
    check_tool.SLOT[0] = 3
    assert check_tool._runners_for_base(FOUR)[0] == "air:~/g", "the base runs: the runner after the slot's own"
    state["down"] = {"m4:~/g"}
    assert check_tool._run("pytest", ["x"], tmp_path, 5, FOUR, remote=True)["remote"] == "air:~/g", "its runner down: the next in the ring"
    check_tool.SLOT[0] = 0


def test_a_down_mark_expires_so_a_runner_that_blipped_is_tried_again_while_other_ladders_run(world, tmp_path, monkeypatch):
    """2026-11-27: the Air blipped at 12:52 and answered at 12:53, but the mark was cleared only when no ladder ran; it ran nothing after."""
    ran, alerts, state = world
    state["down"] = {"air:~/g"}
    check_tool.SLOT[0] = 0
    assert check_tool._run("pytest", ["x"], tmp_path, 5, FOUR, remote=True)["remote"] == "imac:~/g"
    state["down"] = set()
    assert check_tool._run("pytest", ["x"], tmp_path, 5, FOUR, remote=True)["remote"] == "imac:~/g", "within DEAD_S: still skipped"
    later = __import__("time").time() + check_tool.DEAD_S + 1
    monkeypatch.setattr(check_tool.time, "time", lambda: later)
    assert check_tool._run("pytest", ["x"], tmp_path, 5, FOUR, remote=True)["remote"] == "air:~/g", "the mark expired: back in the ring"


def test_ladder_slot_tells_the_ladder_which_slot_it_holds(tmp_path, monkeypatch):
    from fichero_builder import work
    monkeypatch.setattr(journal, "STATE", tmp_path / "s")
    (tmp_path / "s").mkdir()
    monkeypatch.setattr(work, "SLOTS", [0])
    with work.ladder_slot("a", ["x.py"], 4, by_file=False) as s1:
        assert s1 == "ladder" and check_tool.SLOT[0] == 0
        with work.ladder_slot("b", ["y.py"], 4, by_file=False) as s2:
            assert s2 == "ladder-2" and check_tool.SLOT[0] == 1
        assert check_tool.SLOT[0] == 0
    assert check_tool.SLOT[0] == 0


THREE = Config(remote="air:~/g", remotes=("air:~/g", "imac:~/g", "imac:~/g2"))


def test_a_down_runners_slot_takes_the_next_free_gate_dir_not_one_another_slot_holds(world, tmp_path, monkeypatch):
    """2026-11-27 18:17-18:57: the Air was down; its slot queued on imac:~/g behind slot 1's run while imac:~/g2 was idle."""
    ran, alerts, state = world
    monkeypatch.setattr(check_tool, "HELD", {0, 1})  # slot 1 holds imac:~/g
    check_tool.SLOT[0] = 0
    state["down"] = {"air:~/g"}
    assert check_tool._run("pytest", ["x"], tmp_path, 5, THREE, remote=True)["remote"] == "imac:~/g2"
    assert check_tool._runners_for_slot(THREE) == ("air:~/g", "imac:~/g2", "imac:~/g")
    monkeypatch.setattr(check_tool, "HELD", {0})
    assert check_tool._runners_for_slot(THREE) == ("air:~/g", "imac:~/g", "imac:~/g2"), "nothing else held: the ring as before"
    check_tool._DEAD.clear()
    assert check_tool._runners_for_slot(THREE)[0] == "air:~/g"


def test_a_red_that_stood_on_a_second_gate_dir_is_not_retried_again_in_that_ladder(world, tmp_path, monkeypatch):
    """2026-11-27 18:34-18:38: six runner-retry rows in four minutes, each red again on imac:~/fichero-gate2."""
    ran, alerts, state = world
    monkeypatch.setattr(check_tool, "RED_STOOD", set())
    check_tool._KEY[0] = "check a..b"
    check_tool.SLOT[0] = 0
    state.update(down={"air:~/g"}, remote_res={"imac:~/g": RED, "imac:~/g2": RED})
    for _ in range(3):
        assert check_tool._run("pytest", ["x"], tmp_path, 5, THREE, remote=True)["ok"] is False
    assert len([r for r in journal.read() if r["event"] == "runner-retry"]) == 1, "the first red is retried once; after it stood, none"
    check_tool._KEY[0] = "check c..d"  # another ladder judges its runners afresh
    check_tool._run("pytest", ["x"], tmp_path, 5, THREE, remote=True)
    assert len([r for r in journal.read() if r["event"] == "runner-retry"]) == 2
    check_tool._KEY[0] = ""


def test_every_listed_gate_dir_gets_a_runner_row_even_with_the_slot_count_off(tmp_path, monkeypatch):
    """2026-11-27: m4 ran nothing all day and no row said so; with slots_from_runners off there were no runner rows at all."""
    from fichero_builder import queue, work
    monkeypatch.setattr(journal, "STATE", tmp_path / "s")
    for k, v in (("RUNNERS", {}), ("PROBING", [None]), ("PROBED_AT", [0.0])):
        monkeypatch.setattr(queue, k, v)
    monkeypatch.setattr(work, "SLOTS", [0])
    (tmp_path / "harness.toml").write_text('[check]\nparallel = 4\nremote = ["air:~/g", "imac:~/g", "imac:~/g2", "m4:~/g"]\n')
    probed = []
    probe = lambda n: probed.append(n) or ({"runner": n, "reachable": False, "detail": "no route"} if n.startswith("m4") else  # noqa: E731
                                           {"runner": n, "reachable": True, "cores": 8, "load": 1.0, "free_ram_gb": 8.0, "free_gb": 50.0})
    assert queue.count_slots(tmp_path, probe=probe, now=1000.0) == 0, "the count stays [check].parallel"
    rows = [r for r in journal.read() if r["event"] == "runner"]
    assert [r["runner"] for r in rows] == ["air:~/g", "imac:~/g", "imac:~/g2", "m4:~/g"] and probed == ["air:~/g", "imac:~/g", "m4:~/g"], "one ssh a host"
    assert next(r for r in rows if r["runner"] == "m4:~/g")["reachable"] is False
    queue.count_slots(tmp_path, probe=probe, now=1000.0 + 60)
    assert len([r for r in journal.read() if r["event"] == "runner"]) == 4, "not again within RUNNER_ROW_S"
    queue.count_slots(tmp_path, probe=probe, now=1000.0 + queue.RUNNER_ROW_S)
    assert len([r for r in journal.read() if r["event"] == "runner"]) == 8
