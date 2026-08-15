"""The ingest skip-set is scoped to the DESTINATION subtree (2026-08-11).

Root cause of "67 images, only 10 imported": the dedup skip-set was
library-GLOBAL, so a re-import — into the same place after an interrupted
import, or into a brand-new destination — skipped every file whose
(source_path, checksum) existed ANYWHERE, leaving the new tree Swiss-cheese.
Scoped to the import root: same destination stays idempotent and repairs a
partial import; a new destination receives a full copy.
"""

from pathlib import Path

import pytest

from fichero_server.importers.ingest import IngestMode, ingest_folder
from fichero_server.models import Document, DocType


def _make_source(tmp_path, count=5):
    folder = tmp_path / "archive"
    folder.mkdir()
    for i in range(1, count + 1):
        (folder / f"scan.{i}.jpg").write_bytes(b"image-bytes-%d" % i)
    return folder


def _subtree_file_names(db, root_id):
    names, stack = [], [root_id]
    while stack:
        pid = stack.pop()
        for child in db.query(Document, parent_id=pid):
            if child.doc_type == DocType.folder:
                stack.append(child.id)
            else:
                names.append(child.name)
    return sorted(names)


def _import(folder, db, test_package, parent_id=None, should_cancel=None):
    return ingest_folder(
        folder,
        mode=IngestMode.LINK,
        db=db,
        package_path=Path(test_package),
        parent_id=parent_id,
        extract_text=False,
        auto_embed=False,
        should_cancel=should_cancel,
    )


def _root(db, parent_id=None):
    roots = [
        d
        for d in db.query(Document, parent_id=parent_id)
        if d.doc_type == DocType.folder and d.name == "archive"
    ]
    assert len(roots) == 1, f"expected one archive root, got {len(roots)}"
    return roots[0]


class TestSameDestination:
    def test_reimport_is_idempotent(self, db, test_package, tmp_path):
        folder = _make_source(tmp_path)
        _import(folder, db, test_package)
        _import(folder, db, test_package)
        assert len(_subtree_file_names(db, _root(db).id)) == 5

    def test_reimport_repairs_an_interrupted_import(self, db, test_package, tmp_path):
        """An import killed partway (engine shutdown cancels the task) leaves
        a partial tree; importing the same folder again must fill it in."""
        folder = _make_source(tmp_path)
        seen = {"n": 0}

        def cancel_after_two():
            seen["n"] += 1
            return seen["n"] > 2

        _import(folder, db, test_package, should_cancel=cancel_after_two)
        partial = _subtree_file_names(db, _root(db).id)
        assert 0 < len(partial) < 5, f"expected a partial tree, got {partial}"

        _import(folder, db, test_package)
        assert len(_subtree_file_names(db, _root(db).id)) == 5


class TestNewDestination:
    def test_import_into_a_second_parent_lands_every_file(
        self, db, test_package, tmp_path
    ):
        """The Swiss-cheese bug: files already imported under one tree were
        skipped from a NEW destination, which therefore only received the
        never-before-seen files."""
        folder = _make_source(tmp_path)
        _import(folder, db, test_package)

        inbox = Document(name="Inbox", doc_type=DocType.folder)
        db.save(inbox)
        _import(folder, db, test_package, parent_id=inbox.id)

        assert len(_subtree_file_names(db, _root(db, inbox.id).id)) == 5
        # The original tree is untouched.
        assert len(_subtree_file_names(db, _root(db).id)) == 5
