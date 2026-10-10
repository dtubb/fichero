"""`source.recipe.missing-model-offered`, for a Kraken reader (2026-10-10, overnight check in the Dev Embedded app).

Setup assembled Spanish handwriting with a Zenodo Kraken reader for "Read each line"; the Start plan listed no
download, Start ran, and every page failed "Kraken recognition model 'kraken-zenodo-21788410' is not downloaded".
The spec says the plan names such a model and Start waits for it, "so the step never fails at run time for want
of it" -- it held for spaCy pipelines only.
"""

from __future__ import annotations

from fichero_server.recipes.start import _kraken_reader_here as REAL_CHECK  # before conftest's autouse stands in
from tests.unit.recipes.test_recipe_execution_to_spec import _recipe, _save

READER = "kraken-zenodo-21788410"
READ = {"id": "read", "job": "read-a-line", "model": {"zenodo": "10.5281/zenodo.21788410"}}
LINES = {"id": "lines", "job": "find-lines", "model": {"kraken": "blla", "kraken_version": "bundled"}}


def test_a_kraken_reader_not_on_this_mac_is_offered_and_start_waits(client, tmp_path, monkeypatch):
    from fichero_server.recipes import start

    monkeypatch.setattr(start, "_kraken_reader_here", lambda name: False)
    _save(client, _recipe(tmp_path, LINES, READ))
    plan = client.get("/api/recipes/project/start").json()
    (offer,) = plan["downloads"]
    assert (offer["runtime"], offer["model"]) == ("kraken", READER), offer
    assert offer["action"] == "model.download" and offer["params"] == {"runtime": "kraken", "model": READER}
    assert "read" in offer["steps"], offer  # with "lines": one Kraken run does both
    assert any(READER in r and "download it first" in r for r in plan["refusals"]), plan["refusals"]
    assert client.post("/api/recipes/project/start").status_code == 422


def test_an_installed_kraken_reader_is_not_offered(client, tmp_path, monkeypatch):
    from fichero_server.llm import kraken_runtime
    from fichero_server.recipes import start

    monkeypatch.setattr(start, "_kraken_reader_here", REAL_CHECK)  # the real look at the model store

    model = tmp_path / "reader.mlmodel"
    model.write_bytes(b"weights")
    monkeypatch.setattr(kraken_runtime, "recognition_model_path",
                        lambda model_id, home=None: str(model) if model_id == READER else None)
    _save(client, _recipe(tmp_path, LINES, READ))
    plan = client.get("/api/recipes/project/start").json()
    assert plan["downloads"] == [] and not any(READER in r for r in plan["refusals"]), plan
