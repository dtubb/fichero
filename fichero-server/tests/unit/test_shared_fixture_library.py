"""The shared test-fixtures library and the --with-files seeder extension.

Covers #4248: the canonical specimen tree at <repo>/test-fixtures/files, the
single Python resolver (tests.fixture_paths), and seed_test_library.py's
--with-files mode that turns those specimens into file-backed documents.
"""

from __future__ import annotations

import filecmp

import pytest

from tests.fixture_paths import SAMPLE_FILES_DIR, sample_file
from tests.integration._seedlib import seed


class TestFixtureTree:
    def test_sample_dir_exists_at_repo_root(self):
        assert SAMPLE_FILES_DIR.is_dir()
        assert SAMPLE_FILES_DIR.parent.name == "test-fixtures"

    @pytest.mark.parametrize(
        "name",
        [
            "sample.pdf", "multipage.pdf", "sample.jpg", "sample.png",
            "sample.heic", "sample.docx", "sample.doc", "sample.md",
            "sample.txt", "iiif_manifest.json",
            # corrupt / edge specimens
            "sample_corrupted.docx", "empty.txt", "wrong_extension.pdf",
        ],
    )
    def test_specimen_present(self, name):
        assert sample_file(name).is_file()

    def test_resolver_raises_on_missing_specimen(self):
        with pytest.raises(FileNotFoundError):
            sample_file("no-such-fixture.xyz")

    def test_empty_specimen_is_zero_bytes(self):
        assert sample_file("empty.txt").stat().st_size == 0

    def test_wrong_extension_specimen_is_png_bytes(self):
        assert sample_file("wrong_extension.pdf").read_bytes().startswith(b"\x89PNG")

    def test_multipage_pdf_has_three_pages(self):
        fitz = pytest.importorskip("fitz")
        with fitz.open(sample_file("multipage.pdf")) as doc:
            assert doc.page_count == 3

    def test_size_discipline_no_fixture_over_one_megabyte(self):
        for path in SAMPLE_FILES_DIR.iterdir():
            assert path.stat().st_size < 1_000_000, f"fixture too big: {path.name}"


class TestSeederWithFiles:
    def test_default_seed_unchanged(self, tmp_path):
        summary = seed(tmp_path / "plain.fichero")
        assert summary["expected"]["workflows"] == 1
        assert summary["expected"]["children_of_collection"] == 2

    def test_with_files_adds_real_file_backed_documents(self, tmp_path):
        lib = tmp_path / "seeded.fichero"
        summary = seed(lib, with_files=True)
        expected = summary["expected"]
        assert expected["workflows"] == 3
        assert expected["children_of_collection"] == 5
        # copies are byte-identical to the shared specimens
        assert filecmp.cmp(
            lib / "files" / "test-doc-fixture-pdf.pdf",
            sample_file("multipage.pdf"),
            shallow=False,
        )
        assert filecmp.cmp(
            lib / "files" / "test-doc-fixture-jpg.jpg",
            sample_file("sample.jpg"),
            shallow=False,
        )


class TestSeederFull:
    """The --full synthetic library (2026-08-04 decisions): one library for all
    live consumers, deterministic by construction and proven so."""

    def test_full_seed_covers_every_doc_type_and_the_alias_kind(self, tmp_path):
        from fichero_server.db import db_manager
        from fichero_server.models import Document

        from tests.integration._seedlib import seeder_module

        lib = tmp_path / "full.fichero"
        seeder_module.seed(lib, full=True)
        db = db_manager.get_database(lib)
        try:
            docs = db.all(Document)
            doc_types = {d.doc_type.value for d in docs}
            node_kinds = {d.node_kind for d in docs}
            attrs_by_name = {d.name: d.attributes for d in docs}
        finally:
            db_manager.close_all()
        assert doc_types == {"folder", "group", "file", "page", "chunk"}
        assert "alias" in node_kinds
        # the read-only system folder is really read-only + system
        assert attrs_by_name["System Fixtures"]["read_only"] is True
        assert attrs_by_name["System Fixtures"]["system"] is True

    def test_full_seed_has_both_runnable_workflow_shapes(self, tmp_path):
        from fichero_server.db import db_manager
        from fichero_server.models import Workflow

        from tests.integration._seedlib import seeder_module

        lib = tmp_path / "full.fichero"
        seeder_module.seed(lib, full=True)
        db = db_manager.get_database(lib)
        try:
            formats = {w.format for w in db.all(Workflow)}
            nodes_wf = [w for w in db.all(Workflow) if w.format == "nodes" and w.nodes]
        finally:
            db_manager.close_all()
        assert {"steps", "nodes"} <= formats
        assert nodes_wf, "the nodes-shape workflow must carry real nodes"

    def test_full_ids_are_uuid5_stable(self):
        import uuid

        from tests.integration._seedlib import seeder_module

        # A pinned value: if the namespace or key scheme changes, every consumer
        # holding seeded ids breaks — this makes that change loud and deliberate.
        assert seeder_module._sid("folder-inbox") == str(
            uuid.uuid5(
                uuid.NAMESPACE_URL, "fichero://seed-test-library/folder-inbox"
            )
        )

    def test_self_test_proves_determinism_and_can_fire(self):
        from tests.integration._seedlib import seeder_module

        # The seeder's own proof: builds twice, compares structurally
        # (timestamps included — they are pinned), and asserts a mutated copy
        # is DETECTED, so the comparison is known capable of failing.
        assert seeder_module._self_test() == 0
