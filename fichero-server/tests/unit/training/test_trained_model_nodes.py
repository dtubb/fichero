"""Models in the training node (#5439, `source.model.node-in-sidebar`, `source.model.node-inspector`).

Through the real routes `GET /api/training/models` and `GET /api/training/model`, with fixture cards
written where the landing code writes them: a Kraken reader's install record (`training.landing`) and a
vision student's `fichero-card.json` in the MLX store. Scores are appended by the evaluation job's own
card writer (`evaluation.record_on_card`). Nothing is trained, run, downloaded or sent.
"""
from __future__ import annotations

import json

import pytest

from fichero_server.llm import kraken_runtime
from fichero_server.training import evaluation
from fichero_server.training.landing import land_trained_reader

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


def _reader(tmp_path, *, job: str, not_for_release: bool | None = True) -> str:
    out = tmp_path / f"out-{job[:4]}"
    out.mkdir()
    (out / "reader_best.mlmodel").write_bytes(b"trained weights")
    card = {"display_name": "Notebook reader", "teacher": TEACHER, "base": "kraken-mccatmus", "training_set": TS,
            "held_out": HELD, "target": "huggingface-jobs"}
    if not_for_release is not None:
        card["not_for_release"] = not_for_release
    return land_trained_reader(out, job_id=job, model_name="reader", card=card)


def _vision(store, name: str = "student") -> str:
    model_id = f"fichero-trained/{name}"
    dest = store.trained_dir(model_id)
    dest.mkdir(parents=True)
    (dest / "model.safetensors").write_bytes(b"x" * 1000)
    (dest / "fichero-card.json").write_text(json.dumps({
        "display_name": "Qwen student", "teacher": TEACHER, "base": "Qwen/Qwen3-VL-4B-Instruct",
        "base_licence": "apache-2.0", "base_licence_note": "Apache-2.0 on its Hub card.", "training_set": TS,
        "held_out": HELD, "target": "huggingface-jobs", "job_id": "job-v", "trained_at": "2026-10-04T10:00:00+00:00",
        "not_for_release": False,
        "builds": {"mlx": {"model_id": model_id, "path": str(dest), "runs_on": "Apple silicon"},
                   "hf": {"bucket": "b", "runs_on": "Linux GPU (transformers, vLLM)"}}}), encoding="utf-8")
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
    assert node["size_bytes"] > 1000  # weights and card on disk
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
