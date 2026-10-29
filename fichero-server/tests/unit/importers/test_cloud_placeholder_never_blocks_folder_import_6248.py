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


def test_a_loose_file_whose_read_blocks_is_refused_within_its_bound(tmp_path, monkeypatch):
    """A loose file (ingest_file -> require_local_bytes) went through a read on the import's own thread: an online-only
    Box file whose read blocked held the request until the app gave up. Now the read is only the download's trigger,
    on its own thread, and the import waits within the bound."""
    import threading
    import time

    import pytest

    f = tmp_path / "Library" / "CloudStorage" / "Box-Box" / "big.pdf"
    f.parent.mkdir(parents=True)
    f.write_bytes(b"x" * 4096)
    release = threading.Event()
    real_open = type(f).open

    def blocking_open(self, *a, **kw):
        if self == f:
            release.wait(10)  # fileproviderd never answers
        return real_open(self, *a, **kw)

    monkeypatch.setattr(type(f), "open", blocking_open)
    monkeypatch.setattr("shutil.which", lambda name: None)  # no brctl: the read is the trigger
    monkeypatch.setattr(dataless, "dataless_reason", lambda p: "dataless (test)")
    monkeypatch.setattr(dataless, "_MIN_TIMEOUT_SECONDS", 0.5)
    started = time.monotonic()
    try:
        with pytest.raises(dataless.DatalessSourceError) as excinfo:
            dataless.require_local_bytes(f)
    finally:
        release.set()
    assert time.monotonic() - started < 5, "the import thread waited on the blocked read"
    words = str(excinfo.value)
    assert "big.pdf" in words and "Box" in words and "no local bytes" in words and "Download" in words


def test_a_folder_import_says_it_is_still_downloading(tmp_path, monkeypatch):
    """The app fails a folder import whose status has not changed in 300 s; one large file coming down from Box
    changed nothing. While it downloads, the progress moves inside that file's share."""
    import time

    folder = tmp_path / "Box" / "letters"
    folder.mkdir(parents=True)
    big = folder / "big.txt"
    big.write_text("x", encoding="utf-8")
    local_at = time.monotonic() + 1.2

    monkeypatch.setattr(dataless, "dataless_reason",
                        lambda p: "dataless (test)" if p.name == "big.txt" and time.monotonic() < local_at else None)
    monkeypatch.setattr(ingest, "dataless_reason", dataless.dataless_reason)
    monkeypatch.setattr(dataless, "request_download", lambda p: None)
    seen: list[float] = []

    def on_progress(current, total, fetching=0.0):
        seen.append((current + fetching) / total)

    db = Database(tmp_path / "lib" / "fichero.duckdb")
    try:
        ingest.ingest_folder(folder, db=db, auto_embed=False, on_progress=on_progress)
    finally:
        db.close()
    waiting = [p for p in seen if 0 < p < 1]
    assert len(set(waiting)) >= 2, f"progress did not move while the file came down: {seen}"
    assert waiting == sorted(waiting) and seen[-1] == 1.0
