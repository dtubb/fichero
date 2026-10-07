"""A trained model lives inside its project (#5539, ruled 2026-10-06).

`compute/jobs-and-fine-tuning.md`, "Where a trained model lives, and sharing it": a model trained for a
project lands in the project's package (card and weights), the project's readers find it there, a
project moved to another place carries it, and **Make Global** copies it to the engine's store so every
project can use it, its card (`not_for_release` included) unchanged.

Through the real paths: the training job's own run (Hugging Face replaced by `FakeHub`, as in
`test_training_job.py`), the library opened by the engine's database manager, the Kraken and MLX
resolvers a reader calls, and the routes `GET /api/training/models` and
`POST /api/training/models/make-global`. Nothing is trained, downloaded or sent.
"""
# ruff: noqa: F811  (the fixtures imported from test_training_job are pytest fixtures, used by name)
from __future__ import annotations

import json
import shutil

import pytest

from fichero_server.db import db_manager
from fichero_server.execution import jobs
from fichero_server.llm import kraken_runtime as kr
from fichero_server.training import job as training_job
from fichero_server.training import project_models as pm
from fichero_server.training.model_nodes import model_nodes
from tests.unit.training.test_kraken_training_set import TEACHER
from tests.unit.training.test_training_job import (  # noqa: F401  (fixtures)
    FakeHub,
    _request,
    _subject,
    full_size_notebook,
    isolated,
    notebook,
)


@pytest.fixture
def store(tmp_path, monkeypatch):
    """The MLX store in the test's own folder, never this Mac's."""
    from fichero_server.llm import mlx_model_store as store_module
    from fichero_server.training import mlx_landing

    s = store_module.MLXModelStore(root=tmp_path / "mlx")
    monkeypatch.setattr(store_module, "get_mlx_model_store", lambda: s)

    def convert(merged, dest):
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "model.safetensors").write_bytes(b"4-bit")

    monkeypatch.setattr(mlx_landing, "convert_for_mlx", convert)
    monkeypatch.setattr(jobs, "run_on_lane_blocking", lambda library_path, kind, subject, *, model, fn: fn())
    return s


def _train_reader(db, notebook) -> str:
    hub = FakeHub()
    started = training_job.start(db, _request(notebook), started_by="historian", target_factory=lambda: hub)
    return training_job.run(db, _subject(db, started["job_id"]), target=hub, sleep=lambda s: None)


def _train_student(db, notebook) -> str:
    from fichero_server.training.job import TrainVisionLoraRequest

    hub = FakeHub()
    request = TrainVisionLoraRequest(scope_ids=[notebook.folder.id], teacher=TEACHER,
                                     held_out_ids=[notebook.test_page.id], name="sergio-qwen7b",
                                     language="Spanish", pages_may_leave=True)
    started = training_job.start(db, request, started_by="historian", target_factory=lambda: hub)
    return training_job.run(db, _subject(db, started["job_id"]), target=hub, sleep=lambda s: None)


def _package(db):
    from pathlib import Path

    return Path(db.path).parent


def _listed(client) -> dict[str, dict]:
    r = client.get("/api/training/models")
    assert r.status_code == 200, r.text
    return {m["id"]: m for m in r.json()["models"]}


def test_a_reader_trained_for_a_project_lands_inside_it_and_reads_from_there(db, notebook, client):
    """WHY: on 2026-10-06 a project copied to another Mac lost its Kraken fine-tunes, which lived in the
    engine's store. The reader's weights and card must be IN the package, and reading must use them."""
    reader = _train_reader(db, notebook)
    folder = pm.model_folder(_package(db), reader)

    record = json.loads((folder / pm.CARD).read_text(encoding="utf-8"))
    assert record["model_path"] == "sergio.safetensors", "named relative to the record, so a move keeps it"
    assert (folder / "sergio.safetensors").read_bytes() == b"trained weights"
    assert record["trained"]["teacher"] == TEACHER and record["trained"]["not_for_release"] is True
    assert not kr._global_marker_path(reader).exists(), "nothing lands in the engine's global store"

    path, catalog_id = kr.resolve_recognition_model(reader)
    assert path == str(folder / "sergio.safetensors") and catalog_id == reader
    node = _listed(client)[reader]
    assert node["lives"] == "project" and node["may_publish"] is False


def test_a_project_moved_elsewhere_carries_its_reader(db, notebook, tmp_path):
    """WHY: "a project copied or moved to another Mac carries its models". A path on the card that named
    the old place would leave the moved project with a reader that is not there."""
    reader = _train_reader(db, notebook)
    old = _package(db)
    db_manager.close_all()
    moved = tmp_path / "elsewhere" / old.name
    moved.parent.mkdir()
    shutil.move(str(old), str(moved))

    assert kr.recognition_spec(reader) is None, "with the project closed, its reader is not on offer"
    moved_db = db_manager.get_database(moved)
    path, _ = kr.resolve_recognition_model(reader)
    assert path == str(pm.model_folder(moved, reader) / "sergio.safetensors")
    assert [n["id"] for n in model_nodes(moved_db)] == [reader]


def test_a_vision_student_lands_inside_its_project_and_loads_from_there(db, full_size_notebook, store, client):
    """WHY: the 4-bit student is what reads on this Mac; it, its card and its adapter belong to the project,
    and the store must load it from there by its id like any model."""
    model_id = _train_student(db, full_size_notebook)
    folder = pm.model_folder(_package(db), model_id)

    assert model_id == "fichero-trained/sergio-qwen7b"
    assert (folder / "mlx" / "model.safetensors").is_file() and (folder / "adapter" / "weights.safetensors").is_file()
    assert not (folder / "hf").exists(), "the merged weights are not kept unless asked"
    assert not (store.global_trained_dir(model_id) / "fichero-card.json").exists()
    assert store.resolve_model_path(model_id) == str(folder / "mlx")
    card = store.trained_card(model_id)
    assert card["builds"]["mlx"]["path"] == "mlx" and card["adapter_path"] == "adapter"
    node = _listed(client)[model_id]
    assert node["lives"] == "project"
    assert {r["build"]: r["here"] for r in node["runs_on"]} == {"mlx": True, "hf": False}


def test_make_global_copies_a_reader_to_the_engine_so_every_project_can_use_it(db, notebook, client):
    """WHY: "Use in all projects" puts the model in the app's store. The project keeps its own copy, and
    once global the reader resolves with no project open."""
    reader = _train_reader(db, notebook)

    r = client.post("/api/training/models/make-global", json={"model": reader})
    assert r.status_code == 200, r.text
    made = r.json()
    assert made["model_id"] == reader and made["may_publish"] is False
    marker = json.loads(kr._global_marker_path(reader).read_text(encoding="utf-8"))
    assert marker["trained"]["made_global_from"]["project_path"] == str(_package(db))
    assert (pm.model_folder(_package(db), reader) / "sergio.safetensors").is_file(), "the project keeps its copy"
    assert _listed(client)[reader]["lives"] == "both"

    again = client.post("/api/training/models/make-global", json={"model": reader})
    assert again.status_code == 409, "the global copy is never overwritten"
    missing = client.post("/api/training/models/make-global", json={"model": "kraken-trained-000000000000"})
    assert missing.status_code == 404

    db_manager.close_all()
    path, _ = kr.resolve_recognition_model(reader)
    assert path == made["global_path"] and path.startswith(str(kr.recognition_data_home()))


def test_make_global_keeps_a_model_that_may_not_be_released_unreleasable(db, full_size_notebook, store, client):
    """WHY (#5539): Sergio's models may never be published. Copying one to the global store must carry
    `not_for_release` with it, so no later Publish, in any project, can treat the copy as free to release."""
    model_id = _train_student(db, full_size_notebook)

    r = client.post("/api/training/models/make-global", json={"model": model_id})
    assert r.status_code == 200, r.text
    assert r.json()["may_publish"] is False
    db_manager.close_all()
    card = store.trained_card(model_id)
    assert card["not_for_release"] is True and card["made_global_from"]
    assert store.resolve_model_path(model_id) == str(store.global_trained_dir(model_id))
    assert card["builds"]["mlx"]["path"] == str(store.global_trained_dir(model_id))
    assert "merged_here" not in card["builds"]["hf"]
    (entry,) = [e for e in store.list_catalog_entries() if e.model_id == model_id]
    assert entry.license_label == "not for release"


def test_a_reader_in_the_global_store_from_before_keeps_working(db, client, tmp_path):
    """WHY: every model landed before this ruling lives in the engine's store; no migration is needed, and
    a project can still read with a global model."""
    from fichero_server.training.landing import land_trained_reader
    from fichero_server.training.model_nodes import project_of

    out = tmp_path / "out-old"
    out.mkdir()
    (out / "reader_best.mlmodel").write_bytes(b"old weights")
    reader = land_trained_reader(out, job_id="aaaa-bbbb-cccc-dddd", model_name="reader",
                                 card={"teacher": TEACHER, "project": project_of(db)})
    assert kr._global_marker_path(reader).exists()
    assert kr.resolve_recognition_model(reader)[0].startswith(str(kr.recognition_data_home()))
    assert _listed(client)[reader]["lives"] == "global"
