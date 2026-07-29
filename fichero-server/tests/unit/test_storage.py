"""Unit tests for storage module."""
import base64
import pytest
from pathlib import Path
from unittest.mock import Mock
import tempfile
import os
import subprocess


class TestUploadStreaming:
    @pytest.mark.asyncio
    async def test_save_uploaded_file_stops_streaming_after_cap_is_hit(self):
        from fichero_server.db.storage import UploadTooLargeError, save_uploaded_file

        class ChunkedUpload:
            filename = "oversized.txt"

            def __init__(self) -> None:
                self._chunks = [b"a" * 4, b"b" * 4, b"c" * 4, b"d" * 4]
                self.read_calls = 0

            async def read(self, size: int) -> bytes:
                assert size == 4
                self.read_calls += 1
                if not self._chunks:
                    return b""
                return self._chunks.pop(0)

        upload = ChunkedUpload()

        with pytest.raises(UploadTooLargeError):
            await save_uploaded_file(upload, max_bytes=10, chunk_size=4)

        assert upload.read_calls < 4
        assert upload._chunks


class TestStorageSettings:
    """Tests for StorageSettings configuration."""

    def test_default_paths(self, monkeypatch):
        """Default paths should be in Application Support — when
        FICHERO_BASE_PATH isn't set (conftest sets it for test isolation,
        so clear it here to assert the actual default).
        """
        monkeypatch.delenv("FICHERO_BASE_PATH", raising=False)
        from fichero_server.db.storage import StorageSettings

        s = StorageSettings()
        assert "Application Support" in str(s.base_path)
        assert s.thumb_dir == s.base_path / "thumbnails"
        assert s.db_path == s.base_path / "library.duckdb"
        assert s.vectors_dir == s.base_path / "vectors"

    def test_computed_fields(self):
        """Computed fields should derive from base_path."""
        from fichero_server.db.storage import StorageSettings

        with tempfile.TemporaryDirectory() as tmpdir:
            s = StorageSettings(base_path=Path(tmpdir))
            assert s.thumb_dir == Path(tmpdir) / "thumbnails"
            assert s.db_path == Path(tmpdir) / "library.duckdb"
            assert s.vectors_dir == Path(tmpdir) / "vectors"

    def test_size_tuples(self):
        """Size properties should return tuples."""
        from fichero_server.db.storage import StorageSettings, THUMBNAIL_MAX_DIMENSION

        s = StorageSettings()
        assert s.thumb_size == (THUMBNAIL_MAX_DIMENSION, THUMBNAIL_MAX_DIMENSION)
        assert s.display_size == (1000, 1000)

    def test_custom_sizes(self):
        """Custom dimensions should work."""
        from fichero_server.db.storage import StorageSettings

        s = StorageSettings(thumb_width=150, thumb_height=150)
        assert s.thumb_size == (150, 150)

    def test_env_override(self, monkeypatch):
        """Environment variables should override defaults."""
        from fichero_server.db.storage import StorageSettings

        monkeypatch.setenv("FICHERO_QUALITY", "90")
        s = StorageSettings()
        assert s.quality == 90


class TestPathHelpers:
    """Tests for path helper functions."""

    def test_sharding_uses_first_two_chars(self):
        """Thumbnail paths should use first 2 chars for sharding."""
        from fichero_server.db.storage import expected_thumbnail_path

        path = expected_thumbnail_path("a1b2c3d4")
        assert "a1" in str(path)
        assert path.name == "a1b2c3d4.jpg"

    def test_sharding_lowercase(self):
        """Sharding should be case-insensitive."""
        from fichero_server.db.storage import expected_thumbnail_path

        path = expected_thumbnail_path("A1B2C3D4")
        assert "a1" in str(path)

    def test_display_path_suffix(self):
        """Display paths should have _display suffix."""
        from fichero_server.db.storage import expected_display_path

        path = expected_display_path("abc123")
        assert path.name == "abc123_display.jpg"

    def test_has_thumbnail_false_for_nonexistent(self):
        """has_thumbnail returns False for non-existent files."""
        from fichero_server.db.storage import has_thumbnail

        assert has_thumbnail("nonexistent-id-12345") is False

    def test_has_display_false_for_nonexistent(self):
        """has_display returns False for non-existent files."""
        from fichero_server.db.storage import has_display

        assert has_display("nonexistent-id-12345") is False

    def test_sips_conversion_timeout_is_logged(self, tmp_path, monkeypatch, caplog):
        """#2137: thumbnail conversion failures should be debug-visible."""
        from fichero_server.db.storage import _sips_convert

        source = tmp_path / "bad.jpg"
        source.write_bytes(b"not really a jpeg")

        def timeout(*args, **kwargs):
            raise subprocess.TimeoutExpired(cmd=args[0], timeout=30)

        monkeypatch.setattr("subprocess.run", timeout)

        caplog.set_level("DEBUG", logger="fichero_server.db.storage")
        assert _sips_convert(source) is None
        assert "sips thumbnail conversion timed out" in caplog.text


class TestResolveSource:
    """Tests for resolve_source function."""

    def test_path_exists(self, tmp_path):
        """Should return path if doc.path exists."""
        from fichero_server.db.storage import resolve_source

        file = tmp_path / "test.jpg"
        file.touch()

        doc = Mock()
        doc.path = str(file)
        doc.metadata = {}

        result = resolve_source(doc, library_root=tmp_path)
        assert result == file

    def test_path_missing_uses_metadata_fallback(self, tmp_path):
        """Should fallback to metadata paths if doc.path missing."""
        from fichero_server.db.storage import resolve_source

        file = tmp_path / "test.jpg"
        file.touch()

        doc = Mock()
        doc.path = "/nonexistent/path.jpg"
        doc.metadata = {"source_path": str(file)}

        result = resolve_source(doc, library_root=tmp_path)
        assert result == file

    def test_metadata_tilde_path_is_expanded(self, tmp_path, monkeypatch):
        """source_path with '~' should resolve via expanduser()."""
        from fichero_server.db.storage import resolve_source

        monkeypatch.setenv("HOME", str(tmp_path))
        file = tmp_path / "from-home.jpg"
        file.touch()

        doc = Mock()
        doc.path = "/nonexistent/path.jpg"
        doc.metadata = {"source_path": "~/from-home.jpg"}

        result = resolve_source(doc, library_root=tmp_path)
        assert result == file

    def test_returns_none_if_nothing_exists(self):
        """Should return None if no paths exist."""
        from fichero_server.db.storage import resolve_source

        doc = Mock()
        doc.path = "/nonexistent/path.jpg"
        doc.metadata = {
            "source_path": "/also/nonexistent.jpg",
            "full_path": "/still/nonexistent.jpg",
        }

        result = resolve_source(doc)
        assert result is None

    def test_invalid_metadata_path_types_are_ignored(self):
        """Non-string metadata path values should not raise."""
        from fichero_server.db.storage import resolve_source

        doc = Mock()
        doc.path = "/nonexistent/path.jpg"
        doc.metadata = {
            "source_path": 1234,
            "full_path": {"bad": "type"},
            "local_path": None,
        }

        assert resolve_source(doc) is None

    def test_metadata_priority_order(self, tmp_path):
        """Should check metadata paths in correct order."""
        from fichero_server.db.storage import resolve_source

        # Only full_path exists
        file = tmp_path / "full.jpg"
        file.touch()

        doc = Mock()
        doc.path = "/nonexistent/path.jpg"
        doc.metadata = {
            "source_path": "/nonexistent/source.jpg",
            "full_path": str(file),
        }

        result = resolve_source(doc, library_root=tmp_path)
        assert result == file

    def test_library_relative_doc_path_resolves_under_current_library(self, tmp_path):
        """Copied-in package paths should resolve after a library move/rename."""
        from fichero_server.db.storage import resolve_source

        library_root = tmp_path / "Renamed.fichero"
        source = library_root / "files" / "ab" / "page.jpg"
        source.parent.mkdir(parents=True)
        source.touch()

        doc = Mock()
        doc.path = "files/ab/page.jpg"
        doc.metadata = {}

        result = resolve_source(doc, library_root=library_root)
        assert result == source

    def test_old_absolute_files_path_falls_back_to_current_library(self, tmp_path):
        """Old absolute paths baking in a prior .fichero name should recover."""
        from fichero_server.db.storage import resolve_source

        old_root = tmp_path / "Old.fichero"
        new_root = tmp_path / "New.fichero"
        source = new_root / "files" / "cd" / "page.jpg"
        source.parent.mkdir(parents=True)
        source.touch()

        doc = Mock()
        doc.path = str(old_root / "files" / "cd" / "page.jpg")
        doc.metadata = {}

        result = resolve_source(doc, library_root=new_root)
        assert result == source

    def test_invalid_bookmark_raises_instead_of_falling_back_to_path(self, tmp_path):
        """Corrupt bookmark metadata must not silently select another source."""
        from fichero_server.db.storage import _get_bookmark

        bookmark_file = tmp_path / "bookmark.jpg"
        bookmark_file.touch()

        path_file = tmp_path / "path.jpg"
        path_file.touch()

        doc = Mock()
        doc.id = "broken-bookmark"
        doc.path = str(path_file)
        doc.metadata = {"bookmark": "invalid_base64"}  # Invalid bookmark

        with pytest.raises(ValueError, match="broken-bookmark has invalid bookmark"):
            _get_bookmark(doc)

    def test_remote_bookmark_disabled_prefers_package_path(self, tmp_path, monkeypatch):
        """Remote engines must not resolve Mac bookmarks from by-reference docs."""
        from fichero_server import bookmarks
        from fichero_server.db.storage import resolve_source

        library_root = tmp_path / "Remote.fichero"
        source = library_root / "files" / "aa" / "page.jpg"
        source.parent.mkdir(parents=True)
        source.touch()

        doc = Mock()
        doc.path = "files/aa/page.jpg"
        doc.metadata = {
            "bookmark": base64.b64encode(b"mac-client-bookmark").decode("ascii"),
            "source_path": "/Users/daniel/Desktop/original.jpg",
        }

        def fail_if_called(bookmark_data):
            raise AssertionError("remote engine attempted to resolve a Mac bookmark")

        monkeypatch.setenv("FICHERO_ENABLE_MAC_BOOKMARKS", "0")
        monkeypatch.setattr(bookmarks, "resolve_bookmark", fail_if_called)

        result = resolve_source(doc, library_root=library_root)
        assert result == source


class TestThumbnailGeneration:
    """Tests for thumbnail generation functions."""

    def test_ensure_thumbnail_no_pillow(self):
        """Should return None if Pillow not available."""
        from fichero_server.db import storage

        original_image = storage.Image
        original_load = storage._load_pil
        # PIL is now bound lazily (#3985): _load_pil() re-imports it on first
        # render. To simulate Pillow-absent, neutralise the loader so the None
        # sentinel sticks — exactly what _load_pil() leaves it as when the real
        # `from PIL import ...` raises ImportError.
        storage._load_pil = lambda: None
        storage.Image = None

        try:
            doc = Mock()
            doc.id = "test123"
            result = storage.ensure_thumbnail(doc)
            assert result is None
        finally:
            storage.Image = original_image
            storage._load_pil = original_load

    def test_ensure_thumbnail_no_source(self, tmp_path):
        """Should return None if no source found."""
        from fichero_server.db.storage import ensure_thumbnail

        doc = Mock()
        doc.id = "test123"
        doc.path = "/nonexistent/file.jpg"
        doc.metadata = {}

        result = ensure_thumbnail(doc)
        assert result is None

    @pytest.mark.skipif(
        not Path("/System").exists(),
        reason="Requires Pillow"
    )
    def test_ensure_thumbnail_creates_file(self, tmp_path):
        """Should create thumbnail file."""
        from fichero_server.db import storage
        from fichero_server.db.storage import (
            THUMBNAIL_MAX_DIMENSION,
            ensure_thumbnail,
            StorageSettings,
        )

        try:
            from PIL import Image
        except ImportError:
            pytest.skip("Pillow not installed")

        # Create source image
        source = tmp_path / "files" / "source.jpg"
        source.parent.mkdir(parents=True, exist_ok=True)
        img = Image.new("RGB", (500, 500), color="red")
        img.save(source)

        # Override settings for test
        test_settings = StorageSettings(base_path=tmp_path)
        original_settings = storage.settings
        storage.settings = test_settings

        try:
            doc = Mock()
            doc.id = "abc123"
            doc.path = str(source)
            doc.metadata = {}

            result = ensure_thumbnail(doc)

            assert result is not None
            assert result.exists()
            assert "ab" in str(result)  # Sharded path
            with Image.open(result) as thumb:
                assert max(thumb.size) == 500
                assert max(thumb.size) <= THUMBNAIL_MAX_DIMENSION
        finally:
            storage.settings = original_settings

    @pytest.mark.skipif(
        not Path("/System").exists(),
        reason="Requires Pillow"
    )
    def test_ensure_thumbnail_caps_long_edge_at_max_dimension(self, tmp_path):
        """Large source images should be capped at the configured thumbnail size."""
        from fichero_server.db import storage
        from fichero_server.db.storage import (
            THUMBNAIL_MAX_DIMENSION,
            ensure_thumbnail,
            StorageSettings,
        )

        try:
            from PIL import Image
        except ImportError:
            pytest.skip("Pillow not installed")

        source = tmp_path / "files" / "source-large.jpg"
        source.parent.mkdir(parents=True, exist_ok=True)
        img = Image.new("RGB", (2400, 1600), color="blue")
        img.save(source)

        test_settings = StorageSettings(base_path=tmp_path)
        original_settings = storage.settings
        storage.settings = test_settings

        try:
            doc = Mock()
            doc.id = "wide123"
            doc.path = str(source)
            doc.metadata = {}

            result = ensure_thumbnail(doc)

            assert result is not None
            with Image.open(result) as thumb:
                assert max(thumb.size) == THUMBNAIL_MAX_DIMENSION
                assert thumb.size == (THUMBNAIL_MAX_DIMENSION, 683)
        finally:
            storage.settings = original_settings

    @pytest.mark.skipif(
        not Path("/System").exists(),
        reason="Requires Pillow"
    )
    def test_ensure_thumbnail_writes_versioned_cache_and_alias(self, tmp_path):
        """Thumbnail cache files should be keyed by doc id, size, and source mtime."""
        from fichero_server.db import storage
        from fichero_server.db.storage import ensure_thumbnail, get_thumbnail, StorageSettings

        try:
            from PIL import Image
        except ImportError:
            pytest.skip("Pillow not installed")

        source = tmp_path / "files" / "source-cache.jpg"
        source.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (800, 600), color="green").save(source)

        test_settings = StorageSettings(base_path=tmp_path)
        original_settings = storage.settings
        storage.settings = test_settings

        try:
            doc = Mock()
            doc.id = "cache123"
            doc.path = str(source)
            doc.metadata = {}

            result = ensure_thumbnail(doc)

            assert result is not None
            assert "__1024x1024__" in result.name
            alias_path = tmp_path / "thumbnails" / "ca" / "cache123.jpg"
            assert alias_path.exists()
            assert get_thumbnail(doc) == result
        finally:
            storage.settings = original_settings


class TestStorageRouteHeaders:
    """Tests for storage route response headers."""

    def test_inline_content_disposition_ascii_filename(self):
        """ASCII filenames should preserve readable fallback and encoded variant."""
        from fichero_server.api.routes.storage import _inline_content_disposition

        header = _inline_content_disposition("report.pdf")
        assert 'filename="report.pdf"' in header
        assert "filename*=UTF-8''report.pdf" in header

    def test_inline_content_disposition_unicode_filename(self):
        """Unicode filenames should not crash header generation."""
        from fichero_server.api.routes.storage import _inline_content_disposition

        header = _inline_content_disposition("résumé-日本語.pdf")
        assert 'filename="r?sum?-???.pdf"' in header
        assert "filename*=UTF-8''r%C3%A9sum%C3%A9-%E6%97%A5%E6%9C%AC%E8%AA%9E.pdf" in header

    @pytest.mark.skipif(
        not Path("/System").exists(),
        reason="Requires Pillow"
    )
    def test_ensure_thumbnail_skips_existing(self, tmp_path):
        """Should skip if thumbnail already exists and is newer."""
        from fichero_server.db import storage
        from fichero_server.db.storage import ensure_thumbnail, StorageSettings

        try:
            from PIL import Image
        except ImportError:
            pytest.skip("Pillow not installed")

        # Create source and existing thumbnail
        source = tmp_path / "files" / "source.jpg"
        source.parent.mkdir(parents=True, exist_ok=True)
        img = Image.new("RGB", (500, 500), color="red")
        img.save(source)

        # Override settings
        test_settings = StorageSettings(base_path=tmp_path)
        original_settings = storage.settings
        storage.settings = test_settings

        try:
            # Create existing thumbnail
            thumb_dir = tmp_path / "thumbnails" / "ab"
            thumb_dir.mkdir(parents=True)
            existing_thumb = thumb_dir / "abc123.jpg"
            img.save(existing_thumb)

            # Touch to make it newer than source
            os.utime(existing_thumb, None)

            doc = Mock()
            doc.id = "abc123"
            doc.path = str(source)
            doc.metadata = {}

            # Get mtime before
            mtime_before = existing_thumb.stat().st_mtime

            result = ensure_thumbnail(doc)

            # Should promote the legacy file into the versioned cache without
            # re-rendering, while preserving the legacy alias path.
            assert result is not None
            assert result.name.startswith("abc123__1024x1024__")
            assert existing_thumb.exists()
            assert existing_thumb.stat().st_mtime == mtime_before
        finally:
            storage.settings = original_settings


class TestCleanup:
    """Tests for cleanup functions."""

    def test_cleanup_orphans_removes_invalid(self, tmp_path):
        """Should remove thumbnails for missing documents."""
        from fichero_server.db import storage
        from fichero_server.db.storage import cleanup_orphans, StorageSettings

        test_settings = StorageSettings(base_path=tmp_path)
        original_settings = storage.settings
        storage.settings = test_settings

        try:
            # Create thumbnail structure
            shard = tmp_path / "thumbnails" / "ab"
            shard.mkdir(parents=True)

            # Valid thumbnail
            (shard / "abc123.jpg").touch()
            # Orphan thumbnail
            (shard / "orphan1.jpg").touch()
            (shard / "orphan1_display.jpg").touch()

            valid_ids = {"abc123"}
            removed = cleanup_orphans(valid_ids)

            assert removed == 2
            assert (shard / "abc123.jpg").exists()
            assert not (shard / "orphan1.jpg").exists()
            assert not (shard / "orphan1_display.jpg").exists()
        finally:
            storage.settings = original_settings

    def test_cleanup_orphans_keeps_versioned_cache_for_live_doc(self, tmp_path):
        """Versioned cache files should map back to the owning document id."""
        from fichero_server.db import storage
        from fichero_server.db.storage import cleanup_orphans, StorageSettings

        test_settings = StorageSettings(base_path=tmp_path)
        original_settings = storage.settings
        storage.settings = test_settings

        try:
            shard = tmp_path / "thumbnails" / "ab"
            shard.mkdir(parents=True)
            (shard / "abc123__1024x1024__123456.jpg").touch()
            (shard / "dead999__1024x1024__123456.jpg").touch()

            removed = cleanup_orphans({"abc123"})

            assert removed == 1
            assert (shard / "abc123__1024x1024__123456.jpg").exists()
            assert not (shard / "dead999__1024x1024__123456.jpg").exists()
        finally:
            storage.settings = original_settings

    def test_cleanup_orphans_empty_dir(self, tmp_path):
        """Should handle non-existent thumb directory."""
        from fichero_server.db import storage
        from fichero_server.db.storage import cleanup_orphans, StorageSettings

        test_settings = StorageSettings(base_path=tmp_path)
        original_settings = storage.settings
        storage.settings = test_settings

        try:
            # Don't create thumb dir
            removed = cleanup_orphans({"abc"})
            assert removed == 0
        finally:
            storage.settings = original_settings


class TestStats:
    """Tests for stats function."""

    def test_stats_empty(self, tmp_path):
        """Should return zeros for empty storage."""
        from fichero_server.db import storage
        from fichero_server.db.storage import stats, StorageSettings

        test_settings = StorageSettings(base_path=tmp_path)
        original_settings = storage.settings
        storage.settings = test_settings

        try:
            result = stats()
            assert result["count"] == 0
            assert result["size_mb"] == 0.0
            assert result["shards"] == 0
        finally:
            storage.settings = original_settings

    def test_stats_with_files(self, tmp_path):
        """Should count files and calculate size."""
        from fichero_server.db import storage
        from fichero_server.db.storage import stats, StorageSettings

        test_settings = StorageSettings(base_path=tmp_path)
        original_settings = storage.settings
        storage.settings = test_settings

        try:
            # Create thumbnail structure
            shard1 = tmp_path / "thumbnails" / "ab"
            shard1.mkdir(parents=True)
            shard2 = tmp_path / "thumbnails" / "cd"
            shard2.mkdir(parents=True)

            (shard1 / "abc123.jpg").write_bytes(b"x" * 1000)
            (shard2 / "cde456.jpg").write_bytes(b"x" * 2000)

            result = stats()
            assert result["count"] == 2
            assert result["shards"] == 2
            # 3000 bytes = 0.00286 MB, rounds to 0.0 at 2 decimal places
            assert result["size_mb"] == 0.0
        finally:
            storage.settings = original_settings


class TestBatchGeneration:
    """Tests for batch thumbnail generation."""

    def test_ensure_thumbnails_returns_futures(self, tmp_path):
        """Should return list of futures."""
        from fichero_server.db import storage
        from fichero_server.db.storage import ensure_thumbnails, StorageSettings

        test_settings = StorageSettings(base_path=tmp_path)
        original_settings = storage.settings
        storage.settings = test_settings

        try:
            # Mock docs - no sources, so no actual work
            docs = [
                Mock(id="abc123", path="/nonexistent1.jpg", metadata={}),
                Mock(id="def456", path="/nonexistent2.jpg", metadata={}),
            ]

            futures = ensure_thumbnails(docs)

            # Should return futures (may be empty if thumbs exist)
            assert isinstance(futures, list)
        finally:
            storage.settings = original_settings
            storage.shutdown()

    def test_callback_called_on_completion(self, tmp_path):
        """Callback should be called when thumbnail generation completes."""
        from fichero_server.db import storage
        from fichero_server.db.storage import ensure_thumbnails, StorageSettings

        test_settings = StorageSettings(base_path=tmp_path)
        original_settings = storage.settings
        storage.settings = test_settings

        try:
            completed_ids = []

            def on_progress(doc_id, path):
                completed_ids.append(doc_id)

            docs = [
                Mock(id="abc123", path="/nonexistent1.jpg", metadata={}),
            ]

            futures = ensure_thumbnails(docs, on_progress=on_progress)

            # Wait for completion
            for f in futures:
                f.result()

            assert "abc123" in completed_ids
        finally:
            storage.settings = original_settings
            storage.shutdown()


class TestShutdown:
    """Tests for executor shutdown."""

    def test_shutdown_idempotent(self):
        """Shutdown should be safe to call multiple times."""
        from fichero_server.db.storage import shutdown

        # Should not raise
        shutdown()
        shutdown()
        shutdown()
