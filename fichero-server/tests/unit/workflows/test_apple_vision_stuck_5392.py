"""A recogniser that never returns must not take the gate with it (#5392, `compute.apple-vision.bounded-and-deadlined`).

The call that timed out is abandoned, but Apple's recogniser still holds its thread. It used to keep its gate slot too, so two
such calls closed the gate and every later read, the app's own included, waited a whole deadline and failed (the defaults matrix,
2026-10-21). Now the timed-out call FREES its slot and its page fails by name; the abandoned threads are counted, and past a small
ceiling a new call fails fast, saying Apple Vision is stuck until the engine restarts."""
from __future__ import annotations

import asyncio
import threading
import time

import pytest

from fichero_server.execution import throttle
from fichero_server.workflows.tools import vision_base as vb

GB = 1024**3
DEADLINE = 0.3


@pytest.fixture(autouse=True)
def _gate(monkeypatch):
    monkeypatch.setattr(throttle, "memory_available_bytes", lambda: 16 * GB)
    monkeypatch.setattr(throttle, "memory_pressure_level", lambda: 1)
    monkeypatch.setattr(vb, "_apple_vision_deadline", lambda: DEADLINE)
    never = threading.Event()  # a recogniser that never returns, until the test lets it go

    def recogniser(path, language="en"):
        if path.startswith("stuck"):
            never.wait(30)
        return f"read {path}"

    monkeypatch.setattr(vb, "apple_vision_ocr", recogniser)
    yield
    never.set()
    for _ in range(80):
        if vb._APPLE_VISION_GATE.in_flight == 0:
            break
        time.sleep(0.05)


def _read(path: str) -> str:
    return asyncio.run(vb.apple_vision_ocr_async(path))


def _stuck_page_fails_by_name(path: str) -> float:
    began = time.monotonic()
    with pytest.raises(vb.AppleVisionTimeout):
        _read(path)
    return time.monotonic() - began


def test_a_page_that_never_returns_fails_within_the_timeout_and_the_next_call_still_gets_a_slot():
    # two stuck pages: with the bound at two, the old gate was now closed for good
    for n in range(vb.APPLE_VISION_CONCURRENCY):
        assert _stuck_page_fails_by_name(f"stuck{n}") < DEADLINE + 1.0
    began = time.monotonic()
    assert _read("fine") == "read fine"
    assert time.monotonic() - began < DEADLINE, "a later read waited for a slot a dead call still held"


def test_past_the_ceiling_a_call_fails_fast_saying_apple_vision_is_stuck():
    for n in range(vb.APPLE_VISION_STUCK_CEILING):
        _stuck_page_fails_by_name(f"stuck{n}")
    began = time.monotonic()
    with pytest.raises(vb.AppleVisionStuck) as refused:
        _read("fine")
    assert time.monotonic() - began < DEADLINE / 2, "it waited for a deadline instead of failing at once"
    words = str(refused.value).lower()
    assert "stuck" in words and "restart" in words
    assert isinstance(refused.value, vb.AppleVisionTimeout)  # every handler that names the timeout still catches it
