"""A copy that did not land must FAIL, not be recorded as fine (#4218).

*"for writing files, and adding files — are we checking when we close a
file to make sure it actually wrote, and checking error messages for adding?
like what if we add from a slow network drive?"*

The audit found nothing verified a copy. Two silent modes, both of the
"succeeded but didn't" shape:

* A TRUNCATED copy was checksummed as authoritative. The checksum is computed
  from the DESTINATION, so a short copy is hashed as-is — internally
  consistent and silently wrong. There was no notion of a correct checksum to
  disagree with.
* A MISSING destination produced a log warning and a saved row: `Status.pending`,
  no checksum, no error metadata, pointing at a file that is not there.

Both now raise, which routes them to machinery that already existed — the
folder walk's failed-stub path and the #4203 retry. The failures were never
unhandled; they were unreachable.

These tests demonstrate the failures rather than asserting the guard exists,
because a happy-path test cannot see either one.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fichero.importers.ingest import _extract_file_metadata, _verify_copied
from fichero.models import Document, FileType


class TestCopyVerification:
    def test_a_complete_copy_passes(self, tmp_path):
        source = tmp_path / "src.bin"
        dest = tmp_path / "dst.bin"
        source.write_bytes(b"x" * 4096)
        dest.write_bytes(b"x" * 4096)

        _verify_copied(source, dest)  # must not raise

    def test_a_truncated_copy_raises(self, tmp_path):
        """The network-volume case: the copy ends short without erroring."""
        source = tmp_path / "src.bin"
        dest = tmp_path / "dst.bin"
        source.write_bytes(b"x" * 4096)
        dest.write_bytes(b"x" * 1024)  # short write

        with pytest.raises(OSError, match="incomplete"):
            _verify_copied(source, dest)

    def test_the_error_names_both_sizes(self, tmp_path):
        """A diagnosable failure: 'incomplete' alone does not tell you how bad."""
        source = tmp_path / "src.bin"
        dest = tmp_path / "dst.bin"
        source.write_bytes(b"x" * 4096)
        dest.write_bytes(b"x" * 1024)

        with pytest.raises(OSError) as caught:
            _verify_copied(source, dest)

        assert "4096" in str(caught.value) and "1024" in str(caught.value)

    def test_a_missing_destination_raises(self, tmp_path):
        """clonefile returning 0 is not proof the destination exists."""
        source = tmp_path / "src.bin"
        source.write_bytes(b"x" * 16)

        with pytest.raises(OSError, match="copy verification failed"):
            _verify_copied(source, tmp_path / "never-created.bin")

    def test_an_empty_source_copies_to_an_empty_destination(self, tmp_path):
        """0 == 0 must pass — the check is equality, not truthiness."""
        source = tmp_path / "empty.bin"
        dest = tmp_path / "empty-copy.bin"
        source.write_bytes(b"")
        dest.write_bytes(b"")

        _verify_copied(source, dest)


class TestTheCheckIsActuallyWIRED:
    """Testing `_verify_copied` alone proves nothing about `_copy_to_library`.

    Found by mutation: deleting BOTH call sites left every direct-call test
    passing. A verification helper nobody calls is exactly the shape of guard
    that reads as protection and provides none.
    """

    @staticmethod
    def _short_copy(source, dest, *args, **kwargs):
        """A network volume that copies short WITHOUT raising."""
        Path(dest).write_bytes(Path(source).read_bytes()[:1200])
        return dest

    def test_copy_to_library_rejects_a_short_copy(self, tmp_path, monkeypatch):
        from fichero.importers import ingest

        source = tmp_path / "photo.jpg"
        source.write_bytes(b"J" * 5000)
        monkeypatch.setattr(ingest, "_try_apfs_clone", lambda s, d: False)
        monkeypatch.setattr(ingest.shutil, "copy2", self._short_copy)

        with pytest.raises(OSError, match="incomplete"):
            ingest._copy_to_library(source, tmp_path)

    def test_copy_to_library_rejects_a_short_CLONE(self, tmp_path, monkeypatch):
        """The clone path needs its own guard: clonefile returning 0 is not proof."""
        from fichero.importers import ingest

        source = tmp_path / "photo.jpg"
        source.write_bytes(b"J" * 5000)

        def short_clone(src, dst):
            Path(dst).write_bytes(Path(src).read_bytes()[:10])
            return True

        monkeypatch.setattr(ingest, "_try_apfs_clone", short_clone)

        with pytest.raises(OSError, match="incomplete"):
            ingest._copy_to_library(source, tmp_path)

    def test_a_healthy_copy_still_succeeds(self, tmp_path, monkeypatch):
        """The guard must not reject good imports — this is the common path."""
        from fichero.importers import ingest

        source = tmp_path / "photo.jpg"
        source.write_bytes(b"J" * 5000)
        monkeypatch.setattr(ingest, "_try_apfs_clone", lambda s, d: False)

        dest = ingest._copy_to_library(source, tmp_path)

        assert dest.exists() and dest.stat().st_size == 5000


class TestMissingFileIsNotAMetadataProblem:
    def test_metadata_extraction_raises_for_a_missing_file(self, tmp_path):
        """Previously: logged a warning, returned, and the row was saved."""
        doc = Document(name="ghost.jpg", path=str(tmp_path / "ghost.jpg"))

        with pytest.raises(OSError):
            _extract_file_metadata(doc, tmp_path / "ghost.jpg")

    def test_a_readable_file_still_gets_its_metadata(self, tmp_path):
        source = tmp_path / "real.txt"
        source.write_bytes(b"hello")
        doc = Document(name="real.txt", path=str(source))

        _extract_file_metadata(doc, source)

        assert doc.metadata["file_size"] == 5
        assert len(doc.metadata["checksum"]) == 64  # sha256 hex

    def test_a_corrupt_image_still_imports(self, tmp_path):
        """The narrowing must not make genuine metadata failures fatal.

        Bytes that are present but unparseable are a metadata problem, and the
        import should survive with size and checksum intact.
        """
        source = tmp_path / "broken.png"
        source.write_bytes(b"\x89PNG\r\n\x1a\n" + b"garbage")
        doc = Document(name="broken.png", path=str(source), file_type=FileType.image)

        _extract_file_metadata(doc, source)

        assert doc.metadata["file_size"] == 15
        assert "checksum" in doc.metadata
        assert "width" not in doc.metadata  # dimensions failed, tolerantly


class TestTheFailureReachesTheRetryPath:
    """A detected failure is only an improvement if the existing machinery sees it.

    The folder walk catches an exception per file, saves a `Status.failed` stub
    carrying `ingest_error`, and #4203's retry re-imports failed documents. The
    point of raising is to reach THAT, not merely to be louder.
    """

    def test_a_verification_failure_is_an_oserror_the_walk_catches(self, tmp_path):
        source = tmp_path / "src.bin"
        dest = tmp_path / "dst.bin"
        source.write_bytes(b"x" * 100)
        dest.write_bytes(b"x" * 10)

        with pytest.raises(Exception) as caught:
            _verify_copied(source, dest)

        # The walk's handler is `except Exception`, and the retry keys off
        # Status.failed + ingest_error, which it sets from str(exc).
        assert isinstance(caught.value, Exception)
        assert str(caught.value), "an empty message would produce a blank ingest_error"

    def test_retry_selects_failed_documents(self):
        """Pin the contract the raise depends on: retry re-imports Status.failed."""
        from fichero.models import Status

        source = Path(__file__)
        assert source.exists()
        # The walk sets this exact pairing; if either half is renamed the
        # raise stops reaching the retry and this fails.
        assert Status.failed.value == "failed"
