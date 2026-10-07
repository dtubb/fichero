"""A snapshot of a project keeps the project's trained models, card and weights (#5539).

A model trained for a project lives inside it, under `models/`; a backup that left that folder
out would lose the model. These pin that every snapshot copies it (not opt-in like `files/`),
that a card rewritten after the snapshot does not change the snapshot's copy, and that a restore
brings back a model the project lost without touching one trained since.
"""
from __future__ import annotations

import json
from pathlib import Path

from fichero_server.db import storage_snapshots
from fichero_server.db.storage import StorageSettings

READER = "kraken-trained-abc123def456"
VISION = "fichero-trained--sergio"


def _use_snapshot_state(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(storage_snapshots, "settings", StorageSettings(base_path=tmp_path / "state"))


def _project(tmp_path: Path) -> Path:
    from fichero_server.db import Database
    from fichero_server.models import Document

    package = tmp_path / "Sergio.fichero"
    package.mkdir(parents=True)
    db = Database(package / "fichero.duckdb")
    try:
        db.save(Document(id="doc-1", name="Page", page_content="a page long enough to keep"))
    finally:
        db.conn.close()
    reader = package / "models" / READER
    reader.mkdir(parents=True)
    (reader / "best.mlmodel").write_bytes(b"reader weights")
    (reader / "fichero-card.json").write_text(
        json.dumps({"model_path": "best.mlmodel", "trained": {"not_for_release": True}}), encoding="utf-8")
    vision = package / "models" / VISION / "mlx"
    vision.mkdir(parents=True)
    (vision / "model.safetensors").write_bytes(b"mlx weights")
    (vision / "fichero-card.json").write_text(json.dumps({"evaluations": []}), encoding="utf-8")
    return package


def test_a_snapshot_copies_the_projects_models_card_and_weights(tmp_path: Path, monkeypatch) -> None:
    _use_snapshot_state(monkeypatch, tmp_path)
    package = _project(tmp_path)

    snapshot = storage_snapshots.snapshot_library(str(package), reason="safety net")

    copy = Path(snapshot.snapshot_path) / "models_copy"
    assert (copy / READER / "best.mlmodel").read_bytes() == b"reader weights"
    card = json.loads((copy / READER / "fichero-card.json").read_text(encoding="utf-8"))
    assert card["trained"]["not_for_release"] is True
    assert (copy / VISION / "mlx" / "model.safetensors").read_bytes() == b"mlx weights"
    manifest = json.loads((Path(snapshot.snapshot_path) / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["paths"]["models"] == str(copy.relative_to(storage_snapshots.settings.snapshots_dir))
    assert manifest["sizes"]["models_size_bytes"] > 0


def test_a_card_rewritten_after_the_snapshot_leaves_the_snapshots_card_alone(
    tmp_path: Path, monkeypatch
) -> None:
    _use_snapshot_state(monkeypatch, tmp_path)
    package = _project(tmp_path)
    snapshot = storage_snapshots.snapshot_library(str(package), reason="safety net")

    # an evaluation is written into the card in place, as the landing code does
    (package / "models" / VISION / "mlx" / "fichero-card.json").write_text(
        json.dumps({"evaluations": [{"cer": 0.1}]}), encoding="utf-8")

    kept = Path(snapshot.snapshot_path) / "models_copy" / VISION / "mlx" / "fichero-card.json"
    assert json.loads(kept.read_text(encoding="utf-8")) == {"evaluations": []}


def test_deleting_the_projects_model_leaves_the_snapshots_weights(tmp_path: Path, monkeypatch) -> None:
    _use_snapshot_state(monkeypatch, tmp_path)
    package = _project(tmp_path)
    snapshot = storage_snapshots.snapshot_library(str(package), reason="safety net")

    (package / "models" / READER / "best.mlmodel").unlink()

    kept = Path(snapshot.snapshot_path) / "models_copy" / READER / "best.mlmodel"
    assert kept.read_bytes() == b"reader weights"


def test_a_project_with_no_models_snapshots_as_before(tmp_path: Path, monkeypatch) -> None:
    _use_snapshot_state(monkeypatch, tmp_path)
    package = _project(tmp_path)
    import shutil

    shutil.rmtree(package / "models")

    snapshot = storage_snapshots.snapshot_library(str(package), reason="safety net")

    assert not (Path(snapshot.snapshot_path) / "models_copy").exists()
    assert storage_snapshots.restore_snapshot(snapshot.id)["models_restored"] == []


def test_restore_brings_back_a_lost_model_and_keeps_one_trained_since(tmp_path: Path, monkeypatch) -> None:
    _use_snapshot_state(monkeypatch, tmp_path)
    package = _project(tmp_path)
    snapshot = storage_snapshots.snapshot_library(str(package), reason="safety net")

    import shutil

    shutil.rmtree(package / "models" / READER)
    newer = package / "models" / "kraken-trained-999999999999"
    newer.mkdir()
    (newer / "best.mlmodel").write_bytes(b"trained after the snapshot")
    (package / "models" / VISION / "mlx" / "fichero-card.json").write_text(
        json.dumps({"evaluations": [{"cer": 0.1}]}), encoding="utf-8")

    result = storage_snapshots.restore_snapshot(snapshot.id)

    assert result["models_restored"] == [READER]
    assert (package / "models" / READER / "best.mlmodel").read_bytes() == b"reader weights"
    assert (newer / "best.mlmodel").read_bytes() == b"trained after the snapshot"
    # a model in both keeps the project's own copy
    card = json.loads((package / "models" / VISION / "mlx" / "fichero-card.json").read_text(encoding="utf-8"))
    assert card == {"evaluations": [{"cer": 0.1}]}
