"""`distill.card.evaluations-survive-a-rewrite` (#6138, from review ## 1254): a card written again by a re-download or by
Make Global keeps the `evaluations` and `reasons_ab` entries recorded on the card it replaces.

WHY: both writers built the new card whole from what they had at hand, so a measurement taken on the old card (an
evaluation recorded while the weights were being copied, or on the marker a re-download replaced) was lost and the
reader looked never measured.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from fichero_server.llm import kraken_runtime as kr
from fichero_server.training import project_models as pm

EVAL = {"pages": ["p1"], "per_page": [], "at": "2026-10-25T10:00:00"}
AB = {"winner": "a", "held_out": 3}


@pytest.fixture
def data_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("FICHERO_KRAKEN_DATA_DIR", str(tmp_path / "kraken-data"))
    return tmp_path


def _land():
    folder = kr.recognition_data_home() / "kraken-mccatmus" / "uuid-abc"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "McCATMuS.mlmodel").write_bytes(b"weights")


def test_a_redownload_keeps_the_evaluations_and_reasons_on_the_marker_it_replaces(data_home):
    kr.download_recognition_model("kraken-mccatmus", run_call=lambda op: _land())
    marker = kr._marker_path("kraken-mccatmus")
    marker.write_text(json.dumps({**json.loads(marker.read_text()), "evaluations": [EVAL], "reasons_ab": [AB]}))
    kr.download_recognition_model("kraken-mccatmus", run_call=lambda op: _land())
    card = json.loads(marker.read_text())
    assert card["evaluations"] == [EVAL] and card["reasons_ab"] == [AB]
    assert card["model_path"].endswith("McCATMuS.mlmodel"), "the fetched model is still what the marker names"


def test_a_first_download_has_no_evaluations_to_carry(data_home):
    kr.download_recognition_model("kraken-mccatmus", run_call=lambda op: _land())
    assert "evaluations" not in json.loads(kr._marker_path("kraken-mccatmus").read_text())


def test_make_global_keeps_an_evaluation_recorded_while_the_weights_were_copied(data_home, monkeypatch):
    package = data_home / "P.fichero"
    model_id = f"{kr.TRAINED_READER_PREFIX}test"
    record = pm.kraken_record(package, model_id)
    record.parent.mkdir(parents=True)
    (record.parent / "w.mlmodel").write_bytes(b"w")
    record.write_text(json.dumps({"model_path": "w.mlmodel", "trained": {}, "evaluations": [EVAL]}))
    real_copy = shutil.copy2

    def copy_then_an_evaluation_lands(src, dst, **kw):
        out = real_copy(src, dst, **kw)
        card = json.loads(record.read_text())
        card["evaluations"].append({**EVAL, "at": "later"})  # recorded on the project's card while it is copied
        record.write_text(json.dumps(card))
        return out

    monkeypatch.setattr(shutil, "copy2", copy_then_an_evaluation_lands)
    pm._kraken_global(package, model_id, {"at": "now"})
    made = json.loads(kr._global_marker_path(model_id).read_text())
    assert [e["at"] for e in made["evaluations"]] == ["2026-10-25T10:00:00", "later"]


def test_a_redownload_of_a_different_revision_does_not_carry_the_old_weights_measurements(data_home):
    kr.download_recognition_model("kraken-mccatmus", run_call=lambda op: _land())
    marker = kr._marker_path("kraken-mccatmus")
    old = json.loads(marker.read_text())
    marker.write_text(json.dumps({**old, "doi": "10.0000/an-older-version", "evaluations": [EVAL], "reasons_ab": [AB]}))
    kr.download_recognition_model("kraken-mccatmus", run_call=lambda op: _land())
    card = json.loads(marker.read_text())
    assert "evaluations" not in card and "reasons_ab" not in card and card["doi"] != "10.0000/an-older-version"
