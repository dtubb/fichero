from __future__ import annotations

import asyncio
import json
import shutil
import unicodedata
from pathlib import Path

import pytest

from fichero.db import Database
from fichero.models import Document, KnownLibrary, LibrarySnapshot, SnapshotInitiatorType
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


def _write_original_files(library_path: Path, files: dict[str, str]) -> None:
    originals = library_path / "files"
    originals.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        (originals / name).write_text(content, encoding="utf-8")


def _register_known_library(library_path: Path, **kwargs) -> KnownLibrary:
    registry_db = Database(storage_snapshots.settings.global_library_path / "fichero.duckdb")
    try:
        library = KnownLibrary(
            path=str(library_path.resolve()),
            name=library_path.name,
            **kwargs,
        )
        registry_db.save(library)
        return library
    finally:
        registry_db.conn.close()


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


def test_snapshot_include_files_copies_originals_and_records_sizes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _use_snapshot_state(monkeypatch, tmp_path)
    library_path = tmp_path / "FilesIncluded.fichero"
    _create_library_with_document(library_path)
    originals = {
        "one.txt": "alpha",
        "two.txt": "beta",
        "résumé.txt": "gamma",
    }
    _write_original_files(library_path, originals)

    snapshot = storage_snapshots.snapshot_library(
        str(library_path),
        reason="include originals",
        include_files=True,
    )

    files_copy = Path(snapshot.snapshot_path) / "files_copy"
    assert snapshot.includes_files is True
    assert snapshot.files_path is not None
    assert files_copy.exists()
    assert snapshot.files_size_bytes == sum(
        len(content.encode("utf-8")) for content in originals.values()
    )
    for name, content in originals.items():
        assert (files_copy / name).read_text(encoding="utf-8") == content

    manifest = json.loads((Path(snapshot.snapshot_path) / "manifest.json").read_text())
    assert manifest["includes_files"] is True
    assert manifest["paths"]["files"] == snapshot.files_path
    assert manifest["sizes"]["files_size_bytes"] == snapshot.files_size_bytes


def test_snapshot_normalizes_unicode_library_name_to_nfc(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _use_snapshot_state(monkeypatch, tmp_path)
    library_path = tmp_path / unicodedata.normalize("NFC", "Chocó.fichero")
    _create_library_with_document(library_path)

    snapshot = storage_snapshots.snapshot_library(
        unicodedata.normalize("NFD", str(library_path)),
        reason="unicode path",
    )

    assert snapshot.library_name == unicodedata.normalize("NFC", "Chocó")
    assert Path(snapshot.snapshot_path).parts[-2] == unicodedata.normalize("NFC", "Chocó")


def test_snapshot_restore_round_trips_original_files_when_included(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _use_snapshot_state(monkeypatch, tmp_path)
    library_path = tmp_path / "RestoreFiles.fichero"
    _create_library_with_document(library_path)
    _write_original_files(
        library_path,
        {
            "keep.txt": "before",
            "résumé.txt": "accented",
            "three.txt": "third",
        },
    )

    snapshot = storage_snapshots.snapshot_library(
        str(library_path),
        reason="before file mutation",
        include_files=True,
    )
    originals_dir = library_path / "files"
    (originals_dir / "keep.txt").write_text("after", encoding="utf-8")
    (originals_dir / "résumé.txt").unlink()
    (originals_dir / "new.txt").write_text("new", encoding="utf-8")

    result = storage_snapshots.restore_snapshot(snapshot.id)

    assert result["files_restored_path"] == str(originals_dir)
    assert Path(result["files_backup_path"]).exists()
    assert (originals_dir / "keep.txt").read_text(encoding="utf-8") == "before"
    assert (originals_dir / "résumé.txt").read_text(encoding="utf-8") == "accented"
    assert not (originals_dir / "new.txt").exists()

    backup_dir = Path(result["files_backup_path"])
    assert (backup_dir / "keep.txt").read_text(encoding="utf-8") == "after"
    assert (backup_dir / "new.txt").read_text(encoding="utf-8") == "new"


def test_auto_snapshot_before_risky_operation_passes_include_files(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _use_snapshot_state(monkeypatch, tmp_path)
    calls: list[dict[str, object]] = []

    def snapshot_spy(library_path: str, **kwargs):
        calls.append({"library_path": library_path, **kwargs})
        return "snapshot"

    monkeypatch.setattr(storage_snapshots, "snapshot_library", snapshot_spy)

    result = storage_snapshots.auto_snapshot_before_risky_operation(
        tmp_path / "AutoFiles.fichero",
        reason="before merge",
        include_files=True,
    )

    assert result == "snapshot"
    assert calls == [
        {
            "library_path": str(tmp_path / "AutoFiles.fichero"),
            "reason": "before merge",
            "initiator": "system",
            "auto_expire_days": 14,
            "include_files": True,
        }
    ]


def test_snapshot_quiesces_database_manager_before_copy(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _use_snapshot_state(monkeypatch, tmp_path)
    library_path = tmp_path / "QuiesceSnapshot.fichero"
    _create_library_with_document(library_path)
    calls: list[tuple[Path, bool]] = []

    def quiesce_spy(path: Path, *, close: bool) -> None:
        calls.append((path, close))

    monkeypatch.setattr(storage_snapshots, "_quiesce_library_database", quiesce_spy)

    storage_snapshots.snapshot_library(str(library_path), reason="safe copy")

    assert calls == [(library_path, False)]


def test_restore_quiesces_database_manager_before_swap(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _use_snapshot_state(monkeypatch, tmp_path)
    library_path = tmp_path / "QuiesceRestore.fichero"
    _create_library_with_document(library_path)
    snapshot = storage_snapshots.snapshot_library(str(library_path), reason="before")
    calls: list[tuple[Path, bool]] = []

    def quiesce_spy(path: Path, *, close: bool) -> None:
        calls.append((path, close))

    monkeypatch.setattr(storage_snapshots, "_quiesce_library_database", quiesce_spy)

    storage_snapshots.restore_snapshot(snapshot.id)

    assert calls == [(library_path, True)]


@pytest.mark.parametrize(
    ("duckdb_path", "lance_path"),
    [
        ("/etc/passwd", "safe/vectors"),
        ("../escape", "safe/vectors"),
        ("safe/duckdb", "/etc/passwd"),
        ("safe/duckdb", "../escape"),
    ],
)
def test_snapshot_restore_refuses_record_paths_outside_snapshots_dir(
    tmp_path: Path,
    monkeypatch,
    duckdb_path: str,
    lance_path: str,
) -> None:
    _use_snapshot_state(monkeypatch, tmp_path)
    library_path = tmp_path / "Traversal.fichero"
    _create_library_with_document(library_path)
    snapshot = LibrarySnapshot(
        id=f"snap-{abs(hash((duckdb_path, lance_path)))}",
        library_path=str(library_path),
        library_name="Traversal",
        reason="malicious record",
        initiator=SnapshotInitiatorType.user,
        snapshot_path=str(storage_snapshots.settings.snapshots_dir / "Traversal"),
        duckdb_path=duckdb_path,
        lance_path=lance_path,
    )
    storage_snapshots._save_snapshot_record(snapshot)

    with pytest.raises(FileNotFoundError):
        storage_snapshots.restore_snapshot(snapshot.id)


def test_snapshot_export_uses_read_only_duckdb_connection(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Snapshot export must not open a second read-write DuckDB connection."""
    _use_snapshot_state(monkeypatch, tmp_path)
    library_path = tmp_path / "ReadOnlyExport.fichero"
    _create_library_with_document(library_path)
    real_connect = storage_snapshots.duckdb.connect
    read_only_flags: list[bool] = []

    def connect_spy(path, *args, **kwargs):
        read_only = kwargs.get("read_only", False)
        read_only_flags.append(read_only)
        if not read_only:
            raise AssertionError("snapshot opened DuckDB read-write")
        return real_connect(path, *args, **kwargs)

    monkeypatch.setattr(storage_snapshots.duckdb, "connect", connect_spy)

    storage_snapshots.snapshot_library(
        str(library_path),
        reason="manual checkpoint",
    )

    assert read_only_flags == [True]


def test_snapshot_copies_offsite_when_configured(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _use_snapshot_state(monkeypatch, tmp_path)
    library_path = tmp_path / "Offsite.fichero"
    offsite_root = tmp_path / "external-backups"
    _create_library_with_document(library_path)
    _register_known_library(
        library_path,
        snapshot_offsite_path=str(offsite_root),
    )

    snapshot = storage_snapshots.snapshot_library(
        str(library_path),
        reason="manual checkpoint",
    )

    assert snapshot.offsite_path == str(offsite_root / "Offsite" / snapshot.id)
    assert Path(snapshot.offsite_path).exists()
    assert (Path(snapshot.offsite_path) / "manifest.json").exists()

    manifest_path = Path(snapshot.snapshot_path) / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    assert manifest["paths"]["offsite"] == snapshot.offsite_path


def test_snapshot_offsite_unconfigured_is_noop(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _use_snapshot_state(monkeypatch, tmp_path)
    library_path = tmp_path / "PrimaryOnly.fichero"
    _create_library_with_document(library_path)

    snapshot = storage_snapshots.snapshot_library(
        str(library_path),
        reason="manual checkpoint",
    )

    assert snapshot.offsite_path is None
    manifest_path = Path(snapshot.snapshot_path) / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    assert manifest["paths"]["offsite"] is None


def test_scheduled_snapshots_default_to_disabled_noop(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _use_snapshot_state(monkeypatch, tmp_path)
    library_path = tmp_path / "Disabled.fichero"
    _create_library_with_document(library_path)
    _register_known_library(library_path)

    created = storage_snapshots.run_due_scheduled_snapshots()

    assert created == []
    assert storage_snapshots.list_snapshots(library_name="Disabled") == []
    assert storage_snapshots.start_periodic_snapshot_task() is None


@pytest.mark.asyncio
async def test_periodic_snapshot_loop_creates_snapshot_when_enabled(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _use_snapshot_state(monkeypatch, tmp_path)
    storage_snapshots.settings.scheduled_snapshot_poll_interval_seconds = 0.01
    library_path = tmp_path / "Scheduled.fichero"
    _create_library_with_document(library_path)
    _register_known_library(
        library_path,
        snapshot_interval_seconds=0.01,
    )

    task = storage_snapshots.start_periodic_snapshot_task()
    assert task is not None

    try:
        for _ in range(50):
            snapshots = storage_snapshots.list_snapshots(library_name="Scheduled")
            if snapshots:
                break
            await asyncio.sleep(0.01)
        else:
            pytest.fail("scheduled snapshot was never created")

        assert snapshots[0].reason == "scheduled periodic snapshot"
    finally:
        await storage_snapshots.stop_periodic_snapshot_task(task)


@pytest.mark.asyncio
async def test_periodic_snapshot_shutdown_cancels_cleanly(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _use_snapshot_state(monkeypatch, tmp_path)
    storage_snapshots.settings.scheduled_snapshot_poll_interval_seconds = 0.05
    library_path = tmp_path / "Shutdown.fichero"
    _create_library_with_document(library_path)
    _register_known_library(
        library_path,
        snapshot_interval_seconds=60.0,
    )

    task = storage_snapshots.start_periodic_snapshot_task()
    assert task is not None

    await asyncio.sleep(0)
    await storage_snapshots.stop_periodic_snapshot_task(task)

    assert task.done()
    assert task.cancelled()


@pytest.mark.asyncio
async def test_scheduled_snapshots_enforce_retention(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _use_snapshot_state(monkeypatch, tmp_path)
    storage_snapshots.settings.scheduled_snapshot_poll_interval_seconds = 0.01
    library_path = tmp_path / "ScheduledRetention.fichero"
    _create_library_with_document(library_path)
    _register_known_library(
        library_path,
        snapshot_interval_seconds=0.01,
        snapshot_retention_count=2,
    )

    task = storage_snapshots.start_periodic_snapshot_task()
    assert task is not None

    try:
        for _ in range(80):
            if len(storage_snapshots.list_snapshots(library_name="ScheduledRetention")) >= 2:
                break
            await asyncio.sleep(0.01)
        await asyncio.sleep(0.08)

        snapshots = storage_snapshots.list_snapshots(library_name="ScheduledRetention")
        assert len(snapshots) == 2

        snapshot_dirs = [
            path
            for path in (
                storage_snapshots.settings.snapshots_dir / "ScheduledRetention"
            ).iterdir()
            if path.is_dir()
        ]
        assert len(snapshot_dirs) == 2
    finally:
        await storage_snapshots.stop_periodic_snapshot_task(task)


# ---------------------------------------------------------------------------
# Silent-fallback hardening: registry loading must log, not silently swallow (#2507)
# ---------------------------------------------------------------------------


def test_corrupt_registry_logs_warning_and_returns_empty(
    tmp_path: Path,
    monkeypatch,
    caplog,
) -> None:
    """A corrupt registry JSON must surface a warning, not silently read as
    'no snapshots' (which masks data loss). Behaviour stays resilient: []."""
    _use_snapshot_state(monkeypatch, tmp_path)
    records_path = storage_snapshots._snapshot_records_path()
    records_path.parent.mkdir(parents=True, exist_ok=True)
    records_path.write_text("{ this is not valid json ]")

    with caplog.at_level("WARNING"):
        result = storage_snapshots._load_all_snapshot_records()

    assert result == []
    assert any(
        "Could not read snapshot registry" in rec.message for rec in caplog.records
    ), "corrupt registry must be logged, not swallowed silently"


def test_corrupt_record_is_skipped_with_warning(
    tmp_path: Path,
    monkeypatch,
    caplog,
) -> None:
    """One malformed record must be skipped WITH a warning naming it, while the
    valid records still load — resilience without silence."""
    _use_snapshot_state(monkeypatch, tmp_path)
    records_path = storage_snapshots._snapshot_records_path()
    records_path.parent.mkdir(parents=True, exist_ok=True)
    good = LibrarySnapshot(
        id="good-1",
        library_path=str(tmp_path / "lib.fichero"),
        library_name="Lib",
        snapshot_path=str(tmp_path / "snap"),
        duckdb_path="db.duckdb.export",
        lance_path="vectors",
        initiator=SnapshotInitiatorType.user,
    )
    # Corrupt record: valid initiator (passes the enum coercion) but missing the
    # required library_path/library_name, so LibrarySnapshot(**raw) raises.
    bad = {"id": "bad-1", "initiator": "user"}
    records_path.write_text(json.dumps([good.model_dump(mode="json"), bad]))

    with caplog.at_level("WARNING"):
        result = storage_snapshots._load_all_snapshot_records()

    assert [s.id for s in result] == ["good-1"]
    assert any(
        "Skipping corrupted snapshot record bad-1" in rec.message
        for rec in caplog.records
    ), "a dropped record must be logged with its id, not skipped silently"


def test_valid_registry_loads_without_warnings(
    tmp_path: Path,
    monkeypatch,
    caplog,
) -> None:
    """Regression: a healthy registry must NOT emit the new warnings."""
    _use_snapshot_state(monkeypatch, tmp_path)
    snap = LibrarySnapshot(
        id="ok-1",
        library_path=str(tmp_path / "lib.fichero"),
        library_name="Lib",
        snapshot_path=str(tmp_path / "snap"),
        duckdb_path="db.duckdb.export",
        lance_path="vectors",
        initiator=SnapshotInitiatorType.user,
    )
    storage_snapshots._save_snapshot_record(snap)

    with caplog.at_level("WARNING"):
        result = storage_snapshots._load_all_snapshot_records()

    assert [s.id for s in result] == ["ok-1"]
    assert not any(
        "corrupt" in rec.message.lower() or "Could not read" in rec.message
        for rec in caplog.records
    )
