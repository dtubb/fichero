"""A trained Kraken reader comes home as a reader card (#5398, `compute.tune.model-comes-back-as-a-card`)."""
from __future__ import annotations

import pytest

from fichero_server.llm import kraken_runtime as kr
from fichero_server.llm.local_model_catalog import kraken_catalog_entries
from fichero_server.training.landing import NoTrainedModel, best_model_file, land_trained_reader

CARD = {
    "display_name": "Sergio notebooks (Gemini-taught, PP-OCRv6 base)",
    "summary": "Taught by google/gemini-3-flash-preview on 210 pages; tested on 10 held out.",
    "base": "kraken-zenodo-21788410",
    "teacher": "google/gemini-3-flash-preview",
    "training_set": {"pages": 210, "lines": 9000, "lines_read_by_a_model": 9000, "lines_checked_by_a_person": 0},
    "held_out": [{"document_id": "d1", "name": "SM_NPQ_C01_004.jpg"}],
    "target": "huggingface-jobs", "far_id": "job-123", "flavor": "t4-small",
    "not_for_release": True,
    "release_note": "Trained on the Sergio Mosquera notebooks: models trained on them are not released.",
}


@pytest.fixture(autouse=True)
def kraken_home(tmp_path, monkeypatch):
    monkeypatch.setenv("FICHERO_KRAKEN_DATA_DIR", str(tmp_path / "kraken-data"))


def _out(tmp_path, *names):
    out = tmp_path / "out"
    out.mkdir(parents=True, exist_ok=True)
    for name in names:
        (out / name).write_bytes(b"weights:" + name.encode())
    return out


def test_the_best_model_is_chosen_over_the_last_epoch(tmp_path):
    """WHY: `-q early` keeps every epoch's checkpoint and names the best; landing the last one would
    bring home a worse model than the run found."""
    out = _out(tmp_path, "sergio_7.safetensors", "sergio_best.safetensors", "sergio_9.safetensors")
    assert best_model_file(out, "sergio").name == "sergio_best.safetensors"
    out2 = _out(tmp_path / "b", "sergio_2.safetensors", "sergio_10.safetensors")
    assert best_model_file(out2, "sergio").name == "sergio_10.safetensors"
    with pytest.raises(NoTrainedModel):
        best_model_file(_out(tmp_path / "c", "log.txt"), "sergio")


def test_a_landed_reader_can_be_used_by_name_and_says_where_it_came_from(tmp_path):
    """WHY: a model that comes back must be usable like any reader (a Transcribe run names it), and
    its card must say its base, its teacher and its data, so nobody mistakes a model taught by a
    model for one taught by a person."""
    out = _out(tmp_path, "sergio_best.safetensors")
    reader = land_trained_reader(out, job_id="0f4e2a6c-1111-2222-3333-444455556666", model_name="sergio", card=CARD)

    assert reader.startswith(kr.TRAINED_READER_PREFIX)
    path, catalog_id = kr.resolve_recognition_model(reader)
    assert catalog_id == reader and path.endswith("sergio.safetensors")
    assert open(path, "rb").read() == b"weights:sergio_best.safetensors"
    card = kr.trained_reader_card(reader)
    assert card["teacher"] == CARD["teacher"] and card["base"] == CARD["base"]
    assert card["training_set"]["lines_checked_by_a_person"] == 0 and card["job_id"].startswith("0f4e2a6c")


def test_the_catalogue_lists_it_marked_not_for_release(tmp_path):
    """WHY (the Sergio ruling, 2026-10-03): models trained on those notebooks are not released. The
    reader is listed like any other, and says so wherever it is listed."""
    reader = land_trained_reader(_out(tmp_path, "sergio_best.safetensors"), job_id="abcdef0123456789",
                                 model_name="sergio", card=CARD)
    (entry,) = [e for e in kraken_catalog_entries() if e.model_id == reader]
    assert entry.installed and entry.capabilities == ["recognition"]
    assert "Not for release" in entry.note and entry.license_label == "not for release"


def test_a_trained_reader_is_never_downloaded(tmp_path):
    """WHY: it has no DOI; asking the download path for it must say what it is, not fetch something."""
    reader = land_trained_reader(_out(tmp_path, "sergio_best.safetensors"), job_id="abcdef0123456789",
                                 model_name="sergio", card=CARD)
    with pytest.raises(ValueError, match="trained"):
        kr.download_recognition_model(reader)
