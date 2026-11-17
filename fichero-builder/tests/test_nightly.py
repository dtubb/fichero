"""dev-workflows.run.nightly-build (#6665): the cutoff by lane median, the freeze candidate, the nightly's parts. A fake clock and fake
runners; nothing builds."""
from __future__ import annotations

from datetime import datetime

import pytest

from fichero_builder import journal, nightly, queue
from test_queue_verb import Fake, lane

CFG = nightly.Cfg((22, 0), (0, 0), "m4", "local", "local", "dev", 14336)


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "STATE", tmp_path / "s")
    for n in ("1.1", "1.2"):
        (tmp_path / f"b{n}").write_text(f"brief {n}")
    (tmp_path / "harness.toml").write_text('[check]\nengine_repo = "/e"\n[land]\nbranch = "integration"\n[loop]\nlanes = 1\nrounds = 1\n')
    return tmp_path


def _landed(lane_id, step, sent, landed):
    for ts, st in ((sent, "sent"), (landed, "landed")):
        journal.append("queue", lane=lane_id, step=step, state=st, detail="")
        rows = journal.read()
        rows[-1]["ts"] = ts
        journal.path().write_text("".join(__import__("json").dumps(r, sort_keys=True) + "\n" for r in rows))


def test_the_nightly_table_is_read_whole_and_a_missing_key_is_an_error():
    ok = {"no_new_steps_at": "22:00", "freeze_at": "00:00", "check_runner": "m4", "build_machine": "local", "smoke_machine": "local", "publish": "dev", "check_footprint_mb": 14336}
    assert nightly.load({"nightly": ok}) == CFG and nightly.load({}) is None
    with pytest.raises(ValueError, match="lacks smoke_machine"):
        nightly.load({"nightly": {k: v for k, v in ok.items() if k != "smoke_machine"}})
    with pytest.raises(ValueError, match="not HH:MM"):
        nightly.load({"nightly": {**ok, "freeze_at": "midnight"}})


def test_a_step_after_the_cutoff_starts_only_if_the_lanes_median_fits_before_the_freeze():
    at = lambda h, m: datetime(2026, 11, 17, h, m)  # noqa: E731
    assert nightly.hold_why(at(21, 59), CFG, lambda: 7200) == "", "before the cutoff nothing is held"
    assert nightly.hold_why(at(22, 0), CFG, lambda: 3600) == "" and nightly.hold_why(at(23, 0), CFG, lambda: 3600) == "", "it fits exactly"
    assert "does not fit before the freeze at 00:00" in nightly.hold_why(at(23, 1), CFG, lambda: 3600)
    assert "no landed step" in nightly.hold_why(at(22, 30), CFG, lambda: None)
    assert nightly.hold_why(datetime(2026, 11, 18, 0, 0), CFG, lambda: 9999) == "", "from the freeze on a step starts again"


def test_a_lanes_median_is_over_its_landed_steps_only(state):
    _landed("a", "1", "2026-11-17T10:00:00", "2026-11-17T10:10:00")
    _landed("a", "2", "2026-11-17T11:00:00", "2026-11-17T11:50:00")
    _landed("a", "3", "2026-11-17T12:00:00", "2026-11-17T12:20:00")
    _landed("b", "1", "2026-11-17T10:00:00", "2026-11-17T15:00:00")
    assert nightly.median_land_s(journal.read(), "a") == 20 * 60
    assert nightly.median_land_s(journal.read(), "none") is None


def test_the_loop_holds_a_new_step_after_the_cutoff_and_says_why_once(state):
    lane(state)
    _landed("lane-a", "0.1", "2026-11-17T10:00:00", "2026-11-17T11:30:00")
    fake = Fake()
    fake.procs.nightly, fake.procs.now = CFG, lambda: datetime(2026, 11, 17, 22, 40)
    queue.tick(fake.procs, {}, workers_n=1, push=True, out=lambda s: None)
    queue.tick(fake.procs, {}, workers_n=1, push=True, out=lambda s: None)
    assert fake.starts == [], "a 90 min median does not fit in the 80 min left"
    assert len([r for r in journal.read() if r.get("state") == "night-hold"]) == 1
    fake.procs.now = lambda: datetime(2026, 11, 17, 21, 0)
    queue.tick(fake.procs, {}, workers_n=1, push=True, out=lambda s: None)
    assert [s[1] for s in fake.starts] == ["1.1"], "before the cutoff the step starts"


class Night:
    def __init__(self, **rc):
        self.rc, self.calls, self.texts, self.alerts = rc, [], [], []
        self.runners = nightly.Runners(head=lambda: "f" * 40, check=self.part("check"), dmg=self.part("dmg"), smoke=self.part("smoke"),
                                       publish=self.part("publish"), text=self.texts.append, test_list=lambda sha: f"try {sha[:7]}")

    def part(self, name):
        def run(sha):
            self.calls.append((name, sha))
            return (self.rc.get(name, 0), f"{name} output\nlast {name}")
        return run


def test_at_the_freeze_the_integration_head_is_the_candidate_once_a_night(state):
    n = Night()
    before, at = datetime(2026, 11, 17, 23, 59), datetime(2026, 11, 18, 0, 0, 5)
    nightly.when_due(CFG, n.runners, before, n.alerts.append, None, [])
    assert n.calls == [], "not yet"
    nightly.when_due(CFG, n.runners, at, n.alerts.append, None, [])
    nightly.when_due(CFG, n.runners, datetime(2026, 11, 18, 0, 5), n.alerts.append, None, [])
    cands = [r for r in journal.read() if r["event"] == "nightly" and r["state"] == "candidate"]
    assert [(c["night"], c["sha"]) for c in cands] == [("2026-11-17", "f" * 40)], "one candidate for the night of the 17th"
    assert sorted(c[0] for c in n.calls).count("check") == 1
    nightly.when_due(CFG, n.runners, datetime(2026, 11, 19, 10, 0), n.alerts.append, None, [])
    assert len([r for r in journal.read() if r.get("state") == "candidate"]) == 1, "a freeze long past is not started late"


def test_the_nightly_publishes_and_texts_only_when_every_part_is_green(state):
    n = Night()
    assert nightly.run_night(CFG, n.runners, "a" * 40, "2026-11-17", n.alerts.append) is True
    assert [c[0] for c in n.calls][-2:] == ["smoke", "publish"] and {c[0] for c in n.calls[:2]} == {"check", "dmg"}
    assert n.texts == ["try aaaaaaa"] and n.alerts == []


@pytest.mark.parametrize("red, published", [("check", ()), ("dmg", ()), ("smoke", ("check", "dmg")), ("publish", ("check", "dmg", "smoke"))])
def test_a_red_part_publishes_nothing_and_raises_one_alert_naming_it(state, red, published):
    n = Night(**{red: 1})
    assert nightly.run_night(CFG, n.runners, "a" * 40, "2026-11-17", n.alerts.append) is False
    assert len(n.alerts) == 1 and f"red at {red}" in n.alerts[0] and f"last {red}" in n.alerts[0]
    assert n.texts == [] and ("publish" in [c[0] for c in n.calls]) == (red == "publish")


def test_the_parts_run_in_clean_trees_at_the_frozen_sha_and_auto_notes_runs_before_the_dmg(monkeypatch, tmp_path):
    seen = []
    monkeypatch.setattr(nightly, "_on", lambda machine, script, timeout: seen.append((machine, script)) or (0, ""))
    monkeypatch.setattr(nightly.subprocess, "run", lambda *a, **k: type("P", (), {"returncode": 0, "stdout": "git@x:o/r.git\n", "stderr": ""})())
    r = nightly.real_runners(tmp_path, CFG, "integration", tmp_path / "s")
    r.check("c" * 40), r.dmg("c" * 40)
    check, dmg = seen
    assert check[0] == "m4" and "git clone -q --no-checkout git@x:o/r.git" in check[1] and f"checkout -q {'c' * 40}" in check[1]
    assert "GATE_FOOTPRINT_MB=14336 PYTHONPATH=. python3 -m fichero_builder verify-all --full" in check[1], "the footprint rides the verify command"
    assert "verify-all --full" in check[1] and str(tmp_path) not in check[1].split("verify-all")[0], "never the loop's checkout"
    assert dmg[0] == "local" and f"checkout -q {'c' * 40}" in dmg[1]
    assert dmg[1].index("release_guard.py auto-notes") < dmg[1].index("release-all.sh --dev --skip-testflight")


def test_each_part_has_one_fixed_clone_dir_and_a_machines_dir_is_used(monkeypatch, tmp_path):
    """No per-process /tmp name: the local parts clone under the state dir, a `host:dir` machine under its dir, a bare host under
    ~/fichero-nightly; the next night replaces the clone (rm -rf first)."""
    seen = []
    monkeypatch.setattr(nightly, "_on", lambda machine, script, timeout: seen.append((machine, script)) or (0, ""))
    monkeypatch.setattr(nightly.subprocess, "run", lambda *a, **k: type("P", (), {"returncode": 0, "stdout": "git@x:o/r.git\n", "stderr": ""})())
    cfg = nightly.Cfg((22, 0), (0, 0), "imac:~/code/fichero-worktrees/nightly", "local", "local", "dev", 14336)
    r = nightly.real_runners(tmp_path, cfg, "integration", tmp_path / "s")
    r.check("c" * 40), r.dmg("c" * 40), r.smoke("c" * 40)
    check, dmg, smoke = (x[1] for x in seen)
    assert check.startswith('rm -rf "$HOME"/code/fichero-worktrees/nightly/check &&') and "fichero-nightly-" not in check
    assert dmg.startswith(f"rm -rf {tmp_path}/s/nightly/dmg &&") and f"cd {tmp_path}/s/nightly/dmg &&" in smoke, "the smoke runs in the DMG's tree"


def test_a_smoke_on_another_machine_clones_the_sha_and_copies_the_built_app_over(monkeypatch, tmp_path):
    seen = []
    monkeypatch.setattr(nightly, "_on", lambda machine, script, timeout: seen.append((machine, script)) or (0, ""))
    monkeypatch.setattr(nightly.subprocess, "run", lambda *a, **k: type("P", (), {"returncode": 0, "stdout": "git@x:o/r.git\n", "stderr": ""})())
    cfg = nightly.Cfg((22, 0), (0, 0), "m4", "local", "m4", "dev", 14336)
    nightly.real_runners(tmp_path, cfg, "integration", tmp_path / "s").smoke("c" * 40)
    (m1, s1), (m2, s2), (m3, s3) = seen
    assert (m1, m2, m3) == ("m4", "local", "m4") and f"checkout -q {'c' * 40}" in s1
    assert s2.startswith("rsync -a --delete") and "Fichero.app/ m4:fichero-nightly/smoke/fichero/build/xcode/Products/Release/Fichero.app/" in s2
    assert "scripts/smoke-release-embedded-backend.sh" in s3
    with pytest.raises(ValueError, match="needs a local build_machine"):
        nightly.real_runners(tmp_path, nightly.Cfg((22, 0), (0, 0), "m4", "imac", "m4", "dev", 1), "integration", tmp_path)
