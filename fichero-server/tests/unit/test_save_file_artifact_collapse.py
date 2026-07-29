"""
#2533: the per-media-family `save_artifact` wrappers are collapsed onto the
single shared `llm_base.save_file_artifact`, which forwards to the canonical
`llm_base.save_artifact`.

Before #2533 each family (vision, audio, video) — plus the file-keyed text tool
`extract` — declared its own thin `save_artifact` wrapper. That was a drift
surface: a future family could silently re-introduce the #2430 parent-reroute
bug, and audio/video had already diverged (they lacked the `document=`
pass-through that vision carried). This collapses all of them onto ONE wrapper so
the per-page save contract lives in exactly one place.

These tests are the safety net for the collapse:

  1. Identity: every family's exported `save_artifact` IS the one shared helper
     (one save path, no per-family re-derivation).
  2. Per-family contract: calling each family's `save_artifact` with an explicit
     per-page `document_id` lands the artifact on THAT id, never the parent.
  3. Regression: a genuine lookup miss (db.get returns None, no `document=`)
     returns None and never reroutes to the parent PDF — for every family.

The interior document-resolution logic is exercised against the canonical
`save_artifact` in test_save_artifact_page_child_resolution.py; here we prove the
FAMILY-FACING seams all funnel through it identically.

NOTE: db_manager is imported INSIDE save_artifact via `from fichero_server.db import
db_manager`, so the patch target is "fichero_server.db.db_manager". find_document_by_path
is imported at llm_base module scope, so it patches at
"fichero_server.workflows.tools.llm_base.find_document_by_path".
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# The family-facing `save_artifact` seams under test. Each entry is
# (label, callable). After the #2533 collapse they must all be the SAME object.
# ---------------------------------------------------------------------------

def _family_save_artifacts():
    from fichero_server.workflows.tools.vision_base import save_artifact as vision_save
    from fichero_server.workflows.tools.audio_base import save_artifact as audio_save
    from fichero_server.workflows.tools.video_base import save_artifact as video_save
    from fichero_server.workflows.tools.extract import save_artifact as extract_save
    return [
        ("vision", vision_save),
        ("audio", audio_save),
        ("video", video_save),
        ("extract", extract_save),
    ]


# ---------------------------------------------------------------------------
# Minimal stubs (mirrors test_save_artifact_page_child_resolution.py)
# ---------------------------------------------------------------------------

def _make_document(doc_id: str, path: str | None = None):
    from fichero_server.models import Document, DocType, Status
    return Document(
        id=doc_id,
        name="doc",
        doc_type=DocType.file,
        path=path,
        page_content=None,
        status=Status.pending,
        metadata={},
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )


def _make_llm_config():
    from fichero_server.llm import LLMConfig
    return LLMConfig(provider="openai", model="gpt-4o")


def _make_tool_config():
    from fichero_server.workflows.tools.llm_base import LLMToolConfig
    # update_page_content=False keeps the test focused on artifact routing
    # (the page_content promotion branch is covered elsewhere).
    return LLMToolConfig(
        artifact_type="transcription",
        update_page_content=False,
        trigger_embedding=False,
        skip_if_artifact_exists=False,
    )


# ---------------------------------------------------------------------------
# 1. Identity — the collapse itself
# ---------------------------------------------------------------------------

def test_all_families_share_one_save_path():
    """Every family's `save_artifact` IS `llm_base.save_file_artifact`.

    This is the structural guarantee of #2533: there is exactly one
    file-oriented save path. If a future change re-introduces a per-family
    wrapper, this identity check fails loudly.
    """
    from fichero_server.workflows.tools.llm_base import save_file_artifact

    for label, fn in _family_save_artifacts():
        assert fn is save_file_artifact, (
            f"{label}.save_artifact must BE the shared llm_base.save_file_artifact "
            f"(one save path, no per-family wrapper) — got a different object."
        )


# ---------------------------------------------------------------------------
# 2. Per-family contract — explicit per-page id lands on the page child
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("label,family_save", _family_save_artifacts())
def test_family_save_lands_on_page_child(label, family_save):
    """Saving with an explicit per-page document_id attributes the artifact to
    THAT id — never the parent PDF whose path is also supplied.

    Driven via asyncio.run (sync test) to mirror test_per_page_fanout_concurrency
    and sidestep the anyio+parametrize interaction.
    """
    page_child = _make_document("page-child-id", path=None)

    saved_artifacts: list = []
    mock_db = MagicMock()
    mock_db.get.return_value = page_child           # db.get resolves the page child
    mock_db.save.side_effect = saved_artifacts.append

    with patch("fichero_server.db.db_manager") as mgr:
        mgr.get_database.return_value = mock_db
        artifact_id = asyncio.run(
            family_save(
                file_path="/lib/scan.pdf",          # parent PDF path — must NOT win
                content=f"{label} page-1 transcription.",
                document_id="page-child-id",
                library_path="/lib",
                llm_config=_make_llm_config(),
                task_id=None,
                tool_config=_make_tool_config(),
            )
        )

    assert artifact_id is not None, f"{label}: artifact must be saved, not skipped"
    assert saved_artifacts, f"{label}: save_artifact must persist something"
    assert saved_artifacts[0].document_id == "page-child-id", (
        f"{label}: artifact must land on the page child, "
        f"got {saved_artifacts[0].document_id}"
    )


# ---------------------------------------------------------------------------
# 3. Regression — genuine miss returns None, never reroutes to the parent
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("label,family_save", _family_save_artifacts())
def test_family_genuine_miss_returns_none_no_parent_reroute(label, family_save):
    """An explicit document_id that fails to resolve (db.get None, no document=)
    must FAIL LOUD — return None and never write to the parent PDF via the
    file_path fallback (#2430 / #2523, no silent reroute)."""
    parent_pdf = _make_document("parent-pdf-id", path="/lib/scan.pdf")

    saved_artifacts: list = []
    mock_db = MagicMock()
    mock_db.get.return_value = None                 # transient cross-connection miss
    mock_db.save.side_effect = saved_artifacts.append

    with patch("fichero_server.db.db_manager") as mgr, patch(
        "fichero_server.workflows.tools.llm_base.find_document_by_path",
        return_value=parent_pdf,                    # would reroute if fallback fired
    ):
        mgr.get_database.return_value = mock_db
        result = asyncio.run(
            family_save(
                file_path="/lib/scan.pdf",
                content=f"{label} page-1 transcription.",
                document_id="page-child-id",
                library_path="/lib",
                llm_config=_make_llm_config(),
                task_id=None,
                tool_config=_make_tool_config(),
                # NB: no document= passed — the genuine-miss path.
            )
        )

    assert result is None, (
        f"{label}: explicit-id miss with no document= must return None, "
        f"not fabricate an artifact."
    )
    saved_ids = [a.document_id for a in saved_artifacts if hasattr(a, "document_id")]
    assert "page-child-id" not in saved_ids, (
        f"{label}: no orphan artifact may be saved on the unverified page id. "
        f"Got: {saved_ids}"
    )
    assert "parent-pdf-id" not in saved_ids, (
        f"{label}: #2430 — must NEVER route the artifact to the parent PDF. "
        f"Got: {saved_ids}"
    )


# ---------------------------------------------------------------------------
# 4. document= pass-through is now uniform across families (audio/video gained
#    it in the collapse; previously only vision carried it).
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("label,family_save", _family_save_artifacts())
def test_family_forwards_document_kwarg(label, family_save):
    """Every family's save path accepts and uses `document=` so the per-page
    fan-out can dodge the cross-thread db.get re-fetch race (#2430). The passed
    document is the resolution source — db.get must not be consulted.

    audio/video GAINED this passthrough in the #2533 collapse (previously only
    vision carried it); this pins it uniform across all families.
    """
    page_dict = _make_document("page-pre", path=None).model_dump()

    saved_artifacts: list = []
    mock_db = MagicMock()
    mock_db.save.side_effect = saved_artifacts.append

    with patch("fichero_server.db.db_manager") as mgr:
        mgr.get_database.return_value = mock_db
        artifact_id = asyncio.run(
            family_save(
                file_path="/lib/scan.pdf",
                content=f"{label} pre-loaded page.",
                document_id="page-pre",
                library_path="/lib",
                llm_config=_make_llm_config(),
                task_id=None,
                tool_config=_make_tool_config(),
                document=page_dict,                 # the seam: must be accepted + used
            )
        )

    assert artifact_id is not None, f"{label}: document= passthrough must save"
    mock_db.get.assert_not_called()  # passed doc is the source; no racy re-fetch
    assert saved_artifacts[0].document_id == "page-pre", (
        f"{label}: pre-loaded page artifact must land on its own id."
    )
