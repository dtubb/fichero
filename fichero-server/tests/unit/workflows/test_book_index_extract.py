from unittest.mock import AsyncMock, patch

import pytest

from fichero_server.models.knowledge import (
    EntityResolutionRule,
    EntityResolutionRuleType,
    EntityType,
    KnowledgeClaim,
    KnowledgeEntity,
)
from fichero_server.llm import LLMConfig
from fichero_server.models import Artifact, DocType, Document
from fichero_server.workflows.tools.book_index import (
    _TopicStatement,
    _TopicStatements,
    parse_index_entries,
    book_index_extract,
)


def test_parse_index_entries_handles_ranges_ff_and_subentries():
    entries = parse_index_entries(
        "Artisanal mining, 12-13, 20 ff.\n"
        "  mercury, 21\n"
        "Choco: 4, 6",
        ff_span=2,
    )

    by_term = {entry.term: entry for entry in entries}
    assert by_term["Artisanal mining"].page_refs == [12, 13, 20, 21, 22]
    assert by_term["Artisanal mining"].subentries == ["mercury"]
    assert by_term["Choco"].page_refs == [4, 6]


@pytest.mark.asyncio
async def test_book_index_extract_writes_topic_entity_and_grounded_claim(
    db, test_package
):
    parent = Document(name="book.pdf", doc_type=DocType.file, path="/book.pdf")
    db.save(parent)
    page = Document(
        name="page 13",
        parent_id=parent.id,
        doc_type=DocType.page,
        sequence=13,
        page_content="Artisanal mining used mercury to process gold in the Choco.",
    )
    index_page = Document(
        name="index page",
        parent_id=parent.id,
        doc_type=DocType.page,
        sequence=99,
        page_content="Artisanal mining, 1",
    )
    db.save(page)
    db.save(index_page)
    llm_config = LLMConfig(provider="openai", model="gpt-4o-mini")
    fake_statements = _TopicStatements(
        statements=[
            _TopicStatement(
                text="Artisanal mining used mercury to process gold.",
                verb="used",
                object="mercury to process gold",
                source_text="Artisanal mining used mercury to process gold",
                confidence=0.8,
            )
        ]
    )

    with patch(
        "fichero_server.workflows.tools.book_index.chat_structured_with_fallback",
        new=AsyncMock(return_value=fake_statements),
    ):
        result = await book_index_extract(
            {
                "page_offset": 12,
                "index_start_sequence": 99,
                "index_end_sequence": 99,
                "max_pages_per_topic": 1,
            },
            {"library_path": str(test_package), "selected_doc_ids": [parent.id]},
            llm_config,
        )

    assert result["value"][0]["term"] == "Artisanal mining"
    entities = db.query(KnowledgeEntity, entity_type=EntityType.concept)
    topic = next(entity for entity in entities if entity.canonical_name == "Artisanal mining")
    assert topic.metadata["topic_source"] == "back_of_book_index"
    assert topic.metadata["index_page_refs"] == [1]

    claims = db.query(KnowledgeClaim, source_document_id=page.id)
    assert len(claims) == 1
    claim = claims[0]
    assert claim.subject_entity_id == topic.id
    assert claim.entity_ids == [topic.id]
    assert claim.source_page_label == "1"
    assert claim.source_char_start == 0
    assert claim.predicate_verb == "used"
    assert claim.svo_verb == "used"
    assert claim.confidence_source == "llm"

    artifacts = db.query(Artifact, document_id=parent.id)
    assert any(artifact.artifact_type == "book_index_topics" for artifact in artifacts)


@pytest.mark.asyncio
async def test_book_index_extract_can_read_index_text_from_page_range(
    db, test_package
):
    parent = Document(name="book.pdf", doc_type=DocType.file, path="/book.pdf")
    db.save(parent)
    body = Document(
        name="page 13",
        parent_id=parent.id,
        doc_type=DocType.page,
        sequence=13,
        page_content="Choco appears as a region in this source.",
    )
    index_page = Document(
        name="index page",
        parent_id=parent.id,
        doc_type=DocType.page,
        sequence=99,
        page_content="Choco, 1",
    )
    db.save(body)
    db.save(index_page)
    llm_config = LLMConfig(provider="openai", model="gpt-4o-mini")

    with patch(
        "fichero_server.workflows.tools.book_index.chat_structured_with_fallback",
        new=AsyncMock(return_value=_TopicStatements(statements=[])),
    ):
        result = await book_index_extract(
            {
                "page_offset": 12,
                "index_start_sequence": 99,
                "index_end_sequence": 99,
            },
            {"library_path": str(test_package), "selected_doc_ids": [parent.id]},
            llm_config,
        )

    assert result["value"][0]["term"] == "Choco"
    assert result["value"][0]["pages"][0]["document_id"] == body.id


@pytest.mark.asyncio
async def test_book_index_extract_handles_suppressed_topic_entity(
    db, test_package
):
    parent = Document(name="book.pdf", doc_type=DocType.file, path="/book.pdf")
    db.save(parent)
    page = Document(
        name="page 13",
        parent_id=parent.id,
        doc_type=DocType.page,
        sequence=13,
        page_content="Artisanal mining used mercury to process gold in the Choco.",
    )
    index_page = Document(
        name="index page",
        parent_id=parent.id,
        doc_type=DocType.page,
        sequence=99,
        page_content="Artisanal mining, 1",
    )
    db.save(page)
    db.save(index_page)
    db.save(
        EntityResolutionRule(
            rule_type=EntityResolutionRuleType.suppress,
            match_canonical_name="Artisanal mining",
            match_entity_type=EntityType.concept,
            reason="suppress trivial topic",
        )
    )
    llm_config = LLMConfig(provider="openai", model="gpt-4o-mini")

    with patch(
        "fichero_server.workflows.tools.book_index.chat_structured_with_fallback",
        new=AsyncMock(return_value=_TopicStatements(statements=[])),
    ):
        result = await book_index_extract(
            {
                "page_offset": 12,
                "index_start_sequence": 99,
                "index_end_sequence": 99,
            },
            {"library_path": str(test_package), "selected_doc_ids": [parent.id]},
            llm_config,
        )

    assert result["value"][0]["entity_id"] is None
    assert result["value"][0]["claims_written"] == 0
    assert db.query(KnowledgeEntity, canonical_name="Artisanal mining") == []
    assert db.query(KnowledgeClaim, source_document_id=page.id) == []
