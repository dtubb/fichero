"""The kraken_htr node: recognise per-line and SAVE text tied to baselines.

Daniel: "i want kraken text saved, and ideally tied to the baselines." These
pin the node's contract without a real Kraken venv or model: recognition is
faked, and the assertions are that the node (1) hands the recognised transcript
to save_artifact as page_content-bound content WITH the per-line ocr_geometry,
and (2) refuses clearly when the model is missing or the input is a PDF.
"""

from __future__ import annotations

import asyncio

import pytest

from fichero_server.media.ocr_geometry import OCRGeometryResult, OCRGeometryBox, OCRGeometryLevel
from fichero_server.workflows.tools import kraken_htr as node_mod


def _fake_result(text: str) -> OCRGeometryResult:
    boxes = [
        OCRGeometryBox(
            text=line,
            bbox=[0.1, 0.1 + 0.1 * i, 0.5, 0.05],
            level=OCRGeometryLevel.LINE,
            provider="kraken",
            model="kraken-mccatmus",
            source="kraken-htr",
            metadata={"baseline_px": [[0, i], [10, i]]},
        )
        for i, line in enumerate(text.split("\n"))
    ]
    return OCRGeometryResult(
        text=text, provider="kraken", model="kraken-mccatmus",
        boxes=boxes, source="kraken-htr",
    )


@pytest.fixture
def model_file(tmp_path):
    path = tmp_path / "mccatmus.mlmodel"
    path.write_bytes(b"fake weights")
    return str(path)


def _run(inputs, state):
    from fichero_server.llm import LLMConfig
    return asyncio.run(node_mod.kraken_htr(inputs, state, LLMConfig(provider="", model="")))


def test_recognised_text_is_saved_with_its_geometry(monkeypatch, model_file, tmp_path):
    saved: dict = {}

    async def fake_save_artifact(**kwargs):
        saved.update(kwargs)
        return "artifact-1"

    monkeypatch.setattr(node_mod, "save_artifact", fake_save_artifact)
    monkeypatch.setattr(
        "fichero_server.llm.kraken_runtime.recognize_to_geometry",
        lambda *a, **k: _fake_result("vecino de la ciudad\nde Santa Fe"),
    )

    result = _run(
        {"files": ["/img/page1.png"], "documents": [{"id": "doc-1", "path": "/img/page1.png"}],
         "kraken_model": model_file},
        {"library_path": str(tmp_path / "lib")},
    )

    # The transcript is returned AND handed to save_artifact as content.
    assert result["text"] == "vecino de la ciudad\nde Santa Fe"
    assert result["records"] == [{"doc_id": "doc-1", "text": "vecino de la ciudad\nde Santa Fe"}]
    assert saved["content"] == "vecino de la ciudad\nde Santa Fe"
    # Tied to baselines: the per-line ocr_geometry rides with the save.
    assert saved["ocr_geometry"].source == "kraken-htr"
    assert [b.text for b in saved["ocr_geometry"].boxes] == ["vecino de la ciudad", "de Santa Fe"]
    # Saved as a transcription that becomes page_content.
    assert saved["tool_config"].artifact_type == "transcription"
    assert saved["tool_config"].update_page_content is True
    assert saved["document_id"] == "doc-1"


def test_a_missing_catalog_model_refuses_clearly(monkeypatch):
    # A catalog id that isn't downloaded must raise an actionable error, never
    # run Kraken against a path that isn't there.
    monkeypatch.setattr(
        "fichero_server.llm.kraken_runtime.recognition_model_path",
        lambda model_id, home=None: None,
    )
    with pytest.raises(RuntimeError, match="not downloaded"):
        _run({"files": ["/img/p.png"], "kraken_model": "kraken-mccatmus"}, {"library_path": ""})


def test_a_pdf_is_reported_not_silently_processed(monkeypatch, model_file):
    monkeypatch.setattr(
        "fichero_server.llm.kraken_runtime.recognize_to_geometry",
        lambda *a, **k: _fake_result("should not be called"),
    )
    result = _run(
        {"files": ["/docs/scan.pdf"], "documents": [{"id": "d", "path": "/docs/scan.pdf"}],
         "kraken_model": model_file, "save_to_db": False},
        {"library_path": ""},
    )
    assert result["text"] == ""
    assert "split the PDF" in (result["error"] or "")


def test_no_save_when_save_to_db_is_off(monkeypatch, model_file):
    called = {"n": 0}

    async def fake_save_artifact(**kwargs):
        called["n"] += 1
        return "x"

    monkeypatch.setattr(node_mod, "save_artifact", fake_save_artifact)
    monkeypatch.setattr(
        "fichero_server.llm.kraken_runtime.recognize_to_geometry",
        lambda *a, **k: _fake_result("abc"),
    )
    result = _run(
        {"files": ["/img/p.png"], "documents": [{"id": "d", "path": "/img/p.png"}],
         "kraken_model": model_file, "save_to_db": False},
        {"library_path": "/lib"},
    )
    assert called["n"] == 0
    assert result["text"] == "abc"
