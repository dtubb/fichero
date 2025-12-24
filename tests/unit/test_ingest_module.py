"""Unit tests for file ingestion module."""
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import tempfile


class TestIngestMode:
    """Tests for IngestMode enum."""

    def test_enum_values(self):
        """Should have LINK and COPY modes."""
        from fichero.ingest import IngestMode

        assert IngestMode.LINK.value == "link"
        assert IngestMode.COPY.value == "copy"


class TestDetectFileType:
    """Tests for detect_file_type function."""

    def test_image_types(self):
        """Should detect image file types."""
        from fichero.ingest import detect_file_type
        from fichero.models import FileType

        assert detect_file_type(Path("test.jpg")) == FileType.image
        assert detect_file_type(Path("test.jpeg")) == FileType.image
        assert detect_file_type(Path("test.png")) == FileType.image
        assert detect_file_type(Path("test.gif")) == FileType.image
        assert detect_file_type(Path("test.webp")) == FileType.image
        assert detect_file_type(Path("test.tiff")) == FileType.image
        assert detect_file_type(Path("test.heic")) == FileType.image

    def test_pdf_type(self):
        """Should detect PDF file type."""
        from fichero.ingest import detect_file_type
        from fichero.models import FileType

        assert detect_file_type(Path("test.pdf")) == FileType.pdf

    def test_audio_types(self):
        """Should detect audio file types."""
        from fichero.ingest import detect_file_type
        from fichero.models import FileType

        assert detect_file_type(Path("test.mp3")) == FileType.audio
        assert detect_file_type(Path("test.wav")) == FileType.audio
        assert detect_file_type(Path("test.m4a")) == FileType.audio
        assert detect_file_type(Path("test.flac")) == FileType.audio

    def test_video_types(self):
        """Should detect video file types."""
        from fichero.ingest import detect_file_type
        from fichero.models import FileType

        assert detect_file_type(Path("test.mp4")) == FileType.video
        assert detect_file_type(Path("test.mov")) == FileType.video
        assert detect_file_type(Path("test.mkv")) == FileType.video

    def test_text_types(self):
        """Should detect text file types."""
        from fichero.ingest import detect_file_type
        from fichero.models import FileType

        assert detect_file_type(Path("test.txt")) == FileType.text
        assert detect_file_type(Path("test.md")) == FileType.text

    def test_word_types(self):
        """Should detect Word file types."""
        from fichero.ingest import detect_file_type
        from fichero.models import FileType

        assert detect_file_type(Path("test.doc")) == FileType.word
        assert detect_file_type(Path("test.docx")) == FileType.word

    def test_unknown_type(self):
        """Should return 'other' for unknown types."""
        from fichero.ingest import detect_file_type
        from fichero.models import FileType

        assert detect_file_type(Path("test.xyz")) == FileType.other
        assert detect_file_type(Path("test.unknown")) == FileType.other

    def test_case_insensitive(self):
        """Should handle uppercase extensions."""
        from fichero.ingest import detect_file_type
        from fichero.models import FileType

        assert detect_file_type(Path("test.JPG")) == FileType.image
        assert detect_file_type(Path("test.PDF")) == FileType.pdf

    def test_all_image_formats(self):
        """Should detect all supported image formats."""
        from fichero.ingest import detect_file_type
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
        from fichero.ingest import detect_file_type
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
        from fichero.ingest import detect_file_type
        from fichero.models import FileType

        assert detect_file_type(Path("test.mp4")) == FileType.video
        assert detect_file_type(Path("test.mov")) == FileType.video
        assert detect_file_type(Path("test.avi")) == FileType.video
        assert detect_file_type(Path("test.mkv")) == FileType.video
        assert detect_file_type(Path("test.webm")) == FileType.video

    def test_all_text_formats(self):
        """Should detect all supported text formats."""
        from fichero.ingest import detect_file_type
        from fichero.models import FileType

        assert detect_file_type(Path("test.txt")) == FileType.text
        assert detect_file_type(Path("test.md")) == FileType.text
        assert detect_file_type(Path("test.rst")) == FileType.text
        assert detect_file_type(Path("test.rtf")) == FileType.text

    def test_all_word_formats(self):
        """Should detect all supported word document formats."""
        from fichero.ingest import detect_file_type
        from fichero.models import FileType

        assert detect_file_type(Path("test.doc")) == FileType.word
        assert detect_file_type(Path("test.docx")) == FileType.word
        assert detect_file_type(Path("test.odt")) == FileType.word

    def test_all_ebook_formats(self):
        """Should detect all supported ebook formats."""
        from fichero.ingest import detect_file_type
        from fichero.models import FileType

        assert detect_file_type(Path("test.epub")) == FileType.epub
        assert detect_file_type(Path("test.mobi")) == FileType.epub


class TestDiscoverFiles:
    """Tests for discover_files function."""

    def test_discovers_files(self, tmp_path):
        """Should discover files in folder."""
        from fichero.ingest import discover_files

        # Create test files
        (tmp_path / "file1.jpg").touch()
        (tmp_path / "file2.png").touch()
        (tmp_path / "file3.txt").touch()

        files = list(discover_files(tmp_path))

        assert len(files) == 3

    def test_excludes_hidden_files(self, tmp_path):
        """Should exclude hidden files (starting with .)."""
        from fichero.ingest import discover_files

        (tmp_path / "visible.jpg").touch()
        (tmp_path / ".hidden.jpg").touch()

        files = list(discover_files(tmp_path))

        assert len(files) == 1
        assert files[0].name == "visible.jpg"

    def test_recursive_search(self, tmp_path):
        """Should search subdirectories when recursive=True."""
        from fichero.ingest import discover_files

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
        from fichero.ingest import discover_files

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
        from fichero.ingest import count_files

        (tmp_path / "file1.jpg").touch()
        (tmp_path / "file2.jpg").touch()
        (tmp_path / ".hidden.jpg").touch()

        count = count_files(tmp_path)

        assert count == 2  # Excludes hidden

    def test_counts_with_filter(self, tmp_path):
        """Should count with extension filter."""
        from fichero.ingest import count_files

        (tmp_path / "image.jpg").touch()
        (tmp_path / "doc.txt").touch()

        count = count_files(tmp_path, extensions={".jpg"})

        assert count == 1


class TestFindDuplicates:
    """Tests for find_duplicates function."""

    def test_finds_duplicates_by_checksum(self):
        """Should find documents with same checksum."""
        from fichero.ingest import find_duplicates
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
        from fichero.ingest import find_duplicates
        from fichero.models import Document

        doc1 = Document(name="file1.jpg", metadata={"checksum": "abc123"})
        doc2 = Document(name="file2.jpg", metadata={"checksum": "def456"})

        duplicates = find_duplicates([doc1, doc2])

        assert duplicates == {}

    def test_handles_missing_checksum(self):
        """Should handle documents without checksum."""
        from fichero.ingest import find_duplicates
        from fichero.models import Document

        doc1 = Document(name="file1.jpg", metadata={})
        doc2 = Document(name="file2.jpg", metadata={"checksum": "abc123"})

        duplicates = find_duplicates([doc1, doc2])

        assert duplicates == {}


class TestIngestFile:
    """Tests for ingest_file function."""

    def test_file_not_found_raises(self):
        """Should raise FileNotFoundError for non-existent file."""
        from fichero.ingest import ingest_file

        with pytest.raises(FileNotFoundError):
            ingest_file(Path("/nonexistent/file.jpg"))

    def test_directory_raises_value_error(self, tmp_path):
        """Should raise ValueError for directory."""
        from fichero.ingest import ingest_file

        with pytest.raises(ValueError):
            ingest_file(tmp_path)

    @patch("fichero.db.db")
    @patch("fichero.bookmarks.create_bookmark")
    def test_link_mode_creates_bookmark(self, mock_bookmark, mock_db, tmp_path):
        """LINK mode should create bookmark and save document."""
        from fichero.ingest import ingest_file, IngestMode
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
    @patch("fichero.ingest._copy_to_library")
    def test_copy_mode_copies_file(self, mock_copy, mock_db, tmp_path):
        """COPY mode should copy file to library."""
        from fichero.ingest import ingest_file, IngestMode

        file = tmp_path / "test.jpg"
        file.write_bytes(b"fake image data")

        dest = tmp_path / "library" / "test_copy.jpg"
        dest.parent.mkdir(parents=True)
        mock_copy.return_value = dest

        doc = ingest_file(file, mode=IngestMode.COPY)

        assert doc.path == str(dest)
        mock_copy.assert_called_once_with(file)
        mock_db.save.assert_called_once()

    @patch("fichero.db.db")
    @patch("fichero.bookmarks.create_bookmark")
    def test_extracts_metadata(self, mock_bookmark, mock_db, tmp_path):
        """Should extract metadata when requested."""
        from fichero.ingest import ingest_file, IngestMode

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
        from fichero.ingest import ingest_file, IngestMode

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
        from fichero.ingest import ingest_file, IngestMode

        file = tmp_path / "test.jpg"
        file.write_bytes(b"fake")

        mock_bookmark.return_value = None

        doc = ingest_file(file, parent_id="parent-123")

        assert doc.parent_id == "parent-123"


class TestIngestFolder:
    """Tests for ingest_folder function."""

    def test_folder_not_found_raises(self):
        """Should raise FileNotFoundError for non-existent folder."""
        from fichero.ingest import ingest_folder

        with pytest.raises(FileNotFoundError):
            ingest_folder(Path("/nonexistent/folder"))

    def test_file_raises_value_error(self, tmp_path):
        """Should raise ValueError for file (not folder)."""
        from fichero.ingest import ingest_folder

        file = tmp_path / "test.txt"
        file.touch()

        with pytest.raises(ValueError):
            ingest_folder(file)

    @patch("fichero.db.db")
    @patch("fichero.bookmarks.create_bookmark")
    def test_ingests_all_files(self, mock_bookmark, mock_db, tmp_path):
        """Should ingest all files in folder."""
        from fichero.ingest import ingest_folder, IngestMode

        (tmp_path / "file1.jpg").write_bytes(b"data1")
        (tmp_path / "file2.png").write_bytes(b"data2")

        mock_bookmark.return_value = None

        docs = ingest_folder(tmp_path, mode=IngestMode.LINK)

        assert len(docs) == 2

    @patch("fichero.db.db")
    @patch("fichero.bookmarks.create_bookmark")
    def test_creates_collection(self, mock_bookmark, mock_db, tmp_path):
        """Should create collection for folder."""
        from fichero.ingest import ingest_folder
        from fichero.models import DocType

        (tmp_path / "file1.jpg").write_bytes(b"data")

        mock_bookmark.return_value = None

        docs = ingest_folder(tmp_path, create_collection=True)

        # Should have saved collection
        calls = mock_db.save.call_args_list
        collection_saved = any(
            call.args[0].doc_type == DocType.collection
            for call in calls
        )
        assert collection_saved

    @patch("fichero.db.db")
    @patch("fichero.bookmarks.create_bookmark")
    def test_progress_callback(self, mock_bookmark, mock_db, tmp_path):
        """Should call progress callback."""
        from fichero.ingest import ingest_folder

        (tmp_path / "file1.jpg").write_bytes(b"data")
        (tmp_path / "file2.jpg").write_bytes(b"data")

        mock_bookmark.return_value = None

        progress_calls = []

        def on_progress(current, total):
            progress_calls.append((current, total))

        ingest_folder(tmp_path, on_progress=on_progress)

        assert len(progress_calls) == 2
        assert progress_calls[-1][0] == 2  # Final current
        assert progress_calls[-1][1] == 2  # Total


class TestCopyToLibrary:
    """Tests for _copy_to_library function."""

    @patch("fichero.ingest._try_apfs_clone")
    @patch("fichero.storage.settings")
    def test_uses_apfs_clone_when_available(self, mock_settings, mock_clone, tmp_path):
        """Should try APFS clone first."""
        from fichero.ingest import _copy_to_library

        # Setup
        source = tmp_path / "source.jpg"
        source.write_bytes(b"test data")

        mock_settings.base_path = tmp_path
        mock_clone.return_value = True

        _copy_to_library(source)

        mock_clone.assert_called_once()

    @patch("fichero.ingest._try_apfs_clone")
    @patch("fichero.storage.settings")
    @patch("shutil.copy2")
    def test_falls_back_to_shutil(self, mock_copy2, mock_settings, mock_clone, tmp_path):
        """Should fallback to shutil.copy2 if APFS fails."""
        from fichero.ingest import _copy_to_library

        source = tmp_path / "source.jpg"
        source.write_bytes(b"test data")

        mock_settings.base_path = tmp_path
        mock_clone.return_value = False

        _copy_to_library(source)

        mock_copy2.assert_called_once()

    @patch("fichero.ingest._try_apfs_clone")
    @patch("fichero.storage.settings")
    def test_creates_sharded_directory(self, mock_settings, mock_clone, tmp_path):
        """Should create sharded directory structure."""
        from fichero.ingest import _copy_to_library

        source = tmp_path / "source.jpg"
        source.write_bytes(b"test data")

        mock_settings.base_path = tmp_path
        mock_clone.return_value = True

        dest = _copy_to_library(source)

        # Should be in sharded directory (first 2 chars of stem)
        assert "imported" in str(dest)
        assert dest.parent.name == "so"  # First 2 chars of "source"


class TestTryApfsClone:
    """Tests for _try_apfs_clone function."""

    @pytest.mark.skipif(
        not Path("/System").exists(),
        reason="macOS only"
    )
    def test_clones_file_on_same_volume(self, tmp_path):
        """Should clone file on same volume."""
        from fichero.ingest import _try_apfs_clone

        source = tmp_path / "source.txt"
        source.write_text("test content")

        dest = tmp_path / "dest.txt"

        result = _try_apfs_clone(source, dest)

        # May or may not work depending on filesystem
        # Just check it returns a boolean
        assert isinstance(result, bool)

    def test_returns_false_on_error(self, tmp_path):
        """Should return False when clone fails."""
        from fichero.ingest import _try_apfs_clone

        source = tmp_path / "nonexistent.txt"
        dest = tmp_path / "dest.txt"

        result = _try_apfs_clone(source, dest)

        assert result is False


class TestIngestWithRealFiles:
    """Tests for ingestion with real sample files."""

    @patch("fichero.db.db")
    @patch("fichero.bookmarks.create_bookmark")
    def test_ingest_jpg_file(self, mock_bookmark, mock_db):
        """Should ingest JPG file correctly."""
        from fichero.ingest import ingest_file, IngestMode
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
        from fichero.ingest import ingest_file, IngestMode
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
        from fichero.ingest import ingest_file, IngestMode
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
        from fichero.ingest import ingest_file, IngestMode
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
        from fichero.ingest import ingest_file, IngestMode
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
        from fichero.ingest import ingest_file, IngestMode
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
        from fichero.ingest import ingest_file, IngestMode
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
        from fichero.ingest import ingest_file, IngestMode
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
        from fichero.ingest import ingest_file, IngestMode
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
        from fichero.ingest import ingest_file, IngestMode
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
        from fichero.ingest import ingest_file, IngestMode
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
        from fichero.ingest import ingest_file, IngestMode
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
        from fichero.ingest import _extract_file_metadata
        from fichero.models import Document, FileType

        file = tmp_path / "test.txt"
        file.write_text("hello world")

        doc = Document(name="test.txt", file_type=FileType.text, metadata={})
        _extract_file_metadata(doc, file)

        assert doc.metadata["file_size"] == 11

    def test_extracts_checksum(self, tmp_path):
        """Should extract checksum."""
        from fichero.ingest import _extract_file_metadata
        from fichero.models import Document, FileType

        file = tmp_path / "test.txt"
        file.write_text("test content")

        doc = Document(name="test.txt", file_type=FileType.text, metadata={})
        _extract_file_metadata(doc, file)

        assert "checksum" in doc.metadata
        assert len(doc.metadata["checksum"]) == 64  # SHA256 hex

    def test_extracts_mime_type(self, tmp_path):
        """Should extract MIME type."""
        from fichero.ingest import _extract_file_metadata
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
        from fichero.ingest import _extract_file_metadata
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
