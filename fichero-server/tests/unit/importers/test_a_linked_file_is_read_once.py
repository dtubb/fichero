"""A linked file is read once; a re-drop of a folder reads none of what is already in (#6832, #739).

Spec: docs/contributor_manual/specs/importer/importer.md -- `importer.scale.a-linked-file-is-read-once`,
`importer.resumable-redrop-skips-without-reading`. Driven through `import_folder_impl` (the body of
`POST /api/ingest/folder`) with every read of a file under the folder counted.
"""
from __future__ import annotations

import builtins
import io
import os
import random
from pathlib import Path

import pytest

from fichero_server.api.routes.ingest.core import IngestFolderRequest, import_folder_impl
from fichero_server.execution import jobs
from fichero_server.importers import derivatives
from fichero_server.models import DocType, Document

FILES = 6


def _noisy_jpeg(seed: int) -> bytes:
    from PIL import Image

    rng = random.Random(seed)
    image = Image.frombytes("RGB", (400, 400), bytes(rng.randrange(256) for _ in range(400 * 400 * 3)))
    out = io.BytesIO()
    image.save(out, format="JPEG", quality=95)
    return out.getvalue()


class _Counting:
    def __init__(self, handle, counter):
        self._handle, self._counter = handle, counter

    def read(self, *args):
        data = self._handle.read(*args)
        self._counter["bytes"] += len(data)
        return data

    def __enter__(self):
        self._handle.__enter__()
        return self

    def __exit__(self, *exc):
        return self._handle.__exit__(*exc)

    def __iter__(self):
        return iter(self._handle)

    def __getattr__(self, name):
        return getattr(self._handle, name)


@pytest.fixture
def lib(db, monkeypatch, tmp_path):
    monkeypatch.setattr(jobs, "_scheduler", jobs._Scheduler())
    monkeypatch.setattr(derivatives, "auto_nlp_enabled", lambda: False)
    monkeypatch.setattr(derivatives, "_emit_queue_progress", lambda *a, **k: None)
    monkeypatch.setattr(derivatives, "_emit_queue_activity", lambda *a, **k: None)
    jobs.set_paused(True)
    folder = tmp_path / "Box 4"
    folder.mkdir()
    for i in range(FILES):
        (folder / f"img{i}.jpg").write_bytes(_noisy_jpeg(i))
    yield db, folder, Path(db.path).parent
    jobs.set_paused(False)


def _import_counting(monkeypatch, db, folder, library) -> int:
    counter = {"bytes": 0}
    real_open, real_io_open = builtins.open, io.open

    def counting(wrapped):
        def _open(file, mode="r", *args, **kwargs):
            handle = wrapped(file, mode, *args, **kwargs)
            if "b" in mode and "r" in mode and isinstance(file, (str, os.PathLike)) and str(file).startswith(str(folder)):
                return _Counting(handle, counter)
            return handle

        return _open

    monkeypatch.setattr(builtins, "open", counting(real_open))
    monkeypatch.setattr(io, "open", counting(real_io_open))
    try:
        import_folder_impl(db, IngestFolderRequest(path=str(folder), mode="link", extract_text=False), library)
    finally:
        monkeypatch.setattr(builtins, "open", real_open)
        monkeypatch.setattr(io, "open", real_io_open)
    return counter["bytes"]


def _pages(db):
    return [d for d in db.query(Document) if d.doc_type != DocType.folder]


def test_a_link_import_reads_each_file_once(lib, monkeypatch):
    db, folder, library = lib
    total = sum(p.stat().st_size for p in folder.iterdir())

    read = _import_counting(monkeypatch, db, folder, library)

    assert len(_pages(db)) == FILES
    assert total <= read <= total * 1.15, f"{read} bytes read for a folder of {total}"
    assert all(d.metadata.get("width") == 400 for d in _pages(db))


def test_a_second_drop_reads_none_of_what_is_already_in(lib, monkeypatch):
    db, folder, library = lib
    _import_counting(monkeypatch, db, folder, library)

    read = _import_counting(monkeypatch, db, folder, library)

    assert read == 0
    assert len(_pages(db)) == FILES


def test_a_file_changed_since_the_first_drop_is_read_and_imported_again(lib, monkeypatch):
    db, folder, library = lib
    _import_counting(monkeypatch, db, folder, library)
    changed = folder / "img0.jpg"
    changed.write_bytes(_noisy_jpeg(99))

    read = _import_counting(monkeypatch, db, folder, library)

    assert read >= changed.stat().st_size
    assert len(_pages(db)) == FILES + 1
