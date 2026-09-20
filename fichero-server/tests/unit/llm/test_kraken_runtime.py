"""Kraken as a geometry provider: same vocabulary, honest absence.

Kraken earns its place on evidence, not preference: measured 2026-09-04 on
Caciques 533r, macOS 26's document request found 6 lines and 7 words on a page
of ~30 lines of secretary hand, while Kraken found 33 line polygons with
baselines. These tests pin the two things that make it safe to wire in — that
its output is indistinguishable from Apple's downstream, and that a build
without Kraken says so instead of returning an empty page.

#4959 (2026-09-20): Kraken ships INSIDE the engine bundle (installed at BUILD
time — see `pyproject.toml`'s `[tool.fichero.kraken_bundle]`) and runs
IN-PROCESS, through the single seam `kraken_runtime._kraken_call`. There is no
venv, no runtime pip install, no subprocess and no fork any more — the tests
below pin exactly that shape, so a future edit that reaches back for any of
them fails here first.
"""

from __future__ import annotations

import ast
import threading
import time
from pathlib import Path

import pytest

from fichero_server.llm import kraken_runtime
from fichero_server.llm.kraken_runtime import (
    KrakenRuntimeMissingError,
    KrakenSegmentationError,
)
from fichero_server.media.ocr_geometry import (
    GEOMETRY_SPARSE_KEY,
    OCRGeometryBox,
    OCRGeometryResult,
    OCRGeometryStatus,
    flag_sparse_geometry,
    geometry_status,
    is_sparse_geometry,
)

KRAKEN_RUNTIME_PATH = Path(kraken_runtime.__file__)
SRC_ROOT = KRAKEN_RUNTIME_PATH.resolve().parents[2]  # .../src


def _line(x0: float, y0: float, x1: float, y1: float) -> dict:
    return {
        "polygon": [[x0, y0], [x1, y0], [x1, y1], [x0, y1]],
        "baseline": [[x0, y1], [x1, y1]],
    }


def _read_line(x0: float, y0: float, x1: float, y1: float, text: str) -> dict:
    line = _line(x0, y0, x1, y1)
    line["text"] = text
    return line


def _payload(lines: list[dict], width: int = 1000, height: int = 2000) -> dict:
    return {"width": width, "height": height, "lines": lines}


@pytest.fixture(autouse=True)
def _installed(monkeypatch: pytest.MonkeyPatch):
    """Most tests here exercise the geometry/dispatch shape, not the honest-
    absence path (that gets its own tests below) — default to "installed"."""
    monkeypatch.setattr(kraken_runtime, "is_installed", lambda: True)


# --- the shape itself: no venv, no pip, no subprocess, no fork -------------


def test_kraken_runtime_never_shells_out_or_provisions_a_runtime() -> None:
    """#4959: the whole point of bundling at build time is that this module
    NEVER creates a venv, pip-installs anything, or spawns a process at
    runtime. An AST walk (not a grep) so a re-import under a different name
    or a multi-line call cannot slip past a string match."""
    tree = ast.parse(KRAKEN_RUNTIME_PATH.read_text(encoding="utf-8"))
    banned_modules = {"venv", "subprocess", "multiprocessing"}
    banned_calls = {"fork", "os.fork"}
    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in banned_modules:
                    offenders.append(f"line {node.lineno}: import {alias.name}")
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module.split(".")[0] in banned_modules:
                offenders.append(f"line {node.lineno}: from {node.module} import ...")
        elif isinstance(node, ast.Call):
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
            if name in banned_calls:
                offenders.append(f"line {node.lineno}: call to {name}")
    assert not offenders, "kraken_runtime.py must never provision a runtime:\n" + "\n".join(offenders)


def test_the_seam_is_the_only_importer_of_kraken_in_the_engine() -> None:
    """`import kraken` (and `htrmopo`, its model-fetch library) may appear
    ONLY inside `kraken_runtime.py` — anywhere else means a second, un-
    reviewed place the engine touches Kraken's heavy C extensions outside
    the one lock/throttle seam."""
    offenders: list[str] = []
    for path in sorted(SRC_ROOT.rglob("*.py")):
        if path == KRAKEN_RUNTIME_PATH:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            else:
                continue
            for name in names:
                top = name.split(".")[0]
                if top in ("kraken", "htrmopo"):
                    offenders.append(f"{path.relative_to(SRC_ROOT)}:{node.lineno} imports {name!r}")
    assert not offenders, "only kraken_runtime.py may import kraken/htrmopo:\n  " + "\n  ".join(offenders)


# --- status follows importability -------------------------------------------


def test_status_follows_importability_when_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(kraken_runtime, "is_installed", lambda: True)
    monkeypatch.setattr(kraken_runtime.importlib.metadata, "version", lambda name: "7.1.1")

    status = kraken_runtime.runtime_status()

    assert status == {"installed": True, "kraken_version": "7.1.1", "reason": None}


def test_status_is_honest_when_not_bundled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(kraken_runtime, "is_installed", lambda: False)

    status = kraken_runtime.runtime_status()

    assert status["installed"] is False
    assert status["kraken_version"] is None
    assert "not bundled" in str(status["reason"])
    assert "packaging problem" in str(status["reason"])


def test_an_uninstalled_build_refuses_instead_of_reporting_a_blank_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """"No Kraken in this build" and "no lines on this page" are different
    facts, and only one of them is about the document."""
    monkeypatch.setattr(kraken_runtime, "is_installed", lambda: False)

    with pytest.raises(KrakenRuntimeMissingError, match="not bundled"):
        kraken_runtime.segment_to_geometry("/tmp/page.png")


def test_recognition_download_needs_kraken_first(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(kraken_runtime, "is_installed", lambda: False)

    with pytest.raises(KrakenRuntimeMissingError):
        kraken_runtime.download_recognition_model("kraken-mccatmus")


# --- the seam: one call at a time -------------------------------------------


def test_the_throttle_never_leaks_onto_the_callers_thread(monkeypatch: pytest.MonkeyPatch) -> None:
    """Callers arrive on `asyncio.to_thread`'s POOLED workers. The lowered
    priority must apply to the Kraken work and end with it; a class left on a
    pooled worker would slow whatever unrelated request it serves next."""
    import threading

    from fichero_server.core import background_compute as bc

    monkeypatch.setattr(kraken_runtime, "is_installed", lambda: True)
    seen: dict[str, object] = {}

    def op() -> str:
        seen["thread"] = threading.current_thread().name
        seen["qos_inside"] = bc.current_thread_qos_class()
        return "done"

    def caller() -> None:
        seen["qos_before"] = bc.current_thread_qos_class()
        seen["result"] = kraken_runtime._kraken_call(op)
        seen["qos_after"] = bc.current_thread_qos_class()
        seen["caller"] = threading.current_thread().name

    pooled = threading.Thread(target=caller, name="pretend-pool-worker")
    pooled.start()
    pooled.join()

    assert seen["result"] == "done"
    assert seen["thread"] != seen["caller"], "the work must run on a thread the seam owns"
    assert seen["qos_after"] == seen["qos_before"], "the caller's thread priority must be untouched"
    if seen["qos_inside"] is not None:  # macOS only; None elsewhere
        assert seen["qos_inside"] == bc._QOS_CLASS_UTILITY


def test_an_error_inside_the_seam_reaches_the_caller(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(kraken_runtime, "is_installed", lambda: True)

    def op() -> None:
        raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        kraken_runtime._kraken_call(op)


def test_the_seam_serializes_concurrent_calls() -> None:
    """One Kraken call runs at a time — two pages must never double the
    memory (the maintainer's "never peg the machine" rule)."""
    order: list[tuple[str, str, float]] = []

    def make_op(tag: str):
        def _op() -> str:
            order.append(("start", tag, time.monotonic()))
            time.sleep(0.05)
            order.append(("end", tag, time.monotonic()))
            return tag
        return _op

    threads = [
        threading.Thread(target=lambda t=tag: kraken_runtime._kraken_call(make_op(t)))
        for tag in ("a", "b")
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    by_time = sorted(order, key=lambda e: e[2])
    # The second call's start must come after the first call's end — never
    # interleaved (start, start, end, end) or overlapping.
    assert [e[0] for e in by_time] == ["start", "end", "start", "end"], order


def test_the_seam_refuses_when_kraken_is_not_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(kraken_runtime, "is_installed", lambda: False)

    with pytest.raises(KrakenRuntimeMissingError):
        kraken_runtime._kraken_call(lambda: "never runs")


def test_segment_lines_and_recognize_lines_run_through_the_injectable_seam() -> None:
    """`run_call` lets a caller (here: a test) replace the seam without
    needing a real Kraken install — the production default is `_kraken_call`."""
    calls: list[str] = []

    def fake_call(op):
        calls.append("called")
        return {"width": 10, "height": 20, "lines": []}

    result = kraken_runtime.segment_lines("/tmp/x.png", run_call=fake_call)

    assert calls == ["called"]
    assert result == {"width": 10, "height": 20, "lines": []}


# --- the shared vocabulary --------------------------------------------------


def test_a_kraken_result_is_indistinguishable_from_vision_downstream(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Boxes normalized top-left, level LINE, provider named, frame named.

    Downstream (overlays, alignment, region math) must not need to know which
    engine produced a box. The one thing it DOES need is which picture the box
    was measured on, which is why rendition_id is carried rather than inferred.
    """
    payload = _payload([_line(100, 200, 900, 300), _line(100, 400, 500, 500)])
    monkeypatch.setattr(kraken_runtime, "segment_lines", lambda image_path, **k: payload)

    result = kraken_runtime.segment_to_geometry("/tmp/page.png", rendition_id="rend-7")

    assert result.provider == "kraken"
    assert result.rendition_id == "rend-7"
    assert geometry_status(result) is OCRGeometryStatus.CAPTURED
    assert len(result.boxes) == 2
    first = result.boxes[0]
    assert first.bbox == [0.1, 0.1, 0.8, 0.05]
    assert first.metadata["pixel_frame"] == {"width": 1000.0, "height": 2000.0}
    # The baseline is Kraken's alone — no Apple arm produces one — so it must
    # survive into the record rather than being flattened into the box.
    assert first.metadata["baseline_px"] == [[100.0, 300.0], [900.0, 300.0]]


def test_boxes_carry_no_invented_text(monkeypatch: pytest.MonkeyPatch) -> None:
    """Kraken's segmenter reads nothing; an empty string is the truthful value."""
    payload = _payload([_line(10, 20, 90, 30)])
    monkeypatch.setattr(kraken_runtime, "segment_lines", lambda image_path, **k: payload)

    result = kraken_runtime.segment_to_geometry("/tmp/page.png")

    assert [box.text for box in result.boxes] == [""]


def test_a_page_with_no_lines_says_produced_nothing_not_captured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _payload([])
    monkeypatch.setattr(kraken_runtime, "segment_lines", lambda image_path, **k: payload)

    result = kraken_runtime.segment_to_geometry("/tmp/page.png")

    assert result.boxes == []
    assert geometry_status(result) is OCRGeometryStatus.PRODUCED_NOTHING


def test_a_segmentation_failure_reports_kraken_own_words(monkeypatch: pytest.MonkeyPatch) -> None:
    def explode(op):
        raise RuntimeError("no model")

    monkeypatch.setattr(kraken_runtime, "_kraken_call", explode)

    with pytest.raises(KrakenSegmentationError, match="no model"):
        kraken_runtime.segment_to_geometry("/tmp/page.png")


# --- recognition (segment + read, tied to baselines) ------------------------


def test_recognition_ties_each_read_line_to_its_baseline(monkeypatch: pytest.MonkeyPatch) -> None:
    """Per-line HTR: every box carries the text Kraken read AND the baseline it
    read it from, and char spans index that line's slice of the transcript."""
    payload = _payload(
        [_read_line(100, 200, 900, 300, "vecino de la ciudad"),
         _read_line(100, 400, 500, 500, "de Santa Fe")]
    )
    monkeypatch.setattr(kraken_runtime, "recognize_lines", lambda i, m, **k: payload)

    result = kraken_runtime.recognize_to_geometry(
        "/tmp/page.png", "/models/mccatmus.mlmodel",
        model_id="kraken-mccatmus", rendition_id="rend-7",
    )

    assert result.provider == "kraken"
    assert result.rendition_id == "rend-7"
    assert result.source == "kraken-htr"
    assert result.text == "vecino de la ciudad\nde Santa Fe"
    assert [b.text for b in result.boxes] == ["vecino de la ciudad", "de Santa Fe"]
    assert result.boxes[0].model == "kraken-mccatmus"
    assert result.boxes[0].metadata["baseline_px"] == [[100.0, 300.0], [900.0, 300.0]]
    for box in result.boxes:
        assert result.text[box.char_start:box.char_end] == box.text


def test_recognition_char_spans_are_exact_even_for_identical_lines(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two lines that read the same must map to DIFFERENT spans — a text
    search would tie both to the first occurrence; the running cursor does not."""
    payload = _payload(
        [_read_line(100, 200, 900, 300, "ídem"), _read_line(100, 400, 900, 500, "ídem")]
    )
    monkeypatch.setattr(kraken_runtime, "recognize_lines", lambda i, m, **k: payload)

    result = kraken_runtime.recognize_to_geometry("/tmp/p.png", "/m.mlmodel")

    assert result.text == "ídem\nídem"
    assert (result.boxes[0].char_start, result.boxes[0].char_end) == (0, 4)
    assert (result.boxes[1].char_start, result.boxes[1].char_end) == (5, 9)


def test_recognition_stamps_the_path_when_no_model_id_given(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = _payload([_read_line(10, 20, 90, 30, "abc")])
    monkeypatch.setattr(kraken_runtime, "recognize_lines", lambda i, m, **k: payload)

    result = kraken_runtime.recognize_to_geometry("/tmp/p.png", "/models/x.mlmodel")
    assert result.boxes[0].model == "/models/x.mlmodel"


def test_recognition_of_a_blank_page_says_produced_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = _payload([])
    monkeypatch.setattr(kraken_runtime, "recognize_lines", lambda i, m, **k: payload)

    result = kraken_runtime.recognize_to_geometry("/tmp/p.png", "/m.mlmodel")
    assert result.boxes == []
    assert geometry_status(result) is OCRGeometryStatus.PRODUCED_NOTHING


def test_recognition_failure_surfaces_kraken_own_words(monkeypatch: pytest.MonkeyPatch) -> None:
    def explode(op):
        raise RuntimeError("bad model")

    monkeypatch.setattr(kraken_runtime, "_kraken_call", explode)

    with pytest.raises(KrakenSegmentationError, match="bad model"):
        kraken_runtime.recognize_to_geometry("/tmp/p.png", "/m.mlmodel")


# --- recognition-model catalog + download -----------------------------------


def test_recognition_catalog_is_populated_and_honest() -> None:
    """The picker was empty; the catalog now offers known-good HTR models."""
    models = kraken_runtime.KRAKEN_RECOGNITION_MODELS
    assert "kraken-mccatmus" in models
    assert "kraken-catmus-medieval" in models
    for spec in models.values():
        assert spec["doi"]
        assert int(spec["size_bytes"]) > 0
        assert str(spec["note"]).strip()


@pytest.fixture
def data_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("FICHERO_KRAKEN_DATA_DIR", str(tmp_path / "kraken-data"))
    return tmp_path


def test_download_fails_loud_when_no_model_lands(data_home: Path) -> None:
    """A fetch that produces no `.mlmodel` must raise, never write an
    installed marker for a model that isn't there."""
    with pytest.raises(RuntimeError, match="produced no .mlmodel"):
        kraken_runtime.download_recognition_model(
            "kraken-mccatmus", run_call=lambda op: None,
        )
    assert kraken_runtime.is_recognition_model_installed("kraken-mccatmus") is False


def _land_mlmodel() -> None:
    model_dir = kraken_runtime.recognition_data_home() / "uuid-abc"
    model_dir.mkdir(parents=True, exist_ok=True)
    (model_dir / "McCATMuS.mlmodel").write_bytes(b"weights")


def test_recognition_download_records_the_fetched_model_path(data_home: Path) -> None:
    def fake_call(op):
        _land_mlmodel()
        return None

    assert kraken_runtime.is_recognition_model_installed("kraken-mccatmus") is False
    kraken_runtime.download_recognition_model("kraken-mccatmus", run_call=fake_call)

    resolved = kraken_runtime.recognition_model_path("kraken-mccatmus")
    assert resolved is not None
    assert resolved.endswith("McCATMuS.mlmodel")
    assert kraken_runtime.is_recognition_model_installed("kraken-mccatmus") is True


def test_unknown_recognition_model_is_rejected(data_home: Path) -> None:
    with pytest.raises(ValueError, match="Unknown Kraken recognition model"):
        kraken_runtime.download_recognition_model(
            "kraken-not-a-model", run_call=lambda op: None,
        )


def test_removing_a_recognition_model_drops_its_marker(data_home: Path) -> None:
    kraken_runtime.download_recognition_model(
        "kraken-mccatmus", run_call=lambda op: _land_mlmodel(),
    )
    assert kraken_runtime.is_recognition_model_installed("kraken-mccatmus") is True

    kraken_runtime.remove_recognition_model("kraken-mccatmus")
    assert kraken_runtime.is_recognition_model_installed("kraken-mccatmus") is False


def test_recognition_model_path_is_none_when_not_downloaded(data_home: Path) -> None:
    assert kraken_runtime.recognition_model_path("kraken-mccatmus") is None


# --- sparse honesty ---------------------------------------------------------


def _result(box_count: int, provider: str) -> OCRGeometryResult:
    return OCRGeometryResult(
        provider=provider,
        # Spread inside the page: the bbox validator rejects y + h > 1, and a
        # helper that trips it tests the validator rather than the subject.
        boxes=[
            OCRGeometryBox(text="x", bbox=[0.0, 0.9 * index / max(box_count, 1), 0.1, 0.01])
            for index in range(box_count)
        ],
    )


def test_six_boxes_against_forty_five_is_marked_sparse() -> None:
    """The 533r case: real boxes, but not a description of the page.

    macOS 26 returned 6 lines/7 words where the older API found 45 words on the
    same pixels. Reporting only CAPTURED would turn an engine's failure into a
    claim that the page holds six lines.
    """
    flagged = flag_sparse_geometry(
        _result(6, "vision-recognize-documents"),
        reference_count=45,
        reference_provider="apple_vision",
    )

    assert is_sparse_geometry(flagged) is True
    # Status stays honest: boxes WERE captured. Sparse is an extra fact.
    assert geometry_status(flagged) is OCRGeometryStatus.CAPTURED
    assert "45" in flagged.metadata["geometry_sparse_reference"]
    assert "13%" in flagged.metadata["geometry_sparse_reference"]


def test_a_result_that_broadly_agrees_is_not_marked_sparse() -> None:
    """1923_p10: 115 words against 134. Different engines, same page."""
    flagged = flag_sparse_geometry(
        _result(115, "vision-recognize-documents"),
        reference_count=134,
        reference_provider="apple_vision",
    )

    assert is_sparse_geometry(flagged) is False
    assert GEOMETRY_SPARSE_KEY not in flagged.metadata


def test_no_reference_means_no_sparse_verdict() -> None:
    """Without a second engine on the same pixels there is nothing to judge
    against, and inventing a denominator would be worse than staying silent."""
    result = _result(3, "kraken")

    assert is_sparse_geometry(flag_sparse_geometry(result, reference_count=0, reference_provider="none")) is False


def test_sparse_flagging_does_not_mutate_the_original_result() -> None:
    original = _result(2, "vision-recognize-documents")

    flagged = flag_sparse_geometry(original, reference_count=100, reference_provider="apple_vision")

    assert is_sparse_geometry(flagged) is True
    assert is_sparse_geometry(original) is False
