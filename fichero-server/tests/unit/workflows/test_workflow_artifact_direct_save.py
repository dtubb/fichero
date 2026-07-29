"""#2514: extract_all persists section artifacts via DIRECT db.save.

The #1000 Phase-2 DBWriter queue was removed — the single per-package
connection lock (#2508) already serializes every write, so extract_all now
calls ``db.save(artifact)`` directly. This test drives the REAL extract_all
oneshot path against a REAL database (only the LLM call + KG writer are
stubbed) and asserts the section artifacts actually land as rows.

import_artifacts' equivalent direct-save persistence is proven end-to-end by
test_import_artifacts_workflow.test_import_artifacts_preset_registers_page_artifacts_and_is_idempotent.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from fichero_server.llm import LLMConfig
from fichero_server.models import Artifact, DocType, Document
from fichero_server.workflows.tools import extract_all as module


@pytest.mark.asyncio
async def test_extract_all_persists_section_artifacts_via_direct_db_save(
    db, test_package, monkeypatch
):
    page = Document(name="p1", path="/tmp/p1.png", doc_type=DocType.page)
    db.save(page)

    async def fake_chat_structured(**_kwargs):
        return module._Extraction(
            people=[
                module._Person(
                    name="Ana",
                    verb="appears on",
                    object="the page",
                    source_text="Ana",
                )
            ]
        )

    container = SimpleNamespace(id=page.id, updated_at=None)

    # Stub ONLY the external LLM call + the KG writer (a different code path);
    # the db is real so the artifact db.save we migrated is exercised for real.
    monkeypatch.setattr(module, "chat_structured_with_fallback", fake_chat_structured)
    monkeypatch.setattr(module, "_write_kg_rows", lambda *_a, **_k: ([], []))
    monkeypatch.setattr(module, "_resolve_write_target", lambda *_: container)

    result = await module.extract_all(
        {
            "text": "Ana appears on the page.",
            "records": [{"doc_id": page.id, "text": "Ana appears on the page."}],
            "extraction_mode": "oneshot",
        },
        {
            "library_path": str(test_package),
            "selected_doc_ids": [page.id],
            "task_id": "extract-all-direct-save",
        },
        LLMConfig(provider="openai", model="gpt-4o-mini"),
    )

    assert not result.get("error"), result

    # The section artifacts must be real rows on the page doc — direct db.save,
    # no queue to drain (#2514).
    artifacts = db.query(Artifact, document_id=page.id)
    assert artifacts, "extract_all must persist section artifacts via direct db.save"
