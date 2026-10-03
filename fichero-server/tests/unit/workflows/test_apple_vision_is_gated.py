"""Apple Vision runs at most two pages at once, and a page that never returns fails by name (#5392).

WHY: a 104-photo notebook folder fanned out one Vision call per file at once; Apple's text
recogniser deadlocked (four threads in VNRecognizeTextRequest, 0% CPU) and the run stayed
"running" forever, unstoppable. Calls now pass an engine-wide gate of two, and each has a deadline,
so a stuck page fails with AppleVisionTimeout and the rest of the run finishes.
"""
from __future__ import annotations

import asyncio
import threading
import time

import pytest

from fichero_server.workflows.tools import vision_base as vb


def test_twenty_fanned_out_pages_never_run_more_than_two_at_once(monkeypatch):
    lock, state = threading.Lock(), {"now": 0, "peak": 0}

    def fake_ocr(path, language="en"):
        with lock:
            state["now"] += 1
            state["peak"] = max(state["peak"], state["now"])
        time.sleep(0.05)
        with lock:
            state["now"] -= 1
        return path

    monkeypatch.setattr(vb, "apple_vision_ocr", fake_ocr)

    async def fan_out():
        return await asyncio.gather(*(vb.apple_vision_ocr_async(f"p{i}") for i in range(20)))

    assert asyncio.run(fan_out()) == [f"p{i}" for i in range(20)]
    assert state["peak"] <= vb.APPLE_VISION_CONCURRENCY


def test_a_page_that_never_returns_fails_by_name(monkeypatch):
    release = threading.Event()
    monkeypatch.setattr(vb, "apple_vision_ocr", lambda path, language="en": release.wait(5))
    monkeypatch.setattr(vb, "_apple_vision_deadline", lambda: 0.2)
    with pytest.raises(vb.AppleVisionTimeout, match="did not finish this page"):
        asyncio.run(vb.apple_vision_ocr_async("stuck.jpg"))
    release.set()
