"""One rule for the Mac being in use, a build, battery, memory and heat, applied by every caller (#5819, owner ruling A).

Spec: docs/contributor_manual/specs/ui/activity-and-automatic-work.md (`activity.throttle.use-means-slower`).
A person's work goes flat out and only battery slows it; background work is slowed (lowest priority) by use and by a
build, and held by battery, memory and heat; memory and heat hold everything. The callers agree because they all ask
`throttle.decide` / `throttle.why_wait`.
"""
from __future__ import annotations

import re
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from fichero_server.core import compute_preferences as prefs
from fichero_server.execution import jobs, throttle
from fichero_server.recipes import regions


@pytest.fixture
def mac(monkeypatch):
    state = {"build": False, "idle": 600.0, "battery": False, "pressure": 1, "thermal": 0, "sleeps": []}
    monkeypatch.setenv("FICHERO_JOB_THROTTLE", "1")
    monkeypatch.delenv("FICHERO_COMPUTE_PRIORITY", raising=False)
    monkeypatch.setattr(throttle, "memory_pressure_level", lambda: state["pressure"])
    monkeypatch.setattr(throttle, "memory_available_bytes", lambda: 64 * 1024**3)
    monkeypatch.setattr(throttle, "thermal_state_level", lambda: state["thermal"])
    monkeypatch.setattr(throttle, "battery_or_low_power", lambda: state["battery"])
    monkeypatch.setattr(throttle, "seconds_since_input", lambda: state["idle"])
    monkeypatch.setattr(throttle, "a_build_is_running", lambda: throttle.BUILD_REASON if state["build"] else None)
    monkeypatch.setattr(prefs, "stored_preferences", lambda: {"priority": "balanced", "device": "auto"})
    return state


#: reason -> how to switch it on, and what each kind of work gets: (action, priority as the pages see it)
REASONS = {
    "in use": ({"idle": 1.0}, {True: ("go", "fast"), False: ("slow", "background")}),
    "build": ({"build": True}, {True: ("go", "fast"), False: ("slow", "background")}),
    "battery": ({"battery": True}, {True: ("slow", "balanced"), False: ("hold", "background")}),
    "memory": ({"pressure": 4}, {True: ("hold", "background"), False: ("hold", "background")}),
    "heat": ({"thermal": 2}, {True: ("hold", "background"), False: ("hold", "background")}),
}


@pytest.mark.parametrize("person", [True, False], ids=["person", "background"])
@pytest.mark.parametrize("reason", list(REASONS))
def test_every_caller_gives_the_same_hold_slow_or_fast_answer(mac, monkeypatch, tmp_path, reason, person):
    change, expected = REASONS[reason]
    mac.update(change)
    action, priority = expected[person]

    decision = throttle.decide(person)  # the rule itself
    assert (decision.action, decision.priority) == (action, priority)
    # why_wait (the lane, derivatives, training, the stall watchdog, log tidy) answers only the holds
    assert (throttle.why_wait(person_waiting=person) is not None) == (action == "hold")
    # Kraken's pages: fast, the person's own setting for balanced, the lowest for background
    chosen = prefs.priority_for(person)
    assert chosen == priority  # the person's own setting is "balanced" here, so balanced reads as itself
    # the Activity popover's line is the holds
    assert (throttle.machine_state()["why_wait"] is not None) == (throttle.why_wait() is not None)

    # Find Lines: hold waits (a 5 s poll), slow yields once per page, go does not sleep
    monkeypatch.setattr(jobs, "person_waits_on", lambda _db, _id: person)
    sleeps = []

    def sleep(seconds):
        sleeps.append(seconds)
        if action == "hold":  # the signal clears while it waits
            mac.update(idle=600.0, build=False, battery=False, pressure=1, thermal=0)

    monkeypatch.setattr(regions.time, "sleep", sleep)
    db = SimpleNamespace(path=tmp_path / "lib" / "x.duckdb",
                         get=lambda *_a: SimpleNamespace(path=str(tmp_path / "none.jpg"), id="d", name="n"))
    regions.find_regions(db, ["a", "b"], "run", "m", provider="yolo", say=lambda _w: None)
    if action == "go":
        assert sleeps == []
    elif action == "slow":
        assert sleeps == [regions.SLOWER_YIELD_SECONDS] * 2
    else:
        assert sleeps == [regions.WAIT_POLL_SECONDS]


def test_no_module_but_the_throttle_reads_a_probe_itself():
    """The rule has one home: callers ask `decide`/`why_wait`, never a probe (a local copy of the rule drifts)."""
    probe = re.compile(r"\b(?:throttle\.)?(on_battery|a_build_is_running|mac_is_in_use|memory_is_tight|mac_is_hot)\(")
    root = Path(__file__).resolve().parents[3] / "src" / "fichero_server"
    offenders = []
    for path in root.rglob("*.py"):
        if path.name == "throttle.py":
            continue
        for number, line in enumerate(path.read_text().splitlines(), 1):
            if probe.search(line) and not line.lstrip().startswith(("#", '"""')):
                offenders.append(f"{path.relative_to(root)}:{number}: {line.strip()}")
    assert not offenders, offenders


# --- the lane scheduler agrees ------------------------------------------------------------------------------------


@pytest.fixture
def lane(monkeypatch, mac):
    ran = threading.Event()
    kind = "throttle-probe-5819"
    monkeypatch.setitem(jobs.KINDS, kind, jobs.Kind(run=lambda db, subject: ran.set(), model=None, lane="local-ml",
                                                   name="Probe"))
    monkeypatch.setattr(jobs, "THROTTLE_LOOK_AGAIN_SECONDS", 0.05)
    return SimpleNamespace(kind=kind, ran=ran)


def test_background_lane_work_is_picked_under_a_build_and_in_use(db, lane, mac):
    mac.update(build=True, idle=1.0)
    jobs.enqueue(db, lane.kind, "page")
    assert lane.ran.wait(30)  # picked and run, not held


def test_background_lane_work_is_held_on_battery_and_goes_when_it_clears(db, lane, mac):
    mac["battery"] = True
    job = jobs.enqueue(db, lane.kind, "page")
    time.sleep(0.5)
    assert not lane.ran.is_set()
    assert "battery" in (jobs.state_and_reason(db, job)[1] or "")
    mac["battery"] = False
    assert lane.ran.wait(30)


# --- review 275: who started the RUN decides, not the page's own row ('workflow' for every page) ----------------------


def _chain(db, root_started_by):
    """recipe job -> workflow run -> step -> page, as the recipe runner and the lane write them."""
    jobs._ensure(db)
    rows = [("recipe-1", "run-a-recipe", None, root_started_by), ("thread-1", "workflow", "recipe-1", "workflow"),
            ("thread-1:read", "workflow-step", "thread-1", "workflow"), ("page-1", "read-a-line", "thread-1:read", "workflow")]
    for job_id, kind, parent, who in rows:
        db.execute("INSERT INTO jobs (id, kind, subject, state, created_at, started_by, parent_id) "
                   "VALUES (?, ?, ?, 'running', now(), ?, ?)", [job_id, kind, job_id, who, parent])


def test_an_automatic_runs_pages_are_not_a_persons(db):
    _chain(db, "import")  # the recipe run an import starts by itself
    assert jobs.person_waits_on(db, "page-1") is False


@pytest.mark.parametrize("who", ["automatic", "sync", "kept export"])
def test_other_background_starters_are_not_a_persons(db, who):
    _chain(db, who)
    assert jobs.person_waits_on(db, "page-1") is False


@pytest.mark.parametrize("who", ["owner", "alice", "agent"])
def test_a_runs_the_person_started_has_persons_pages(db, who):
    _chain(db, who)
    assert jobs.person_waits_on(db, "page-1") is True


def test_a_watched_page_is_a_persons_whatever_started_the_run(db):
    _chain(db, "import")
    db.execute("UPDATE jobs SET watched = TRUE WHERE id = 'page-1'")  # a try's page
    assert jobs.person_waits_on(db, "page-1") is True


def test_an_automatic_runs_kraken_page_stays_balanced_and_a_started_ones_goes_fast(db, mac, monkeypatch):
    for who, expected in (("import", "balanced"), ("owner", "fast")):
        db.execute("DELETE FROM jobs")
        _chain(db, who)
        monkeypatch.setattr(jobs, "_current", SimpleNamespace(person=jobs.person_waits_on(db, "page-1")))
        assert prefs.priority_for(jobs.current_job_is_a_persons()) == expected


# --- review 276: every starter the engine writes is decided -----------------------------------------------------------


def test_every_literal_started_by_in_the_engine_is_decided_as_background_or_a_person():
    """A starter nobody decided went flat out and was not held on battery (schedule, trigger: review 276). Read the
    source: a new `started_by="x"` must be added to BACKGROUND_STARTERS or PERSON_STARTERS."""
    root = Path(__file__).resolve().parents[3] / "src" / "fichero_server"
    literal = re.compile(r"started_by\s*[=:]\s*(?:str\s*=\s*)?[\"']([a-z][a-z _-]*)[\"']")
    decided = set(jobs.BACKGROUND_STARTERS) | set(jobs.PERSON_STARTERS)
    found = {}
    for path in root.rglob("*.py"):
        for number, line in enumerate(path.read_text().splitlines(), 1):
            for who in literal.findall(line):
                found.setdefault(who, f"{path.relative_to(root)}:{number}")
    undecided = {who: where for who, where in found.items() if who not in decided}
    assert not undecided, undecided
    assert {"schedule", "trigger", "correction", "import", "sync", "kept export"} <= set(found)  # the scan sees them


@pytest.mark.parametrize("who", ["schedule", "trigger", "correction"])
def test_scheduled_triggered_and_correction_runs_are_background(db, who):
    _chain(db, who)
    assert jobs.person_waits_on(db, "page-1") is False
    assert throttle.decide(jobs.person_waits_on(db, "page-1")).action in ("go", "slow", "hold")
