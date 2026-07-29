from __future__ import annotations

from pathlib import Path

from fichero_server.db import storage_snapshots
from fichero_server.db.storage import StorageSettings


def _use_snapshot_state(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        storage_snapshots,
        "settings",
        StorageSettings(base_path=tmp_path / "state"),
    )


def _create_library_with_document(library_path: Path) -> None:
    from fichero_server.db import Database
    from fichero_server.models import Document

    library_path.mkdir(parents=True, exist_ok=True)
    db = Database(library_path / "fichero.duckdb")
    try:
        doc = Document(
            id="doc-1",
            name="Snapshot Source",
            page_content="the original text is long enough to embed",
        )
        db.save(doc)
        db.save_embedding(doc, [0.1, 0.2, 0.3], text="original embedding text")
    finally:
        db.conn.close()


def _write_original_files(library_path: Path, files: dict[str, str]) -> None:
    originals = library_path / "files"
    originals.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        (originals / name).write_text(content, encoding="utf-8")


def test_snapshot_include_files_false_skips_originals_even_when_present(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _use_snapshot_state(monkeypatch, tmp_path)
    library_path = tmp_path / "NoFilesCopy.fichero"
    _create_library_with_document(library_path)
    _write_original_files(library_path, {"keep.txt": "alpha"})

    snapshot = storage_snapshots.snapshot_library(
        str(library_path),
        reason="db only",
        include_files=False,
    )

    assert snapshot.includes_files is False
    assert snapshot.files_path is None
    assert snapshot.files_size_bytes == 0
    assert not (Path(snapshot.snapshot_path) / "files_copy").exists()


def test_snapshot_include_files_true_handles_missing_files_dir(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _use_snapshot_state(monkeypatch, tmp_path)
    library_path = tmp_path / "EmptyFiles.fichero"
    _create_library_with_document(library_path)

    snapshot = storage_snapshots.snapshot_library(
        str(library_path),
        reason="include empty originals",
        include_files=True,
    )

    assert snapshot.includes_files is True
    assert snapshot.files_path is not None
    assert snapshot.files_size_bytes == 0
    assert (Path(snapshot.snapshot_path) / "files_copy").exists()


def test_restore_db_only_snapshot_leaves_current_files_untouched(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _use_snapshot_state(monkeypatch, tmp_path)
    library_path = tmp_path / "DbOnlyRestore.fichero"
    _create_library_with_document(library_path)
    _write_original_files(library_path, {"keep.txt": "before"})

    snapshot = storage_snapshots.snapshot_library(
        str(library_path),
        reason="db only",
        include_files=False,
    )

    originals_dir = library_path / "files"
    (originals_dir / "keep.txt").write_text("after", encoding="utf-8")
    (originals_dir / "new.txt").write_text("new", encoding="utf-8")

    result = storage_snapshots.restore_snapshot(snapshot.id)

    assert result["files_restored_path"] is None
    assert result["files_backup_path"] is None
    assert (originals_dir / "keep.txt").read_text(encoding="utf-8") == "after"
    assert (originals_dir / "new.txt").read_text(encoding="utf-8") == "new"
