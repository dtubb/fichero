"""
#2430 ROOT CAUSE — concurrency race behind per-page artifact loss.

Background
----------
The per-page vision fan-out processes the pages of one PDF in parallel. Each
worker resolves and saves an artifact via
``fichero.workflows.tools.llm_base.save_artifact`` / ``find_existing_artifact``.

The engine deliberately gives **each thread its own DuckDB connection**
(``DatabaseManager.get_database`` keys its pool by ``(package, thread_ident)``;
see #1000 worker-thread model + #2118-2120 two-writer model). DuckDB allows
many in-process connections to one file and serialises writes via MVCC — but a
row just written/committed on one connection can be *briefly invisible* on a
different connection's snapshot. During the parallel fan-out that meant
``db.get(Document, page_child_id)`` could transiently return ``None``, and the
previous code then **skipped the artifact entirely** → per-page data loss.

These tests drive that exact path with REAL threads + a REAL temp DuckDB
library (no mocks of the DB), and assert every page's artifact + content lands
on ITS page, with no skips and nothing routed to the parent PDF.
"""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_tool_config():
    from fichero.workflows.tools.vision_base import VisionToolConfig
    return VisionToolConfig(
        artifact_type="transcription",
        update_page_content=True,
        trigger_embedding=False,
        supports_apple_vision=False,
        skip_if_artifact_exists=False,
    )


def _make_llm_config():
    from fichero.llm import LLMConfig
    return LLMConfig(provider="openai", model="gpt-4o")


@pytest.fixture
def temp_library(tmp_path, monkeypatch):
    """A real .fichero package backed by a real DuckDB file.

    Yields ``(library_path, db_manager)``. Resets the manager's per-thread
    connection pool afterward so threads in this test don't leak connections
    into other tests.
    """
    # Avoid seeding default workflow presets — keeps the library minimal.
    monkeypatch.setenv("FICHERO_SKIP_DEFAULT_WORKFLOWS", "1")

    from fichero.db.manager import db_manager

    lib = tmp_path / "Concurrency.fichero"
    lib.mkdir(parents=True, exist_ok=True)
    library_path = str(lib)

    yield library_path, db_manager

    # Tear down every connection this test opened across all threads.
    try:
        db_manager.close_all()
    except Exception:
        pass


def _seed_parent_and_pages(db, n_pages: int):
    """Create one parent PDF + ``n_pages`` page-child docs (committed)."""
    from fichero.models import Document, DocType, Status

    now = datetime.now()
    parent = Document(
        id="pdf-parent",
        name="scan.pdf",
        doc_type=DocType.file,
        path="/lib/scan.pdf",
        status=Status.pending,
        metadata={},
        created_at=now,
        updated_at=now,
    )
    db.save(parent)

    page_ids = []
    for i in range(1, n_pages + 1):
        pid = f"page-{i}"
        page = Document(
            id=pid,
            name=f"scan.pdf — p{i}",
            doc_type=DocType.page,
            parent_id="pdf-parent",
            sequence=i,
            path=None,
            status=Status.pending,
            metadata={},
            created_at=now,
            updated_at=now,
        )
        db.save(page)
        page_ids.append(pid)
    return parent.id, page_ids


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestPerPageFanOutConcurrency:

    def test_parallel_save_artifact_lands_on_each_page_no_skips(self, temp_library):
        """Many threads each save a per-page artifact concurrently.

        Each thread gets its OWN DuckDB connection (the genuine concurrency
        the #2430 race lives in). Assert: every page child ends up with exactly
        one artifact keyed on its own id, the parent PDF has zero artifacts,
        and the total equals the page count (no skips, no duplicates).
        """
        from fichero.workflows.tools.llm_base import save_artifact
        from fichero.models import Artifact, Document

        library_path, db_manager = temp_library
        n_pages = 16

        # Seed on the main thread's connection (committed before fan-out).
        main_db = db_manager.get_database(library_path)
        parent_id, page_ids = _seed_parent_and_pages(main_db, n_pages)

        def _save_one(page_id: str):
            # Runs on a worker thread → its own connection via db_manager.
            return asyncio.run(
                save_artifact(
                    document_id=page_id,
                    file_path="/lib/scan.pdf",      # parent path; must NOT win
                    content=f"Transcription for {page_id}.",
                    data=None,
                    library_path=library_path,
                    llm_config=_make_llm_config(),
                    task_id="run-1",
                    tool_config=_make_tool_config(),
                )
            )

        with ThreadPoolExecutor(max_workers=n_pages) as pool:
            results = list(pool.map(_save_one, page_ids))

        # No worker returned None — i.e. nothing was skipped (#2430).
        assert all(r is not None for r in results), (
            f"Every per-page save must return an artifact id (no skips). "
            f"Got: {results}"
        )

        # Re-read on a fresh connection (this thread's own) and verify rows.
        verify_db = db_manager.get_database(library_path)
        all_artifacts = verify_db.all(Artifact)

        # Exactly one artifact per page, each keyed on its own page id.
        by_doc = {}
        for a in all_artifacts:
            by_doc.setdefault(a.document_id, []).append(a)

        for pid in page_ids:
            assert pid in by_doc, f"Page {pid} lost its artifact (skipped) — #2430"
            assert len(by_doc[pid]) == 1, (
                f"Page {pid} should have exactly 1 artifact, got {len(by_doc[pid])}"
            )

        # Nothing routed to the parent PDF.
        assert parent_id not in by_doc, (
            f"#2430: no artifact may be routed to the parent PDF {parent_id}; "
            f"got {len(by_doc.get(parent_id, []))}"
        )

        # No skips, no duplicates: total == page count.
        assert len(all_artifacts) == n_pages, (
            f"Expected exactly {n_pages} artifacts (one per page), "
            f"got {len(all_artifacts)}"
        )

        # Per-page content landed on each page child (cross-connection write
        # visibility), and never on the parent.
        for pid in page_ids:
            page = verify_db.get(Document, pid)
            assert page is not None and page.page_content == f"Transcription for {pid}.", (
                f"Page {pid} page_content not updated correctly: "
                f"{getattr(page, 'page_content', None)!r}"
            )
        parent = verify_db.get(Document, parent_id)
        assert not parent.page_content, (
            "Parent PDF page_content must remain empty — per-page text must "
            "never be promoted onto the parent (#2430)."
        )

    def test_explicit_id_survives_transient_invisibility(self, temp_library):
        """Deterministic repro of the cross-connection MVCC miss + the fix.

        A second real DuckDB connection opens a transaction that creates a page
        child but does NOT commit. ``save_artifact`` running against the main
        connection therefore cannot see that row — ``db.get`` would return
        ``None`` (the old data-loss skip). The #2430 fix passes the page-child
        document THROUGH (``document=``) so save_artifact uses it directly and
        never re-fetches by id across threads — the artifact lands on the page,
        never the parent, despite the invisible row. (A genuine miss with NO
        document passed returns None — see
        test_no_orphan_when_db_get_misses_and_no_document.)
        """
        from fichero.db import Database
        from fichero.workflows.tools.llm_base import save_artifact
        from fichero.models import Artifact

        library_path, db_manager = temp_library

        # Main connection: parent exists and is committed; the page child does
        # NOT exist on this connection at all.
        main_db = db_manager.get_database(library_path)
        _seed_parent_and_pages(main_db, 0)  # parent only

        # A separate real connection creates the page child inside an OPEN
        # (uncommitted) transaction → invisible to main_db's snapshot.
        from fichero.models import Document, DocType, Status

        other = Database(path=main_db.path)
        try:
            other.conn.execute("BEGIN TRANSACTION")
            now = datetime.now()
            hidden = Document(
                id="page-hidden",
                name="scan.pdf — p1",
                doc_type=DocType.page,
                parent_id="pdf-parent",
                sequence=1,
                status=Status.pending,
                metadata={},
                created_at=now,
                updated_at=now,
            )
            # Insert via the open transaction so it is not auto-committed.
            other.save(hidden)

            # main_db.get("page-hidden") must miss (still uncommitted elsewhere).
            assert main_db.get(Document, "page-hidden") is None, (
                "precondition: hidden page must be invisible on main connection"
            )

            result = asyncio.run(
                save_artifact(
                    document_id="page-hidden",
                    file_path="/lib/scan.pdf",   # parent path — must NOT win
                    content="Hidden page transcription.",
                    data=None,
                    library_path=library_path,
                    llm_config=_make_llm_config(),
                    task_id="run-1",
                    tool_config=_make_tool_config(),
                    document=hidden,  # pass-through: the real #2430 fix
                )
            )
        finally:
            try:
                other.conn.execute("ROLLBACK")
            except Exception:
                pass
            other.close()

        # The artifact must be saved (no skip) and keyed on the page id.
        assert result is not None, (
            "#2430: artifact must NOT be skipped when the page row is "
            "transiently invisible on this connection."
        )
        arts = main_db.query(Artifact, document_id="page-hidden")
        assert len(arts) == 1, f"Expected the artifact on page-hidden, got {arts}"
        assert main_db.query(Artifact, document_id="pdf-parent") == [], (
            "#2430: artifact must never be routed to the parent PDF."
        )

    def test_vision_wrapper_forwards_document_kwarg(self, temp_library):
        """The REAL vision_base.save_artifact wrapper must accept+forward the
        ``document=`` pre-loaded page dict.

        process_vision calls this local wrapper with ``document=_preloaded_doc``
        at every per-page save site. Earlier tests mock save_artifact, so they
        never exercise the wrapper signature — and a missing ``document`` param
        there raises ``TypeError`` at runtime on every per-page save (a latent
        break worse than the original #2430 skip). This guards that seam against
        the REAL DB: a pre-loaded dict whose row does NOT exist on this
        connection must still produce an artifact keyed on the page id.
        """
        from fichero.workflows.tools.vision_base import save_artifact as vision_save_artifact
        from fichero.models import Artifact

        library_path, db_manager = temp_library
        main_db = db_manager.get_database(library_path)
        _seed_parent_and_pages(main_db, 0)  # parent row absent too

        page_dict = {
            "id": "page-pre",
            "name": "scan.pdf — p1",
            "doc_type": "page",
            "parent_id": "pdf-parent",
            "sequence": 1,
            "path": None,
            "page_content": None,
            "status": "pending",
            "metadata": {},
            "created_at": "2026-01-01T00:00:00",
            "updated_at": "2026-01-01T00:00:00",
        }

        artifact_id = asyncio.run(
            vision_save_artifact(
                file_path="/lib/scan.pdf",      # parent path — must NOT win
                content="Pre-loaded page transcription.",
                document_id="page-pre",
                library_path=library_path,
                llm_config=_make_llm_config(),
                task_id="run-1",
                tool_config=_make_tool_config(),
                document=page_dict,             # the seam under test
            )
        )

        assert artifact_id is not None, (
            "vision_base.save_artifact must forward document= and save the "
            "artifact (no TypeError, no skip)."
        )
        arts = main_db.query(Artifact, document_id="page-pre")
        assert len(arts) == 1, f"Expected one artifact on page-pre, got {arts}"
        assert main_db.query(Artifact, document_id="pdf-parent") == [], (
            "#2430: pre-loaded page artifact must never route to the parent PDF."
        )
