"""Asking which originals are missing costs a listing per folder, not a path resolution per page (#6828).

Spec: docs/contributor_manual/specs/importer/importer.md -- `importer.originals.missing-check-is-bounded`. Measured
on 500 linked pages that were all present: 311,382 `lstat` and 38,502 `stat` calls. The filesystem calls are counted
by wrapping `os.stat`, `os.lstat`, `os.scandir` and `os.listdir` around the real route's check.
"""

from __future__ import annotations

import contextlib
import os
from pathlib import Path

from fichero_server.importers import relink
from fichero_server.models import DocType, Document, FileType


@contextlib.contextmanager
def _counted(monkeypatch):
    calls: list[str] = []
    for name in ("stat", "lstat", "scandir", "listdir"):
        real = getattr(os, name)

        def wrapper(*a, _real=real, _name=name, **k):
            calls.append(_name)
            return _real(*a, **k)

        monkeypatch.setattr(os, name, wrapper)
    yield calls
    monkeypatch.undo()


def _page(db, path: Path) -> Document:
    doc = Document(name=path.name, doc_type=DocType.file, file_type=FileType.image, path=str(path),
                   metadata={"ingest_mode": "link", "source_path": str(path)})
    db.save(doc)
    return doc


def test_500_linked_pages_in_5_folders_cost_at_most_one_call_a_page(db, tmp_path, monkeypatch):
    pages = []
    for folder in range(5):
        for n in range(100):
            f = tmp_path / "originals" / f"box{folder}" / f"p{n:03d}.jpg"
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(b"x")
            pages.append(_page(db, f))

    with _counted(monkeypatch) as calls:
        assert relink.missing_originals(db) is None
    assert len(calls) <= 505, f"{len(calls)} filesystem calls for 500 pages in 5 folders"


def test_a_missing_file_among_present_ones_is_still_named(db, tmp_path):
    kept = []
    for n in range(4):
        f = tmp_path / "o" / f"p{n}.jpg"
        f.parent.mkdir(exist_ok=True)
        f.write_bytes(b"x")
        kept.append(_page(db, f))
    kept[2].path and Path(kept[2].path).unlink()

    said = relink.missing_originals(db)

    assert said is not None and said["ids"] == [kept[2].id] and said["pages"] == 1


def test_pages_on_a_volume_that_is_not_there_cost_one_call(db, monkeypatch):
    pages = [_page(db, Path(f"/Volumes/NoSuchVolume6828/box{n % 3}/p{n}.jpg")) for n in range(30)]

    with _counted(monkeypatch) as calls:
        said = relink.missing_originals(db)

    assert said is not None and sorted(said["ids"]) == sorted(p.id for p in pages)
    assert len(calls) == 1, calls


def test_the_route_answers_the_same(client, db, tmp_path):
    f = tmp_path / "o" / "p.jpg"
    f.parent.mkdir()
    f.write_bytes(b"x")
    page = _page(db, f)
    assert client.get("/api/documents/missing-originals").json() is None
    f.unlink()
    assert client.get("/api/documents/missing-originals").json()["ids"] == [page.id]
