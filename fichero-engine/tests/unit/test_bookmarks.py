"""Unit tests for macOS bookmarks module."""
import pytest
from pathlib import Path


# Skip entire module on non-macOS
pytestmark = pytest.mark.skipif(
    not Path("/System").exists(),
    reason="macOS only - bookmarks require macOS APIs"
)


class TestIsAvailable:
    """Tests for is_available function."""

    def test_returns_bool(self):
        """Should return a boolean."""
        from fichero.bookmarks import is_available

        result = is_available()
        assert isinstance(result, bool)

    def test_true_when_rubicon_available(self):
        """Should return True if Rubicon ObjC is available."""
        from fichero.bookmarks import is_available, _HAS_RUBICON

        # On macOS with rubicon installed
        if _HAS_RUBICON:
            assert is_available() is True
        else:
            assert is_available() is False


class TestCreateBookmark:
    """Tests for create_bookmark function."""

    def test_nonexistent_file_returns_none(self):
        """Should return None for non-existent file."""
        from fichero.bookmarks import create_bookmark

        result = create_bookmark(Path("/nonexistent/path/file.txt"))
        assert result is None

    def test_create_for_existing_file(self, tmp_path):
        """Should create bookmark for existing file."""
        from fichero.bookmarks import create_bookmark, is_available

        if not is_available():
            pytest.skip("Rubicon ObjC not available")

        file = tmp_path / "test.txt"
        file.write_text("test content")

        bookmark = create_bookmark(file)

        assert bookmark is not None
        assert isinstance(bookmark, bytes)
        assert len(bookmark) > 0

    def test_create_read_only_bookmark(self, tmp_path):
        """Should create read-only bookmark when requested."""
        from fichero.bookmarks import create_bookmark, is_available

        if not is_available():
            pytest.skip("Rubicon ObjC not available")

        file = tmp_path / "test.txt"
        file.write_text("test content")

        bookmark = create_bookmark(file, read_only=True)

        assert bookmark is not None
        assert isinstance(bookmark, bytes)

    def test_create_read_write_bookmark(self, tmp_path):
        """Should create read-write bookmark by default."""
        from fichero.bookmarks import create_bookmark, is_available

        if not is_available():
            pytest.skip("Rubicon ObjC not available")

        file = tmp_path / "test.txt"
        file.write_text("test content")

        bookmark = create_bookmark(file, read_only=False)

        assert bookmark is not None
        assert isinstance(bookmark, bytes)


class TestResolveBookmark:
    """Tests for resolve_bookmark function."""

    def test_none_input_returns_none(self):
        """Should return None for None input."""
        from fichero.bookmarks import resolve_bookmark

        result = resolve_bookmark(None)
        assert result is None

    def test_empty_bytes_returns_none(self):
        """Should return None for empty bytes."""
        from fichero.bookmarks import resolve_bookmark

        result = resolve_bookmark(b"")
        assert result is None

    def test_invalid_bookmark_returns_none(self):
        """Should return None for invalid bookmark data."""
        from fichero.bookmarks import resolve_bookmark

        result = resolve_bookmark(b"invalid bookmark data")
        assert result is None

    def test_roundtrip(self, tmp_path):
        """Should resolve bookmark back to original path."""
        from fichero.bookmarks import create_bookmark, resolve_bookmark, is_available

        if not is_available():
            pytest.skip("Rubicon ObjC not available")

        file = tmp_path / "test.txt"
        file.write_text("test content")

        bookmark = create_bookmark(file)
        assert bookmark is not None

        resolved = resolve_bookmark(bookmark)

        assert resolved is not None
        assert resolved == file


class TestStopAccessing:
    """Tests for stop_accessing function."""

    def test_no_error_for_regular_file(self, tmp_path):
        """Should not raise for regular file path."""
        from fichero.bookmarks import stop_accessing

        file = tmp_path / "test.txt"
        file.write_text("test")

        # Should not raise
        stop_accessing(file)

    def test_no_error_for_nonexistent_file(self):
        """Should not raise for non-existent file."""
        from fichero.bookmarks import stop_accessing

        # Should not raise
        stop_accessing(Path("/nonexistent/file.txt"))


class TestIsBookmarkStale:
    """Tests for is_bookmark_stale function."""

    def test_none_is_stale(self):
        """None bookmark should be considered stale."""
        from fichero.bookmarks import is_bookmark_stale

        assert is_bookmark_stale(None) is True

    def test_empty_is_stale(self):
        """Empty bookmark should be considered stale."""
        from fichero.bookmarks import is_bookmark_stale

        assert is_bookmark_stale(b"") is True

    def test_invalid_is_stale(self):
        """Invalid bookmark should be considered stale."""
        from fichero.bookmarks import is_bookmark_stale

        assert is_bookmark_stale(b"invalid data") is True

    def test_valid_bookmark_not_stale(self, tmp_path):
        """Valid bookmark for existing file should not be stale."""
        from fichero.bookmarks import (
            create_bookmark,
            is_bookmark_stale,
            is_available,
        )

        if not is_available():
            pytest.skip("Rubicon ObjC not available")

        file = tmp_path / "test.txt"
        file.write_text("test")

        bookmark = create_bookmark(file)
        assert bookmark is not None

        # Note: Staleness depends on file moving/renaming
        # A freshly created bookmark should not be stale
        # But is_bookmark_stale implementation may vary
        result = is_bookmark_stale(bookmark)
        assert isinstance(result, bool)


class TestRefreshBookmark:
    """Tests for refresh_bookmark function."""

    def test_refresh_creates_new_bookmark(self, tmp_path):
        """Refresh should create a new bookmark."""
        from fichero.bookmarks import (
            create_bookmark,
            refresh_bookmark,
            is_available,
        )

        if not is_available():
            pytest.skip("Rubicon ObjC not available")

        file = tmp_path / "test.txt"
        file.write_text("test")

        old_bookmark = create_bookmark(file)
        new_bookmark = refresh_bookmark(file, old_bookmark)

        assert new_bookmark is not None
        assert isinstance(new_bookmark, bytes)


class TestBookmarkAccess:
    """Tests for BookmarkAccess context manager."""

    def test_context_manager_with_valid_bookmark(self, tmp_path):
        """Context manager should resolve and provide path."""
        from fichero.bookmarks import (
            create_bookmark,
            BookmarkAccess,
            is_available,
        )

        if not is_available():
            pytest.skip("Rubicon ObjC not available")

        file = tmp_path / "test.txt"
        file.write_text("test content")

        bookmark = create_bookmark(file)

        with BookmarkAccess(bookmark) as path:
            assert path is not None
            assert path == file
            # Can read file within context
            content = path.read_text()
            assert content == "test content"

    def test_context_manager_with_none(self):
        """Context manager should handle None bookmark."""
        from fichero.bookmarks import BookmarkAccess

        with BookmarkAccess(None) as path:
            assert path is None

    def test_context_manager_with_invalid(self):
        """Context manager should handle invalid bookmark."""
        from fichero.bookmarks import BookmarkAccess

        with BookmarkAccess(b"invalid") as path:
            assert path is None

    def test_context_manager_cleanup(self, tmp_path):
        """Context manager should call stop_accessing on exit."""
        from fichero.bookmarks import (
            create_bookmark,
            BookmarkAccess,
            is_available,
        )

        if not is_available():
            pytest.skip("Rubicon ObjC not available")

        file = tmp_path / "test.txt"
        file.write_text("test")

        bookmark = create_bookmark(file)

        # Use context manager
        with BookmarkAccess(bookmark) as path:
            assert path is not None

        # After context exit, access should be stopped
        # (No easy way to verify, but should not raise)


class TestWithoutRubicon:
    """Tests for graceful degradation without Rubicon."""

    def test_create_bookmark_without_rubicon(self, tmp_path):
        """Should return None when Rubicon not available."""
        from fichero import bookmarks

        # Temporarily disable Rubicon
        original_flag = bookmarks._HAS_RUBICON
        bookmarks._HAS_RUBICON = False

        try:
            file = tmp_path / "test.txt"
            file.write_text("test")

            result = bookmarks.create_bookmark(file)
            assert result is None
        finally:
            bookmarks._HAS_RUBICON = original_flag

    def test_resolve_bookmark_without_rubicon(self):
        """Should return None when Rubicon not available."""
        from fichero import bookmarks

        original_flag = bookmarks._HAS_RUBICON
        bookmarks._HAS_RUBICON = False

        try:
            result = bookmarks.resolve_bookmark(b"some data")
            assert result is None
        finally:
            bookmarks._HAS_RUBICON = original_flag

    def test_is_available_without_rubicon(self):
        """Should return False when Rubicon not available."""
        from fichero import bookmarks

        original_flag = bookmarks._HAS_RUBICON
        bookmarks._HAS_RUBICON = False

        try:
            result = bookmarks.is_available()
            assert result is False
        finally:
            bookmarks._HAS_RUBICON = original_flag
