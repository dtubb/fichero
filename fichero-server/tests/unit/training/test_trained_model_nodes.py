"""Models in the training node (#5439, `source.model.node-in-sidebar`, `source.model.node-inspector`).

Through the real routes `GET /api/training/models` and `GET /api/training/model`, with fixture cards
written where the landing code writes them: a Kraken reader's install record (`training.landing`) and a
vision student's `fichero-card.json` in the MLX store. Scores are appended by the evaluation job's own
card writer (`evaluation.record_on_card`). Nothing is trained, run, downloaded or sent.
"""
from __future__ import annotations

import json
from urllib.parse import quote

import pytest

from fichero_server.api.main import app, get_library_database
from fichero_server.llm import kraken_runtime
from fichero_server.training import evaluation
from fichero_server.db import db_manager
from fichero_server.training.landing import land_trained_reader
from fichero_server.training.model_nodes import project_of

TEACHER = "google/gemini-3-flash-preview"
HELD = [{"document_id": "page-2", "name": "SM_NPQ_C01_002"}, {"document_id": "page-3", "name": "SM_NPQ_C01_003"}]
TS = {"teacher": TEACHER, "pages": 8, "lines": 210, "lines_read_by_a_model": 210, "lines_checked_by_a_person": 0,
      "lines_left_out": 3, "held_out": HELD}


@pytest.fixture(autouse=True)
def homes(tmp_path, monkeypatch):
    """Kraken's readers and the MLX store in the test's own folders, never this Mac's."""
    from fichero_server.llm import mlx_model_store

    monkeypatch.setenv("FICHERO_KRAKEN_DATA_DIR", str(tmp_path / "kraken-data"))
    store = mlx_model_store.MLXModelStore(tmp_path / "mlx")
    monkeypatch.setattr(mlx_model_store, "get_mlx_model_store", lambda: store)
    return store


HERE = "test.fichero"  # the `client` fixture's library (conftest `test_package`)
LEGACY = "legacy"  # a card landed before the project was recorded on it


def _project(tmp_path, package: str) -> dict | None:
    """The project a training job in `package` writes on its card, by the job's own function."""
    if package == LEGACY:
        return None
    return project_of(db_manager.get_database(tmp_path / package))


def _reader(tmp_path, *, job: str, not_for_release: bool | None = True, project: str = HERE) -> str:
    out = tmp_path / f"out-{job[:4]}"
    out.mkdir()
    (out / "reader_best.mlmodel").write_bytes(b"trained weights")
    card = {"display_name": "Notebook reader", "teacher": TEACHER, "base": "kraken-mccatmus", "training_set": TS,
            "held_out": HELD, "target": "huggingface-jobs"}
    if not_for_release is not None:
        card["not_for_release"] = not_for_release
    if (where := _project(tmp_path, project)) is not None:
        card["project"] = where
    return land_trained_reader(out, job_id=job, model_name="reader", card=card)


def _vision(store, name: str = "student", project: str = HERE) -> str:
    model_id = f"fichero-trained/{name}"
    dest = store.trained_dir(model_id)
    dest.mkdir(parents=True)
    (dest / "model.safetensors").write_bytes(b"x" * 1000)
    card = {
        "display_name": "Qwen student", "teacher": TEACHER, "base": "Qwen/Qwen3-VL-4B-Instruct",
        "base_licence": "apache-2.0", "base_licence_note": "Apache-2.0 on its Hub card.", "training_set": TS,
        "held_out": HELD, "target": "huggingface-jobs", "job_id": "job-v", "trained_at": "2026-10-04T10:00:00+00:00",
        "not_for_release": False,
        "builds": {"mlx": {"model_id": model_id, "path": str(dest), "runs_on": "Apple silicon"},
                   "hf": {"bucket": "b", "runs_on": "Linux GPU (transformers, vLLM)"}}}
    if (where := _project(store.root.parent, project)) is not None:
        card["project"] = where
    (dest / "fichero-card.json").write_text(json.dumps(card), encoding="utf-8")
    return model_id


def _scored(model: str, reader: str, cer: float) -> None:
    evaluation.record_on_card(model, reader, {
        "job_id": "eval-1", "measured_at": "2026-10-05T01:00:00+00:00", "checked": "anthropic/fable-checked",
        "pages": ["page-2", "page-3"], "role": "trained",
        "scores": {"diplomatic": {"cer": cer + 0.02, "pages": 2}, "layout-insensitive": {"cer": cer, "pages": 2}}})


def _listed(client) -> dict[str, dict]:
    r = client.get("/api/training/models")
    assert r.status_code == 200, r.text
    return {m["id"]: m for m in r.json()["models"]}


def test_a_trained_reader_lists_with_its_provenance_and_held_out_scores(client, tmp_path):
    """source.model.node-inspector: a model in the training node shows where it came from and its scores on
    held-out pages, read from its card. WHY: the node is how a person judges a trained model against what
    can be downloaded; a list that lost the base, teacher, set or score would leave nothing to judge by."""
    reader = _reader(tmp_path, job="0f4e2a6c-1111-2222-3333-444455556666")
    _scored(reader, "kraken", 0.041)

    node = _listed(client)[reader]
    assert node["kind"] == "kraken-reader" and node["name"] == "Notebook reader"
    assert (node["base"], node["teacher"], node["trained_where"]) == ("kraken-mccatmus", TEACHER, "huggingface-jobs")
    assert node["job_id"] == "0f4e2a6c-1111-2222-3333-444455556666" and node["trained_at"]
    assert node["training_set"]["pages"] == 8 and node["training_set"]["held_out_pages"] == 2
    assert node["scores"]["cer"] == {"diplomatic": pytest.approx(0.061), "layout-insensitive": pytest.approx(0.041)}
    assert node["scores"]["pages"] == 2 and node["evaluations"] == 1
    assert node["size_bytes"] == len(b"trained weights")
    assert node["runs_on"] == [{"build": "kraken", "runs_on": "this Mac", "here": True}]
    assert node["licence"] is None  # a Kraken reader's card names no licence: None, never guessed

    inspector = client.get("/api/training/model", params={"model": reader})
    assert inspector.status_code == 200, inspector.text
    body = inspector.json()
    assert body["card"]["held_out"] == HELD and len(body["evaluation_history"]) == 1


def test_a_vision_student_lists_its_licence_builds_and_size(client, homes):
    """source.model.node-inspector: "its size; where it can run; its licence". WHY: a vision student has two
    builds (MLX here, Hugging Face on a GPU) and carries its base's licence; the node must say both."""
    model = _vision(homes)
    node = _listed(client)[model]
    assert node["kind"] == "vision-lora" and node["licence"] == "apache-2.0"
    assert node["size_bytes"] == 1000  # the weights' bytes, not the card's
    assert {(b["build"], b["here"]) for b in node["runs_on"]} == {("mlx", True), ("hf", False)}
    assert node["may_publish"] is True


def test_an_imported_model_is_not_a_training_node(client, tmp_path, homes):
    """source.model.node-in-sidebar: "A model with no training stays in Settings only". WHY: a reader
    downloaded by DOI and a downloaded vision model's evaluation card sit beside trained ones on disk; if
    they listed, the training node would show models nobody trained here."""
    marker = kraken_runtime._marker_path("kraken-mccatmus")
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps({"model_path": str(tmp_path / "m.mlmodel")}), encoding="utf-8")
    _scored("kraken-mccatmus", "kraken", 0.09)
    _scored("mlx-community/Qwen3-VL-4B-Instruct-4bit", "vision", 0.12)
    trained = _reader(tmp_path, job="aaaa1111-2222-3333-4444-555566667777")

    assert set(_listed(client)) == {trained}
    assert client.get("/api/training/model", params={"model": "kraken-mccatmus"}).status_code == 404


def test_a_model_with_no_evaluation_lists_scores_null(client, tmp_path):
    """distill.eval.stored-on-the-model-node: scores come only from an evaluation on the card. WHY: a
    model never evaluated must say so (null), not show a zero or a training-time figure as its score."""
    reader = _reader(tmp_path, job="bbbb1111-2222-3333-4444-555566667777")
    node = _listed(client)[reader]
    assert node["scores"] is None and node["evaluations"] == 0


def test_publish_is_false_for_a_model_trained_on_a_no_release_set(client, tmp_path):
    """source.model.node-inspector "its licence and its release flag" (a set whose models are trained but never released).
    WHY: training records not_for_release on the card; the node must refuse publish for it, and for a card
    that does not say, since silence is not a release."""
    no_release = _reader(tmp_path, job="cccc1111-2222-3333-4444-555566667777", not_for_release=True)
    unsaid = _reader(tmp_path, job="dddd1111-2222-3333-4444-555566667777", not_for_release=None)
    released = _reader(tmp_path, job="eeee1111-2222-3333-4444-555566667777", not_for_release=False)

    listed = _listed(client)
    assert listed[no_release]["may_publish"] is False
    assert listed[unsaid]["may_publish"] is False
    assert listed[released]["may_publish"] is True


def _in(package_path) -> dict[str, str]:
    """The library header of a person working in that project, as the app sends it."""
    return {"X-Fichero-Library-Path": quote(str(package_path), safe="/")}


def test_each_project_lists_only_the_models_trained_in_it(client, tmp_path, homes):
    """source.model.node-in-sidebar, #5483: a model shows under Training in the project it was trained in
    and nowhere else. WHY: cards live on this engine, not in a library; listing every card engine-wide put
    one project's reader (Sergio's) under Training in every other project. Both routes run through the
    real library dependency, keyed by the library header, so the filter is the route's, not a fixture's."""
    other = tmp_path / "other.fichero"
    other.mkdir()
    db_manager.get_database(other)
    mine = _reader(tmp_path, job="1111aaaa-2222-3333-4444-555566667777")
    theirs = _reader(tmp_path, job="2222bbbb-2222-3333-4444-555566667777", project="other.fichero")
    their_student = _vision(homes, project="other.fichero")
    app.dependency_overrides.pop(get_library_database, None)  # the header decides, as in the app

    here = client.get("/api/training/models")
    there = client.get("/api/training/models", headers=_in(other))
    assert here.status_code == there.status_code == 200, (here.text, there.text)
    assert {m["id"] for m in here.json()["models"]} == {mine}
    assert {m["id"] for m in there.json()["models"]} == {theirs, their_student}

    assert client.get("/api/training/model", params={"model": theirs}).status_code == 404
    assert client.get("/api/training/model", params={"model": theirs}, headers=_in(other)).status_code == 200


def test_a_card_that_names_no_project_lists_in_no_project(client, tmp_path, homes):
    """#5483: a reader landed before training recorded the project (Sergio's) names none. WHY: guessing
    its project would put it back in every project, the defect; it stays a reader in the Kraken model
    catalogue (Settings), where downloaded readers live, and in no training node."""
    legacy = _reader(tmp_path, job="3333cccc-2222-3333-4444-555566667777", project=LEGACY)
    _vision(homes, name="old-student", project=LEGACY)

    assert _listed(client) == {}
    assert client.get("/api/training/model", params={"model": legacy}).status_code == 404
    assert legacy in {mid for mid, _card in kraken_runtime.trained_readers()}, "still an installed reader"


def test_size_is_the_weights_bytes_on_disk_and_null_when_they_are_gone(client, tmp_path, homes):
    """source.model.node-inspector "its size", #5483. WHY: the node read a figure off the card (7 bytes for
    Sergio's reader: a record's size, not the model's); size must be the model file's bytes on this Mac,
    read when listed, and null when the weights are not here, never a stale or invented figure."""
    reader = _reader(tmp_path, job="4444dddd-2222-3333-4444-555566667777")
    weights = tmp_path / "big.mlmodel"
    weights.write_bytes(b"w" * 4096)
    marker = kraken_runtime._marker_path(reader)
    record = json.loads(marker.read_text(encoding="utf-8"))
    record["trained"]["size_bytes"] = 7  # what the card says; the node must not repeat it
    record["model_path"] = str(weights)
    marker.write_text(json.dumps(record), encoding="utf-8")
    student = _vision(homes)

    listed = _listed(client)
    assert listed[reader]["size_bytes"] == 4096
    assert listed[student]["size_bytes"] == 1000

    weights.unlink()
    (homes.trained_dir(student) / "model.safetensors").unlink()
    listed = _listed(client)
    assert listed[reader]["size_bytes"] is None
    assert listed[student]["size_bytes"] is None
