"""Heavy local work waits while the Mac needs itself (`activity.throttle.power-heat-memory`, #5358).

Spec: docs/contributor_manual/specs/ui/activity-and-automatic-work.md, section 4; and
compute/jobs-and-fine-tuning.md `compute.tune.on-this-mac`. The maintainer's Mac beachballed with
a heavy job running while he worked. A background model job now waits on memory pressure, heat,
battery and the person using the Mac, says which on its row, and goes on when it clears.

The signals are faked here (the suite turns the throttle off by default: the test machine is
often in use); the probes' readings of the real signals are pinned at the end.
"""
from __future__ import annotations

import time

import pytest

from fichero_server.execution import jobs, throttle


@pytest.fixture
def signals(monkeypatch):
    """Switchable fake signals, in the throttle's own order and with its own exemptions."""
    state = {"memory": False, "hot": False, "battery": False, "in_use": False}
    monkeypatch.setenv("FICHERO_JOB_THROTTLE", "1")
    monkeypatch.setattr(jobs, "THROTTLE_LOOK_AGAIN_SECONDS", 0.05)
    monkeypatch.setattr(throttle, "PROBES", [
        (lambda: "Waiting: memory is tight" if state["memory"] else None, True),
        (lambda: "Waiting: the Mac is hot" if state["hot"] else None, True),
        (lambda: "Waiting: the Mac is on battery" if state["battery"] else None, False),
        (lambda: "Waiting: you're using the Mac" if state["in_use"] else None, False),
    ])
    return state


def _reason(db, subject):
    row = db.execute_fetchone("SELECT state, reason FROM jobs WHERE subject = ?", [subject])
    return row


def _wait_for(predicate, seconds=30.0):
    deadline = time.time() + seconds
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


def test_activity_throttle_power_heat_memory__waits_while_memory_is_tight_and_says_so(db, signals, monkeypatch):
    """Behaviour `activity.throttle.power-heat-memory`: "background lanes slow or wait in Low Power Mode, on low
    battery, under serious thermal state or memory pressure, and say so; no setting." Through the real
    scheduler, with the Mac's signals faked.

    WHY: starting a model under memory pressure is what makes the Mac swap and beachball. The
    job waits, its row says why (not a spinner), and it runs once the pressure eases."""
    ran = []
    monkeypatch.setitem(jobs.KINDS, "t-heavy", jobs.Kind(run=lambda db, s: ran.append(s), model="embedder"))
    signals["memory"] = True
    jobs.enqueue(db, "t-heavy", "page")
    assert _wait_for(lambda: _reason(db, "page") == ("waiting", "Waiting: memory is tight"))
    time.sleep(0.2)
    assert ran == []

    signals["memory"] = False
    assert _wait_for(lambda: ran == ["page"])


@pytest.mark.parametrize("signal,reason", [
    ("hot", "Waiting: the Mac is hot"),
    ("battery", "Waiting: the Mac is on battery"),
    ("in_use", "Waiting: you're using the Mac"),
])
def test_activity_throttle_power_heat_memory__each_signal_says_its_own_reason(db, signals, monkeypatch, signal, reason):
    """Behaviour `activity.throttle.power-heat-memory`: "background lanes slow or wait in Low Power Mode, on low
    battery, under serious thermal state or memory pressure, and say so; no setting." Through the real
    scheduler, with the Mac's signals faked.

    WHY: the row must say which of the four is holding it, or "waiting" reads as stuck."""
    ran = []
    monkeypatch.setitem(jobs.KINDS, "t-heavy", jobs.Kind(run=lambda db, s: ran.append(s), model="embedder"))
    signals[signal] = True
    jobs.enqueue(db, "t-heavy", "page")
    assert _wait_for(lambda: _reason(db, "page") == ("waiting", reason))
    signals[signal] = False
    assert _wait_for(lambda: ran == ["page"])


def test_activity_throttle_watched_first__a_waited_for_page_runs_while_the_mac_is_in_use(db, signals, monkeypatch):
    """Behaviour `activity.throttle.watched-first`: "a job a person is waiting on goes first in its lane";
    with `activity.throttle.power-heat-memory` still holding it under memory pressure.

    WHY: the person pressed Run and is clicking around while it works; holding their page until
    they stop would stall exactly what they asked for. Memory pressure still holds it: that is
    what beachballs. And a background job held for "in use" must not stand in front of it."""
    ran = []
    monkeypatch.setitem(jobs.KINDS, "t-heavy", jobs.Kind(run=lambda db, s: ran.append(s), model="embedder"))
    signals["in_use"] = True
    jobs.enqueue(db, "t-heavy", "background")  # older, and held
    assert jobs.submit(db, "find-lines", "asked-for", model="kraken:blla", fn=lambda: "lines").result(30) == "lines"
    assert ran == []

    signals["memory"] = True
    waiting = jobs.submit(db, "find-lines", "under-pressure", model="kraken:blla", fn=lambda: "lines")
    assert _wait_for(lambda: _reason(db, "under-pressure") == ("waiting", "Waiting: memory is tight"))
    assert not waiting.done()
    signals["memory"] = False
    assert waiting.result(30) == "lines"


def test_activity_throttle_power_heat_memory__the_images_lane_is_not_held(db, test_package, signals, monkeypatch):
    """Behaviour `activity.throttle.power-heat-memory` applies to the heavy lane; thumbnails are a light lane.

    WHY: the throttle is for heavy model work; a thumbnail is a small decode on its own lane,
    and holding it would leave the grid grey while the person is looking at it."""
    from fichero_server.importers import derivatives
    from fichero_server.models import DocType, Document, FileType, Status

    signals["in_use"] = True
    monkeypatch.setattr(derivatives, "_thumbnail_stage", lambda doc_id, library: "thumb")
    monkeypatch.setattr(derivatives, "_embed_stage", lambda doc_id, library: None)
    monkeypatch.setattr(derivatives, "auto_nlp_enabled", lambda: False)
    doc = Document(name="a.md", doc_type=DocType.file, file_type=FileType.text, status=Status.pending,
                   page_content="text")
    db.save(doc)
    thumbnail = derivatives.queue_derivatives([doc], library_path=test_package)[0]
    assert thumbnail.result(30) == "thumb"


class TestTheProbesReadTheMac:
    """`activity.throttle.power-heat-memory`'s signals as read from the Mac. No surface: the signals are
    the operating system's; these pin each probe's reading of them."""

    def test_memory_from_what_is_free_and_the_kernels_critical_level(self, monkeypatch):
        """WHY (#5524): the throttle reads memory exactly as Kraken's guard does (`memory_short`): at
        least 2.5 GB available (free + inactive + speculative pages, what macOS can hand out) and
        pressure below CRITICAL. Holding at WARN parked a check for hours on a busy 16 GB Mac that had
        room, and a throttle that read only pressure released jobs the guard then failed."""
        import fichero_server.llm.kraken_runtime as kraken_runtime

        gb = 1024**3
        for free, level, tight in ((8 * gb, 1, False), (8 * gb, 2, False), (8 * gb, 4, True),
                                   (int(2.3 * gb), 1, True), (None, None, False), (None, 2, False)):
            monkeypatch.setattr(kraken_runtime, "_available_memory_bytes", lambda free=free: free)
            monkeypatch.setattr(kraken_runtime, "_memory_pressure_level", lambda level=level: level)
            reason = throttle.memory_is_tight()
            assert (reason is not None) == tight, (free, level, reason)
            if tight:
                assert reason.startswith(throttle.MEMORY_REASON), reason

    def test_in_use_from_seconds_since_the_last_input(self, monkeypatch):
        import Quartz

        for idle, expected in ((3.0, "Waiting: you're using the Mac"), (300.0, None)):
            monkeypatch.setattr(Quartz, "CGEventSourceSecondsSinceLastEventType", lambda *a, idle=idle: idle)
            assert throttle.mac_is_in_use() == expected

    def test_battery_from_pmset_and_low_power_mode(self, monkeypatch):
        import subprocess

        class Out:
            def __init__(self, stdout):
                self.stdout = stdout

        for text, expected in (("Now drawing from 'Battery Power'", "Waiting: the Mac is on battery"),
                               ("Now drawing from 'AC Power'", None)):
            monkeypatch.setattr(throttle, "_battery", None)
            monkeypatch.setattr(subprocess, "run", lambda *a, text_=text, **k: Out(text_))
            assert throttle.on_battery() == expected

    def test_a_signal_that_cannot_be_read_never_holds_work(self, monkeypatch):
        """WHY: a missing framework or a sandbox refusal must not park the queue for good."""
        import fichero_server.llm.kraken_runtime as kraken_runtime

        monkeypatch.setattr(kraken_runtime, "_memory_pressure_level", lambda: None)
        monkeypatch.setattr(kraken_runtime, "_available_memory_bytes", lambda: None)
        assert throttle.memory_is_tight() is None
        monkeypatch.setenv("FICHERO_JOB_THROTTLE", "0")
        monkeypatch.setattr(throttle, "PROBES", [(lambda: "Waiting: anything", True)])
        assert throttle.why_wait() is None
