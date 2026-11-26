"""dev-workflows.run.heavy-lock: one heavy job at a time per machine; quick things stay free."""
from __future__ import annotations

import os
import subprocess
import sys

import pytest

from fichero_builder import __main__ as cli
from fichero_builder import check_tool, journal


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "STATE", tmp_path / "s")
    monkeypatch.delenv(journal.HEAVY_ENV, raising=False)
    return tmp_path / "s"


def test_a_second_heavy_job_waits_and_a_wait_over_the_limit_names_the_holder(state, monkeypatch, capsys):
    import threading
    monkeypatch.setattr(journal.Lock, "WARN_S", 0.1)
    order = []
    with journal.heavy("the first"):
        def second():
            with journal.heavy("the second"):
                order.append("second")
        t = threading.Thread(target=second)
        t.start()
        t.join(1.3)
        assert t.is_alive() and order == [], "the second waits while the first holds it"
        order.append("first-done")
    t.join(5)
    assert order == ["first-done", "second"]
    assert "waiting for the heavy lock, held by" in capsys.readouterr().err


def test_builder_heavy_runs_the_command_under_the_lock_and_its_children_pass_through(state, capfd):
    code = f"import os; print('held' if os.environ.get({journal.HEAVY_ENV!r}) else 'free')"
    assert cli.main(["heavy", "--state", str(state), "--", sys.executable, "-c", code]) == 0
    assert "held" in capfd.readouterr().out
    assert cli.main(["heavy", "--state", str(state), "--", sys.executable, "-c", "raise SystemExit(3)"]) == 3
    assert cli.main(["heavy", "--state", str(state)]) == 2, "no command is refused"
    with journal.heavy("a child of builder heavy"):  # the env var makes a nested job pass, never deadlock
        os.environ[journal.HEAVY_ENV] = "1"
        try:
            with journal.heavy("nested"):
                pass
        finally:
            del os.environ[journal.HEAVY_ENV]


def test_the_build_rung_and_a_local_full_suite_take_it_the_guards_and_a_remote_suite_do_not(state, monkeypatch, tmp_path):
    """speed batch 3 (manager 2026-11-03): the guards rung has its own `guards` lock, never the heavy one."""
    seen, own = [], []
    monkeypatch.setattr(journal, "heavy", lambda what: __import__("contextlib").nullcontext(seen.append(what)))
    real_lock = journal.Lock
    monkeypatch.setattr(journal, "Lock", lambda name="journal", **k: (own.append(name) if name == "guards" else None, real_lock(name, **k))[1])
    monkeypatch.setattr(check_tool, "_run", lambda *a, **k: {"ok": True, "exit_code": 0, "timed_out": False, "stdout_tail": "", "stderr_tail": "", "seconds": 0})
    monkeypatch.setattr(check_tool, "pytest_rung", lambda *a, **k: {"ok": True, "argv": [], "exit_code": 0, "seconds": 0, "stdout_tail": "", "stderr_tail": ""})
    check_tool.guards(tmp_path, check_tool.Config(guard_glob="ci/x_*.py", min_guards=0))
    check_tool.build(tmp_path, ["fichero/x"], check_tool.Config(build=("true",), build_paths=("fichero/",)))
    check_tool.green_runs(tmp_path, ["fichero-server/tests"], (), check_tool.Config(), 5)
    check_tool.green_runs(tmp_path, ["fichero-server/tests"], (), check_tool.Config(remote="imac:~/g"), 5)
    assert seen == ["xcodebuild (the build rung)", "the full engine suite"], "the guards and the remote suite took no heavy lock"
    assert own == ["guards"], "the guards rung took its own lock"


def test_the_dev_build_takes_the_lock(state, monkeypatch, tmp_path):
    held = []
    monkeypatch.setattr(journal, "heavy", lambda what, yields=False: __import__("contextlib").nullcontext(held.append(what)))
    root = tmp_path / "r"
    (root / "scripts").mkdir(parents=True)
    (root / "fichero" / "Configs").mkdir(parents=True)
    (root / "fichero" / "Configs" / "Version.xcconfig").write_text("MARKETING_VERSION = 1.2.3\n")
    script = root / "scripts" / "build-release-dmg.sh"
    script.write_text('#!/bin/sh\nmkdir -p "$(dirname "$FICHERO_DMG_PATH")" && echo x > "$FICHERO_DMG_PATH"\n')
    script.chmod(0o755)
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    assert cli.main(["build", "--dev", "--root", str(root), "--state", str(state)]) == 0
    assert held == ["the dev build"]


def test_the_remote_wrapper_holds_the_machines_lock_while_its_script_runs_and_passes_the_exit_code(tmp_path):
    """The iMac's own lock (owner 2026-11-02): the wrapper `_remote_run` puts round a remote script serialises two runs on the
    lock file and returns the script's exit code; run here with the local python standing in for the remote one."""
    import shlex
    import time
    lock = str(tmp_path / "heavy.lock")
    log = tmp_path / "log"
    one = check_tool._remote_heavy(sys.executable, lock, f"echo a-start >> {shlex.quote(str(log))}; sleep 1; echo a-end >> {shlex.quote(str(log))}; exit 7")
    two = check_tool._remote_heavy(sys.executable, lock, f"echo b-start >> {shlex.quote(str(log))}; echo b-end >> {shlex.quote(str(log))}")
    p1 = subprocess.Popen(["sh", "-c", one])
    t0 = time.monotonic()  # the first holds the lock once it has written a-start: a fixed 0.4 s lost the race at load 124 (2026-11-07)
    while not (log.exists() and "a-start" in log.read_text()) and time.monotonic() - t0 < 30:
        time.sleep(0.05)
    p2 = subprocess.Popen(["sh", "-c", two])
    assert p1.wait(10) == 7 and p2.wait(10) == 0
    assert log.read_text().split() == ["a-start", "a-end", "b-start", "b-end"], "the second waited for the first"
    assert shlex.split(one)[0] == sys.executable


def test_a_build_yields_to_a_waiting_check_and_a_check_outranks_it(state, monkeypatch):
    import threading
    monkeypatch.setattr(journal, "YIELD_POLL_S", 0.05)
    order = []
    with journal.heavy("a check running"):
        def check():
            with journal.heavy("the next check"):
                order.append("check")

        def build():
            with journal.heavy("the dev build", yields=True):
                order.append("build")
        tc = threading.Thread(target=check)
        tc.start()
        for _ in range(100):  # the check is waiting: its marker stands
            if journal.heavy_waiters():
                break
            threading.Event().wait(0.02)
        assert journal.heavy_waiters() == 1
        tb = threading.Thread(target=build)
        tb.start()
    tc.join(5), tb.join(5)
    assert order == ["check", "build"], "the lock fell free with a check waiting and a build waiting: the check goes first"
    assert not list(state.glob("heavy-wait.*")), "no marker is left behind"


def test_a_build_with_no_check_waiting_takes_the_lock_at_once_and_a_dead_pids_marker_is_dropped(state):
    state.mkdir()
    (state / "heavy-wait.999999999.1").write_text("dead")
    assert journal.heavy_waiters() == 0 and not list(state.glob("heavy-wait.*"))
    with journal.heavy("the dev build", yields=True):
        assert (state / "heavy.lock").read_text().endswith("the dev build")


def test_the_guards_rung_runs_while_a_dev_build_holds_the_heavy_lock(state, tmp_path):
    """speed batch 3: the guards waited 65 min behind a dev build on 2026-11-03; now they never wait on the heavy lock."""
    import threading
    (tmp_path / "ci").mkdir()
    (tmp_path / "ci" / "x_ok.py").write_text("pass\n")
    out = {}
    with journal.heavy("a dev build"):
        t = threading.Thread(target=lambda: out.update(r=check_tool.guards(tmp_path, check_tool.Config(guard_glob="ci/x_*.py", min_guards=1))))
        t.start()
        t.join(30)
        assert not t.is_alive(), "the guards rung waited on the heavy lock"
    assert out["r"]["ok"] and [x["name"] for x in out["r"]["results"]] == ["x_ok"]



def test_a_manual_hold_is_a_live_builder_heavy_holder_and_a_dead_one_is_none(tmp_path, monkeypatch):
    """Owner 2026-11-06: the loop asks whether the person holds the heavy lock (`builder heavy -- ...`); a check's own hold or a dead pid is not."""
    import os
    from fichero_builder import journal
    monkeypatch.setattr(journal, "STATE", tmp_path)
    assert journal.manual_hold() == ""
    (tmp_path / "heavy.lock").write_text(f"{os.getpid()} heavy: sleep 86400")
    assert journal.manual_hold().endswith("heavy: sleep 86400")
    (tmp_path / "heavy.lock").write_text(f"{os.getpid()} xcodebuild (the build rung)")
    assert journal.manual_hold() == "", "a rung's own hold is not the person's"
    (tmp_path / "heavy.lock").write_text("999999 heavy: sleep 86400")
    assert journal.manual_hold() == "", "a dead holder is no hold"


def _fit(name, **kw):
    return {"runner": name, "reachable": True, "cores": 8, "load": 2.0, "free_ram_gb": 10.0, "free_gb": 50.0, "at": 1000.0, **kw}


def test_ladder_slots_are_the_sum_of_runners_under_the_load_and_memory_limits_and_parallel_is_a_ceiling():
    """local.flow.check-slots-from-runners: a fit runner gives slots_per_runner; parallel caps the sum; none fit is one ladder here."""
    from fichero_builder import check_tool
    cfg = check_tool.Config(remotes=("air:~/g", "imac:~/g", "imac:~/g2"), parallel=4, slots_per_runner=1)
    rows = {n: _fit(n) for n in cfg.remotes}
    assert check_tool.runner_slots(rows, cfg, 1010.0, 30)[0] == 3
    assert check_tool.runner_slots(rows, check_tool.Config(remotes=cfg.remotes, parallel=2), 1010.0, 30)[0] == 2, "parallel is a ceiling"
    assert check_tool.runner_slots(rows, check_tool.Config(remotes=cfg.remotes, parallel=9, slots_per_runner=2), 1010.0, 30)[0] == 6
    rows["imac:~/g"] = _fit("imac:~/g", free_ram_gb=1.0)
    n, why = check_tool.runner_slots(rows, cfg, 1010.0, 30)
    assert n == 2 and "free memory" in why["imac:~/g"]
    assert check_tool.runner_slots({}, cfg, 1010.0, 30)[0] == 1, "no runner counted: one ladder on the loop's machine"


def test_a_runner_over_its_load_or_with_a_stale_row_gives_no_slot_and_one_slots_row_says_why(tmp_path, monkeypatch):
    from fichero_builder import queue, work
    monkeypatch.setattr(journal, "STATE", tmp_path / "s")
    monkeypatch.setattr(queue, "RUNNERS", {})
    monkeypatch.setattr(queue, "PROBING", [None])
    monkeypatch.setattr(queue, "SLOT_WHY", [None])
    monkeypatch.setattr(work, "SLOTS", [0])
    (tmp_path / "harness.toml").write_text('[check]\nslots_from_runners = true\nparallel = 4\nremote = ["air:~/g", "imac:~/g"]\n')
    probe = {"air:~/g": dict(_fit("air:~/g"), load=20.0), "imac:~/g": _fit("imac:~/g")}
    for name in probe:
        probe[name].pop("at")
    assert queue.count_slots(tmp_path, probe=lambda n: dict(probe[n])) == 1 and work.SLOTS[0] == 1
    assert queue.count_slots(tmp_path, probe=lambda n: dict(probe[n])) == 1
    rows = [r for r in journal.read() if r["event"] == "slots"]
    assert len(rows) == 1 and "load 20 on 8 cores" in rows[0]["runners"]["air:~/g"] and rows[0]["runners"]["imac:~/g"] == "counts 1"
    assert len([r for r in journal.read() if r["event"] == "runner"]) == 4, "one runner row a host a tick"
    import time
    n = queue.count_slots(tmp_path, probe=lambda n: dict(probe[n]), now=time.time() + 120)
    assert n == 1 and "no row in three ticks" in [r for r in journal.read() if r["event"] == "slots"][-1]["runners"]["imac:~/g"]
    (tmp_path / "harness.toml").write_text('[check]\nparallel = 4\n')
    assert queue.count_slots(tmp_path) == 0 and work.SLOTS[0] == 0, "off: [check].parallel, as before"


def test_a_train_waiting_for_the_build_lock_builds_before_a_lane_that_waited_longer(state, monkeypatch, tmp_path):
    """local.train.build-lock-first: the lane's build rung waits first, the train second; the train builds first."""
    import fcntl
    import threading
    import time
    monkeypatch.setattr(check_tool, "BUILD_YIELD_S", 0.05)
    cfg = check_tool.Config(build_lock=str(tmp_path / "build.lock"))
    order = []
    holder = open(tmp_path / "build.lock", "a")
    fcntl.flock(holder, fcntl.LOCK_EX)

    def take(who, train):
        with check_tool.build_lock(cfg, train=train):
            order.append(who)
            time.sleep(0.1)
    lane = threading.Thread(target=take, args=("lane", False))
    lane.start()
    time.sleep(0.2)
    tr = threading.Thread(target=take, args=("train", True))
    tr.start()
    for _ in range(100):
        if list(tmp_path.glob("build.lock.train-*")):
            break
        time.sleep(0.02)
    holder.close()
    lane.join(5), tr.join(5)
    assert order == ["train", "lane"]
    assert not list(tmp_path.glob("build.lock.train-*")), "the train's wait file goes with its turn"
    assert any(r.get("state") == "build-lock-yield" for r in journal.read())


def test_a_second_train_sees_the_build_runner_busy_while_a_build_holds_the_lock(state, tmp_path):
    """local.train.build-lock-first: Procs.build_free is the build lock's real state."""
    import fcntl
    cfg = check_tool.Config(build_lock=str(tmp_path / "build.lock"))
    assert check_tool.build_lock_free(cfg)
    with check_tool.build_lock(cfg, train=False):
        assert not check_tool.build_lock_free(cfg)
    assert check_tool.build_lock_free(cfg)
    f = open(tmp_path / "build.lock", "a")
    fcntl.flock(f, fcntl.LOCK_EX)
    assert not check_tool.build_lock_free(cfg)
    f.close()
    assert check_tool.build_lock_free(check_tool.Config()), "no build lock: always free"


def test_the_slot_count_reads_the_pinned_check_and_probes_a_host_with_two_gate_dirs_once(tmp_path, monkeypatch):
    from fichero_builder import land_tool, queue, work
    monkeypatch.setattr(journal, "STATE", tmp_path / "s")
    monkeypatch.setattr(queue, "RUNNERS", {})
    monkeypatch.setattr(queue, "PROBING", [None])
    monkeypatch.setattr(queue, "SLOT_WHY", [None])
    monkeypatch.setattr(work, "SLOTS", [0])
    monkeypatch.setattr(land_tool, "resolve_branch", lambda repo, branch: "abcdef0123")
    live = tmp_path / "live"
    pin = tmp_path / "pins" / "pinned-abcdef0"
    live.mkdir(), pin.mkdir(parents=True)
    (live / "harness.toml").write_text(f'[land]\nbranch = "integration"\npinned_dir = "{tmp_path / "pins"}"\n[check]\nengine_repo = "/r"\nparallel = 1\n')
    (pin / "harness.toml").write_text('[check]\nslots_from_runners = true\nparallel = 4\nremote = ["imac:~/g1", "imac:~/g2", "air:~/g"]\n')
    seen = []
    n = queue.count_slots(live, probe=lambda name: seen.append(name) or {k: v for k, v in _fit(name).items() if k != "at"})
    assert seen == ["imac:~/g1", "air:~/g"], "one probe a host"
    assert n == 3 and set(queue.RUNNERS) == {"imac:~/g1", "imac:~/g2", "air:~/g"}, "the pinned [check]: on, parallel 4; each dir counts"


def test_an_unreadable_rules_file_keeps_the_last_slot_count_with_one_row_and_never_raises(tmp_path, monkeypatch):
    from fichero_builder import queue, work
    monkeypatch.setattr(journal, "STATE", tmp_path / "s")
    monkeypatch.setattr(queue, "SLOT_WHY", [None])
    monkeypatch.setattr(work, "SLOTS", [3])
    (tmp_path / "harness.toml").write_text("[check\nbroken")
    assert queue.count_slots(tmp_path) == 3 and queue.count_slots(tmp_path) == 3 and work.SLOTS[0] == 3
    assert len([r for r in journal.read() if r.get("state") == "slots-cfg-refused"]) == 1
