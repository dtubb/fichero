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
