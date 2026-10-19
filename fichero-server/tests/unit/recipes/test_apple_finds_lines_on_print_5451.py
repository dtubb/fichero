"""`source.recipe.apple-finds-lines-on-print` (#5451, ruled 2026-10-17): Apple finds the lines of print and keeps no text.

Spec: docs/contributor_manual/specs/source/models-chains-and-projects.md. WHY: Apple's OCR of handwriting is noise
(Mosquera SM_NPQ_C01_030: `WtrtNI-`, `¥eTIQ`) and reached the Order tab as a reading. For print and typescript a
recipe's Find lines step runs Apple for the lines only; a handwriting page goes to Kraken. Through the rules
(`POST /api/recipes/assemble`, the shipped cards only), the planner (`plan_start`) and the geometry the tool keeps.
"""
from __future__ import annotations

import pytest

from fichero_server.media.ocr_geometry import OCRGeometryBox, OCRGeometryLevel, OCRGeometryResult, lines_only
from fichero_server.recipes import start
from fichero_server.recipes.start import plan_start

APPLE_LINES = {"builtin": "apple-vision-lines"}


@pytest.fixture(autouse=True)
def _shipped_cards_only(tmp_path, monkeypatch):
    monkeypatch.setenv("FICHERO_MODEL_STORE_ROOT", str(tmp_path / "store"))
    monkeypatch.setenv("FICHERO_LOCAL_ONLY", "1")
    monkeypatch.setattr(start, "local_models_this_mac_cannot_serve", lambda runs, names=None: [])
    monkeypatch.setattr(start, "local_models_to_download", lambda runs: [])


def _lines_step(client, material: str) -> dict:
    body = {"purposes": ["transcribe"], "languages": ["es"], "scripts": ["Latn"], "materials": [material],
            "mac_memory_gb": 32}
    r = client.post("/api/recipes/assemble", json=body)
    assert r.status_code == 200, r.text
    return next(s for s in r.json()["steps"] if s["job"] == "find-lines")


def test_print_gets_apple_for_its_lines_and_handwriting_gets_kraken(client, with_material):
    """source.recipe.apple-finds-lines-on-print: "for print and typescript a recipe's Find lines step runs Apple
    Vision for its line finding only ... A handwriting page goes to Kraken"."""
    assert _lines_step(client, "print")["model"] == APPLE_LINES
    assert _lines_step(client, "typescript")["model"] == APPLE_LINES
    assert _lines_step(client, "handwriting")["model"].get("kraken") == "blla"


def test_the_planner_runs_the_apple_lines_only_workflow_for_that_step():
    """source.recipe.apple-finds-lines-on-print: the Start plan runs a shipped workflow that finds lines with Apple
    and keeps no text, not Kraken's."""
    from fichero_server.workflows.default_workflows import shipped_preset

    step = {"id": "lines", "job": "find-lines", "model": APPLE_LINES, "runs_on": "this-mac"}
    plan = plan_start({"fichero_recipe": 1, "id": "t", "version": "0.1.0", "title": "t", "steps": [step]},
                      stays_local=True)

    assert not plan["skipped"], plan["skipped"]
    run = plan["workflows"][0]
    assert run["steps"] == ["lines"] and "Apple" in run["workflow"], run
    node = next(n for n in shipped_preset("detect_regions_apple_lines")["nodes"] if n["tool"] == "detect_regions")
    assert node["config"]["provider"] == "apple" and node["config"]["keep_text"] is False


def test_apple_lines_only_keeps_the_line_boxes_and_no_text():
    """source.recipe.apple-finds-lines-on-print: Apple "keeps no text": the lines keep their boxes, with no reading,
    and no word boxes."""
    line = OCRGeometryBox(text="WtrtNI-", bbox=[0.1, 0.1, 0.5, 0.05], level=OCRGeometryLevel.LINE)
    word = OCRGeometryBox(text="WtrtNI-", bbox=[0.1, 0.1, 0.2, 0.05], level=OCRGeometryLevel.WORD)
    kept = lines_only(OCRGeometryResult(text="WtrtNI-", provider="apple_vision", boxes=[line, word]))

    assert kept.text == ""
    assert [(b.level, b.text, b.bbox) for b in kept.boxes] == [(OCRGeometryLevel.LINE, "", [0.1, 0.1, 0.5, 0.05])]


def test_lines_with_no_text_still_become_segments():
    """source.recipe.apple-finds-lines-on-print: the lines land as segments (one per line box) with no reading, the way
    Kraken's text-free geometry does."""
    from fichero_server.models.segments import segments_from_result

    line = OCRGeometryBox(text="WtrtNI-", bbox=[0.1, 0.1, 0.5, 0.05], level=OCRGeometryLevel.LINE)
    word = OCRGeometryBox(text="WtrtNI-", bbox=[0.1, 0.1, 0.2, 0.05], level=OCRGeometryLevel.WORD)
    found = lines_only(OCRGeometryResult(text="WtrtNI-", provider="apple_vision", boxes=[line, word]))

    _pass, segments = segments_from_result(document_id="d", artifact_id="a", result=found, provider="apple_vision",
                                           model="VNRecognizeTextRequest", run_id=None, created_at=None,
                                           artifact_type="regions")

    assert len(segments) == 1
    assert not (getattr(segments[0], "text", None) or "").strip(), segments[0]
