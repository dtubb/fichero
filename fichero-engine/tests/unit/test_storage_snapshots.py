from __future__ import annotations

import json
import shutil
from pathlib import Path

from fichero.db import Database
from fichero.models import Document
from fichero.storage import StorageSettings
from fichero import storage_snapshots


def _use_snapshot_state(monkeypatch, tmp_path: Path) -> None:
    test_settings = StorageSettings(base_path=tmp_path / "state")
    monkeypatch.setattr(storage_snapshots, "settings", test_settings)


def _create_library_with_document(library_path: Path, doc_id: str = "doc-1") -> None:
    library_path.mkdir(parents=True, exist_ok=True)
    db = Database(library_path / "fichero.duckdb")
    doc = Document(
        id=doc_id,
        name="Snapshot Source",
        page_content="the original text is long enough to embed",
    )
    db.save(doc)
    db.save_embedding(doc, [0.1, 0.2, 0.3], text="original embedding text")
    db.conn.close()


def test_snapshot_restore_round_trips_database_rows_and_embeddings(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _use_snapshot_state(monkeypatch, tmp_path)
    library_path = tmp_path / "RoundTrip.fichero"
    _create_library_with_document(library_path)

    snapshot = storage_snapshots.snapshot_library(
        str(library_path),
        reason="before destructive test",
    )

    db = Database(library_path / "fichero.duckdb")
    doc = db.get(Document, "doc-1")
    assert doc is not None
    db.delete_embedding("doc-1")
    db.delete(doc)
    db.conn.close()
    shutil.rmtree(library_path / "vectors")

    result = storage_snapshots.restore_snapshot(snapshot.id)

    restored = Database(library_path / "fichero.duckdb")
    restored_doc = restored.get(Document, "doc-1")
    assert restored_doc is not None
    assert restored_doc.name == "Snapshot Source"
    matches = restored.search_similar([0.1, 0.2, 0.3], limit=1)
    assert matches
    assert matches[0]["document_id"] == "doc-1"
    restored.conn.close()

    assert Path(result["duckdb_backup_path"]).exists()
    if result["lance_backup_path"] is not None:
        assert Path(result["lance_backup_path"]).exists()
    assert result["duckdb_restored_path"] == str(library_path / "fichero.duckdb")
    assert result["lance_restored_path"] == str(library_path / "vectors")


def test_snapshot_retention_keeps_last_n_snapshots(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _use_snapshot_state(monkeypatch, tmp_path)
    library_path = tmp_path / "Retention.fichero"
    _create_library_with_document(library_path)

    for index in range(4):
        storage_snapshots.snapshot_library(
            str(library_path),
            reason=f"snapshot {index}",
            max_snapshots=2,
        )

    snapshots = storage_snapshots.list_snapshots(library_name="Retention")
    assert len(snapshots) == 2
    assert [s.reason for s in snapshots] == ["snapshot 3", "snapshot 2"]

    snapshot_dirs = [
        path
        for path in (storage_snapshots.settings.snapshots_dir / "Retention").iterdir()
        if path.is_dir()
    ]
    assert len(snapshot_dirs) == 2


def test_snapshot_manifest_records_reason_paths_and_sizes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _use_snapshot_state(monkeypatch, tmp_path)
    library_path = tmp_path / "Manifest.fichero"
    _create_library_with_document(library_path)

    snapshot = storage_snapshots.snapshot_library(
        str(library_path),
        reason="manual checkpoint",
    )

    manifest_path = Path(snapshot.snapshot_path) / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    assert manifest["id"] == snapshot.id
    assert manifest["reason"] == "manual checkpoint"
    assert manifest["paths"]["duckdb"] == snapshot.duckdb_path
    assert "vectors" in manifest["paths"]["embeddings"]
    assert manifest["sizes"]["duckdb_size_bytes"] > 0
    assert manifest["sizes"]["lance_size_bytes"] > 0
