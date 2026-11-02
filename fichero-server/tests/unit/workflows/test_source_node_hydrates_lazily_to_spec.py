"""`workflows.source-node-hydrates-lazily` (#4390): a source node's output carries ids; a tool gets the text when it runs.

WHY: 500 pages x 40 KB held 20 MB of page text in run state for the whole run
(docs/contributor_manual/design/workflow-source-node-memory.md). State now holds references; the one call that reads a page
gets the full document, and the hydrated copy is not stored back.
"""

from __future__ import annotations

import json

import pytest

from fichero_server.llm import LLMConfig
from fichero_server.models import Document, DocType, FileType
from fichero_server.workflows.builder import _make_node_function
from fichero_server.workflows.document_refs import REF_AWARE_TOOLS, hydrate_documents, is_ref, slim_documents
from fichero_server.workflows.types import NodeDef

LLM = LLMConfig(provider="openai", model="gpt-4o-mini")
TEXT = "page text " * 4000  # about 40 KB


@pytest.fixture
def library(tmp_path, monkeypatch):
    from tests.integration._seedlib import seed

    from fichero_server.db import db_manager

    monkeypatch.setenv("FICHERO_SKIP_DEFAULT_WORKFLOWS", "1")
    path = tmp_path / "lazy.fichero"
    seed(path)
    db = db_manager.get_database(path)
    for i in range(20):
        db.save(Document(id=f"p{i}", name=f"p{i}", doc_type=DocType.page, file_type=FileType.image,
                         path=f"files/p{i}.jpg", page_content=f"{i}: {TEXT}", sequence=i))
    yield str(path), db
    db_manager.close_database(path)


def _full(db, n=20):
    return [db.get(Document, f"p{i}").model_dump(mode="json") for i in range(n)]


def _node(tool, fn, config=None):
    return _make_node_function(NodeDef(id=tool, tool=tool, label=tool, config=config or {}), fn, LLM,
                               workflow_config={}, incoming_edges=[])


def test_a_reference_carries_who_and_where_never_the_text(library):
    _, db = library
    refs = slim_documents(_full(db))
    assert all(is_ref(r) and "page_content" not in r for r in refs)
    assert len(json.dumps(refs)) < len(json.dumps(_full(db))) / 50


def test_hydrate_gives_back_the_full_document_and_leaves_full_ones_alone(library):
    path, db = library
    full = _full(db, 3)
    back = hydrate_documents(slim_documents(full), path)
    assert [d["page_content"] for d in back] == [d["page_content"] for d in full]
    assert hydrate_documents(full, path) == full
    assert hydrate_documents(slim_documents(full), None)[0].get("page_content") is None  # no library: stays a reference


@pytest.mark.asyncio
async def test_the_source_node_stores_references_in_state(library):
    path, db = library

    async def source(inputs, state, llm_config):
        return {"files": [f"files/p{i}.jpg" for i in range(20)], "documents": _full(db), "count": 20}

    update = await _node("files", source)({"outputs": {}, "completed_nodes": [], "task_id": "r", "library_path": path})
    docs = update["outputs"]["files"]["documents"]
    assert len(docs) == 20 and all(is_ref(d) for d in docs)
    assert len(json.dumps(update["outputs"])) < 20_000  # 20 x 40 KB of text is not in state


@pytest.mark.asyncio
async def test_documents_as_full_keeps_the_dump(library):
    path, db = library

    async def source(inputs, state, llm_config):
        return {"files": ["files/p0.jpg"], "documents": _full(db, 1), "count": 1}

    update = await _node("files", source, {"documents_as": "full"})(
        {"outputs": {}, "completed_nodes": [], "task_id": "r", "library_path": path})
    assert update["outputs"]["files"]["documents"][0]["page_content"].startswith("0:")


@pytest.mark.asyncio
async def test_a_tool_that_reads_pages_gets_them_and_state_stays_slim(library):
    path, db = library
    seen = {}

    async def reader(inputs, state, llm_config):
        seen["texts"] = [d["page_content"] for d in state["documents"]]
        return {"text": "ok"}

    state = {"outputs": {}, "completed_nodes": [], "task_id": "r", "library_path": path,
             "documents": slim_documents(_full(db, 5))}
    update = await _node("clean_text", reader)(state)
    assert [t[:2] for t in seen["texts"]] == ["0:", "1:", "2:", "3:", "4:"]
    assert all(is_ref(d) for d in state["documents"]), "the hydrated copy is not stored back"
    assert "page_content" not in json.dumps(update["outputs"])


@pytest.mark.asyncio
async def test_a_reference_aware_tool_gets_the_references_untouched(library):
    path, db = library
    assert "date_extract" in REF_AWARE_TOOLS
    seen = {}

    async def dates(inputs, state, llm_config):
        seen["docs"] = state["documents"]
        return {"dates": []}

    refs = slim_documents(_full(db, 3))
    await _node("date_extract", dates)({"outputs": {}, "completed_nodes": [], "task_id": "r",
                                        "library_path": path, "documents": refs})
    assert seen["docs"] == refs
