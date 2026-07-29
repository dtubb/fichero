"""Focused regression for keyword extractor claim entity_ids (#1296)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

from fichero_server.models.knowledge import EntityType, KnowledgeClaim, KnowledgeEntity
from fichero_server.llm import LLMConfig
from fichero_server.models import DocType, Document


async def test_keyword_claims_reference_their_concept_entities(db, test_package):
    from fichero_server.workflows.tools.extractors import (
        _SECTION_SCHEMAS,
        _SECTIONS,
        _run_extractor,
    )

    doc = Document(name="Keyword source", path="/tmp/source.txt", doc_type=DocType.file)
    db.save(doc)

    section = next(item for item in _SECTIONS if item["name"] == "keywords_extract")
    schema = _SECTION_SCHEMAS[section["schema_key"]]
    payload = json.loads('{"keywords": ["mining", "AI", "RNA"]}')
    fake_result = schema(items=payload["keywords"])

    with patch(
        "fichero_server.workflows.tools.extractors.chat_structured_with_fallback",
        new=AsyncMock(return_value=fake_result),
    ):
        await _run_extractor(
            section,
            {"text": "The source discusses mining, AI, and RNA."},
            {
                "library_path": str(test_package),
                "selected_doc_ids": [doc.id],
            },
            LLMConfig(provider="openai", model="gpt-4o-mini"),
        )

    concepts = {
        entity.canonical_name: entity
        for entity in db.query(KnowledgeEntity, entity_type=EntityType.concept)
    }
    claims = db.query(KnowledgeClaim, source_document_id=doc.id)
    claims_by_subject = {claim.subject_canonical: claim for claim in claims}

    assert set(concepts) == {"mining", "AI", "RNA"}
    assert set(claims_by_subject) == {"mining", "AI", "RNA"}
    for keyword, claim in claims_by_subject.items():
        assert claim.entity_ids == [concepts[keyword].id]
