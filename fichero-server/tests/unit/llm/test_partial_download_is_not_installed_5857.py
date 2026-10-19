"""A partial download is never offered as installed (`source.model.partial-download-is-not-installed`, #5857).

WHY: on the owner's Pro the PP-OCRv6 folder held only `medium.safetensors.part` (13 MB) and a README, and runs picked the
model. The installed check needs the marker, the file, no `.part` beside it, and the size the download recorded."""
from __future__ import annotations

import json

import pytest

from fichero_server.llm import kraken_runtime as kr

READER = "kraken-zenodo-21788410"


@pytest.fixture
def folder(tmp_path, monkeypatch):
    monkeypatch.setenv("FICHERO_KRAKEN_DATA_DIR", str(tmp_path / "kraken"))
    where = kr.recognition_data_home() / READER
    where.mkdir(parents=True)
    return where


def _marker(file, **more):
    marker = kr._marker_path(READER)
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps({"doi": "10.5281/zenodo.21788410", "model_path": str(file), **more}))


def test_only_a_part_file_and_a_readme_is_not_installed(folder):
    (folder / "README.md").write_text("x")
    (folder / "medium.safetensors.part").write_bytes(b"x" * 13)
    assert not kr.is_recognition_model_installed(READER)  # no marker
    _marker(folder / "medium.safetensors")  # a stale marker naming a file that is not there
    assert not kr.is_recognition_model_installed(READER)
    assert kr.recognition_download_problem(READER) == "its model file is missing"
    assert kr.recognition_partial_bytes(READER) == 13


def test_a_part_file_beside_the_model_keeps_it_from_being_installed(folder):
    weights = folder / "medium.safetensors"
    weights.write_bytes(b"w" * 100)
    (folder / "other.bin.part").write_bytes(b"x")
    _marker(weights)
    assert not kr.is_recognition_model_installed(READER)
    assert kr.recognition_download_problem(READER) == "its download did not finish"


def test_a_file_of_another_size_than_recorded_is_not_installed_and_the_right_one_is(folder):
    weights = folder / "medium.safetensors"
    weights.write_bytes(b"w" * 100)
    _marker(weights, bytes=200)
    assert not kr.is_recognition_model_installed(READER)
    _marker(weights, bytes=100)
    assert kr.is_recognition_model_installed(READER)
    assert kr.recognition_download_problem(READER) is None


def test_a_run_refuses_a_partial_reader_in_words(folder):
    """Review 330 MED: the run's resolver asked only the marker; it now asks the one installed check."""
    (folder / "medium.safetensors.part").write_bytes(b"x" * 13)
    _marker(folder / "medium.safetensors")  # stale
    assert kr.recognition_model_path(READER) is None
    with pytest.raises(RuntimeError) as refused:
        kr.resolve_recognition_model(READER)
    said = str(refused.value)
    assert "not downloaded whole" in said and "its model file is missing" in said and READER not in said


def test_a_whole_reader_still_resolves(folder):
    weights = folder / "medium.safetensors"
    weights.write_bytes(b"w" * 100)
    _marker(weights, bytes=100)
    assert kr.recognition_model_path(READER) == str(weights)
    assert kr.resolve_recognition_model(READER) == (str(weights), READER)
