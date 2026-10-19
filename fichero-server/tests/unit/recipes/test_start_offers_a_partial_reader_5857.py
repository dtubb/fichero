"""Start offers the download of a partial Kraken reader (`source.model.partial-download-is-not-installed`, #5857, review
330): a stale marker over a half-fetched file is not installed, so the plan names the download. The run's own refusal is
pinned in `tests/unit/llm/test_partial_download_is_not_installed_5857.py`."""
from __future__ import annotations

import json

import pytest

from fichero_server.llm import kraken_runtime as kr
from tests.unit.recipes.test_kraken_reader_offered_before_start import LINES, READ, REAL_CHECK, _recipe, _save
from tests.unit.recipes.test_recipe_execution_to_spec import pages  # noqa: F401 (fixture)

READER = "kraken-zenodo-21788410"


@pytest.fixture
def folder(tmp_path, monkeypatch):
    monkeypatch.setenv("FICHERO_KRAKEN_DATA_DIR", str(tmp_path / "kraken"))
    where = kr.recognition_data_home() / READER
    where.mkdir(parents=True)
    return where


def test_start_offers_the_download_of_a_partial_reader(folder, client, pages, tmp_path, monkeypatch):  # noqa: F811
    """Review 330 MED: Start's check (`_kraken_reader_here`) trusted a stale marker, so a run still picked a partial
    reader. It now asks the one installed check."""
    from fichero_server.recipes import start

    monkeypatch.setattr(start, "_kraken_reader_here", REAL_CHECK)  # the real look at the model store
    (folder / "medium.safetensors.part").write_bytes(b"x" * 13)
    marker = kr._marker_path(READER)
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps({"doi": "10.5281/zenodo.21788410", "model_path": str(folder / "medium.safetensors")}))
    assert kr.recognition_model_path(READER) is None

    _save(client, _recipe(tmp_path, LINES, READ))
    plan = client.get("/api/recipes/project/start").json()
    (offer,) = plan["downloads"]
    assert (offer["runtime"], offer["model"]) == ("kraken", READER)
