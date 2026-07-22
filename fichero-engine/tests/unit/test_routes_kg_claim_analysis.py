"""Coverage for claim contradiction and evidence-chain routes."""

from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from fichero.api.routes import kg_claim_analysis as routes
from fichero.models.knowledge import ClaimRelationType, KnowledgeClaim, KnowledgeClaimLink
from fichero.models import Document


class FakeDB:
    def __init__(self, claims, documents, links):
        self.claims = {claim.id: claim for claim in claims}
        self.documents = {document.id: document for document in documents}
        self.links = links

    def get(self, model, key):
        if model is KnowledgeClaim:
            return self.claims.get(key)
        if model is Document:
            return self.documents.get(key)
        raise AssertionError(f"unexpected model: {model}")

    def query(self, model, **filters):
        assert model is KnowledgeClaimLink
        return [link for link in self.links if all(getattr(link, key) == value for key, value in filters.items())]


def _fixture_db() -> FakeDB:
    source = Document(id="doc-1", name="source.pdf", metadata={"page": 2}, path="files/source.pdf")
    root = KnowledgeClaim(id="claim-1", text="Root claim", source_document_id=source.id)
    outgoing = KnowledgeClaim(id="claim-2", text="Outgoing contradiction", source_ids=[source.id])
    incoming = KnowledgeClaim(id="claim-3", text="Incoming contradiction")
    links = [
        KnowledgeClaimLink(
            claim_id=root.id,
            related_claim_id=outgoing.id,
            relation_type=ClaimRelationType.contradicts,
            link_quality=0.9,
            evidence="outgoing evidence",
        ),
        KnowledgeClaimLink(
            claim_id=incoming.id,
            related_claim_id=root.id,
            relation_type=ClaimRelationType.contradicts,
            link_quality=0.8,
            evidence="incoming evidence",
        ),
        KnowledgeClaimLink(
            claim_id=root.id,
            related_claim_id="missing",
            relation_type=ClaimRelationType.contradicts,
            link_quality=1.0,
        ),
    ]
    return FakeDB([root, outgoing, incoming], [source], links)


def test_contradictions_collects_both_directions_and_filters_quality():
    db = _fixture_db()
    result = asyncio.run(routes.contradictions("claim-1", min_link_quality=0.85, db=db))

    assert result.count == 1
    assert result.items[0].contradicting_claim_id == "claim-2"
    assert result.items[0].relation_type == "outgoing"
    assert result.items[0].source_documents == [{"id": "doc-1", "name": "source.pdf", "metadata": {"page": 2}}]


def test_contradictions_returns_not_found_for_unknown_claim():
    with pytest.raises(HTTPException) as caught:
        asyncio.run(routes.contradictions("missing", db=_fixture_db()))

    assert caught.value.status_code == 404


def test_evidence_chain_depth_one_contains_claim_and_sources_only():
    result = asyncio.run(routes.evidence_chain("claim-1", max_depth=1, db=_fixture_db()))

    assert [item.step_type for item in result.chain] == ["claim", "source"]
    assert result.sources[0]["path"] == "files/source.pdf"
    assert result.related_claims == []


def test_evidence_chain_depth_two_includes_related_claims_in_both_directions():
    result = asyncio.run(routes.evidence_chain("claim-1", max_depth=2, db=_fixture_db()))

    assert set(result.related_claims) == {"claim-2", "claim-3"}
    assert [item.relation_type for item in result.chain[2:]] == ["contradicts", "reverse:contradicts"]


def test_evidence_chain_returns_not_found_for_unknown_claim():
    with pytest.raises(HTTPException) as caught:
        asyncio.run(routes.evidence_chain("missing", db=_fixture_db()))

    assert caught.value.status_code == 404
