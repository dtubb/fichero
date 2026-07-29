import asyncio
from datetime import datetime, timedelta
from unittest.mock import MagicMock

from fichero_server.api.routes.citation.usages import list_citation_usages
from fichero_server.knowledge.knowledge_models import DocumentCitation, KnowledgeClaim


def _citation(source: str, *, metadata=None, created_at=None) -> DocumentCitation:
    return DocumentCitation(
        source_document_id=source,
        target_citation_text="Quoted work",
        detector="llm-usage",
        metadata=metadata or {},
        created_at=created_at or datetime.now(),
    )


def test_lists_newest_usages_and_batches_claim_lookup():
    older = _citation(
        "source-a",
        metadata={"claim_id": "claim-1", "matched_reference_id": "ref-1", "stance": "supports"},
        created_at=datetime.now() - timedelta(minutes=1),
    )
    newer = _citation(
        "source-b",
        metadata={"claim_id": "claim-2", "matched_reference_id": "ref-2", "stance": "mentions"},
    )
    db = MagicMock()
    db.query.return_value = [older, newer]
    db.query_in.return_value = [KnowledgeClaim(id="claim-1", text="First"), KnowledgeClaim(id="claim-2", text="Second")]

    response = asyncio.run(
        list_citation_usages(
            source_document_id=None,
            target_document_id=None,
            reference_id=None,
            stance=None,
            db=db,
        )
    )

    assert response.count == 2
    assert [item.citation.id for item in response.items] == [newer.id, older.id]
    assert [item.claim.text for item in response.items] == ["Second", "First"]
    assert db.query.call_args.args == (DocumentCitation,)
    assert db.query.call_args.kwargs == {"detector": "llm-usage"}
    assert set(db.query_in.call_args.args[2]) == {"claim-1", "claim-2"}


def test_applies_database_and_metadata_filters_without_n_plus_one_lookup():
    matching = _citation(
        "source-a",
        metadata={"matched_reference_id": "ref-1", "stance": "supports"},
    )
    rejected = _citation(
        "source-a",
        metadata={"matched_reference_id": "ref-2", "stance": "contradicts"},
    )
    db = MagicMock()
    db.query.return_value = [matching, rejected]

    response = asyncio.run(
        list_citation_usages(
            source_document_id="source-a",
            target_document_id="target-a",
            reference_id="ref-1",
            stance="supports",
            db=db,
        )
    )

    assert [item.citation.id for item in response.items] == [matching.id]
    assert db.query.call_args.kwargs == {
        "detector": "llm-usage",
        "source_document_id": "source-a",
        "target_document_id": "target-a",
    }
    db.query_in.assert_not_called()


def test_tolerates_non_dictionary_metadata_and_missing_claims():
    citation = _citation("source-a")
    citation.metadata = "legacy"  # type: ignore[assignment]
    db = MagicMock()
    db.query.return_value = [citation]

    response = asyncio.run(
        list_citation_usages(
            source_document_id=None,
            target_document_id=None,
            reference_id=None,
            stance=None,
            db=db,
        )
    )

    assert response.count == 1
    assert response.items[0].metadata == {}
    assert response.items[0].claim is None
    db.query_in.assert_not_called()
