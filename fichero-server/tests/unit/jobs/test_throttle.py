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


def test_a_background_model_job_waits_while_memory_is_tight_says_so_and_then_runs(db, signals, monkeypatch):
    """WHY: starting a model under memory pressure is what makes the Mac swap and beachball. The
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
def test_each_signal_holds_background_work_with_its_own_reason(db, signals, monkeypatch, signal, reason):
    """WHY: the row must say which of the four is holding it, or "waiting" reads as stuck."""
    ran = []
    monkeypatch.setitem(jobs.KINDS, "t-heavy", jobs.Kind(run=lambda db, s: ran.append(s), model="embedder"))
    signals[signal] = True
    jobs.enqueue(db, "t-heavy", "page")
    assert _wait_for(lambda: _reason(db, "page") == ("waiting", reason))
    signals[signal] = False
    assert _wait_for(lambda: ran == ["page"])


def test_a_page_someone_waits_for_runs_while_they_use_the_mac_but_not_under_memory_pressure(db, signals, monkeypatch):
    """WHY: the person pressed Run and is clicking around while it works; holding their page until
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


def test_thumbnails_are_not_held(db, test_package, signals, monkeypatch):
    """WHY: the throttle is for heavy model work; a thumbnail is a small decode on its own lane,
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
    def test_memory_pressure_from_the_kernels_level(self, monkeypatch):
        """WHY: macOS's own pressure level (2 warn, 4 critical) is the signal that predicts a
        beachball; free memory alone does not (macOS keeps little memory free on purpose)."""
        import fichero_server.llm.kraken_runtime as kraken_runtime

        for level, expected in ((1, None), (2, "Waiting: memory is tight"), (4, "Waiting: memory is tight"),
                                (None, None)):
            monkeypatch.setattr(kraken_runtime, "_memory_pressure_level", lambda level=level: level)
            assert throttle.memory_is_tight() == expected

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
        assert throttle.memory_is_tight() is None
        monkeypatch.setenv("FICHERO_JOB_THROTTLE", "0")
        monkeypatch.setattr(throttle, "PROBES", [(lambda: "Waiting: anything", True)])
        assert throttle.why_wait() is None
