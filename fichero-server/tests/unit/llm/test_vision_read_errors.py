"""A failed read says why and fails its step; the local model server says why it cannot serve (#5534).

WHY: 2026-10-06, reading Sergio's page 004 with a landed vision student through 'Read Lines
(Kraken lines, vision model)'. Try 1 ended 'local model unavailable' with no cause: the line
reader asks four lines at once, four concurrent model switches each stopped the server another had
just started (three servers spawned in one second), and the losers had no error to report. Try 2
ran 189 s, logged 'Vision processing failed for SM_NPQ_C01_004.jpg: ' -- an exception whose
message was empty -- and ended 'Workflow completed successfully' with nothing written, because
every check downstream reads a file's error by its truthiness and '' is false.

No model is loaded and no real memory is read: the model call, the server process and the store
are stubbed.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
from types import SimpleNamespace
from typing import Any

import pytest

from fichero_server import llm
from fichero_server.api.routes.ai import local_inference as routes
from fichero_server.core.failure_text import failure_text
from fichero_server.db.manager import db_manager
from fichero_server.llm import LLMConfig
from fichero_server.llm.local_inference import LocalInferenceServiceManager, LocalServiceState
from tests.unit.llm.test_local_model_choice import _Healthy, _Process, mac  # noqa: F401 -- the fixture


# --- an error is never empty ----------------------------------------------------------------------


@pytest.mark.parametrize("exc", [TimeoutError(), concurrent.futures.CancelledError(), RuntimeError("")])
def test_an_exception_with_no_message_is_named_by_its_type(exc):
    """WHY: str() of these is '', and '' is read downstream as 'no error'."""
    said = failure_text(exc)
    assert said and type(exc).__name__ in said


def test_an_empty_exception_names_its_cause():
    try:
        try:
            raise ConnectionResetError("the model server closed the connection")
        except ConnectionResetError as inner:
            raise TimeoutError() from inner
    except TimeoutError as outer:
        said = failure_text(outer)
    assert "TimeoutError" in said and "the model server closed the connection" in said


def test_a_message_is_kept_as_it_is():
    assert failure_text(ValueError("bad page")) == "bad page"


# --- a failed read fails its step -----------------------------------------------------------------


def _page(db, tmp_path):
    from PIL import Image

    from fichero_server.models import DocType, Document, FileType

    path = tmp_path / "SM_NPQ_C01_004.png"
    Image.new("RGB", (32, 32), "white").save(path)
    doc = Document(name=path.name, doc_type=DocType.file, file_type=FileType.image, path=str(path))
    db.save(doc)
    return doc


async def _transcribe(library, doc):
    from fichero_server.workflows.tools.sources import files_tool
    from fichero_server.workflows.tools.transcribe import transcribe

    config = LLMConfig(provider="omlx", model="fichero-trained/mosquera-qwen25vl3b")
    src = await files_tool(inputs={}, state={"selected_doc_ids": [doc.id], "library_path": library},
                           llm_config=config)
    return src, await transcribe(inputs={"files": src["files"], "documents": src["documents"],
                                         "vision_mode": "llm", "force_ocr": True},
                                 state={"library_path": library}, llm_config=config)


@pytest.mark.asyncio
async def test_a_read_that_fails_with_no_message_fails_the_step_and_the_run(test_package, tmp_path, monkeypatch):
    """The step's error names the failure, the fan-out counts the file as failed, and the run's
    completion check records every file failed -- never 'completed' with nothing written."""
    from fichero_server.execution.runner import _ALL_FILES_FAILED_MARKER, _detect_empty_text_output

    async def model(images, prompt, config, **_):
        raise TimeoutError()

    monkeypatch.setattr(llm, "vision", model)
    library = str(test_package)
    doc = _page(db_manager.get_database(library), tmp_path)

    src, result = await _transcribe(library, doc)

    assert result.get("error"), f"a failed read must fail its step, got {result.get('error')!r}"
    assert "TimeoutError" in result["error"]
    assert result["results"][0]["error"] == result["error"]
    empty, reason = _detect_empty_text_output({"files": src["files"], "outputs": {"read": result}})
    assert empty and _ALL_FILES_FAILED_MARKER in reason and "TimeoutError" in reason, reason


@pytest.mark.asyncio
async def test_a_model_servers_error_reaches_the_steps_reason(test_package, tmp_path, monkeypatch):
    """The server's own words (here: it could not load the model) are the step's reason."""
    from fichero_server.llm import LocalModelUnavailableError

    async def model(images, prompt, config, **_):
        raise LocalModelUnavailableError(
            "The local model server could not load fichero-trained/x: local inference process exited 1: "
            "ValueError: Unrecognized image processor Qwen3VLImageProcessor")

    monkeypatch.setattr(llm, "vision", model)
    library = str(test_package)
    doc = _page(db_manager.get_database(library), tmp_path)

    _src, result = await _transcribe(library, doc)
    assert "Unrecognized image processor" in (result.get("error") or "")


# --- the line reader: a line's read is bounded, and a cut-short line is kept to be flagged ---------


def _lines(n: int):
    from fichero_server.media.ocr_geometry import OCRGeometryBox, OCRGeometryLevel, OCRGeometryResult

    boxes = [OCRGeometryBox(text="", bbox=[0, i / n, 1, 1 / n], level=OCRGeometryLevel.LINE,
                            provider="kraken", model="blla", source="kraken-blla",
                            metadata={"polygon_px": [[0, i * 8], [32, i * 8], [32, i * 8 + 8], [0, i * 8 + 8]]})
             for i in range(n)]
    return OCRGeometryResult(text="", provider="kraken", model="blla", boxes=boxes, source="kraken-blla")


@pytest.mark.asyncio
async def test_a_line_read_asks_for_a_lines_worth_of_tokens_and_keeps_a_cut_short_line(tmp_path, monkeypatch):
    """WHY: measured 2026-10-06, the student looped on a line ('1000000000…') to the server's
    2,048-token cap -- ~100 s a line at 20 tokens/s, past the 60 s request timeout, and every retry
    ran it again. A line's read is capped at a line's worth; a line that hits the cap is kept
    (and the read checker marks it), never dropped as a line with no writing."""
    from PIL import Image

    from fichero_server.llm import line_reader
    from fichero_server.llm.read_guard import READ_FLAG_KEY, ModelText

    page = tmp_path / "page.png"
    Image.new("RGB", (32, 16), "white").save(page)
    asked: list[int] = []

    async def model(images, prompt, config, **_):
        asked.append(config.max_tokens)
        return ModelText('["' + "1000000000" * 40, "length")

    monkeypatch.setattr(llm, "vision", model)
    monkeypatch.setattr(line_reader, "lines_per_call", lambda config: 1)
    result = await line_reader.read_lines(str(page), _lines(2), LLMConfig(provider="omlx", model="student"))

    assert asked and all(t <= line_reader.TOKENS_PER_LINE + 32 for t in asked), asked
    assert len(result.boxes) == 2, "a cut-short line was dropped as 'no writing'"
    assert all(READ_FLAG_KEY in box.metadata for box in result.boxes)


# --- 'local model unavailable' says why ----------------------------------------------------------


class _SlowProcess(_Process):
    """A server process whose start and stop take a moment, as real ones do: long enough for the
    line reader's other three asks to arrive while it switches."""

    started = 0

    async def start(self) -> None:
        await asyncio.sleep(0.01)
        type(self).started += 1
        await super().start()

    async def stop(self) -> None:
        await asyncio.sleep(0.01)
        await super().stop()


@pytest.mark.asyncio
async def test_four_lines_asked_at_once_switch_the_model_once(mac, monkeypatch):  # noqa: F811
    mac.install("Qwen2.5-VL-3B", "mlx-community/Qwen3-VL-8B")
    old = LocalInferenceServiceManager(
        routes._configured_omlx_profile("mlx-community/Qwen3-VL-8B"), _SlowProcess(running=True), _Healthy())
    old.state = LocalServiceState.healthy
    routes._MANAGERS[old.profile.id] = old
    made: list[LocalInferenceServiceManager] = []

    def new_manager(profile):
        manager = LocalInferenceServiceManager(profile, _SlowProcess(), _Healthy(), poll_interval_seconds=0)
        routes._MANAGERS[profile.id] = manager
        made.append(manager)
        return manager

    monkeypatch.setattr(routes, "_new_manager", new_manager)
    _SlowProcess.started = 0
    config = LLMConfig(provider="omlx", model="Qwen2.5-VL-3B")

    await asyncio.gather(*(llm._ensure_managed_local_provider_ready(config, capability="vision") for _ in range(4)))

    assert len(made) == 1 and _SlowProcess.started == 1, (
        f"{len(made)} managers and {_SlowProcess.started} servers for one switch")
    assert routes._MANAGERS[old.profile.id].status().healthy


@pytest.mark.asyncio
async def test_a_server_that_dies_loading_says_so_with_its_own_words(mac, monkeypatch):  # noqa: F811
    from fichero_server.llm import LocalModelUnavailableError

    mac.install("Qwen2.5-VL-3B")

    class Dies(_Process):
        async def start(self) -> None:
            self.running = False
            self.last_error = "local inference process exited 1: ValueError: Unrecognized image processor"

        def output_tail(self) -> str:
            return "Traceback (most recent call last): | ValueError: Unrecognized image processor"

    def new_manager(profile):
        manager = LocalInferenceServiceManager(profile, Dies(), _Healthy(), poll_interval_seconds=0)
        routes._MANAGERS[profile.id] = manager
        return manager

    monkeypatch.setattr(routes, "_new_manager", new_manager)
    with pytest.raises(LocalModelUnavailableError) as refused:
        await llm._ensure_managed_local_provider_ready(LLMConfig(provider="omlx", model="Qwen2.5-VL-3B"),
                                                       capability="vision")
    said = str(refused.value)
    assert "could not load Qwen2.5-VL-3B" in said and "Unrecognized image processor" in said, said


def test_a_server_stopped_while_it_started_says_it_was_switched():
    manager: Any = SimpleNamespace(profile=SimpleNamespace(model_id="Qwen2.5-VL-3B"), process=SimpleNamespace())
    status = SimpleNamespace(model_id="Qwen2.5-VL-3B", state=LocalServiceState.stopped, last_error=None)
    said = llm.local_model_unavailable_reason(manager, status)
    assert "stopped before it was ready" in said and "Qwen2.5-VL-3B" in said
    assert said != "local model unavailable"
