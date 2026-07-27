from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from fichero.api.routes.chains import _build_paleography_chain


def _wf(id_: str, name: str):
    return SimpleNamespace(id=id_, name=name)


def test_build_paleography_chain_matches_a_b_c_workflows():
    workflows = [
        _wf("w1", "Transcribe Manuscripts"),
        _wf("w2", "Extract Entities and NER"),
        _wf("w3", "Catalogue Synthesis"),
    ]

    chain, matched = _build_paleography_chain(workflows)
    assert matched == {"A": "w1", "B": "w2", "C": "w3"}
    assert chain.entry_step == "stage_a_transcription"
    assert [s.id for s in chain.steps] == [
        "stage_a_transcription",
        "stage_b_extract_ner",
        "stage_c_catalogue",
    ]


def test_build_paleography_chain_prefers_paleography_transcription():
    workflows = [
        _wf("generic", "Transcribe Manuscripts with OCR"),
        _wf("paleography", "Transcribe Paleography"),
        _wf("extract", "Extract Entities and NER"),
        _wf("catalogue", "Catalogue Synthesis"),
    ]

    _, matched = _build_paleography_chain(workflows)

    assert matched["A"] == "paleography"


def test_build_paleography_chain_raises_when_required_stage_missing():
    workflows = [
        _wf("w1", "Transcribe Manuscripts"),
        _wf("w2", "Extract Entities and NER"),
    ]
    with pytest.raises(HTTPException) as exc:
        _build_paleography_chain(workflows)
    assert exc.value.status_code == 400
    assert "missing workflows" in str(exc.value.detail).lower()
