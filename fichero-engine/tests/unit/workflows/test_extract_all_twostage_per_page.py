from __future__ import annotations

import pytest

from fichero.knowledge_models import EntityType, KnowledgeClaim, KnowledgeEntity
from fichero.llm import LLMConfig
from fichero.models import DocType, Document
from fichero.workflows.tools import extract_all as extract_all_module


@pytest.mark.asyncio
async def test_two_stage_writes_kg_rows_to_page_docs_not_folder(db, test_package, monkeypatch):
    folder = Document(name="Folder", path="/tmp/folder", doc_type=DocType.folder)
    page1 = Document(name="p1", path="/tmp/folder/p1.png", doc_type=DocType.page)
    page2 = Document(name="p2", path="/tmp/folder/p2.png", doc_type=DocType.page)
    db.save(folder)
    db.save(page1)
    db.save(page2)

    async def fake_stage1(**kwargs):
        schema = kwargs.get("schema")
        if schema is not extract_all_module._EntitiesOnly:
            raise AssertionError(f"unexpected schema: {schema!r}")
        return extract_all_module._EntitiesOnly(
            people=[extract_all_module._EntityOnly(name="Ada", entity_type="person")],
            places=[],
            organizations=[],
            dates=[],
            events=[],
        )

    async def fake_claims_for_entity(*args, **kwargs):
        return [
            {
                "verb": "signed",
                "object": "the ledger",
                "source_text": "Ada signed the ledger",
            }
        ]

    monkeypatch.setattr(
        "fichero.workflows.tools.extract_all.chat_structured_with_fallback",
        fake_stage1,
    )
    monkeypatch.setattr(
        "fichero.workflows.tools.extract_all._extract_claims_for_entity",
        fake_claims_for_entity,
    )

    state = {
        "library_path": str(test_package),
        "selected_doc_ids": [folder.id],
    }
    llm_config = LLMConfig(provider="openai", model="gpt-4o-mini")

    await extract_all_module._run_two_stage(
        text="Ada signed the ledger.",
        recovered_records=[
            {"doc_id": page1.id, "text": "Ada signed the ledger."},
            {"doc_id": page2.id, "text": "Ada signed the ledger again."},
        ],
        state=state,
        llm_config=llm_config,
        output_language="English",
        inputs={"persist_kg": True},
    )

    entities = db.query(KnowledgeEntity, entity_type=EntityType.person)
    assert entities, "expected person KnowledgeEntity rows to be persisted"

    folder_claims = db.query(KnowledgeClaim, source_document_id=folder.id)
    page1_claims = db.query(KnowledgeClaim, source_document_id=page1.id)
    page2_claims = db.query(KnowledgeClaim, source_document_id=page2.id)

    assert len(folder_claims) == 0, "claims should be attached to page docs"
    assert len(page1_claims) > 0
    assert len(page2_claims) > 0
