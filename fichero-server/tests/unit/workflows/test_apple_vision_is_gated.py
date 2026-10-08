"""Apple Vision reads at most two pages at once (one when memory is tight), and a page that never
returns fails by name (#5392, `compute.apple-vision.bounded-and-deadlined`).

WHY: a 104-photo notebook folder fanned out one Vision call per file at once; Apple's text
recogniser deadlocked (four threads in VNRecognizeTextRequest, 0% CPU) and the run stayed
"running" forever, unstoppable. Calls now pass an engine-wide gate -- the smaller of two and what
memory allows (`throttle.memory_short`, #5537) -- and each has a deadline, so a stuck page fails
with AppleVisionTimeout and the rest of the run finishes.

The stub below deadlocks the way Vision did: a call entered while the gate's bound is already in
flight blocks forever. Through the real fan-out (`process_vision`, every file at once) the run
finishes only because the gate never lets that happen; a regression fails on the short deadline
instead of hanging the suite.
"""
from __future__ import annotations

import asyncio
import threading
import time
from pathlib import Path

import pytest

from fichero_server.execution import throttle
from fichero_server.llm import LLMConfig
from fichero_server.workflows.tools import vision_base as vb

GB = 1024**3


@pytest.fixture(autouse=True)
def _plenty_of_memory(monkeypatch):
    """Memory readings are injected, never the machine's: 16 GB free, pressure normal."""
    monkeypatch.setattr(throttle, "memory_available_bytes", lambda: 16 * GB)
    monkeypatch.setattr(throttle, "memory_pressure_level", lambda: 1)
    monkeypatch.setattr(vb, "_apple_vision_deadline", lambda: 5.0)
    import fichero_server.workflows.builder as builder

    builder._vision_fan_out_sem = None  # the fan-out's semaphore belongs to one event loop
    yield
    builder._vision_fan_out_sem = None


class _VisionThatDeadlocks:
    """A stand-in for VNRecognizeTextRequest: entered beyond `bound` at once, it blocks forever
    (until the test lets go), as four concurrent requests did in #5392."""

    def __init__(self, bound: int, hold: float = 0.05) -> None:
        self.bound, self.hold = bound, hold
        self.lock, self.now, self.peak, self.calls = threading.Lock(), 0, 0, 0
        self.stuck = threading.Event()

    def __call__(self, path, language="en", reference_text=None):
        with self.lock:
            self.now += 1
            self.calls += 1
            self.peak = max(self.peak, self.now)
            over = self.now > self.bound
        try:
            if over:
                self.stuck.wait(30)  # the deadlock; released at the test's end
            time.sleep(self.hold)
            return vb.VisionOCRResult(text=f"text of {Path(path).name}", line_boxes=[], word_boxes=[])
        finally:
            with self.lock:
                self.now -= 1


def _photos(tmp_path, n):
    paths = []
    for i in range(n):
        path = tmp_path / f"photo{i:03d}.jpg"
        path.write_bytes(b"jpeg")
        paths.append(str(path))
    return paths


async def _transcribe_folder(files):
    tool = vb.VisionToolConfig(artifact_type="transcription", update_page_content=False,
                               trigger_embedding=False, supports_apple_vision=True,
                               skip_if_artifact_exists=False)
    return await vb.process_vision(
        files=files, documents=[], prompt="Transcribe.",
        llm_config=LLMConfig(provider="apple", model="apple-vision"), library_path="",
        task_id=None, tool_config=tool, vision_mode="apple", save_to_db=False)


def _run_folder(monkeypatch, tmp_path, vision, n=12):
    monkeypatch.setattr(vb, "apple_vision_ocr_with_geometry", vision)
    files = _photos(tmp_path, n)
    started = time.monotonic()
    try:
        result = asyncio.run(_transcribe_folder(files))
    finally:
        vision.stuck.set()
    return files, result, time.monotonic() - started


def test_a_fanned_out_folder_reads_two_at_once_and_never_deadlocks(monkeypatch, tmp_path):
    vision = _VisionThatDeadlocks(bound=vb.APPLE_VISION_CONCURRENCY)
    files, result, elapsed = _run_folder(monkeypatch, tmp_path, vision)

    assert result["texts"] == [f"text of {Path(f).name}" for f in files]
    assert vision.peak == vb.APPLE_VISION_CONCURRENCY == 2
    assert elapsed < 4.0, f"the folder took {elapsed:.1f}s; a page waited on the deadlock"


def test_memory_short_reads_one_page_at_a_time(monkeypatch, tmp_path):
    """The maintainer's rule: concurrency follows measured memory. Short of memory (the same
    `throttle.memory_short` every local model asks), the second page waits for the first."""
    monkeypatch.setattr(throttle, "memory_available_bytes", lambda: GB // 2)
    assert vb.apple_vision_reads_at_once() == 1
    vision = _VisionThatDeadlocks(bound=1, hold=0.02)
    files, result, _ = _run_folder(monkeypatch, tmp_path, vision, n=6)

    assert result["texts"] == [f"text of {Path(f).name}" for f in files]
    assert vision.peak == 1


def test_critical_pressure_also_reads_one_at_a_time(monkeypatch):
    monkeypatch.setattr(throttle, "memory_pressure_level", lambda: 4)
    assert vb.apple_vision_reads_at_once() == 1


def test_a_stuck_page_fails_by_name_and_the_folder_finishes(monkeypatch, tmp_path):
    release = threading.Event()

    def vision(path, language="en", reference_text=None):
        if Path(path).name == "photo002.jpg":
            release.wait(30)  # Apple's recogniser never returns on this page
        return vb.VisionOCRResult(text=f"text of {Path(path).name}", line_boxes=[], word_boxes=[])

    monkeypatch.setattr(vb, "apple_vision_ocr_with_geometry", vision)
    monkeypatch.setattr(vb, "_apple_vision_deadline", lambda: 0.5)
    files = _photos(tmp_path, 5)
    started = time.monotonic()
    try:
        result = asyncio.run(_transcribe_folder(files))
    finally:
        release.set()

    assert time.monotonic() - started < 4.0
    stuck = [r for r in result["results"] if r.get("file") == files[2]]
    assert stuck and "Apple Vision did not finish this page" in str(stuck[0].get("error")), stuck
    read = [r.get("text") for r in result["results"] if r.get("file") != files[2]]
    assert read == [f"text of {Path(f).name}" for f in files if f != files[2]]


def test_the_apple_provider_route_passes_the_same_gate(monkeypatch, tmp_path):
    """`llm.vision` on provider apple (extract, compare, similarity, a node on the apple provider)
    reached Vision on its own thread per call, outside the gate."""
    from fichero_server.llm import _apple_vision_dispatch

    vision = _VisionThatDeadlocks(bound=vb.APPLE_VISION_CONCURRENCY)
    monkeypatch.setattr(vb, "apple_vision_ocr", lambda path, language="en": vision(path).text)
    monkeypatch.setattr(vb, "validate_vision_language", lambda language: "en-US")
    files = _photos(tmp_path, 10)
    config = LLMConfig(provider="apple", model="apple-vision")

    async def fan_out():
        return await asyncio.gather(*(_apple_vision_dispatch([f], "", config) for f in files))

    try:
        texts = asyncio.run(fan_out())
    finally:
        vision.stuck.set()
    assert texts == [f"text of {Path(f).name}" for f in files]
    assert vision.peak == 2


def test_economy_htr_passes_the_gate_and_its_deadline(monkeypatch, tmp_path):
    from fichero_server.workflows.tools.economy_htr import economy_htr_file

    release = threading.Event()
    monkeypatch.setattr(vb, "apple_vision_ocr_with_geometry",
                        lambda path, language="en": release.wait(30))
    monkeypatch.setattr(vb, "_apple_vision_deadline", lambda: 0.3)
    (photo,) = _photos(tmp_path, 1)
    try:
        result = economy_htr_file(photo, backend="apple")
    finally:
        release.set()
    assert "Apple Vision did not finish this page" in result["error"]


def test_a_page_abandoned_before_its_turn_never_starts(monkeypatch):
    """A page that timed out (or whose run was stopped) while waiting for the gate is not read
    later: it would load Vision for a page already failed."""
    release, calls = threading.Event(), []

    def vision(path, language="en"):
        calls.append(path)
        release.wait(30)
        return path

    monkeypatch.setattr(vb, "apple_vision_ocr", vision)
    monkeypatch.setattr(vb, "_apple_vision_deadline", lambda: 0.3)

    async def three():
        return await asyncio.gather(*(vb.apple_vision_ocr_async(f"p{i}") for i in range(3)),
                                    return_exceptions=True)

    outcomes = asyncio.run(three())
    release.set()
    for _ in range(40):
        if vb._APPLE_VISION_GATE.in_flight == 0:
            break
        time.sleep(0.05)
    time.sleep(0.3)  # long enough for the third page to start, were it going to
    assert all(isinstance(o, vb.AppleVisionTimeout) for o in outcomes)
    assert len(calls) == vb.APPLE_VISION_CONCURRENCY, calls
    assert vb._APPLE_VISION_GATE.in_flight == 0
