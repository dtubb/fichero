"""The fan-out hands a region node its OWN crop.

`files[i]` is paired POSITIONALLY with `documents[i]`. For a diary entry —
a band of a page that shares the page's file — `files[i]` is the whole page,
so "run Detect Regions on this entry" ran it on everything around the entry.

The length invariant is the load-bearing property here: a substitution that
dropped or added an element would shift every later file against its document
and mis-pair the batch silently, which is far worse than not narrowing at all.
"""

from __future__ import annotations

from pathlib import Path

from fichero_server.media.region_crops import REGION_CROP_ROLE
from fichero_server.models import Document, Rendition
from fichero_server.models.anchors import NodeRegion
from fichero_server.workflows.tools.vision_base import _substitute_region_crops


def _page(db, tmp_path) -> Document:
    from PIL import Image

    path = tmp_path / "page.png"
    Image.new("RGB", (400, 800), "white").save(path)
    doc = Document(name="page.png", path=str(path))
    db.save(doc)
    return doc


def _entry(db, page, rect=(0.0, 0.25, 1.0, 0.25), rendition_id=None) -> Document:
    entry = Document(
        name="entry", parent_id=page.id, path=page.path,
        region_in_parent=NodeRegion(rect=list(rect), rendition_id=rendition_id),
    )
    db.save(entry)
    return entry


class TestTheLengthInvariant:
    """Checked first because everything else depends on it."""

    def test_the_list_length_never_changes(self, db, tmp_path, test_package):
        page = _page(db, tmp_path)
        entry = _entry(db, page)
        files = [page.path, page.path, page.path]
        documents = [{"id": page.id}, {"id": entry.id}, {"id": page.id}]

        out = _substitute_region_crops(files, documents, str(test_package))

        assert len(out) == len(files)

    def test_a_refused_crop_still_keeps_alignment(self, db, tmp_path, test_package):
        """The dangerous case: a node we CANNOT crop must keep its slot."""
        page = _page(db, tmp_path)
        blocked = _entry(db, page, rendition_id="rend-rotated")
        files = [page.path, page.path]
        documents = [{"id": blocked.id}, {"id": page.id}]

        out = _substitute_region_crops(files, documents, str(test_package))

        assert len(out) == 2
        assert out[0] == page.path  # falls back to the parent, in place
        assert out[1] == page.path

    def test_documents_shorter_than_files_does_not_truncate(self, db, tmp_path, test_package):
        page = _page(db, tmp_path)
        files = [page.path, page.path, page.path]

        out = _substitute_region_crops(files, [{"id": page.id}], str(test_package))

        assert len(out) == 3


class TestSubstitution:
    def test_an_entry_gets_its_own_crop(self, db, tmp_path, test_package):
        page = _page(db, tmp_path)
        entry = _entry(db, page)

        out = _substitute_region_crops(
            [page.path], [{"id": entry.id}], str(test_package)
        )

        assert out[0] != page.path
        assert Path(out[0]).is_file()

    def test_the_substituted_file_is_the_persisted_rendition(self, db, tmp_path, test_package):
        page = _page(db, tmp_path)
        entry = _entry(db, page)

        out = _substitute_region_crops(
            [page.path], [{"id": entry.id}], str(test_package)
        )

        rendition = db.query(Rendition, document_id=entry.id)[0]
        assert rendition.role == REGION_CROP_ROLE
        assert out[0] == rendition.path

    def test_only_the_region_node_is_swapped(self, db, tmp_path, test_package):
        page = _page(db, tmp_path)
        entry = _entry(db, page)

        out = _substitute_region_crops(
            [page.path, page.path],
            [{"id": page.id}, {"id": entry.id}],
            str(test_package),
        )

        assert out[0] == page.path      # a plain page is untouched
        assert out[1] != page.path      # the entry is narrowed


class TestTheOrdinaryPathIsUntouched:
    """The regression that would actually matter."""

    def test_plain_pages_pass_through_unchanged(self, db, tmp_path, test_package):
        page = _page(db, tmp_path)
        files = [page.path, page.path]

        out = _substitute_region_crops(
            files, [{"id": page.id}, {"id": page.id}], str(test_package)
        )

        assert out == files

    def test_no_documents_is_a_no_op(self, db, tmp_path, test_package):
        page = _page(db, tmp_path)
        assert _substitute_region_crops([page.path], [], str(test_package)) == [page.path]

    def test_no_library_path_is_a_no_op(self, db, tmp_path):
        page = _page(db, tmp_path)
        assert _substitute_region_crops([page.path], [{"id": page.id}], "") == [page.path]

    def test_an_unknown_document_id_is_skipped_not_fatal(self, db, tmp_path, test_package):
        page = _page(db, tmp_path)
        out = _substitute_region_crops(
            [page.path], [{"id": "does-not-exist"}], str(test_package)
        )
        assert out == [page.path]


class TestRefusalIsVisible:
    def test_a_declined_crop_is_logged_loudly(self, db, tmp_path, test_package, caplog):
        """Falling back to the full page is defensible; doing it SILENTLY is
        not — the result then covers more than the caller asked for."""
        import logging

        page = _page(db, tmp_path)
        blocked = _entry(db, page, rendition_id="rend-rotated")

        with caplog.at_level(logging.WARNING):
            _substitute_region_crops(
                [page.path], [{"id": blocked.id}], str(test_package)
            )

        assert any("FULL parent image" in r.getMessage() for r in caplog.records)
