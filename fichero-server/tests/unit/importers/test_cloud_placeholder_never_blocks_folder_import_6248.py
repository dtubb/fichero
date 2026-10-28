"""#6248: a folder import from Box Drive (~/Library/CloudStorage) timed out as a whole instead of downloading the
online-only files. A placeholder is now brought down through the bounded fetch (`dataless.fetch_first`, the #5669
path) before its bytes are read; one that does not come down is named and skipped, and the import goes on."""
from __future__ import annotations

from fichero_server.db import Database
from fichero_server.importers import dataless, ingest
from fichero_server.models import Document, Status


def test_a_placeholder_that_never_comes_down_is_named_and_the_rest_import(tmp_path, monkeypatch):
    folder = tmp_path / "Box" / "letters"
    folder.mkdir(parents=True)
    (folder / "here.txt").write_text("local", encoding="utf-8")
    online_only = folder / "online-only.txt"
    online_only.write_text("x", encoding="utf-8")

    monkeypatch.setattr(dataless, "dataless_reason",
                        lambda p: "dataless (test)" if p.name == "online-only.txt" else None)
    monkeypatch.setattr(ingest, "dataless_reason", dataless.dataless_reason)
    monkeypatch.setattr(dataless, "request_download", lambda p: None)  # the download never finishes
    monkeypatch.setattr(dataless, "_MIN_TIMEOUT_SECONDS", 0.2)
    real_checksum = ingest._file_checksum

    def checksum(path, *a, **kw):
        assert path.name != "online-only.txt", "read a placeholder's bytes with no bound"
        return real_checksum(path, *a, **kw)

    monkeypatch.setattr(ingest, "_file_checksum", checksum)

    db = Database(tmp_path / "lib" / "fichero.duckdb")
    try:
        ingest.ingest_folder(folder, db=db, auto_embed=False)
        docs = {d.name: d for d in db.query(Document)}
        assert docs["here.txt"].status != Status.failed
        failed = docs["online-only.txt"]
        assert failed.status == Status.failed
        assert "did not download" in failed.metadata["ingest_error"] and "online-only.txt" in failed.metadata["ingest_error"]
    finally:
        db.close()


def test_the_words_name_the_cloud_the_file_is_in(tmp_path):
    assert dataless.cloud_name(tmp_path / "Library" / "CloudStorage" / "Box-Box" / "a.jpg") == "Box"
    assert dataless.cloud_name(tmp_path / "Library" / "Mobile Documents" / "a.jpg") == "iCloud"
