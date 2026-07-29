"""#2544 — bound the eager load of folder/collection sources.

A folder/collection source otherwise loads ALL Documents eagerly into workflow
state: a 100k-image folder materializes 100k Document objects + 100k JSON dicts
before any processing starts, blowing up RAM up front.

These tests pin the cap behaviour:
  - a folder UNDER the cap returns everything (the common case is unchanged);
  - a folder OVER the cap returns exactly `cap` files + documents, index-aligned;
  - clipping emits a LOUD warning naming the cap and how to raise it (no silent
    truncation);
  - the cap is overridable via FICHERO_SOURCE_MAX_FILES (incl. 0 = unbounded);
  - files/documents stay index-aligned at and across the cap boundary.
"""
from __future__ import annotations

import logging

import pytest
from unittest.mock import patch

from fichero_server.models import Document, DocType, FileType
from fichero_server.llm import LLMConfig
from fichero_server.workflows.tools.sources import (
    _source_max_files,
    _resolve_source_limit,
    _load_capped_folder_files,
    _DEFAULT_SOURCE_MAX_FILES,
    folder_tool,
)

_LLM_CFG = LLMConfig(provider="openai", model="gpt-4o", api_key="test-key")
_LIB = "/Users/test/Library"


class _StubDB:
    """Minimal DB stub backed by a real document hierarchy.

    `_get_files_in_folder` runs for real against this (it is NOT patched), so the
    cap path is exercised end-to-end. Image files are used so folder_tool's
    per-page PDF expansion never triggers (page-children query returns []).
    """

    def __init__(self, docs: list[Document]):
        self._docs = {d.id: d for d in docs}

    def get(self, _model, doc_id):
        return self._docs.get(doc_id)

    def query(self, _model, **kwargs):
        results = list(self._docs.values())
        for k, v in kwargs.items():
            results = [d for d in results if getattr(d, k, None) == v]
        return results


def _make_folder_with_files(n: int, folder_id: str = "folder-1") -> _StubDB:
    folder = Document(id=folder_id, name="Big Folder", doc_type=DocType.folder)
    files = [
        Document(
            id=f"img{i:06d}",
            name=f"scan_{i:06d}.jpg",
            doc_type=DocType.file,
            file_type=FileType.image,
            path=f"files/fi/scan_{i:06d}.jpg",
            parent_id=folder_id,
        )
        for i in range(n)
    ]
    return _StubDB([folder, *files])


# ---------------------------------------------------------------------------
# Cap resolution helpers
# ---------------------------------------------------------------------------


def test_source_max_files_default_when_env_unset(monkeypatch):
    monkeypatch.delenv("FICHERO_SOURCE_MAX_FILES", raising=False)
    assert _source_max_files() == _DEFAULT_SOURCE_MAX_FILES


def test_source_max_files_env_override(monkeypatch):
    monkeypatch.setenv("FICHERO_SOURCE_MAX_FILES", "42")
    assert _source_max_files() == 42


def test_source_max_files_zero_is_unbounded(monkeypatch):
    monkeypatch.setenv("FICHERO_SOURCE_MAX_FILES", "0")
    assert _source_max_files() == 0


def test_source_max_files_garbage_falls_back_to_default(monkeypatch, caplog):
    monkeypatch.setenv("FICHERO_SOURCE_MAX_FILES", "not-a-number")
    with caplog.at_level(logging.WARNING):
        assert _source_max_files() == _DEFAULT_SOURCE_MAX_FILES
    assert "FICHERO_SOURCE_MAX_FILES" in caplog.text


def test_resolve_source_limit_explicit_per_run_limit_wins(monkeypatch):
    monkeypatch.setenv("FICHERO_SOURCE_MAX_FILES", "5000")
    # An explicit per-run limit is already a deliberate cap and takes precedence.
    assert _resolve_source_limit(10) == 10


def test_resolve_source_limit_falls_back_to_env_when_unspecified(monkeypatch):
    monkeypatch.setenv("FICHERO_SOURCE_MAX_FILES", "123")
    assert _resolve_source_limit(0) == 123


# ---------------------------------------------------------------------------
# _load_capped_folder_files
# ---------------------------------------------------------------------------


def test_under_cap_returns_everything(monkeypatch):
    """The common case: a small folder is entirely unaffected by the cap."""
    monkeypatch.setenv("FICHERO_SOURCE_MAX_FILES", "5000")
    db = _make_folder_with_files(20)

    files = _load_capped_folder_files(
        db,
        "folder-1",
        recursive=False,
        file_types=[],
        status_filter="all",
        requested_limit=0,
        source_label="Folder folder-1",
    )
    assert len(files) == 20


def test_over_cap_returns_exactly_cap_and_logs_loudly(monkeypatch, caplog):
    monkeypatch.setenv("FICHERO_SOURCE_MAX_FILES", "10")
    db = _make_folder_with_files(25)

    with caplog.at_level(logging.WARNING):
        files = _load_capped_folder_files(
            db,
            "folder-1",
            recursive=False,
            file_types=[],
            status_filter="all",
            requested_limit=0,
            source_label="Folder folder-1",
        )

    assert len(files) == 10, "over-cap folder must return exactly `cap` files"
    # Loud, honest warning — names the cap, says more were dropped, and how to raise.
    assert "10-file source cap" in caplog.text
    assert "FICHERO_SOURCE_MAX_FILES" in caplog.text
    assert "NOT processed" in caplog.text


def test_exactly_cap_does_not_warn(monkeypatch, caplog):
    """A folder with exactly `cap` files is taken whole, with no clip warning."""
    monkeypatch.setenv("FICHERO_SOURCE_MAX_FILES", "10")
    db = _make_folder_with_files(10)

    with caplog.at_level(logging.WARNING):
        files = _load_capped_folder_files(
            db,
            "folder-1",
            recursive=False,
            file_types=[],
            status_filter="all",
            requested_limit=0,
            source_label="Folder folder-1",
        )

    assert len(files) == 10
    assert "source cap" not in caplog.text


def test_env_zero_disables_cap(monkeypatch):
    """FICHERO_SOURCE_MAX_FILES=0 is the explicit opt-in for ALL files."""
    monkeypatch.setenv("FICHERO_SOURCE_MAX_FILES", "0")
    db = _make_folder_with_files(37)

    files = _load_capped_folder_files(
        db,
        "folder-1",
        recursive=False,
        file_types=[],
        status_filter="all",
        requested_limit=0,
        source_label="Folder folder-1",
    )
    assert len(files) == 37


# ---------------------------------------------------------------------------
# End-to-end through folder_tool: index alignment preserved at the boundary
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_folder_tool_caps_and_keeps_files_documents_aligned(monkeypatch):
    monkeypatch.setenv("FICHERO_SOURCE_MAX_FILES", "5")
    db = _make_folder_with_files(50)

    with (
        patch("fichero_server.workflows.tools.sources.db_manager") as mock_dbm,
        patch(
            "fichero_server.workflows.tools.sources._resolve_abs_path",
            side_effect=lambda doc, lib: f"{lib}/{doc.path}",
        ),
    ):
        mock_dbm.get_database.return_value = db
        result = await folder_tool(
            inputs={"folder_id": "folder-1"},
            state={"library_path": _LIB},
            llm_config=_LLM_CFG,
        )

    files = result["files"]
    docs = result["documents"]
    assert len(files) == 5, "folder_tool must clip to the cap"
    assert len(docs) == 5, "documents must clip with files"
    # Index-aligned: documents[i] is the doc whose path produced files[i].
    for path, doc in zip(files, docs):
        assert doc["name"] in path, f"{doc['name']!r} not aligned with {path!r}"


@pytest.mark.asyncio
async def test_folder_tool_under_cap_unchanged(monkeypatch):
    """A normal 20-file folder behaves exactly as before — no clipping."""
    monkeypatch.setenv("FICHERO_SOURCE_MAX_FILES", "5000")
    db = _make_folder_with_files(20)

    with (
        patch("fichero_server.workflows.tools.sources.db_manager") as mock_dbm,
        patch(
            "fichero_server.workflows.tools.sources._resolve_abs_path",
            side_effect=lambda doc, lib: f"{lib}/{doc.path}",
        ),
    ):
        mock_dbm.get_database.return_value = db
        result = await folder_tool(
            inputs={"folder_id": "folder-1"},
            state={"library_path": _LIB},
            llm_config=_LLM_CFG,
        )

    assert len(result["files"]) == 20
    assert len(result["documents"]) == 20
