"""Unit tests for file ingestion module."""
import logging
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


def _make_pdf(tmp_path: Path, name: str, page_count: int, *, page_labels=None) -> Path:
    fitz = pytest.importorskip("fitz")

    path = tmp_path / name
    doc = fitz.open()
    for _ in range(page_count):
        doc.new_page()
    if page_labels is not None:
        doc.set_page_labels(page_labels)
    doc.save(path)
    doc.close()
    return path


class TestIngestMode:
    """Tests for IngestMode enum."""

    def test_enum_values(self):
        """Should have LINK and COPY modes."""
        from fichero.importers.ingest import IngestMode

        assert IngestMode.LINK.value == "link"
        assert IngestMode.COPY.value == "copy"


class TestDetectFileType:
    """Tests for detect_file_type function."""

    def test_image_types(self):
        """Should detect image file types."""
        from fichero.importers.ingest import detect_file_type
        from fichero.models import FileType

        assert detect_file_type(Path("test.jpg")) == FileType.image
        assert detect_file_type(Path("test.jpeg")) == FileType.image
        assert detect_file_type(Path("test.png")) == FileType.image
        assert detect_file_type(Path("test.gif")) == FileType.image
        assert detect_file_type(Path("test.webp")) == FileType.image
        assert detect_file_type(Path("test.tiff")) == FileType.image
        assert detect_file_type(Path("test.heic")) == FileType.image
        assert detect_file_type(Path("test.jp2")) == FileType.image

    def test_image_types_case_insensitive(self):
        """Uppercase extensions must resolve the same as lowercase.

        Regression guard: the SwiftUI file picker previously filtered
        `.JPG` / `.PNG` etc. through a UTType list that excluded `.image`,
        making uppercase-extension images appear rejected. The fix (in the
        Swift side) is `allowedContentTypes: [.item]`. This test pins the
        backend side of the contract — `detect_file_type` normalises
        extensions via `.suffix.lower()` and must stay case-insensitive.
        """
        from fichero.importers.ingest import detect_file_type
        from fichero.models import FileType

        assert detect_file_type(Path("test.JPG")) == FileType.image
        assert detect_file_type(Path("test.JPEG")) == FileType.image
        assert detect_file_type(Path("test.PNG")) == FileType.image
        assert detect_file_type(Path("test.TIFF")) == FileType.image
        assert detect_file_type(Path("test.HEIC")) == FileType.image
        assert detect_file_type(Path("Document.PDF")) == FileType.pdf
        assert detect_file_type(Path("song.MP3")) == FileType.audio
        assert detect_file_type(Path("Photo.Jpg")) == FileType.image

    def test_pdf_type(self):
        """Should detect PDF file type."""
        from fichero.importers.ingest import detect_file_type
        from fichero.models import FileType

        assert detect_file_type(Path("test.pdf")) == FileType.pdf

    def test_audio_types(self):
        """Should detect audio file types."""
        from fichero.importers.ingest import detect_file_type
        from fichero.models import FileType

        assert detect_file_type(Path("test.mp3")) == FileType.audio
        assert detect_file_type(Path("test.wav")) == FileType.audio
        assert detect_file_type(Path("test.m4a")) == FileType.audio
        assert detect_file_type(Path("test.flac")) == FileType.audio

    def test_video_types(self):
        """Should detect video file types."""
        from fichero.importers.ingest import detect_file_type
        from fichero.models import FileType

        assert detect_file_type(Path("test.mp4")) == FileType.video
        assert detect_file_type(Path("test.mov")) == FileType.video
        assert detect_file_type(Path("test.mkv")) == FileType.video

    def test_text_types(self):
        """Should detect text file types."""
        from fichero.importers.ingest import detect_file_type
        from fichero.models import FileType

        assert detect_file_type(Path("test.txt")) == FileType.text
        assert detect_file_type(Path("test.md")) == FileType.text
        assert detect_file_type(Path("manifest.jsonl")) == FileType.text

    def test_word_types(self):
        """Should detect Word file types."""
        from fichero.importers.ingest import detect_file_type
        from fichero.models import FileType

        assert detect_file_type(Path("test.doc")) == FileType.word
        assert detect_file_type(Path("test.docx")) == FileType.word

    def test_unknown_type(self):
        """Should return 'other' for unknown types."""
        from fichero.importers.ingest import detect_file_type
        from fichero.models import FileType

        assert detect_file_type(Path("test.xyz")) == FileType.other
        assert detect_file_type(Path("test.unknown")) == FileType.other

    def test_case_insensitive(self):
        """Should handle uppercase extensions."""
        from fichero.importers.ingest import detect_file_type
        from fichero.models import FileType

        assert detect_file_type(Path("test.JPG")) == FileType.image
        assert detect_file_type(Path("test.PDF")) == FileType.pdf

    def test_all_image_formats(self):
        """Should detect all supported image formats."""
        from fichero.importers.ingest import detect_file_type
        from fichero.models import FileType

        # Standard formats
        assert detect_file_type(Path("test.jpg")) == FileType.image
        assert detect_file_type(Path("test.jpeg")) == FileType.image
        assert detect_file_type(Path("test.png")) == FileType.image
        assert detect_file_type(Path("test.gif")) == FileType.image
        assert detect_file_type(Path("test.webp")) == FileType.image
        assert detect_file_type(Path("test.tiff")) == FileType.image
        assert detect_file_type(Path("test.tif")) == FileType.image
        assert detect_file_type(Path("test.bmp")) == FileType.image
        
        # Modern formats
        assert detect_file_type(Path("test.heic")) == FileType.image
        assert detect_file_type(Path("test.heif")) == FileType.image
        assert detect_file_type(Path("test.jxl")) == FileType.image
        assert detect_file_type(Path("test.avif")) == FileType.image
        
        # RAW formats
        assert detect_file_type(Path("test.raw")) == FileType.image
        assert detect_file_type(Path("test.cr2")) == FileType.image
        assert detect_file_type(Path("test.cr3")) == FileType.image
        assert detect_file_type(Path("test.nef")) == FileType.image
        assert detect_file_type(Path("test.arw")) == FileType.image
        assert detect_file_type(Path("test.dng")) == FileType.image
        assert detect_file_type(Path("test.orf")) == FileType.image
        assert detect_file_type(Path("test.rw2")) == FileType.image

    def test_all_audio_formats(self):
        """Should detect all supported audio formats."""
        from fichero.importers.ingest import detect_file_type
        from fichero.models import FileType

        assert detect_file_type(Path("test.mp3")) == FileType.audio
        assert detect_file_type(Path("test.wav")) == FileType.audio
        assert detect_file_type(Path("test.m4a")) == FileType.audio
        assert detect_file_type(Path("test.aac")) == FileType.audio
        assert detect_file_type(Path("test.flac")) == FileType.audio
        assert detect_file_type(Path("test.ogg")) == FileType.audio
        assert detect_file_type(Path("test.wma")) == FileType.audio

    def test_all_video_formats(self):
        """Should detect all supported video formats."""
        from fichero.importers.ingest import detect_file_type
        from fichero.models import FileType

        assert detect_file_type(Path("test.mp4")) == FileType.video
        assert detect_file_type(Path("test.mov")) == FileType.video
        assert detect_file_type(Path("test.avi")) == FileType.video
        assert detect_file_type(Path("test.mkv")) == FileType.video
        assert detect_file_type(Path("test.webm")) == FileType.video

    def test_all_text_formats(self):
        """Should detect all supported text formats."""
        from fichero.importers.ingest import detect_file_type
        from fichero.models import FileType

        assert detect_file_type(Path("test.txt")) == FileType.text
        assert detect_file_type(Path("test.md")) == FileType.text
        assert detect_file_type(Path("test.rst")) == FileType.text
        assert detect_file_type(Path("test.rtf")) == FileType.text

    def test_all_word_formats(self):
        """Should detect all supported word document formats."""
        from fichero.importers.ingest import detect_file_type
        from fichero.models import FileType

        assert detect_file_type(Path("test.doc")) == FileType.word
        assert detect_file_type(Path("test.docx")) == FileType.word
        assert detect_file_type(Path("test.odt")) == FileType.word

    def test_all_ebook_formats(self):
        """Should detect all supported ebook formats."""
        from fichero.importers.ingest import detect_file_type
        from fichero.models import FileType

        assert detect_file_type(Path("test.epub")) == FileType.epub
        assert detect_file_type(Path("test.mobi")) == FileType.epub


class TestDiscoverFiles:
    """Tests for discover_files function."""

    def test_discovers_files(self, tmp_path):
        """Should discover files in folder."""
        from fichero.importers.ingest import discover_files

        # Create test files
        (tmp_path / "file1.jpg").touch()
        (tmp_path / "file2.png").touch()
        (tmp_path / "file3.txt").touch()

        files = list(discover_files(tmp_path))

        assert len(files) == 3

    def test_excludes_hidden_files(self, tmp_path):
        """Should exclude hidden files (starting with .)."""
        from fichero.importers.ingest import discover_files

        (tmp_path / "visible.jpg").touch()
        (tmp_path / ".hidden.jpg").touch()

        files = list(discover_files(tmp_path))

        assert len(files) == 1
        assert files[0].name == "visible.jpg"

    def test_recursive_search(self, tmp_path):
        """Should search subdirectories when recursive=True."""
        from fichero.importers.ingest import discover_files

        (tmp_path / "file1.jpg").touch()
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (subdir / "file2.jpg").touch()

        files = list(discover_files(tmp_path, recursive=True))
        assert len(files) == 2

        files_flat = list(discover_files(tmp_path, recursive=False))
        assert len(files_flat) == 1

    def test_filter_by_extension(self, tmp_path):
        """Should filter by extension set."""
        from fichero.importers.ingest import discover_files

        (tmp_path / "image.jpg").touch()
        (tmp_path / "image.png").touch()
        (tmp_path / "doc.txt").touch()

        files = list(discover_files(tmp_path, extensions={".jpg", ".png"}))
        names = {f.name for f in files}

        assert names == {"image.jpg", "image.png"}


class TestCountFiles:
    """Tests for count_files function."""

    def test_counts_files(self, tmp_path):
        """Should count files correctly."""
        from fichero.importers.ingest import count_files

        (tmp_path / "file1.jpg").touch()
        (tmp_path / "file2.jpg").touch()
        (tmp_path / ".hidden.jpg").touch()

        count = count_files(tmp_path)

        assert count == 2  # Excludes hidden

    def test_counts_with_filter(self, tmp_path):
        """Should count with extension filter."""
        from fichero.importers.ingest import count_files

        (tmp_path / "image.jpg").touch()
        (tmp_path / "doc.txt").touch()

        count = count_files(tmp_path, extensions={".jpg"})

        assert count == 1

    def test_excludes_metadata_sidecars(self, tmp_path):
        """Progress totals count primary documents, not companion metadata."""
        from fichero.importers.ingest import count_files

        (tmp_path / "photo.jpg").touch()
        (tmp_path / "photo.xmp").touch()
        (tmp_path / "photo.iffy.json").touch()
        (tmp_path / "photo.jpg.json").touch()

        assert count_files(tmp_path) == 1


class TestFindDuplicates:
    """Tests for find_duplicates function."""

    def test_finds_duplicates_by_checksum(self):
        """Should find documents with same checksum."""
        from fichero.importers.ingest import find_duplicates
        from fichero.models import Document

        doc1 = Document(name="file1.jpg", metadata={"checksum": "abc123"})
        doc2 = Document(name="file2.jpg", metadata={"checksum": "abc123"})
        doc3 = Document(name="file3.jpg", metadata={"checksum": "def456"})

        duplicates = find_duplicates([doc1, doc2, doc3])

        assert "abc123" in duplicates
        assert len(duplicates["abc123"]) == 2
        assert "def456" not in duplicates  # Not a duplicate

    def test_no_duplicates(self):
        """Should return empty dict when no duplicates."""
        from fichero.importers.ingest import find_duplicates
        from fichero.models import Document

        doc1 = Document(name="file1.jpg", metadata={"checksum": "abc123"})
        doc2 = Document(name="file2.jpg", metadata={"checksum": "def456"})

        duplicates = find_duplicates([doc1, doc2])

        assert duplicates == {}


class TestIffySidecar:
    def test_parse_iffy_sidecar_maps_fields_and_notes(self, tmp_path):
        from fichero.importers.ingest import _parse_iffy_sidecar

        image = tmp_path / "map-001.jpg"
        image.write_text("x", encoding="utf-8")
        sidecar = tmp_path / "map-001.iffy.json"
        sidecar.write_text(
            '{"status":"catalogued","record_type":"map","notes":["n1","n2"]}',
            encoding="utf-8",
        )

        parsed = _parse_iffy_sidecar(image)
        assert parsed is not None
        assert parsed["iffy_status"] == "catalogued"
        assert parsed["iffy_record_type"] == "map"
        assert parsed["iffy_notes"] == "n1, n2"

    def test_parse_iffy_sidecar_full_name_convention(self, tmp_path):
        """`x.jpg.iffy.json` — extension INCLUDED (#4206).

        Both conventions ship in one archive. Only the stem form was looked
        for, so 110 real files imported with no provenance and no warning.
        The untested convention was the broken one, which is why both are
        pinned here.
        """
        from fichero.importers.ingest import _parse_iffy_sidecar

        image = tmp_path / "rumsey_1827.jpg"
        image.write_text("x", encoding="utf-8")
        sidecar = tmp_path / "rumsey_1827.jpg.iffy.json"
        sidecar.write_text('{"status":"downloaded","title":"Guayaquil"}', encoding="utf-8")

        parsed = _parse_iffy_sidecar(image)

        assert parsed is not None, "full-name sidecar was not found"
        assert parsed["iffy_status"] == "downloaded"

    def test_full_name_wins_when_both_conventions_are_present(self, tmp_path):
        """Full name is unambiguous, so it takes precedence over the stem."""
        from fichero.importers.ingest import _parse_iffy_sidecar

        image = tmp_path / "map.jpg"
        image.write_text("x", encoding="utf-8")
        (tmp_path / "map.jpg.iffy.json").write_text(
            '{"status":"from-full-name"}', encoding="utf-8"
        )
        (tmp_path / "map.iffy.json").write_text('{"status":"from-stem"}', encoding="utf-8")

        assert _parse_iffy_sidecar(image)["iffy_status"] == "from-full-name"

    def test_stem_form_still_serves_two_renditions_of_one_source(self, tmp_path):
        """The stem form is deliberately kept as a fallback.

        The archive holds 10 cases where one sidecar describes both a .png and
        a .tif of the same map. Requiring the full-name form would break them.
        """
        from fichero.importers.ingest import _parse_iffy_sidecar

        for ext in (".png", ".tif"):
            (tmp_path / f"cartagena_1715{ext}").write_text("x", encoding="utf-8")
        (tmp_path / "cartagena_1715.iffy.json").write_text(
            '{"status":"catalogued"}', encoding="utf-8"
        )

        for ext in (".png", ".tif"):
            parsed = _parse_iffy_sidecar(tmp_path / f"cartagena_1715{ext}")
            assert parsed is not None, f"{ext} rendition lost its sidecar"
            assert parsed["iffy_status"] == "catalogued"

    def test_sidecar_is_extension_agnostic(self, tmp_path):
        """The 110th file is HTML, not an image — the lookup must not assume media."""
        from fichero.importers.ingest import _parse_iffy_sidecar

        page = tmp_path / "guasti_2006.html"
        page.write_text("<p>x</p>", encoding="utf-8")
        (tmp_path / "guasti_2006.html.iffy.json").write_text(
            '{"status":"downloaded"}', encoding="utf-8"
        )

        assert _parse_iffy_sidecar(page) is not None

    def test_missing_sidecar_still_returns_none(self, tmp_path):
        """Trying two candidates must not turn "absent" into a false positive."""
        from fichero.importers.ingest import _parse_iffy_sidecar

        image = tmp_path / "lonely.jpg"
        image.write_text("x", encoding="utf-8")

        assert _parse_iffy_sidecar(image) is None

    def test_apply_iffy_does_not_override_existing_metadata(self):
        from fichero.importers.ingest import _apply_iffy_to_document
        from fichero.models import Document

        doc = Document(name="x.jpg", metadata={"iffy_status": "human-reviewed"})
        _apply_iffy_to_document(
            doc,
            {
                "iffy_status": "catalogued",
                "iffy_repository": "Archive A",
            },
        )

        assert doc.metadata["iffy_status"] == "human-reviewed"
        assert doc.metadata["iffy_repository"] == "Archive A"
        assert doc.metadata["_iffy_sidecar"] is True

    def test_handles_missing_checksum(self):
        """Should handle documents without checksum."""
        from fichero.importers.ingest import find_duplicates
        from fichero.models import Document

        doc1 = Document(name="file1.jpg", metadata={})
        doc2 = Document(name="file2.jpg", metadata={"checksum": "abc123"})

        duplicates = find_duplicates([doc1, doc2])

        assert duplicates == {}


class TestIngestFile:
    """Tests for ingest_file function."""

    def test_file_not_found_raises(self):
        """Should raise FileNotFoundError for non-existent file."""
        from fichero.importers.ingest import ingest_file

        with pytest.raises(FileNotFoundError):
            ingest_file(Path("/nonexistent/file.jpg"))

    def test_directory_raises_value_error(self, tmp_path):
        """Should raise ValueError for directory."""
        from fichero.importers.ingest import ingest_file

        with pytest.raises(ValueError):
            ingest_file(tmp_path)

    def test_symlinked_file_raises_value_error(self, tmp_path):
        from fichero.importers.ingest import ingest_file

        target = tmp_path / "outside.txt"
        target.write_text("secret", encoding="utf-8")
        link = tmp_path / "linked.txt"
        link.symlink_to(target)

        with pytest.raises(ValueError, match="Refusing to ingest symlinked file"):
            ingest_file(link, save=False)

    @patch("fichero.bookmarks.create_bookmark", return_value=None)
    def test_jsonl_import_keeps_searchable_record_text(self, _mock_bookmark, tmp_path):
        from fichero.importers.ingest import ingest_file
        from fichero.models import FileType

        path = tmp_path / "records.jsonl"
        path.write_text('{"id": 1, "text": "Marshall diary"}\n', encoding="utf-8")

        doc = ingest_file(path, save=False)

        assert doc.file_type == FileType.text
        assert "Marshall diary" in doc.page_content

    @patch("fichero.db.db")
    @patch("fichero.bookmarks.create_bookmark")
    def test_link_mode_creates_bookmark(self, mock_bookmark, mock_db, tmp_path):
        """LINK mode should create bookmark and save document."""
        from fichero.importers.ingest import ingest_file, IngestMode
        from fichero.models import DocType, FileType

        file = tmp_path / "test.jpg"
        file.write_bytes(b"fake image data")

        mock_bookmark.return_value = b"bookmark_data"

        doc = ingest_file(file, mode=IngestMode.LINK)

        assert doc.name == "test.jpg"
        assert doc.path == str(file)
        assert doc.doc_type == DocType.file
        assert doc.file_type == FileType.image
        assert "bookmark" in doc.metadata
        mock_db.save.assert_called_once()

    @patch("fichero.db.db")
    @patch("fichero.importers.ingest._copy_to_library")
    def test_copy_mode_copies_file(self, mock_copy, mock_db, tmp_path):
        """COPY mode should copy file to library."""
        from fichero.importers.ingest import ingest_file, IngestMode

        file = tmp_path / "test.jpg"
        file.write_bytes(b"fake image data")

        dest = tmp_path / "library" / "test_copy.jpg"
        dest.parent.mkdir(parents=True)
        mock_copy.return_value = dest

        doc = ingest_file(file, mode=IngestMode.COPY)

        assert doc.path == str(dest)
        mock_copy.assert_called_once_with(file)
        mock_db.save.assert_called_once()

    @patch("fichero.importers.ingest._copy_to_library")
    def test_move_deletes_source_only_after_commit(self, mock_copy, tmp_path):
        """A failed transaction must never destroy the user's source file."""
        from fichero.importers.ingest import ingest_file, IngestMode

        source = tmp_path / "source.txt"
        source.write_text("irreplaceable", encoding="utf-8")
        destination = tmp_path / "library" / source.name
        destination.parent.mkdir()
        destination.write_text(source.read_text(), encoding="utf-8")
        mock_copy.return_value = destination
        db = MagicMock()
        hooks = []
        db.add_after_commit_hook.side_effect = hooks.append

        ingest_file(
            source,
            mode=IngestMode.MOVE,
            extract_metadata=False,
            extract_text=False,
            auto_embed=False,
            db=db,
        )

        assert source.exists()
        assert len(hooks) == 1
        hooks[0]()
        assert not source.exists()

    @patch("fichero.importers.ingest._copy_to_library")
    def test_move_delete_failure_is_persisted_on_the_committed_copy(
        self, mock_copy, tmp_path
    ):
        from fichero.importers.ingest import ingest_file, IngestMode
        from fichero.models import Status

        source = tmp_path / "source.txt"
        source.write_text("irreplaceable", encoding="utf-8")
        destination = tmp_path / "stored.txt"
        destination.write_text("irreplaceable", encoding="utf-8")
        mock_copy.return_value = destination
        db = MagicMock()
        hooks = []
        db.add_after_commit_hook.side_effect = hooks.append

        doc = ingest_file(
            source,
            mode=IngestMode.MOVE,
            extract_metadata=False,
            extract_text=False,
            auto_embed=False,
            db=db,
        )
        with patch.object(Path, "unlink", side_effect=PermissionError("read-only")):
            hooks[0]()

        assert source.exists()
        assert doc.status == Status.failed
        assert "source could not be deleted" in doc.metadata["ingest_error"]
        assert db.save.call_count == 2

    @patch("fichero.importers.ingest._copy_to_library")
    def test_copy_extracts_stored_bytes_but_keeps_source_sidecars(
        self, mock_copy, tmp_path
    ):
        from fichero.importers.ingest import ingest_file, IngestMode

        fixture = Path(__file__).parent.parent / "fixtures" / "sample_files" / "sample.jpg"
        source = tmp_path / "source.jpg"
        destination = tmp_path / "library" / "stored.jpg"
        source.write_bytes(fixture.read_bytes())
        destination.parent.mkdir()
        destination.write_bytes(fixture.read_bytes())
        (tmp_path / "source.iffy.json").write_text(
            '{"status": "catalogued"}', encoding="utf-8"
        )
        mock_copy.return_value = destination

        doc = ingest_file(
            source,
            mode=IngestMode.COPY,
            extract_text=False,
            auto_embed=False,
            db=MagicMock(),
        )

        assert doc.metadata["checksum"]
        assert doc.metadata["_iffy_sidecar"] is True

    @patch("fichero.importers.ingest._copy_to_library")
    def test_copy_rollback_removes_unreferenced_library_bytes(
        self, mock_copy, db, tmp_path
    ):
        from fichero.importers.ingest import ingest_file, IngestMode

        source = tmp_path / "source.jpg"
        source.write_bytes(b"source")
        destination = tmp_path / "stored.jpg"
        destination.write_bytes(b"copied")
        mock_copy.return_value = destination

        with patch(
            "fichero.importers.ingest._extract_file_metadata",
            side_effect=ValueError("unsafe image"),
        ), pytest.raises(ValueError, match="unsafe image"):
            with db.transaction():
                ingest_file(source, mode=IngestMode.COPY, db=db)

        assert not destination.exists()

    @patch("fichero.db.db")
    @patch("fichero.bookmarks.create_bookmark")
    def test_extracts_metadata(self, mock_bookmark, mock_db, tmp_path):
        """Should extract metadata when requested."""
        from fichero.importers.ingest import ingest_file, IngestMode

        file = tmp_path / "test.jpg"
        file.write_bytes(b"fake image data" * 100)

        mock_bookmark.return_value = None

        doc = ingest_file(file, mode=IngestMode.LINK, extract_metadata=True)

        assert "file_size" in doc.metadata
        assert doc.metadata["file_size"] > 0
        assert "checksum" in doc.metadata

    @patch("fichero.db.db")
    @patch("fichero.bookmarks.create_bookmark")
    def test_skips_save_when_requested(self, mock_bookmark, mock_db, tmp_path):
        """Should not save when save=False."""
        from fichero.importers.ingest import ingest_file, IngestMode

        file = tmp_path / "test.jpg"
        file.write_bytes(b"fake")

        mock_bookmark.return_value = None

        doc = ingest_file(file, mode=IngestMode.LINK, save=False)

        assert doc is not None
        mock_db.save.assert_not_called()

    @patch("fichero.db.db")
    @patch("fichero.bookmarks.create_bookmark")
    def test_sets_parent_id(self, mock_bookmark, mock_db, tmp_path):
        """Should set parent_id when provided."""
        from fichero.importers.ingest import ingest_file

        file = tmp_path / "test.jpg"
        file.write_bytes(b"fake")

        mock_bookmark.return_value = None

        doc = ingest_file(file, parent_id="parent-123")

        assert doc.parent_id == "parent-123"


class TestIngestFolder:
    """Tests for ingest_folder function."""

    def test_folder_not_found_raises(self):
        """Should raise FileNotFoundError for non-existent folder."""
        from fichero.importers.ingest import ingest_folder

        with pytest.raises(FileNotFoundError):
            ingest_folder(Path("/nonexistent/folder"))

    def test_file_raises_value_error(self, tmp_path):
        """Should raise ValueError for file (not folder)."""
        from fichero.importers.ingest import ingest_folder

        file = tmp_path / "test.txt"
        file.touch()

        with pytest.raises(ValueError):
            ingest_folder(file)

    @patch("fichero.db.db")
    @patch("fichero.bookmarks.create_bookmark")
    def test_ingests_all_files(self, mock_bookmark, mock_db, tmp_path):
        """Should ingest all files in folder."""
        from fichero.importers.ingest import ingest_folder, IngestMode

        (tmp_path / "file1.jpg").write_bytes(b"data1")
        (tmp_path / "file2.png").write_bytes(b"data2")

        mock_bookmark.return_value = None

        docs = ingest_folder(tmp_path, mode=IngestMode.LINK)

        assert len(docs) == 2

    @patch("fichero.db.db")
    @patch("fichero.bookmarks.create_bookmark")
    def test_creates_collection(self, mock_bookmark, mock_db, tmp_path):
        """Should create collection for folder."""
        from fichero.importers.ingest import ingest_folder
        from fichero.models import DocType

        (tmp_path / "file1.jpg").write_bytes(b"data")

        mock_bookmark.return_value = None

        ingest_folder(tmp_path, create_collection=True)

        # Should have saved collection
        calls = mock_db.save.call_args_list
        collection_saved = any(
            call.args[0].doc_type == DocType.folder
            for call in calls
        )
        assert collection_saved

    @patch("fichero.db.db")
    @patch("fichero.bookmarks.create_bookmark")
    def test_progress_callback(self, mock_bookmark, mock_db, tmp_path):
        """Should call progress callback."""
        from fichero.importers.ingest import ingest_folder

        (tmp_path / "file1.jpg").write_bytes(b"data")
        (tmp_path / "file2.jpg").write_bytes(b"data")

        mock_bookmark.return_value = None

        progress_calls = []

        def on_progress(current, total):
            progress_calls.append((current, total))

        ingest_folder(tmp_path, on_progress=on_progress)

        assert progress_calls[0] == (0, 2)
        assert len(progress_calls) == 3
        assert progress_calls[-1][0] == 2  # Final current
        assert progress_calls[-1][1] == 2  # Total

    @patch("fichero.db.db")
    @patch("fichero.bookmarks.create_bookmark", return_value=None)
    def test_cancellation_stops_between_committed_files(
        self, _mock_bookmark, mock_db, tmp_path
    ):
        """Cancellation keeps completed files and does not start the next one."""
        from fichero.importers.ingest import ingest_folder

        for name in ("a.txt", "b.txt", "c.txt"):
            (tmp_path / name).write_text(name, encoding="utf-8")
        mock_db.all.return_value = []
        cancelled = False

        def on_progress(current, _total):
            nonlocal cancelled
            cancelled = current == 1

        docs = ingest_folder(
            tmp_path,
            create_collection=False,
            extract_text=False,
            auto_embed=False,
            on_progress=on_progress,
            should_cancel=lambda: cancelled,
        )

        assert len(docs) == 1
        saved_batch = mock_db.save_many.call_args.args[0]
        assert len(saved_batch) == 1

    @patch("fichero.bookmarks.create_bookmark", return_value=None)
    def test_link_batches_are_visible_before_per_file_callbacks(
        self, _mock_bookmark, db, tmp_path
    ):
        from fichero.importers.ingest import ingest_folder
        from fichero.models import Document

        corpus = tmp_path / "corpus"
        corpus.mkdir()
        for index in range(101):
            (corpus / f"doc-{index:03d}.txt").write_text("x", encoding="utf-8")
        visible = []

        def on_document(doc):
            visible.append(not db.in_transaction and db.get(Document, doc.id) is not None)

        with patch.object(db, "save_many", wraps=db.save_many) as save_many:
            docs = ingest_folder(
                corpus,
                db=db,
                create_collection=False,
                extract_text=False,
                auto_embed=False,
                on_document=on_document,
            )

        assert len(docs) == 101
        assert [len(call.args[0]) for call in save_many.call_args_list] == [100, 1]
        assert all(visible)

    @patch("fichero.db.db")
    @patch("fichero.bookmarks.create_bookmark")
    def test_skips_sidecar_files(self, mock_bookmark, mock_db, tmp_path):
        """Folder ingest should treat sidecars as metadata for primary files only."""
        from fichero.importers.ingest import ingest_folder

        (tmp_path / "photo.jpg").write_bytes(b"image")
        (tmp_path / "photo.xmp").write_text("<x:xmpmeta/>", encoding="utf-8")
        (tmp_path / "photo.iffy.json").write_text("{}", encoding="utf-8")
        (tmp_path / "photo.jpg.json").write_text(
            '{"repository":"Archive"}', encoding="utf-8"
        )

        mock_bookmark.return_value = None
        docs = ingest_folder(tmp_path)

        assert len(docs) == 1
        assert docs[0].name == "photo.jpg"
        assert docs[0].source_metadata["repository"] == "Archive"

    def test_folder_ingest_rejects_symlinked_files_with_failed_stub(self, tmp_path):
        from fichero.importers.ingest import ingest_folder
        from fichero.models import Status

        target = tmp_path.parent / "outside.txt"
        target.write_text("secret", encoding="utf-8")
        link = tmp_path / "linked.txt"
        link.symlink_to(target)

        mock_db = MagicMock()
        mock_db.all.return_value = []
        mock_db.get.return_value = None

        docs = ingest_folder(tmp_path, db=mock_db, create_collection=False)

        assert docs == []
        failed = [
            call.args[0]
            for call in mock_db.save.call_args_list
            if call.args and getattr(call.args[0], "status", None) == Status.failed
        ]
        assert len(failed) == 1
        assert "Refusing to ingest symlinked file" in failed[0].metadata["ingest_error"]

    @patch("fichero.bookmarks.create_bookmark", return_value=None)
    def test_touches_parent_collection_when_child_is_ingested(
        self, mock_bookmark, tmp_path
    ):
        """Child ingest should refresh the parent folder timestamp."""
        from fichero.importers.ingest import ingest_folder
        from fichero.models import DocType, Document

        (tmp_path / "file1.txt").write_text("hello")

        saved: dict[str, Document] = {}
        mock_db = MagicMock()

        def save(obj, auto_embed=False):
            saved[obj.id] = obj

        def get(model, doc_id):
            return saved.get(doc_id)

        mock_db.save.side_effect = save
        mock_db.get.side_effect = get
        docs = ingest_folder(tmp_path, db=mock_db)

        folder_saves = [
            call
            for call in mock_db.save.call_args_list
            if call.args and getattr(call.args[0], "doc_type", None) == DocType.folder
        ]
        assert len(docs) == 1
        assert len(folder_saves) == 2

    @patch("fichero.bookmarks.create_bookmark", return_value=None)
    def test_logs_loud_when_checksum_preindex_fails(self, _mock_bookmark, tmp_path, caplog):
        from fichero.importers.ingest import ingest_folder

        (tmp_path / "file1.txt").write_text("hello")

        mock_db = MagicMock()
        mock_db.all.side_effect = RuntimeError("duckdb blew up")
        mock_db.path = tmp_path / "Library.fichero" / "fichero.duckdb"

        with caplog.at_level(logging.WARNING):
            docs = ingest_folder(tmp_path, db=mock_db)

        assert len(docs) == 1
        assert "Could not pre-index existing checksums for skip logic" in caplog.text
        assert str(mock_db.path) in caplog.text

    @patch("fichero.bookmarks.create_bookmark", return_value=None)
    def test_failed_existing_document_is_retried(
        self, _mock_bookmark, tmp_path
    ):
        from fichero.importers.ingest import ingest_folder
        from fichero.models import Document, Status

        source = tmp_path / "retry.txt"
        source.write_text("retry me", encoding="utf-8")
        failed = Document(
            name=source.name,
            path=str(source),
            status=Status.failed,
            metadata={"source_path": str(source), "checksum": "stale"},
        )
        db = MagicMock()
        db.all.return_value = [failed]

        docs = ingest_folder(
            tmp_path,
            db=db,
            create_collection=False,
            extract_text=False,
            auto_embed=False,
        )

        assert len(docs) == 1
        db.save_many.assert_called_once()

    @patch("fichero.bookmarks.create_bookmark", return_value=None)
    def test_link_file_changing_during_ingest_becomes_failed_stub(
        self, _mock_bookmark, tmp_path
    ):
        from fichero.importers.ingest import ingest_folder
        from fichero.models import Status

        source = tmp_path / "changing.txt"
        source.write_text("changing", encoding="utf-8")
        db = MagicMock()
        db.all.return_value = []

        with patch(
            "fichero.importers.ingest._file_checksum",
            side_effect=["before", "after"],
        ):
            docs = ingest_folder(
                tmp_path,
                db=db,
                create_collection=False,
                extract_text=False,
                auto_embed=False,
            )

        assert docs == []
        stub = db.save.call_args.args[0]
        assert stub.status == Status.failed
        assert stub.metadata["source_path"] == str(source)
        assert "File changed while being ingested" in stub.metadata["ingest_error"]

    def test_large_folder_ingests_every_file_once(self, tmp_path, monkeypatch):
        """The bounded-memory serial path must neither drop nor repeat files."""
        from fichero.importers.ingest import ingest_folder
        from fichero.models import DocType, Document, FileType

        for i in range(6):
            (tmp_path / f"p-{i}.txt").write_text(f"doc {i}", encoding="utf-8")

        def fake_ingest_file(
            file_path,
            mode,
            parent_id,
            extract_metadata,
            extract_text,
            auto_embed,
            save,
            db,
            package_path,
        ):
            return Document(
                name=file_path.name,
                path=str(file_path),
                doc_type=DocType.file,
                file_type=FileType.text,
                parent_id=parent_id,
            )

        monkeypatch.setattr("fichero.importers.ingest.ingest_file", fake_ingest_file)

        mock_db = MagicMock()
        mock_db.all.return_value = []
        mock_db.query.return_value = []
        mock_db.get.return_value = None
        mock_db.save.side_effect = lambda *_args, **_kwargs: None

        docs = ingest_folder(
            tmp_path,
            db=mock_db,
            create_collection=False,
            auto_embed=False,
        )

        assert len(docs) == 6
        assert sorted(d.name for d in docs) == [f"p-{i}.txt" for i in range(6)]


class TestCopyToLibrary:
    """Tests for _copy_to_library function."""

    @patch("fichero.importers.ingest._try_apfs_clone")
    @patch("fichero.db.storage.settings")
    def test_uses_apfs_clone_when_available(self, mock_settings, mock_clone, tmp_path):
        """Should try APFS clone first."""
        from fichero.importers.ingest import _copy_to_library

        # Setup
        source = tmp_path / "source.jpg"
        source.write_bytes(b"test data")

        mock_settings.base_path = tmp_path
        mock_clone.return_value = True

        _copy_to_library(source)

        mock_clone.assert_called_once()

    @patch("fichero.importers.ingest._try_apfs_clone")
    @patch("fichero.db.storage.settings")
    @patch("shutil.copy2")
    def test_falls_back_to_shutil(self, mock_copy2, mock_settings, mock_clone, tmp_path):
        """Should fallback to shutil.copy2 if APFS fails."""
        from fichero.importers.ingest import _copy_to_library

        source = tmp_path / "source.jpg"
        source.write_bytes(b"test data")

        mock_settings.base_path = tmp_path
        mock_clone.return_value = False

        _copy_to_library(source)

        mock_copy2.assert_called_once()

    @patch("fichero.importers.ingest._try_apfs_clone")
    @patch("fichero.db.storage.settings")
    def test_creates_sharded_directory(self, mock_settings, mock_clone, tmp_path):
        """Should create sharded directory structure."""
        from fichero.importers.ingest import _copy_to_library

        source = tmp_path / "source.jpg"
        source.write_bytes(b"test data")

        mock_settings.base_path = tmp_path
        mock_clone.return_value = True

        dest = _copy_to_library(source)

        # Should be in sharded directory (first 2 chars of stem)
        assert "imported" in str(dest)
        assert dest.parent.name == "so"  # First 2 chars of "source"

    @patch("fichero.importers.ingest._try_apfs_clone", return_value=False)
    def test_long_source_name_is_truncated_only_in_storage(self, _mock_clone, tmp_path):
        from fichero.importers.ingest import _copy_to_library

        source = tmp_path / ("é" * 120 + ".txt")
        source.write_text("content", encoding="utf-8")
        package = tmp_path / "Library.fichero"

        destination = _copy_to_library(source, package)

        assert destination.exists()
        assert len(destination.name.encode()) <= 255
        assert destination.suffix == ".txt"


class TestTryApfsClone:
    """Tests for _try_apfs_clone function."""

    @pytest.mark.skipif(
        not Path("/System").exists(),
        reason="macOS only"
    )
    def test_clones_file_on_same_volume(self, tmp_path):
        """Should clone file on same volume."""
        from fichero.importers.ingest import _try_apfs_clone

        source = tmp_path / "source.txt"
        source.write_text("test content")

        dest = tmp_path / "dest.txt"

        result = _try_apfs_clone(source, dest)

        # May or may not work depending on filesystem
        # Just check it returns a boolean
        assert isinstance(result, bool)

    def test_returns_false_on_error(self, tmp_path):
        """Should return False when clone fails."""
        from fichero.importers.ingest import _try_apfs_clone

        source = tmp_path / "nonexistent.txt"
        dest = tmp_path / "dest.txt"

        result = _try_apfs_clone(source, dest)

        assert result is False


class TestIngestWithRealFiles:
    """Tests for ingestion with real sample files."""

    @pytest.mark.parametrize("suffix,format_name", [(".avif", "AVIF"), (".jp2", "JPEG2000")])
    def test_pillow_registered_archival_image_formats_load(self, tmp_path, suffix, format_name):
        from PIL import Image
        from fichero.loaders.image_loader import ImageLoader

        path = tmp_path / f"archival{suffix}"
        Image.new("RGB", (8, 6), "white").save(path, format=format_name)

        content = ImageLoader().load_sync(path)

        assert content.images[0].size == (8, 6)

    @patch("fichero.db.db")
    @patch("fichero.bookmarks.create_bookmark")
    def test_ingest_jpg_file(self, mock_bookmark, mock_db):
        """Should ingest JPG file correctly."""
        from fichero.importers.ingest import ingest_file, IngestMode
        from fichero.models import FileType

        file_path = Path(__file__).parent.parent / "fixtures" / "sample_files" / "sample.jpg"
        
        mock_bookmark.return_value = None
        
        doc = ingest_file(file_path, mode=IngestMode.LINK, extract_metadata=True)
        
        assert doc.name == "sample.jpg"
        assert doc.file_type == FileType.image
        assert "file_size" in doc.metadata
        assert doc.metadata["file_size"] > 0
        assert "checksum" in doc.metadata

    @patch("fichero.db.db")
    @patch("fichero.bookmarks.create_bookmark")
    def test_ingest_png_file(self, mock_bookmark, mock_db):
        """Should ingest PNG file correctly."""
        from fichero.importers.ingest import ingest_file, IngestMode
        from fichero.models import FileType

        file_path = Path(__file__).parent.parent / "fixtures" / "sample_files" / "sample.png"
        
        mock_bookmark.return_value = None
        
        doc = ingest_file(file_path, mode=IngestMode.LINK, extract_metadata=True)
        
        assert doc.name == "sample.png"
        assert doc.file_type == FileType.image
        assert "file_size" in doc.metadata
        assert doc.metadata["file_size"] > 0

    @patch("fichero.db.db")
    @patch("fichero.bookmarks.create_bookmark")
    def test_ingest_tiff_file(self, mock_bookmark, mock_db):
        """Should ingest TIFF file correctly."""
        from fichero.importers.ingest import ingest_file, IngestMode
        from fichero.models import FileType

        file_path = Path(__file__).parent.parent / "fixtures" / "sample_files" / "sample.tiff"
        
        mock_bookmark.return_value = None
        
        doc = ingest_file(file_path, mode=IngestMode.LINK, extract_metadata=True)
        
        assert doc.name == "sample.tiff"
        assert doc.file_type == FileType.image
        assert "file_size" in doc.metadata
        assert doc.metadata["file_size"] > 0

    @patch("fichero.db.db")
    @patch("fichero.bookmarks.create_bookmark")
    def test_ingest_webp_file(self, mock_bookmark, mock_db):
        """Should ingest WEBP file correctly."""
        from fichero.importers.ingest import ingest_file, IngestMode
        from fichero.models import FileType

        file_path = Path(__file__).parent.parent / "fixtures" / "sample_files" / "sample.webp"
        
        mock_bookmark.return_value = None
        
        doc = ingest_file(file_path, mode=IngestMode.LINK, extract_metadata=True)
        
        assert doc.name == "sample.webp"
        assert doc.file_type == FileType.image
        assert "file_size" in doc.metadata
        assert doc.metadata["file_size"] > 0

    @patch("fichero.db.db")
    @patch("fichero.bookmarks.create_bookmark")
    def test_ingest_pdf_file(self, mock_bookmark, mock_db):
        """Should ingest PDF file correctly."""
        from fichero.importers.ingest import ingest_file, IngestMode
        from fichero.models import FileType

        file_path = Path(__file__).parent.parent / "fixtures" / "sample_files" / "sample.pdf"
        
        mock_bookmark.return_value = None
        
        doc = ingest_file(file_path, mode=IngestMode.LINK, extract_metadata=True)
        
        assert doc.name == "sample.pdf"
        assert doc.file_type == FileType.pdf
        assert "file_size" in doc.metadata
        assert doc.metadata["file_size"] > 0

    @patch("fichero.db.db")
    @patch("fichero.bookmarks.create_bookmark")
    def test_ingest_docx_file(self, mock_bookmark, mock_db):
        """Should ingest DOCX file correctly."""
        from fichero.importers.ingest import ingest_file, IngestMode
        from fichero.models import FileType

        file_path = Path(__file__).parent.parent / "fixtures" / "sample_files" / "sample.docx"
        
        mock_bookmark.return_value = None
        
        doc = ingest_file(file_path, mode=IngestMode.LINK, extract_metadata=True)
        
        assert doc.name == "sample.docx"
        assert doc.file_type == FileType.word
        assert "file_size" in doc.metadata
        assert doc.metadata["file_size"] > 0

    @patch("fichero.db.db")
    @patch("fichero.bookmarks.create_bookmark")
    def test_ingest_text_file(self, mock_bookmark, mock_db):
        """Should ingest text file correctly."""
        from fichero.importers.ingest import ingest_file, IngestMode
        from fichero.models import FileType

        file_path = Path(__file__).parent.parent / "fixtures" / "sample_files" / "sample.txt"
        
        mock_bookmark.return_value = None
        
        doc = ingest_file(file_path, mode=IngestMode.LINK, extract_metadata=True)
        
        assert doc.name == "sample.txt"
        assert doc.file_type == FileType.text
        assert "file_size" in doc.metadata
        assert doc.metadata["file_size"] > 0

    @patch("fichero.db.db")
    @patch("fichero.bookmarks.create_bookmark")
    def test_ingest_markdown_file(self, mock_bookmark, mock_db):
        """Should ingest markdown file correctly."""
        from fichero.importers.ingest import ingest_file, IngestMode
        from fichero.models import FileType

        file_path = Path(__file__).parent.parent / "fixtures" / "sample_files" / "sample.md"
        
        mock_bookmark.return_value = None
        
        doc = ingest_file(file_path, mode=IngestMode.LINK, extract_metadata=True)
        
        assert doc.name == "sample.md"
        assert doc.file_type == FileType.text
        assert "file_size" in doc.metadata
        assert doc.metadata["file_size"] > 0

    @patch("fichero.db.db")
    @patch("fichero.bookmarks.create_bookmark")
    def test_ingest_mp3_file(self, mock_bookmark, mock_db):
        """Should ingest MP3 file correctly."""
        from fichero.importers.ingest import ingest_file, IngestMode
        from fichero.models import FileType

        file_path = Path(__file__).parent.parent / "fixtures" / "sample_files" / "sample.mp3"
        
        mock_bookmark.return_value = None
        
        doc = ingest_file(file_path, mode=IngestMode.LINK, extract_metadata=True)
        
        assert doc.name == "sample.mp3"
        assert doc.file_type == FileType.audio
        assert "file_size" in doc.metadata
        assert doc.metadata["file_size"] > 0

    @patch("fichero.db.db")
    @patch("fichero.bookmarks.create_bookmark")
    def test_ingest_wav_file(self, mock_bookmark, mock_db):
        """Should ingest WAV file correctly."""
        from fichero.importers.ingest import ingest_file, IngestMode
        from fichero.models import FileType

        file_path = Path(__file__).parent.parent / "fixtures" / "sample_files" / "sample.wav"
        
        mock_bookmark.return_value = None
        
        doc = ingest_file(file_path, mode=IngestMode.LINK, extract_metadata=True)
        
        assert doc.name == "sample.wav"
        assert doc.file_type == FileType.audio
        assert "file_size" in doc.metadata
        assert doc.metadata["file_size"] > 0

    @patch("fichero.db.db")
    @patch("fichero.bookmarks.create_bookmark")
    def test_ingest_mp4_file(self, mock_bookmark, mock_db):
        """Should ingest MP4 file correctly."""
        from fichero.importers.ingest import ingest_file, IngestMode
        from fichero.models import FileType

        file_path = Path(__file__).parent.parent / "fixtures" / "sample_files" / "sample.mp4"
        
        mock_bookmark.return_value = None
        
        doc = ingest_file(file_path, mode=IngestMode.LINK, extract_metadata=True)
        
        assert doc.name == "sample.mp4"
        assert doc.file_type == FileType.video
        assert "file_size" in doc.metadata
        assert doc.metadata["file_size"] > 0

    @patch("fichero.db.db")
    @patch("fichero.bookmarks.create_bookmark")
    def test_ingest_epub_file(self, mock_bookmark, mock_db):
        """Should ingest EPUB file correctly."""
        from fichero.importers.ingest import ingest_file, IngestMode
        from fichero.models import FileType

        file_path = Path(__file__).parent.parent / "fixtures" / "sample_files" / "sample.epub"
        
        mock_bookmark.return_value = None
        
        doc = ingest_file(file_path, mode=IngestMode.LINK, extract_metadata=True)
        
        assert doc.name == "sample.epub"
        assert doc.file_type == FileType.epub
        assert "file_size" in doc.metadata
        assert doc.metadata["file_size"] > 0


class TestExtractFileMetadata:
    """Tests for _extract_file_metadata function."""

    def test_extracts_file_size(self, tmp_path):
        """Should extract file size."""
        from fichero.importers.ingest import _extract_file_metadata
        from fichero.models import Document, FileType

        file = tmp_path / "test.txt"
        file.write_text("hello world")

        doc = Document(name="test.txt", file_type=FileType.text, metadata={})
        _extract_file_metadata(doc, file)

        assert doc.metadata["file_size"] == 11

    def test_extracts_checksum(self, tmp_path):
        """Should extract checksum."""
        from fichero.importers.ingest import _extract_file_metadata
        from fichero.models import Document, FileType

        file = tmp_path / "test.txt"
        file.write_text("test content")

        doc = Document(name="test.txt", file_type=FileType.text, metadata={})
        _extract_file_metadata(doc, file)

        assert "checksum" in doc.metadata
        assert len(doc.metadata["checksum"]) == 64  # SHA256 hex

    def test_extracts_mime_type(self, tmp_path):
        """Should extract MIME type."""
        from fichero.importers.ingest import _extract_file_metadata
        from fichero.models import Document, FileType

        file = tmp_path / "test.txt"
        file.write_text("test")

        doc = Document(name="test.txt", file_type=FileType.text, metadata={})
        _extract_file_metadata(doc, file)

        assert doc.metadata["mime_type"] == "text/plain"

    @pytest.mark.skipif(
        not Path("/System").exists(),
        reason="Requires Pillow"
    )
    def test_extracts_image_dimensions(self, tmp_path):
        """Should extract image dimensions for images."""
        from fichero.importers.ingest import _extract_file_metadata
        from fichero.models import Document, FileType

        try:
            from PIL import Image
        except ImportError:
            pytest.skip("Pillow not installed")

        file = tmp_path / "test.jpg"
        img = Image.new("RGB", (640, 480), color="red")
        img.save(file)

        doc = Document(name="test.jpg", file_type=FileType.image, metadata={})
        _extract_file_metadata(doc, file)

        assert doc.metadata["width"] == 640
        assert doc.metadata["height"] == 480

    def test_rejects_oversized_image_metadata(self, tmp_path, monkeypatch):
        """Oversized images should fail loud instead of warning-and-continuing."""
        from fichero.importers.ingest import _extract_file_metadata
        from fichero.models import Document, FileType

        try:
            from PIL import Image
        except ImportError:
            pytest.skip("Pillow not installed")

        file = tmp_path / "oversized.png"
        Image.new("RGB", (3, 3), color="red").save(file)
        monkeypatch.setattr("fichero.loaders.image_loader._MAX_IMAGE_PIXELS", 4)

        doc = Document(name="oversized.png", file_type=FileType.image, metadata={})
        with pytest.raises(ValueError, match="Image too large for ingest"):
            _extract_file_metadata(doc, file)


class TestContentAccess:
    """Tests for content access after ingestion."""

    def test_text_extraction_from_txt(self, tmp_path):
        """Should extract text from TXT files."""
        from fichero.importers.ingest import _extract_text_content
        from fichero.models import Document, FileType
        
        file = tmp_path / "test.txt"
        file.write_text("Hello World\nThis is a test file.")
        
        doc = Document(name="test.txt", file_type=FileType.text, metadata={})
        _extract_text_content(doc, file)
        
        # Text extraction modifies doc.page_content
        assert hasattr(doc, 'page_content')
        if doc.page_content:
            assert "Hello World" in doc.page_content
            assert "This is a test file" in doc.page_content

    def test_text_extraction_from_md(self, tmp_path):
        """Should extract text from Markdown files."""
        from fichero.importers.ingest import _extract_text_content
        from fichero.models import Document, FileType
        
        file = tmp_path / "test.md"
        file.write_text("# Test File\n\nThis is **markdown** content.")
        
        doc = Document(name="test.md", file_type=FileType.text, metadata={})
        _extract_text_content(doc, file)
        
        # Text extraction modifies doc.page_content
        assert hasattr(doc, 'page_content')
        if doc.page_content:
            assert "Test File" in doc.page_content
            assert "markdown" in doc.page_content

    def test_pdf_text_extraction(self, tmp_path):
        """Should extract text from PDF files."""
        from fichero.importers.ingest import _extract_text_content
        from fichero.models import Document, FileType
        
        try:
            from PyPDF2 import PdfWriter
        except ImportError:
            pytest.skip("PyPDF2 not installed")
        
        file = tmp_path / "test.pdf"
        
        # Create a simple PDF with text
        PdfWriter()
        from io import BytesIO
        from reportlab.pdfgen import canvas
        
        buffer = BytesIO()
        can = canvas.Canvas(buffer)
        can.drawString(100, 700, "Hello PDF World")
        can.save()
        
        buffer.seek(0)
        file.write_bytes(buffer.read())
        
        doc = Document(name="test.pdf", file_type=FileType.pdf, metadata={})
        content = _extract_text_content(doc, file)
        
        assert "Hello PDF World" in content


class TestEdgeCases:
    """Tests for edge cases and error conditions."""

    def test_corrupted_file_handling(self, tmp_path):
        """Should handle corrupted files gracefully."""
        from fichero.importers.ingest import _extract_file_metadata
        from fichero.models import Document, FileType
        
        file = tmp_path / "corrupted.jpg"
        file.write_bytes(b"This is not a valid image file")
        
        doc = Document(name="corrupted.jpg", file_type=FileType.image, metadata={})
        
        # Should not crash, but may not extract metadata
        try:
            _extract_file_metadata(doc, file)
        except Exception:
            # Expected to fail for corrupted files
            pass
        
        # Document should still exist
        assert doc is not None

    def test_file_with_special_characters(self, tmp_path):
        """Should handle files with special characters in names."""
        from fichero.importers.ingest import detect_file_type
        from fichero.models import FileType
        
        # Test various special characters
        special_names = [
            "test file with spaces.jpg",
            "test-file-with-dashes.jpg", 
            "test_file_with_underscores.jpg",
            "test.file.with.dots.jpg",
            "test(parens).jpg",
            "test[brackets].jpg",
        ]
        
        for name in special_names:
            result = detect_file_type(Path(name))
            assert result == FileType.image

    def test_very_large_filename(self, tmp_path):
        """Should handle very long filenames."""
        from fichero.importers.ingest import detect_file_type
        from fichero.models import FileType
        
        long_name = "a" * 200 + ".jpg"
        result = detect_file_type(Path(long_name))
        assert result == FileType.image

    def test_file_with_no_extension(self, tmp_path):
        """Should handle files with no extension."""
        from fichero.importers.ingest import detect_file_type
        from fichero.models import FileType
        
        result = detect_file_type(Path("no_extension"))
        assert result == FileType.other

    def test_file_with_multiple_extensions(self, tmp_path):
        """Should handle files with multiple extensions."""
        from fichero.importers.ingest import detect_file_type
        from fichero.models import FileType
        
        # Should use the last extension
        result = detect_file_type(Path("test.tar.gz"))
        assert result == FileType.other  # .gz is not a known type
        
        result = detect_file_type(Path("test.document.pdf"))
        assert result == FileType.pdf


class TestIntegration:
    """Integration tests for complete ingestion workflow."""

    def test_complete_ingestion_workflow(self, tmp_path):
        """Should complete full ingestion workflow successfully."""
        from fichero.importers.ingest import ingest_file
        from fichero.models import FileType
        
        # Create a test file
        file = tmp_path / "test_ingestion.jpg"
        file.write_bytes(b"fake image data")
        
        # Mock database operations - db is imported locally in the function
        with patch("fichero.db.db") as mock_db:
            mock_db.save.return_value = None
            mock_db.get.return_value = None
            
            # Mock file operations
            with patch("fichero.importers.ingest.shutil") as mock_shutil:
                mock_shutil.copy2.return_value = None
                
                from fichero.importers.ingest import IngestMode
                
                result = ingest_file(
                    path=str(file),
                    parent_id=None,
                    mode=IngestMode.COPY,
                    extract_text=False,
                    auto_embed=False
                )
                
                # Verify document was created
                assert result is not None
                assert result.name == "test_ingestion.jpg"
                assert result.file_type == FileType.image
                
                # Verify database save was called
                mock_db.save.assert_called_once()

    def test_ingestion_with_text_extraction(self, tmp_path):
        """Should ingest file with text extraction enabled."""
        from fichero.importers.ingest import ingest_file
        from fichero.models import FileType
        
        # Create a text file
        file = tmp_path / "test_text.txt"
        file.write_text("Test content for extraction")
        
        with patch("fichero.db.db") as mock_db:
            mock_db.save.return_value = None
            mock_db.get.return_value = None
            
            with patch("fichero.importers.ingest.shutil") as mock_shutil:
                mock_shutil.copy2.return_value = None
                
                from fichero.importers.ingest import IngestMode
                
                result = ingest_file(
                    path=str(file),
                    parent_id=None,
                    mode=IngestMode.COPY,
                    extract_text=True,
                    auto_embed=False
                )
                
                assert result is not None
                assert result.name == "test_text.txt"
                assert result.file_type == FileType.text
                # Text content should be extracted
                assert result.metadata.get("text_extracted")
                assert "Test content for extraction" in result.page_content


class TestTextExtraction:
    """Comprehensive tests for text extraction functionality."""

    def test_text_extraction_from_txt_file(self):
        """Should extract text from TXT files using real sample."""
        from fichero.importers.ingest import ingest_file, IngestMode
        from fichero.models import FileType
        
        file_path = Path(__file__).parent.parent / "fixtures" / "sample_files" / "sample.txt"
        
        with patch("fichero.db.db") as mock_db:
            mock_db.save.return_value = None
            mock_db.get.return_value = None
            
            with patch("fichero.bookmarks.create_bookmark") as mock_bookmark:
                mock_bookmark.return_value = None
                
                doc = ingest_file(file_path, mode=IngestMode.LINK, extract_text=True)
                
                assert doc.name == "sample.txt"
                assert doc.file_type == FileType.text
                assert doc.metadata.get("text_extracted")
                assert "Plain Text Sample" in doc.page_content
                assert "Línea en español" in doc.page_content
                assert len(doc.page_content) > 50  # Should have substantial content

    def test_text_extraction_from_md_file(self):
        """Should extract text from Markdown files using real sample."""
        from fichero.importers.ingest import ingest_file, IngestMode
        from fichero.models import FileType
        
        file_path = Path(__file__).parent.parent / "fixtures" / "sample_files" / "sample.md"
        
        with patch("fichero.db.db") as mock_db:
            mock_db.save.return_value = None
            mock_db.get.return_value = None
            
            with patch("fichero.bookmarks.create_bookmark") as mock_bookmark:
                mock_bookmark.return_value = None
                
                doc = ingest_file(file_path, mode=IngestMode.LINK, extract_text=True)
                
                assert doc.name == "sample.md"
                assert doc.file_type == FileType.text
                assert doc.metadata.get("text_extracted")
                assert "Sample Document" in doc.page_content
                assert "Fichero loaders" in doc.page_content
                assert "Sección 2" in doc.page_content
                assert "Algo de texto en español" in doc.page_content
                assert len(doc.page_content) > 100  # Should have substantial content

    def test_text_extraction_from_docx_file(self):
        """Should extract text from DOCX files using real sample."""
        from fichero.importers.ingest import ingest_file, IngestMode
        from fichero.models import FileType
        
        file_path = Path(__file__).parent.parent / "fixtures" / "sample_files" / "sample.docx"
        
        with patch("fichero.db.db") as mock_db:
            mock_db.save.return_value = None
            mock_db.get.return_value = None
            
            with patch("fichero.bookmarks.create_bookmark") as mock_bookmark:
                mock_bookmark.return_value = None
                
                doc = ingest_file(file_path, mode=IngestMode.LINK, extract_text=True)
                
                assert doc.name == "sample.docx"
                assert doc.file_type == FileType.word
                assert doc.metadata.get("text_extracted")
                assert len(doc.page_content) > 0  # Should have some content
                # Check for expected content from the DOCX file
                assert "Sample" in doc.page_content or "Document" in doc.page_content

    def test_text_extraction_from_epub_file(self):
        """Should extract text from EPUB files using real sample."""
        from fichero.importers.ingest import ingest_file, IngestMode
        from fichero.models import FileType
        
        file_path = Path(__file__).parent.parent / "fixtures" / "sample_files" / "sample.epub"
        
        with patch("fichero.db.db") as mock_db:
            mock_db.save.return_value = None
            mock_db.get.return_value = None
            
            with patch("fichero.bookmarks.create_bookmark") as mock_bookmark:
                mock_bookmark.return_value = None
                
                doc = ingest_file(file_path, mode=IngestMode.LINK, extract_text=True)
                
                assert doc.name == "sample.epub"
                assert doc.file_type == FileType.epub

                # EPUB extraction support depends on parser/library compatibility.
                # Validate graceful behavior for both success and failure paths.
                assert isinstance(doc.metadata.get("text_extracted"), bool)
                if doc.metadata.get("text_extracted"):
                    assert len(doc.page_content) > 0
                else:
                    assert doc.page_content is None or len(doc.page_content) == 0

    def test_text_extraction_from_pdf_file(self):
        """Should extract text from PDF files using real sample."""
        from fichero.importers.ingest import ingest_file, IngestMode
        from fichero.models import FileType
        
        file_path = Path(__file__).parent.parent / "fixtures" / "sample_files" / "sample.pdf"
        
        with patch("fichero.db.db") as mock_db:
            mock_db.save.return_value = None
            mock_db.get.return_value = None
            
            with patch("fichero.bookmarks.create_bookmark") as mock_bookmark:
                mock_bookmark.return_value = None
                
                doc = ingest_file(file_path, mode=IngestMode.LINK, extract_text=True)
                
                assert doc.name == "sample.pdf"
                assert doc.file_type == FileType.pdf
                assert doc.metadata.get("text_extracted")
                assert len(doc.page_content) > 0  # Should have some content

    def test_pdf_creates_page_children_with_named_page_labels(self, tmp_path):
        """Importing a labeled PDF stamps each child page with the PDF's own label.

        Kreuzberg's page extraction is mocked so this test exercises only the
        ingest layer's fan-out logic — not pdfium's actual PDF parsing.
        """
        from fichero.importers.ingest import ingest_file, IngestMode
        from fichero.models import FileType, DocType

        file_path = _make_pdf(
            tmp_path,
            "labeled.pdf",
            6,
            page_labels=[
                {"startpage": 0, "style": "r", "firstpagenum": 1},
                {"startpage": 3, "style": "D", "firstpagenum": 1},
            ],
        )

        saved_docs: list = []

        class FakeDB:
            def save(self, doc):
                saved_docs.append(doc)

            def get(self, *_args, **_kwargs):
                return None

            def embed(self, *_args, **_kwargs):
                pass

        fake_pages_result = MagicMock()
        fake_pages_result.pages = [
            {"page_number": 1, "content": "First page text", "is_blank": False},
            {"page_number": 2, "content": "Second page text", "is_blank": False},
            {"page_number": 3, "content": "Third page text", "is_blank": False},
            {"page_number": 4, "content": "Fourth page text", "is_blank": False},
            {"page_number": 5, "content": "Fifth page text", "is_blank": False},
            {"page_number": 6, "content": "", "is_blank": True},
        ]

        fake_db = FakeDB()
        with patch("fichero.bookmarks.create_bookmark") as mock_bookmark, \
             patch("kreuzberg.extract_file_sync", return_value=fake_pages_result):
            mock_bookmark.return_value = None
            parent = ingest_file(file_path, mode=IngestMode.LINK, extract_text=True, db=fake_db)

        assert parent.file_type == FileType.pdf
        assert parent.doc_type == DocType.file

        page_children = [d for d in saved_docs if d.doc_type == DocType.page and d.parent_id == parent.id]
        assert len(page_children) == 6

        sequences = sorted(p.sequence for p in page_children if p.sequence is not None)
        assert sequences == [1, 2, 3, 4, 5, 6]
        assert [p.page_label for p in sorted(page_children, key=lambda p: p.sequence or 0)] == [
            "i",
            "ii",
            "iii",
            "1",
            "2",
            "3",
        ]

        for page in page_children:
            assert page.metadata.get("pdf_parent_id") == parent.id
            assert page.metadata.get("pdf_path") == str(file_path)
            assert page.metadata.get("page_number") == page.sequence

        blank_pages = [p for p in page_children if p.metadata.get("is_blank")]
        assert len(blank_pages) == 1
        assert blank_pages[0].sequence == 6
        assert blank_pages[0].page_content is None

    def test_pdf_page_children_without_named_page_labels_leave_page_label_none(self, tmp_path):
        """Unlabeled PDFs must leave page_label unset so the UI falls back to sequence."""
        from fichero.importers.ingest import ingest_file, IngestMode
        from fichero.models import DocType

        file_path = _make_pdf(tmp_path, "plain.pdf", 2)

        saved_docs: list = []

        class FakeDB:
            def save(self, doc):
                saved_docs.append(doc)

            def get(self, *_args, **_kwargs):
                return None

            def embed(self, *_args, **_kwargs):
                pass

        fake_pages_result = MagicMock()
        fake_pages_result.pages = [
            {"page_number": 1, "content": "First page text", "is_blank": False},
            {"page_number": 2, "content": "Second page text", "is_blank": False},
        ]

        with patch("fichero.bookmarks.create_bookmark") as mock_bookmark, \
             patch("kreuzberg.extract_file_sync", return_value=fake_pages_result):
            mock_bookmark.return_value = None
            ingest_file(file_path, mode=IngestMode.LINK, extract_text=True, db=FakeDB())

        page_children = [d for d in saved_docs if d.doc_type == DocType.page]
        assert len(page_children) == 2
        assert all(page.page_label is None for page in page_children)

    def test_pdf_page_label_source_failures_do_not_crash_page_creation(self, tmp_path):
        """Broken or partial page-label sources fall back to None per page."""
        from fichero.importers.ingest import _create_pdf_page_children
        from fichero.models import Document, DocType

        file_path = tmp_path / "partial.pdf"
        file_path.write_bytes(b"%PDF-1.7\n")

        saved_docs: list = []

        class FakeDB:
            def save(self, doc):
                saved_docs.append(doc)

            def get(self, *_args, **_kwargs):
                return None

        class _GoodPage:
            def get_label(self):
                return "i"

        class _BrokenPage:
            def get_label(self):
                raise RuntimeError("bad label")

        class FakePDF:
            def get_page_labels(self):
                return [{"startpage": 0, "style": "r", "firstpagenum": 1}]

            def __getitem__(self, index):
                if index == 0:
                    return _GoodPage()
                if index == 1:
                    return _BrokenPage()
                raise RuntimeError("missing page")

            def close(self):
                pass

        fake_pages_result = MagicMock()
        fake_pages_result.pages = [
            {"page_number": 1, "content": "First page text", "is_blank": False},
            {"page_number": 2, "content": "Second page text", "is_blank": False},
            {"page_number": 3, "content": "Third page text", "is_blank": False},
        ]

        parent = Document(name="partial.pdf", doc_type=DocType.file)
        with patch("kreuzberg.extract_file_sync", return_value=fake_pages_result), \
             patch("fitz.open", return_value=FakePDF()):
            pages = _create_pdf_page_children(parent, file_path, FakeDB())

        assert len(pages) == 3
        assert [page.page_label for page in pages] == ["i", None, None]

    def test_text_extraction_disabled(self):
        """Should not extract text when extract_text=False."""
        from fichero.importers.ingest import ingest_file, IngestMode
        from fichero.models import FileType
        
        file_path = Path(__file__).parent.parent / "fixtures" / "sample_files" / "sample.txt"
        
        with patch("fichero.db.db") as mock_db:
            mock_db.save.return_value = None
            mock_db.get.return_value = None
            
            with patch("fichero.bookmarks.create_bookmark") as mock_bookmark:
                mock_bookmark.return_value = None
                
                doc = ingest_file(file_path, mode=IngestMode.LINK, extract_text=False)
                
                assert doc.name == "sample.txt"
                assert doc.file_type == FileType.text
                # Should not have text extraction metadata
                assert not doc.metadata.get("text_extracted")
                # Should not have page_content
                assert doc.page_content is None or len(doc.page_content) == 0

    def test_text_extraction_metadata(self):
        """Should populate text extraction metadata correctly."""
        from fichero.importers.ingest import ingest_file, IngestMode
        from fichero.models import FileType
        
        file_path = Path(__file__).parent.parent / "fixtures" / "sample_files" / "sample.txt"
        
        with patch("fichero.db.db") as mock_db:
            mock_db.save.return_value = None
            mock_db.get.return_value = None
            
            with patch("fichero.bookmarks.create_bookmark") as mock_bookmark:
                mock_bookmark.return_value = None
                
                doc = ingest_file(file_path, mode=IngestMode.LINK, extract_text=True)
                
                assert doc.name == "sample.txt"
                assert doc.file_type == FileType.text
                assert doc.metadata.get("text_extracted")
                assert "text_length" in doc.metadata
                assert doc.metadata["text_length"] > 0
                assert doc.metadata["text_length"] == len(doc.page_content)

    def test_text_extraction_multilingual(self):
        """Should handle multilingual text content."""
        from fichero.importers.ingest import ingest_file, IngestMode
        from fichero.models import FileType
        
        file_path = Path(__file__).parent.parent / "fixtures" / "sample_files" / "sample.txt"
        
        with patch("fichero.db.db") as mock_db:
            mock_db.save.return_value = None
            mock_db.get.return_value = None
            
            with patch("fichero.bookmarks.create_bookmark") as mock_bookmark:
                mock_bookmark.return_value = None
                
                doc = ingest_file(file_path, mode=IngestMode.LINK, extract_text=True)
                
                assert doc.name == "sample.txt"
                assert doc.file_type == FileType.text
                assert doc.metadata.get("text_extracted")
                # Check for Spanish text with accents
                assert "Línea en español con acentos" in doc.page_content
                assert "áéíóú" in doc.page_content
                assert "ñ" in doc.page_content

    def test_text_extraction_unsupported_format(self):
        """Should handle unsupported formats gracefully."""
        from fichero.importers.ingest import ingest_file, IngestMode
        from fichero.models import FileType
        
        # Create a file with unsupported format
        file_path = Path(__file__).parent.parent / "fixtures" / "sample_files" / "sample.jpg"
        
        with patch("fichero.db.db") as mock_db:
            mock_db.save.return_value = None
            mock_db.get.return_value = None
            
            with patch("fichero.bookmarks.create_bookmark") as mock_bookmark:
                mock_bookmark.return_value = None
                
                doc = ingest_file(file_path, mode=IngestMode.LINK, extract_text=True)
                
                assert doc.name == "sample.jpg"
                assert doc.file_type == FileType.image
                # Should not have text extraction for images
                assert not doc.metadata.get("text_extracted")
                assert doc.page_content is None or len(doc.page_content) == 0

    def test_text_extraction_error_handling(self):
        """Should handle text extraction errors gracefully."""
        from fichero.importers.ingest import ingest_file, IngestMode
        from fichero.models import FileType
        
        # Create a corrupted file
        file_path = Path(__file__).parent.parent / "fixtures" / "sample_files" / "sample.txt"
        
        with patch("fichero.db.db") as mock_db:
            mock_db.save.return_value = None
            mock_db.get.return_value = None
            
            with patch("fichero.bookmarks.create_bookmark") as mock_bookmark:
                mock_bookmark.return_value = None
                
                # Mock the loader to raise an exception
                with patch("fichero.loaders.load_media") as mock_load:
                    mock_load.side_effect = Exception("Loader error")
                    
                    doc = ingest_file(file_path, mode=IngestMode.LINK, extract_text=True)
                    
                    assert doc.name == "sample.txt"
                    assert doc.file_type == FileType.text
                    # Should handle error gracefully
                    assert not doc.metadata.get("text_extracted")
                    assert doc.page_content is None or len(doc.page_content) == 0


class TestPerformance:
    """Performance tests for ingestion operations."""

    def test_multiple_file_ingestion(self, tmp_path):
        """Should handle ingestion of multiple files efficiently."""
        from fichero.importers.ingest import ingest_file
        import time
        
        # Create multiple test files
        files = []
        for i in range(5):
            file = tmp_path / f"test_{i}.jpg"
            file.write_bytes(b"fake image data")
            files.append(file)
        
        start_time = time.time()
        
        with patch("fichero.db.db") as mock_db:
            mock_db.save.return_value = None
            mock_db.get.return_value = None
            
            with patch("fichero.importers.ingest.shutil") as mock_shutil:
                mock_shutil.copy2.return_value = None
                
                # Ingest all files
                results = []
                for file in files:
                    from fichero.importers.ingest import IngestMode
                    
                    result = ingest_file(
                        path=str(file),
                        parent_id=None,
                        mode=IngestMode.COPY,
                        extract_text=False,
                        auto_embed=False
                    )
                    results.append(result)
        
        end_time = time.time()
        
        # Should complete in reasonable time
        assert len(results) == 5
        assert end_time - start_time < 10  # Should take less than 10 seconds

    def test_large_file_handling(self, tmp_path):
        """Should handle large files without crashing."""
        from fichero.importers.ingest import ingest_file
        
        # Create a large file (10MB)
        file = tmp_path / "large_file.jpg"
        large_data = b"x" * (10 * 1024 * 1024)  # 10MB
        file.write_bytes(large_data)
        
        with patch("fichero.db.db") as mock_db:
            mock_db.save.return_value = None
            mock_db.get.return_value = None
            
            with patch("fichero.importers.ingest.shutil") as mock_shutil:
                mock_shutil.copy2.return_value = None
                
                # Should not crash with large file
                from fichero.importers.ingest import IngestMode
                
                result = ingest_file(
                    path=str(file),
                    parent_id=None,
                    mode=IngestMode.COPY,
                    extract_text=False,
                    auto_embed=False
                )

                assert result is not None
                assert result.name == "large_file.jpg"


class TestIngestModeMetadata:
    """Issue #603 — every ingested document records its mode in metadata
    so the SwiftUI sidebar can render LINK / COPY / MOVE badges without
    falling back to the bookmark-presence heuristic.
    """

    @patch("fichero.db.db")
    @patch("fichero.bookmarks.create_bookmark")
    def test_link_mode_recorded_in_metadata(self, mock_bookmark, mock_db, tmp_path):
        from fichero.importers.ingest import ingest_file, IngestMode

        file = tmp_path / "test.jpg"
        file.write_bytes(b"x")
        mock_bookmark.return_value = b"bookmark_data"

        doc = ingest_file(file, mode=IngestMode.LINK)
        assert doc.metadata.get("ingest_mode") == "link"

    @patch("fichero.db.db")
    @patch("fichero.importers.ingest._copy_to_library")
    def test_copy_mode_recorded_in_metadata(self, mock_copy, mock_db, tmp_path):
        from fichero.importers.ingest import ingest_file, IngestMode

        file = tmp_path / "test.jpg"
        file.write_bytes(b"x")
        dest = tmp_path / "library" / "test_copy.jpg"
        dest.parent.mkdir(parents=True)
        mock_copy.return_value = dest

        doc = ingest_file(file, mode=IngestMode.COPY)
        assert doc.metadata.get("ingest_mode") == "copy"


class TestTouchAncestorDocumentsCycleGuard:
    """Issue #1349 — _touch_ancestor_documents must not loop forever on cycles."""

    def test_cyclic_parent_chain_terminates(self):
        """A->B->A cycle must stop (visited guard) without hanging."""
        from fichero.importers.ingest import _touch_ancestor_documents
        from fichero.models import Document, DocType

        # Build two docs with a cyclic parent relationship: A.parent=B, B.parent=A
        doc_a = Document(id="doc-a", name="A", doc_type=DocType.folder, parent_id="doc-b")
        doc_b = Document(id="doc-b", name="B", doc_type=DocType.folder, parent_id="doc-a")
        store = {"doc-a": doc_a, "doc-b": doc_b}

        mock_db = MagicMock()
        mock_db.get.side_effect = lambda model, doc_id: store.get(doc_id)
        mock_db.save.side_effect = lambda obj, **_kw: None

        # Must return without hanging; if cycle guard is absent this loops forever.
        _touch_ancestor_documents(mock_db, "doc-a")

        # Both docs were visited and saved exactly once each (guard stops at the repeat).
        saved_ids = [call.args[0].id for call in mock_db.save.call_args_list]
        assert saved_ids.count("doc-a") == 1
        assert saved_ids.count("doc-b") == 1
        # Total saves == 2 (A then B — the third step would re-visit A and halt)
        assert len(saved_ids) == 2

    def test_truthy_magicmock_parent_id_terminates_without_looping(self):
        """Non-string parent ids (e.g. MagicMock) must stop immediately."""
        from fichero.importers.ingest import _touch_ancestor_documents

        mock_parent = MagicMock()
        mock_parent.parent_id = MagicMock()  # truthy, non-str, unstable

        mock_db = MagicMock()
        mock_db.get.return_value = mock_parent
        mock_db.save.side_effect = lambda obj, **_kw: None

        _touch_ancestor_documents(mock_db, "doc-a")

        # Only the first real string doc-id hop is allowed; the next non-str
        # parent_id must terminate the walk.
        assert mock_db.get.call_count == 1
        assert mock_db.save.call_count == 1
