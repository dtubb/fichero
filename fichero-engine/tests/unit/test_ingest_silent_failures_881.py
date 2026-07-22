"""Regression tests for #881 — silent WARNING-level failures must not
leave page_content=None for text-bearing files, and ingest_folder must
not silently drop files that raise during ingest.

Two root-cause paths:

1. _extract_text_content swallows loader exceptions at WARNING level
   → page_content stays None, doc is saved without content, no signal
   to the caller or to the DB that extraction failed.

2. ingest_folder swallows per-file exceptions at WARNING level
   → the file is simply omitted from the returned list; no failed-status
   Document is persisted, so the UI shows nothing and the user can't
   tell which files were skipped.

Fix contract (asserted by tests below):
  • When a loader raises, _extract_text_content must record a
    text_extraction_error in doc.metadata AND set doc.status = Status.failed.
  • When ingest_file raises inside ingest_folder, a stub Document with
    status=Status.failed and an ingest_error in its metadata MUST be
    persisted to the DB so the failure is visible.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from fichero.importers.ingest import ingest_file, ingest_folder, IngestMode
from fichero.models import Status


# ---------------------------------------------------------------------------
# 1. _extract_text_content: loader exception → doc gets Status.failed
# ---------------------------------------------------------------------------


class TestExtractTextContentFailLoud:
    """_extract_text_content must not silently swallow loader exceptions."""

    def test_loader_exception_sets_failed_status(self, tmp_path):
        """When the loader raises, the doc must get Status.failed — not a
        silent None with no signal.

        Pre-fix: doc.status stays Status.pending (the ingest_file default),
        page_content is None, and only a WARNING log is emitted.
        Post-fix: doc.status is Status.failed AND
        doc.metadata['text_extraction_error'] records the reason.
        """
        md_file = tmp_path / "notes.md"
        md_file.write_text("# Test\n\nSome content here.\n", encoding="utf-8")

        boom = RuntimeError("Simulated loader crash")

        async def exploding_load_media(path):
            raise boom

        # load_media is imported inside _extract_text_content at call time, so
        # we must patch it in the fichero.loaders namespace.
        with patch("fichero.loaders.load_media", exploding_load_media):
            doc = ingest_file(md_file, mode=IngestMode.LINK, save=False)

        # The document must signal the failure — NOT stay silently None
        assert doc.status == Status.failed, (
            "doc.status must be Status.failed when the loader raises, "
            f"but got {doc.status!r}"
        )
        assert "text_extraction_error" in doc.metadata, (
            "doc.metadata must contain 'text_extraction_error' key when "
            "the loader raises"
        )
        assert "Simulated loader crash" in str(
            doc.metadata["text_extraction_error"]
        ), "text_extraction_error should include the exception message"

    def test_loader_returns_none_text_does_not_set_failed(self, tmp_path):
        """A loader that returns a result with text=None/empty is a valid
        'no content' outcome (e.g., empty file), NOT an error. The status
        should NOT be Status.failed in that case.
        """
        md_file = tmp_path / "empty.md"
        md_file.write_text("", encoding="utf-8")

        mock_content = MagicMock()
        mock_content.text = None  # No text, but no error
        mock_content.metadata = {}

        async def no_text_load_media(path):
            return mock_content

        # load_media is imported inside _extract_text_content at call time
        with patch("fichero.loaders.load_media", no_text_load_media):
            doc = ingest_file(md_file, mode=IngestMode.LINK, save=False)

        # Empty/no-content is not an error — status must not be failed
        assert doc.status != Status.failed, (
            "A loader returning None text (empty file) should NOT set "
            "Status.failed — that is a legitimate 'no content' outcome."
        )
        assert doc.metadata.get("text_extracted") is False


# ---------------------------------------------------------------------------
# 2. ingest_folder: per-file exception → failed stub Document is persisted
# ---------------------------------------------------------------------------


class TestIngestFolderFailLoud:
    """ingest_folder must surface failures via Status.failed Documents,
    not swallow them silently.

    Contract after the #881 fix:
    - When _extract_text_content raises for a file, ingest_file catches
      it, sets doc.status=Status.failed + records text_extraction_error,
      saves the document, and RETURNS it.  ingest_folder therefore receives
      a Status.failed document in the return list (not nothing).
    - When ingest_file itself raises entirely (e.g. file not found,
      copy failed), ingest_folder catches it, persists a stub Document
      with status=Status.failed and metadata['ingest_error'], and the
      file does NOT appear in the success list.
    """

    def test_text_extraction_failure_yields_failed_status_doc_in_return(self, tmp_path):
        """When _extract_text_content raises for bad.txt, ingest_file saves
        and returns a Status.failed Document for it — the file is included
        in ingest_folder's return value with the failure status visible.

        Pre-fix: the exception was swallowed in _extract_text_content,
        page_content stayed None, doc.status stayed pending — no signal.
        Post-fix: doc.status=Status.failed is set and the doc is saved
        with text_extraction_error in its metadata.
        """
        good_file = tmp_path / "good.txt"
        good_file.write_text("Good content.", encoding="utf-8")
        bad_file = tmp_path / "bad.txt"
        bad_file.write_text("Bad content.", encoding="utf-8")

        saved_docs: list = []
        mock_db = MagicMock()
        mock_db.get.return_value = None
        mock_db.save.side_effect = lambda doc, **kw: saved_docs.append(doc)

        import fichero.importers.ingest as _ingest_mod
        real_extract = _ingest_mod._extract_text_content

        def selective_extract(doc, path):
            if path.name == "bad.txt":
                raise OSError("Disk error on bad.txt")
            real_extract(doc, path)

        with patch("fichero.bookmarks.create_bookmark", return_value=None):
            with patch.object(_ingest_mod, "_extract_text_content", selective_extract):
                docs = ingest_folder(
                    tmp_path,
                    db=mock_db,
                    create_collection=False,
                    extract_text=True,
                    auto_embed=False,
                )

        # Both files appear in the return list (failed ones included so the
        # caller knows about them)
        assert len(docs) == 2, (
            f"Expected 2 docs (good + failed), got {len(docs)}: "
            f"{[d.name for d in docs]}"
        )

        # good.txt has pending/completed status (success)
        good_docs = [d for d in docs if d.name == "good.txt"]
        assert len(good_docs) == 1
        assert good_docs[0].status != Status.failed

        # bad.txt must have Status.failed with the error recorded
        bad_docs = [d for d in docs if d.name == "bad.txt"]
        assert len(bad_docs) == 1, "bad.txt must appear in the returned docs"
        bad_doc = bad_docs[0]
        assert bad_doc.status == Status.failed, (
            f"bad.txt doc.status must be Status.failed, got {bad_doc.status!r}"
        )
        assert "text_extraction_error" in bad_doc.metadata, (
            "bad.txt doc must have 'text_extraction_error' in metadata"
        )

        # The failed doc must also be persisted in DB (saved_docs)
        persisted_failed = [
            d for d in saved_docs
            if d.name == "bad.txt" and d.status == Status.failed
        ]
        assert len(persisted_failed) >= 1, (
            "bad.txt with Status.failed must have been saved to the DB"
        )

    def test_ingest_file_hard_failure_produces_persisted_stub(self, tmp_path):
        """When ingest_file raises entirely (not just text extraction), e.g.
        FileNotFoundError or copy failure, ingest_folder must persist a
        failed stub Document to the DB so the failure is visible.

        Pre-fix: the exception was swallowed with only a WARNING log — no
        DB record at all.
        Post-fix: a stub Document with status=Status.failed and
        metadata['ingest_error'] is saved.
        """
        good_file = tmp_path / "good.txt"
        good_file.write_text("Good content.", encoding="utf-8")
        bad_file = tmp_path / "bad.txt"
        bad_file.write_text("Bad content.", encoding="utf-8")

        saved_docs: list = []
        mock_db = MagicMock()
        mock_db.get.return_value = None
        mock_db.save.side_effect = lambda doc, **kw: saved_docs.append(doc)

        import fichero.importers.ingest as _ingest_mod3
        real_ingest_file = _ingest_mod3.ingest_file

        def selective_ingest_file(path, **kwargs):
            if path.name == "bad.txt":
                raise FileNotFoundError("File vanished: bad.txt")
            return real_ingest_file(path, **kwargs)

        with patch("fichero.bookmarks.create_bookmark", return_value=None):
            with patch.object(_ingest_mod3, "ingest_file", selective_ingest_file):
                docs = ingest_folder(
                    tmp_path,
                    db=mock_db,
                    create_collection=False,
                    extract_text=False,
                    auto_embed=False,
                )

        # good.txt returned as success
        good_docs = [d for d in docs if d.name == "good.txt"]
        assert len(good_docs) == 1

        # bad.txt must NOT be in docs (ingest_file raised before returning)
        bad_in_docs = [d for d in docs if d.name == "bad.txt"]
        assert len(bad_in_docs) == 0, (
            "bad.txt should not be in the success list since ingest_file raised"
        )

        # But a failed stub must be in saved_docs
        failed_stubs = [
            d for d in saved_docs
            if getattr(d, "name", "") == "bad.txt"
            and getattr(d, "status", None) == Status.failed
        ]
        assert len(failed_stubs) >= 1, (
            "ingest_folder must persist a Status.failed stub for bad.txt. "
            f"saved_docs: {[(d.name, getattr(d, 'status', '?')) for d in saved_docs]}"
        )
        stub = failed_stubs[0]
        assert "ingest_error" in stub.metadata, (
            "Failed stub must have 'ingest_error' in metadata"
        )
        assert "vanished" in stub.metadata["ingest_error"]

    def test_all_files_fail_stubs_persisted_for_each(self, tmp_path):
        """When every file's ingest_file call raises, the returned list is
        empty but the DB receives a failed stub for each file.
        """
        for name in ["a.txt", "b.txt"]:
            (tmp_path / name).write_text("content", encoding="utf-8")

        saved_docs: list = []
        mock_db = MagicMock()
        mock_db.get.return_value = None
        mock_db.save.side_effect = lambda doc, **kw: saved_docs.append(doc)

        import fichero.importers.ingest as _ingest_mod4

        def always_raises(path, **kwargs):
            raise RuntimeError("always fails")

        with patch("fichero.bookmarks.create_bookmark", return_value=None):
            with patch.object(_ingest_mod4, "ingest_file", always_raises):
                docs = ingest_folder(
                    tmp_path,
                    db=mock_db,
                    create_collection=False,
                    extract_text=False,
                    auto_embed=False,
                )

        # Returned list has no successful docs
        assert docs == [], f"Expected empty list when all ingest_file calls raise, got {docs}"

        # A failed stub must be persisted for each file
        failed_stubs = [
            d for d in saved_docs
            if getattr(d, "status", None) == Status.failed
        ]
        assert len(failed_stubs) == 2, (
            "Expected 2 failed stub Documents (one per file), "
            f"got {len(failed_stubs)}: "
            f"{[(d.name, d.status) for d in failed_stubs]}"
        )
