"""Kraken as a geometry provider: same vocabulary, honest absence.

Kraken earns its place on evidence, not preference: measured 2026-09-04 on
Caciques 533r, macOS 26's document request found 6 lines and 7 words on a page
of ~30 lines of secretary hand, while Kraken found 33 line polygons with
baselines. These tests pin the two things that make it safe to wire in — that
its output is indistinguishable from Apple's downstream, and that a runtime
nobody installed says so instead of returning an empty page.
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess

import pytest

from fichero_server.llm import kraken_runtime
from fichero_server.llm.kraken_runtime import (
    KRAKEN_SCIPY_OVERRIDE,
    KRAKEN_VERSION,
    KrakenRuntimeMissingError,
    KrakenSegmentationError,
)
from fichero_server.media.ocr_geometry import (
    GEOMETRY_SPARSE_KEY,
    OCRGeometryBox,
    OCRGeometryLevel,
    OCRGeometryResult,
    OCRGeometryStatus,
    flag_sparse_geometry,
    geometry_status,
    is_sparse_geometry,
)


@pytest.fixture
def runtime_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("FICHERO_KRAKEN_RUNTIME_DIR", str(tmp_path / "kraken-runtime"))
    return tmp_path


def _mark_installed(runtime_home: Path) -> None:
    directory = kraken_runtime.kraken_runtime_dir()
    (directory / "bin").mkdir(parents=True, exist_ok=True)
    (directory / "bin" / "python").write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    (directory / "runtime.json").write_text(
        json.dumps({"kraken_version": KRAKEN_VERSION, "scipy_override": KRAKEN_SCIPY_OVERRIDE}),
        encoding="utf-8",
    )


def _payload(lines: list[dict], width: int = 1000, height: int = 2000) -> str:
    return "noise on stdout\n__FICHERO_KRAKEN__" + json.dumps(
        {"width": width, "height": height, "lines": lines}
    )


def _line(x0: float, y0: float, x1: float, y1: float) -> dict:
    return {
        "polygon": [[x0, y0], [x1, y0], [x1, y1], [x0, y1]],
        "baseline": [[x0, y1], [x1, y1]],
    }


# --- honest absence ---------------------------------------------------------


def test_an_uninstalled_runtime_refuses_instead_of_reporting_a_blank_page(
    runtime_home: Path,
) -> None:
    """"No segmenter installed" and "no lines on this page" are different facts.

    Only one of them is about the document, and a provider that returns an
    empty result for the first is asserting the second.
    """
    status = kraken_runtime.runtime_status()

    assert status["installed"] is False
    assert "not installed" in str(status["reason"])
    with pytest.raises(KrakenRuntimeMissingError, match="never installed automatically"):
        kraken_runtime.segment_to_geometry("/tmp/page.png")


def test_the_install_is_never_automatic_in_the_status_it_reports(runtime_home: Path) -> None:
    """~1 GB may not arrive by surprise: the refusal says so in the same breath."""
    reason = str(kraken_runtime.runtime_status()["reason"])

    assert "GB" in reason
    assert "never installed automatically" in reason


def test_a_venv_without_the_metadata_file_is_not_installed(runtime_home: Path) -> None:
    """The metadata lands last, so its absence means the install did not finish.

    Same lesson as the MLX runtime (#4504): a venv that exists is not a runtime
    that works, and reporting otherwise sends the failure somewhere confusing.
    """
    directory = kraken_runtime.kraken_runtime_dir()
    (directory / "bin").mkdir(parents=True)
    (directory / "bin" / "python").write_text("#!/usr/bin/env python3\n", encoding="utf-8")

    assert kraken_runtime.is_installed() is False


def test_install_overrides_the_scipy_pin_after_kraken_not_before(runtime_home: Path) -> None:
    """Order is load-bearing: kraken installs its own pinned scipy.

    kraken pins scipy~=1.15.3, whose PROPACK binary this OS refuses to dlopen,
    so `import kraken` fails outright until it is replaced. Upgrading BEFORE
    kraken would let kraken's pin win and reinstate the broken build.
    """
    commands: list[list[str]] = []

    def fake_venv(target: Path) -> None:
        (target / "bin").mkdir(parents=True, exist_ok=True)
        (target / "bin" / "python").write_text("#!/usr/bin/env python3\n", encoding="utf-8")

    kraken_runtime.install(run_command=commands.append, create_venv=fake_venv)

    assert commands[0][-1] == f"kraken=={KRAKEN_VERSION}"
    assert commands[1][-1] == KRAKEN_SCIPY_OVERRIDE
    assert kraken_runtime.is_installed() is True
    assert kraken_runtime.runtime_status()["scipy_override"] == KRAKEN_SCIPY_OVERRIDE


# --- the shared vocabulary --------------------------------------------------


def test_a_kraken_result_is_indistinguishable_from_vision_downstream(
    runtime_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Boxes normalized top-left, level LINE, provider named, frame named.

    Downstream (overlays, alignment, region math) must not need to know which
    engine produced a box. The one thing it DOES need is which picture the box
    was measured on, which is why rendition_id is carried rather than inferred.
    """
    _mark_installed(runtime_home)

    class Completed:
        stdout = _payload([_line(100, 200, 900, 300), _line(100, 400, 500, 500)])
        stderr = ""

    monkeypatch.setattr(kraken_runtime.subprocess, "run", lambda *a, **k: Completed())

    result = kraken_runtime.segment_to_geometry("/tmp/page.png", rendition_id="rend-7")

    assert result.provider == "kraken"
    assert result.rendition_id == "rend-7"
    assert geometry_status(result) is OCRGeometryStatus.CAPTURED
    assert len(result.boxes) == 2
    first = result.boxes[0]
    assert first.level is OCRGeometryLevel.LINE
    assert first.bbox == [0.1, 0.1, 0.8, 0.05]
    assert first.metadata["pixel_frame"] == {"width": 1000.0, "height": 2000.0}
    # The baseline is Kraken's alone — no Apple arm produces one — so it must
    # survive into the record rather than being flattened into the box.
    assert first.metadata["baseline_px"] == [[100.0, 300.0], [900.0, 300.0]]


def test_boxes_carry_no_invented_text(runtime_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Kraken reads nothing; an empty string is the truthful value."""
    _mark_installed(runtime_home)

    class Completed:
        stdout = _payload([_line(10, 20, 90, 30)])
        stderr = ""

    monkeypatch.setattr(kraken_runtime.subprocess, "run", lambda *a, **k: Completed())

    result = kraken_runtime.segment_to_geometry("/tmp/page.png")

    assert [box.text for box in result.boxes] == [""]


def test_a_page_with_no_lines_says_produced_nothing_not_captured(
    runtime_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _mark_installed(runtime_home)

    class Completed:
        stdout = _payload([])
        stderr = ""

    monkeypatch.setattr(kraken_runtime.subprocess, "run", lambda *a, **k: Completed())

    result = kraken_runtime.segment_to_geometry("/tmp/page.png")

    assert result.boxes == []
    assert geometry_status(result) is OCRGeometryStatus.PRODUCED_NOTHING


def test_a_segmenter_that_printed_nothing_is_an_error_not_an_empty_page(
    runtime_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _mark_installed(runtime_home)

    class Completed:
        stdout = ""
        stderr = "zsh: killed"

    monkeypatch.setattr(kraken_runtime.subprocess, "run", lambda *a, **k: Completed())

    with pytest.raises(KrakenSegmentationError, match="no geometry payload"):
        kraken_runtime.segment_to_geometry("/tmp/page.png")


def test_a_crashed_segmenter_reports_its_own_last_words(
    runtime_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _mark_installed(runtime_home)

    def explode(*args: object, **kwargs: object) -> None:
        raise subprocess.CalledProcessError(1, "python", stderr="RuntimeError: no model")

    monkeypatch.setattr(kraken_runtime.subprocess, "run", explode)

    with pytest.raises(KrakenSegmentationError, match="no model"):
        kraken_runtime.segment_to_geometry("/tmp/page.png")


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
