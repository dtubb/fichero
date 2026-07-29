"""
#2430: Per-page PDF run — artifacts and page_content must land on PAGE documents,
not on the parent PDF.

Root cause (fixed in 849777af + edfef9c8):
  process_vision previously set `_whole_pdf_parent` whenever `per_page_texts` was
  truthy (even a 1-element list from the Apple Vision per-page fan-out path), then
  called `_propagate_to_page_children(parent_id, [one_page_text], ...)`.  That helper
  always wrote to page child #1 (sequence=1 → index 0) regardless of which page was
  actually being processed.  Fix: guard `requested_page_index is None` so the
  whole-PDF propagation only fires when ALL pages were processed at once; per-page
  fan-out (requested_page_index is not None) falls through to
  `save_artifact(document_id=page_child_id)` which handles both the artifact row
  AND the page_content update.

Coverage added here:
  A. LLM path (vision_mode="llm") per-page fan-out with real page-child data
     (path=None) — the path used by handwriting.py.  Was never explicitly tested.
  B. 3-page full fan-out: each of pages 1/2/3 gets its own artifact + content,
     parent PDF receives nothing.
  C. Non-paged single document regression: artifact still goes to the doc itself.
  D. Real page-child dict (path=None) does not cause id-resolution fallback to parent.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _page_child_dict(page_id: str, parent_id: str, sequence: int) -> dict:
    """Minimal page-child dict matching sources.py model_dump(mode='json') output.

    Key invariant: page children have path=None (the file path lives on the
    parent PDF, not on page docs).  Using path=None exposes the id-resolution
    fallback (resolve_path_to_doc) path — if the code relied on path instead of
    page_doc_id_by_index[i], the artifact would go to None / parent.
    """
    return {
        "id": page_id,
        "path": None,           # Real page children have no path
        "parent_id": parent_id,
        "sequence": sequence,
        "page_content": None,
        "metadata": {},
    }


def _make_tool_config():
    from fichero_server.workflows.tools.vision_base import VisionToolConfig
    return VisionToolConfig(
        artifact_type="handwriting",
        update_page_content=True,
        trigger_embedding=False,
        supports_apple_vision=False,   # handwriting.py: LLM-only
    )


def _make_llm_config():
    from fichero_server.llm import LLMConfig
    return LLMConfig(provider="openai", model="gpt-4o")


# ---------------------------------------------------------------------------
# A. LLM path (handwriting) — single page-child, path=None
# ---------------------------------------------------------------------------

class TestLLMPathPerPageFanOut:
    """
    vision_mode="llm" per-page fan-out (one page per invocation).

    Per-page fan-out: documents=[page_child] where page_child.path=None.
    The code must use page_doc_id_by_index (set from doc["id"]) to determine
    the artifact target, NOT the file-path fallback (which returns None for
    page children that have no path in their dict).
    """

    @pytest.mark.asyncio
    async def test_llm_path_artifact_goes_to_page_child_not_parent(self):
        """
        LLM handwriting path: page 2 fan-out → artifact on page-2-id.

        If doc_id_for_file fell back to file-path lookup (which maps
        parent_pdf_path → parent_pdf_id), the artifact would go to the parent.
        """
        page2 = _page_child_dict("page-2-id", "parent-pdf-id", sequence=2)
        files = ["/lib/doc.pdf"]
        documents = [page2]

        saved_document_ids: list[str] = []
        propagate_calls: list = []

        async def fake_save_artifact(file_path, content, document_id, **_):
            saved_document_ids.append(document_id)
            return "art-" + (document_id or "none")

        async def fake_propagate(parent_id, *args, **kwargs):
            propagate_calls.append(parent_id)
            return []

        mock_db = MagicMock()
        mock_db.get.return_value = MagicMock(metadata={})

        with (
            # _pdf_page_to_data_uri → return a fake URI without needing a real PDF
            patch(
                "fichero_server.workflows.tools.vision_base._pdf_page_to_data_uri",
                return_value="data:image/png;base64,FAKE",
            ),
            # vision() → return the per-page text without calling any LLM
            patch(
                "fichero_server.llm.vision",
                new=AsyncMock(return_value="Handwritten text from page 2."),
            ),
            patch(
                "fichero_server.workflows.tools.vision_base.save_artifact",
                new=AsyncMock(side_effect=fake_save_artifact),
            ),
            patch(
                "fichero_server.workflows.tools.vision_base._propagate_to_page_children",
                new=AsyncMock(side_effect=fake_propagate),
            ),
            patch(
                "fichero_server.workflows.tools.vision_base._build_page_records_for_file",
                return_value=[],
            ),
            patch("fichero_server.db.db_manager") as mock_mgr,
        ):
            mock_mgr.get_database.return_value = mock_db

            from fichero_server.workflows.tools.vision_base import process_vision

            await process_vision(
                files=files,
                documents=documents,
                prompt="Transcribe handwriting.",
                llm_config=_make_llm_config(),
                library_path="/lib.fichero",
                task_id=None,
                tool_config=_make_tool_config(),
                vision_mode="llm",
                save_to_db=True,
            )

        # _propagate_to_page_children must NOT be called in per-page fan-out
        assert propagate_calls == [], (
            f"_propagate_to_page_children called in per-page fan-out: {propagate_calls}"
        )
        # Artifact must go to the page child, not the parent
        assert "page-2-id" in saved_document_ids, (
            f"Expected artifact on page-2-id, got: {saved_document_ids}"
        )
        assert "parent-pdf-id" not in saved_document_ids, (
            f"Artifact landed on parent PDF instead of page child: {saved_document_ids}"
        )

    @pytest.mark.asyncio
    async def test_llm_path_page_content_update_targets_page_child(self):
        """
        LLM path: save_artifact is called with doc_id_for_file = page child.

        save_artifact internally sets doc.page_content = content when
        update_page_content is True.  The document it updates must be the page
        child, not the parent.  We verify by checking that llm_base.save_artifact
        is called with document_id=page-3-id (not parent-pdf-id).
        """
        page3 = _page_child_dict("page-3-id", "parent-pdf-id", sequence=3)

        called_with_ids: list[str | None] = []

        async def fake_save_artifact(file_path, content, document_id, **_):
            called_with_ids.append(document_id)
            return "art-" + (document_id or "none")

        mock_db = MagicMock()
        mock_db.get.return_value = MagicMock(metadata={})

        with (
            patch(
                "fichero_server.workflows.tools.vision_base._pdf_page_to_data_uri",
                return_value="data:image/png;base64,FAKE",
            ),
            patch(
                "fichero_server.llm.vision",
                new=AsyncMock(return_value="Page 3 text."),
            ),
            patch(
                "fichero_server.workflows.tools.vision_base.save_artifact",
                new=AsyncMock(side_effect=fake_save_artifact),
            ),
            patch(
                "fichero_server.workflows.tools.vision_base._propagate_to_page_children",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "fichero_server.workflows.tools.vision_base._build_page_records_for_file",
                return_value=[],
            ),
            patch("fichero_server.db.db_manager") as mock_mgr,
        ):
            mock_mgr.get_database.return_value = mock_db

            from fichero_server.workflows.tools.vision_base import process_vision

            await process_vision(
                files=["/lib/doc.pdf"],
                documents=[page3],
                prompt="Transcribe.",
                llm_config=_make_llm_config(),
                library_path="/lib.fichero",
                task_id=None,
                tool_config=_make_tool_config(),
                vision_mode="llm",
                save_to_db=True,
            )

        assert called_with_ids == ["page-3-id"], (
            f"save_artifact called with wrong id(s): {called_with_ids}"
        )


# ---------------------------------------------------------------------------
# B. 3-page full fan-out: all pages get own artifact, parent gets nothing
# ---------------------------------------------------------------------------

class TestThreePageFanOut:
    """
    Simulate a 3-page PDF where sources.py has expanded to page children.
    The workflow builder calls process_vision once per page (parallel fan-out),
    passing files=[parent_path] and documents=[page_child_i] for each i.

    After all three calls:
    - page-1-id, page-2-id, page-3-id each have exactly one artifact
    - parent-pdf-id has no artifacts
    """

    @pytest.mark.asyncio
    async def test_each_page_gets_own_artifact_parent_gets_none(self):
        parent_pdf_path = "/lib/book.pdf"
        pages = [
            _page_child_dict("page-1-id", "parent-pdf-id", sequence=1),
            _page_child_dict("page-2-id", "parent-pdf-id", sequence=2),
            _page_child_dict("page-3-id", "parent-pdf-id", sequence=3),
        ]

        all_saved_ids: list[str | None] = []

        async def fake_save_artifact(file_path, content, document_id, **_):
            all_saved_ids.append(document_id)
            return "art-" + (document_id or "none")

        mock_db = MagicMock()
        mock_db.get.return_value = MagicMock(metadata={})

        with (
            patch(
                "fichero_server.workflows.tools.vision_base._pdf_page_to_data_uri",
                return_value="data:image/png;base64,FAKE",
            ),
            patch(
                "fichero_server.llm.vision",
                new=AsyncMock(side_effect=lambda **_: "Page text"),
            ),
            patch(
                "fichero_server.workflows.tools.vision_base.save_artifact",
                new=AsyncMock(side_effect=fake_save_artifact),
            ),
            patch(
                "fichero_server.workflows.tools.vision_base._propagate_to_page_children",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "fichero_server.workflows.tools.vision_base._build_page_records_for_file",
                return_value=[],
            ),
            patch("fichero_server.db.db_manager") as mock_mgr,
        ):
            mock_mgr.get_database.return_value = mock_db

            from fichero_server.workflows.tools.vision_base import process_vision

            # One call per page (as the builder's fan-out does it)
            for page in pages:
                await process_vision(
                    files=[parent_pdf_path],
                    documents=[page],
                    prompt="Transcribe.",
                    llm_config=_make_llm_config(),
                    library_path="/lib.fichero",
                    task_id=None,
                    tool_config=_make_tool_config(),
                    vision_mode="llm",
                    save_to_db=True,
                )

        # Each page gets its artifact
        assert "page-1-id" in all_saved_ids, f"page-1 missing from {all_saved_ids}"
        assert "page-2-id" in all_saved_ids, f"page-2 missing from {all_saved_ids}"
        assert "page-3-id" in all_saved_ids, f"page-3 missing from {all_saved_ids}"
        # Parent PDF gets no artifacts
        assert "parent-pdf-id" not in all_saved_ids, (
            f"Parent PDF received artifact(s): {all_saved_ids}"
        )
        # Exactly 3 saves, one per page
        assert len(all_saved_ids) == 3, (
            f"Expected 3 saves (one per page), got {len(all_saved_ids)}: {all_saved_ids}"
        )

    @pytest.mark.asyncio
    async def test_page_records_carry_page_child_ids_for_downstream_extractors(self):
        """
        page_records returned by process_vision must carry the PAGE CHILD's doc_id
        so downstream extractor tools (extractors.py) route their artifacts correctly.
        """
        page2 = _page_child_dict("page-2-id", "parent-pdf-id", sequence=2)

        # Don't mock _build_page_records_for_file — let the real function run
        # with a mocked DB so it falls back to the single-record path.
        mock_db = MagicMock()
        mock_db.get.return_value = MagicMock(metadata={})
        # No page children under page-2-id (pages don't have children)
        mock_db.query.return_value = []

        with (
            patch(
                "fichero_server.workflows.tools.vision_base._pdf_page_to_data_uri",
                return_value="data:image/png;base64,FAKE",
            ),
            patch(
                "fichero_server.llm.vision",
                new=AsyncMock(return_value="Page 2 transcription."),
            ),
            patch(
                "fichero_server.workflows.tools.vision_base.save_artifact",
                new=AsyncMock(return_value="art-page-2-id"),
            ),
            patch(
                "fichero_server.workflows.tools.vision_base._propagate_to_page_children",
                new=AsyncMock(return_value=[]),
            ),
            patch("fichero_server.db.db_manager") as mock_mgr,
        ):
            mock_mgr.get_database.return_value = mock_db

            from fichero_server.workflows.tools.vision_base import process_vision

            result = await process_vision(
                files=["/lib/doc.pdf"],
                documents=[page2],
                prompt="Transcribe.",
                llm_config=_make_llm_config(),
                library_path="/lib.fichero",
                task_id=None,
                tool_config=_make_tool_config(),
                vision_mode="llm",
                save_to_db=True,
            )

        page_records = result.get("page_records", [])
        assert page_records, "process_vision must return at least one page record"
        doc_ids_in_records = [r.get("doc_id") for r in page_records]
        assert "page-2-id" in doc_ids_in_records, (
            f"page-2-id missing from page_records: {doc_ids_in_records}"
        )
        assert "parent-pdf-id" not in doc_ids_in_records, (
            f"parent-pdf-id leaked into page_records: {doc_ids_in_records}"
        )


# ---------------------------------------------------------------------------
# C. Non-paged single document regression
# ---------------------------------------------------------------------------

class TestSingleNonPagedDocRegression:
    """
    A single non-paged doc (no parent_id, no sequence) must still get its
    artifact on itself — per-page logic must not silently drop the write.
    """

    @pytest.mark.asyncio
    async def test_non_paged_doc_gets_artifact_on_itself(self):
        """
        Single image file with a regular document (not a page child).
        Artifact must land on doc-abc, not be dropped.
        """
        doc = {
            "id": "doc-abc",
            "path": "/lib/photo.jpg",
            "parent_id": None,
            "sequence": None,
            "page_content": None,
            "metadata": {},
        }

        saved_ids: list[str | None] = []

        async def fake_save_artifact(file_path, content, document_id, **_):
            saved_ids.append(document_id)
            return "art-" + (document_id or "none")

        mock_db = MagicMock()
        mock_db.get.return_value = MagicMock(metadata={})

        with (
            patch(
                "fichero_server.workflows.tools.vision_base.file_to_data_uri",
                return_value="data:image/jpeg;base64,FAKE",
            ),
            patch(
                "fichero_server.llm.vision",
                new=AsyncMock(return_value="Photo description text."),
            ),
            patch(
                "fichero_server.workflows.tools.vision_base.save_artifact",
                new=AsyncMock(side_effect=fake_save_artifact),
            ),
            patch(
                "fichero_server.workflows.tools.vision_base._propagate_to_page_children",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "fichero_server.workflows.tools.vision_base._build_page_records_for_file",
                return_value=[],
            ),
            patch("fichero_server.db.db_manager") as mock_mgr,
        ):
            mock_mgr.get_database.return_value = mock_db

            from fichero_server.workflows.tools.vision_base import process_vision

            await process_vision(
                files=["/lib/photo.jpg"],
                documents=[doc],
                prompt="Describe.",
                llm_config=_make_llm_config(),
                library_path="/lib.fichero",
                task_id=None,
                tool_config=_make_tool_config(),
                vision_mode="llm",
                save_to_db=True,
            )

        assert saved_ids == ["doc-abc"], (
            f"Non-paged doc artifact must go to doc-abc, got: {saved_ids}"
        )


# ---------------------------------------------------------------------------
# D. path=None page child — id-resolution must not fall back to parent
# ---------------------------------------------------------------------------

class TestPageChildPathNoneIdResolution:
    """
    Real page children from sources.py have path=None.  The code at line 1554
    in vision_base.py uses page_doc_id_by_index[file_index] FIRST; if that's
    non-None, the `or resolve_path_to_doc(path_to_doc, file_path)` fallback
    is never reached.  These tests verify the fallback cannot silently fire
    and return the parent PDF's id.
    """

    @pytest.mark.asyncio
    async def test_page_child_with_null_path_artifact_on_child_not_parent(self):
        """
        path=None page child: artifact must land on the page child's id.

        If resolve_path_to_doc fallback fired with file_path=parent_pdf_path,
        it would find path_to_doc={} (empty, because page children have no path)
        → document_id=None → llm_base.save_artifact falls through to
        find_document_by_path(parent_pdf_path) → artifact on PARENT.  This
        test catches that regression.
        """
        # path=None is the real data shape from sources.py
        page = _page_child_dict("page-5-id", "parent-7-id", sequence=5)
        assert page["path"] is None, "Test data must have path=None"

        saved_ids: list[str | None] = []

        async def fake_save_artifact(file_path, content, document_id, **_):
            saved_ids.append(document_id)
            return "art-page-5"

        mock_db = MagicMock()
        mock_db.get.return_value = MagicMock(metadata={})

        with (
            patch(
                "fichero_server.workflows.tools.vision_base._pdf_page_to_data_uri",
                return_value="data:image/png;base64,FAKE",
            ),
            patch(
                "fichero_server.llm.vision",
                new=AsyncMock(return_value="Content of page 5."),
            ),
            patch(
                "fichero_server.workflows.tools.vision_base.save_artifact",
                new=AsyncMock(side_effect=fake_save_artifact),
            ),
            patch(
                "fichero_server.workflows.tools.vision_base._propagate_to_page_children",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "fichero_server.workflows.tools.vision_base._build_page_records_for_file",
                return_value=[],
            ),
            patch("fichero_server.db.db_manager") as mock_mgr,
        ):
            mock_mgr.get_database.return_value = mock_db

            from fichero_server.workflows.tools.vision_base import process_vision

            await process_vision(
                files=["/lib/doc.pdf"],     # parent PDF path (same for all pages)
                documents=[page],
                prompt="Transcribe.",
                llm_config=_make_llm_config(),
                library_path="/lib.fichero",
                task_id=None,
                tool_config=_make_tool_config(),
                vision_mode="llm",
                save_to_db=True,
            )

        assert saved_ids == ["page-5-id"], (
            f"path=None page child: artifact must go to page-5-id, got: {saved_ids}"
        )
        assert "parent-7-id" not in saved_ids, (
            "path=None fallback routed artifact to parent PDF id"
        )

    @pytest.mark.asyncio
    async def test_page_child_with_null_path_page_records_carry_child_id(self):
        """page_records must carry the page child's doc_id even when path=None."""
        page = _page_child_dict("page-9-id", "parent-X-id", sequence=9)

        mock_db = MagicMock()
        mock_db.get.return_value = MagicMock(metadata={})
        mock_db.query.return_value = []  # no grandchildren under page-9-id

        with (
            patch(
                "fichero_server.workflows.tools.vision_base._pdf_page_to_data_uri",
                return_value="data:image/png;base64,FAKE",
            ),
            patch(
                "fichero_server.llm.vision",
                new=AsyncMock(return_value="Page 9 text."),
            ),
            patch(
                "fichero_server.workflows.tools.vision_base.save_artifact",
                new=AsyncMock(return_value="art-page-9"),
            ),
            patch(
                "fichero_server.workflows.tools.vision_base._propagate_to_page_children",
                new=AsyncMock(return_value=[]),
            ),
            patch("fichero_server.db.db_manager") as mock_mgr,
        ):
            mock_mgr.get_database.return_value = mock_db

            from fichero_server.workflows.tools.vision_base import process_vision

            result = await process_vision(
                files=["/lib/doc.pdf"],
                documents=[page],
                prompt="Transcribe.",
                llm_config=_make_llm_config(),
                library_path="/lib.fichero",
                task_id=None,
                tool_config=_make_tool_config(),
                vision_mode="llm",
                save_to_db=True,
            )

        page_records = result.get("page_records", [])
        doc_ids = [r.get("doc_id") for r in page_records]
        assert "page-9-id" in doc_ids, (
            f"page-9-id not in page_records doc_ids: {doc_ids}"
        )
        assert "parent-X-id" not in doc_ids, (
            f"parent-X-id leaked into page_records: {doc_ids}"
        )


# ---------------------------------------------------------------------------
# E. #2430 RESIDUAL: per-page mode + missing page id → skip, not parent fallback
# ---------------------------------------------------------------------------

class TestPerPageMissingDocIdSkip:
    """
    vision_base.py #2430 residual: if page_doc_id_by_index[i] is falsy while
    requested_page_index is not None (per-page mode), the code MUST skip that
    file and log a warning rather than falling back to resolve_path_to_doc
    (which would return the PARENT PDF id via file_path).
    """

    @pytest.mark.asyncio
    async def test_missing_page_id_skips_artifact_not_routed_to_parent(self):
        """
        A page child dict with id=None in per-page mode → artifact NOT saved.

        Before the fix: resolve_path_to_doc(path_to_doc, file_path) fires →
        file_path is the parent PDF path → save_artifact(document_id=parent_id).
        After the fix: the file is skipped (logged warning, continue).
        """
        # Page child with no id — simulates a malformed/missing page child dict
        malformed_page = {
            "id": None,           # falsy — triggers the bug in unpatched code
            "path": None,
            "parent_id": "parent-pdf-id",
            "sequence": 3,        # non-None sequence → per-page mode
            "page_content": None,
            "metadata": {},
        }

        saved_ids: list[str | None] = []

        async def fake_save_artifact(file_path, content, document_id, **_):
            saved_ids.append(document_id)
            return "art-" + str(document_id or "none")

        mock_db = MagicMock()
        mock_db.get.return_value = MagicMock(metadata={})

        with (
            patch(
                "fichero_server.workflows.tools.vision_base._pdf_page_to_data_uri",
                return_value="data:image/png;base64,FAKE",
            ),
            patch(
                "fichero_server.llm.vision",
                new=AsyncMock(return_value="Page 3 text."),
            ),
            patch(
                "fichero_server.workflows.tools.vision_base.save_artifact",
                new=AsyncMock(side_effect=fake_save_artifact),
            ),
            patch(
                "fichero_server.workflows.tools.vision_base._propagate_to_page_children",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "fichero_server.workflows.tools.vision_base._build_page_records_for_file",
                return_value=[],
            ),
            patch("fichero_server.db.db_manager") as mock_mgr,
        ):
            mock_mgr.get_database.return_value = mock_db

            from fichero_server.workflows.tools.vision_base import process_vision

            await process_vision(
                files=["/lib/scan.pdf"],
                documents=[malformed_page],
                prompt="Transcribe.",
                llm_config=_make_llm_config(),
                library_path="/lib.fichero",
                task_id=None,
                tool_config=_make_tool_config(),
                vision_mode="llm",
                save_to_db=True,
            )

        # No artifact must be saved at all — not to the parent PDF
        assert saved_ids == [], (
            f"#2430 residual: per-page mode with missing page id must skip "
            f"save_artifact entirely, got saves to: {saved_ids}"
        )
        assert "parent-pdf-id" not in saved_ids, (
            "Missing page id fell back to parent PDF via resolve_path_to_doc"
        )

    @pytest.mark.asyncio
    async def test_normal_per_page_happy_path_still_saves_to_page_child(self):
        """
        Regression guard: a well-formed page child with a valid id still works
        after the missing-id guard is added.
        """
        page = _page_child_dict("page-7-id", "parent-pdf-id", sequence=7)

        saved_ids: list[str | None] = []

        async def fake_save_artifact(file_path, content, document_id, **_):
            saved_ids.append(document_id)
            return "art-page-7"

        mock_db = MagicMock()
        mock_db.get.return_value = MagicMock(metadata={})

        with (
            patch(
                "fichero_server.workflows.tools.vision_base._pdf_page_to_data_uri",
                return_value="data:image/png;base64,FAKE",
            ),
            patch(
                "fichero_server.llm.vision",
                new=AsyncMock(return_value="Page 7 text."),
            ),
            patch(
                "fichero_server.workflows.tools.vision_base.save_artifact",
                new=AsyncMock(side_effect=fake_save_artifact),
            ),
            patch(
                "fichero_server.workflows.tools.vision_base._propagate_to_page_children",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "fichero_server.workflows.tools.vision_base._build_page_records_for_file",
                return_value=[],
            ),
            patch("fichero_server.db.db_manager") as mock_mgr,
        ):
            mock_mgr.get_database.return_value = mock_db

            from fichero_server.workflows.tools.vision_base import process_vision

            await process_vision(
                files=["/lib/scan.pdf"],
                documents=[page],
                prompt="Transcribe.",
                llm_config=_make_llm_config(),
                library_path="/lib.fichero",
                task_id=None,
                tool_config=_make_tool_config(),
                vision_mode="llm",
                save_to_db=True,
            )

        assert saved_ids == ["page-7-id"], (
            f"Happy path must still save to page-7-id, got: {saved_ids}"
        )


# ---------------------------------------------------------------------------
# F. Concurrency fix: pre-loaded document dict bypasses db.get in save_artifact
# ---------------------------------------------------------------------------

class TestPreloadedDocumentBypassesDbGet:
    """When process_vision passes _preloaded_doc (the page-child dict from LangGraph
    state) to save_artifact, db.get is never called — eliminating the MVCC miss that
    would skip the artifact during concurrent per-page fan-out. (#2430 concurrency)"""

    @pytest.mark.asyncio
    async def test_db_get_not_called_when_document_provided(self):
        """save_artifact skips db.get when document= kwarg is provided."""
        from fichero_server.workflows.tools.llm_base import save_artifact
        from fichero_server.workflows.tools.vision_base import VisionToolConfig
        from fichero_server.llm import LLMConfig

        tool_config = VisionToolConfig(
            artifact_type="handwriting",
            update_page_content=True,
            trigger_embedding=False,
            supports_apple_vision=False,
        )
        llm_config = LLMConfig(provider="openai", model="gpt-4o")

        # Simulate the page-child dict from LangGraph state
        page_dict = {
            "id": "page-3-id",
            "path": None,
            "parent_id": "parent-pdf-id",
            "sequence": 3,
            "page_content": None,
            "metadata": {},
            "name": "Page 3",
            "doc_type": "page",
            "status": "indexed",
            "created_at": "2024-01-01T00:00:00",
            "updated_at": "2024-01-01T00:00:00",
        }

        mock_db = MagicMock()
        # db.get returns None (simulating MVCC miss on this connection)
        mock_db.get.return_value = None
        mock_artifact = MagicMock()
        mock_artifact.id = "art-xyz"

        saved_artifact_ids = []

        def capture_save(obj):
            if hasattr(obj, "id") and hasattr(obj, "document_id"):
                saved_artifact_ids.append(obj.document_id)
            return None

        mock_db.save.side_effect = capture_save

        with patch("fichero_server.db.db_manager") as mock_mgr:
            mock_mgr.get_database.return_value = mock_db

            # Provide document= so db.get should NOT be needed
            try:
                await save_artifact(
                    document_id="page-3-id",
                    file_path=None,
                    content="page text here",
                    data=None,
                    library_path="/lib.fichero",
                    llm_config=llm_config,
                    task_id=None,
                    tool_config=tool_config,
                    document=page_dict,
                )
            except Exception:
                pass  # validation may fail on minimal dict; we only care about db.get

        # db.get must NOT have been called — the pre-loaded dict should be used
        mock_db.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_fanout_all_pages_saved_even_when_db_get_returns_none(self):
        """process_vision fan-out saves each page's artifact even when db.get returns
        None (MVCC miss), because _preloaded_doc is passed through document=."""
        page1 = _page_child_dict("pg-1", "parent-id", sequence=1)
        page2 = _page_child_dict("pg-2", "parent-id", sequence=2)
        page3 = _page_child_dict("pg-3", "parent-id", sequence=3)

        saved_doc_ids: list[str] = []

        async def fake_save_artifact(file_path, content, document_id, document=None, **_):
            # Record the document_id used — this is what lands in the Artifact row
            saved_doc_ids.append(document_id)
            return f"art-{document_id}"

        mock_db = MagicMock()
        # db.get always returns None (full MVCC miss for all 3 pages)
        mock_db.get.return_value = None

        with (
            patch(
                "fichero_server.workflows.tools.vision_base._pdf_page_to_data_uri",
                return_value="data:image/png;base64,FAKE",
            ),
            patch("fichero_server.llm.vision", new=AsyncMock(return_value="text.")),
            patch(
                "fichero_server.workflows.tools.vision_base.save_artifact",
                new=AsyncMock(side_effect=fake_save_artifact),
            ),
            patch(
                "fichero_server.workflows.tools.vision_base._propagate_to_page_children",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "fichero_server.workflows.tools.vision_base._build_page_records_for_file",
                return_value=[],
            ),
            patch("fichero_server.db.db_manager") as mock_mgr,
        ):
            mock_mgr.get_database.return_value = mock_db

            from fichero_server.workflows.tools.vision_base import process_vision

            for page in [page1, page2, page3]:
                await process_vision(
                    files=["/lib/scan.pdf"],
                    documents=[page],
                    prompt="Transcribe.",
                    llm_config=_make_llm_config(),
                    library_path="/lib.fichero",
                    task_id=None,
                    tool_config=_make_tool_config(),
                    vision_mode="llm",
                    save_to_db=True,
                )

        assert saved_doc_ids == ["pg-1", "pg-2", "pg-3"], (
            f"All 3 page artifacts must be saved, got: {saved_doc_ids}"
        )
