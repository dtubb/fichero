"""Tests for body citation-usage extraction (#1277)."""

from fichero_server.models.knowledge import (
    DocumentCitation,
    KnowledgeClaim,
    Reference,
    ReferenceCitationLocation,
    ReferenceKind,
    ReferenceProvenance,
)
from fichero_server.models import Document
from fichero_server.workflows.tools.extractors import _SECTIONS, _write_kg_rows


def test_citation_usage_writer_links_citation_and_claim(db):
    source = Document(
        name="Citing Doc",
        source_metadata={"authors": ["Smith, Alex"]},
    )
    target = Document(name="Cited Work")
    db.save(source)
    db.save(target)
    reference = Reference(
        title="The Cited Work",
        authors=["Doe, Jane"],
        year=1999,
        kind=ReferenceKind.book,
        realized_as_document_id=target.id,
    )
    db.save(reference)
    db.save(
        ReferenceProvenance(
            reference_id=reference.id,
            document_id=source.id,
            page="bibliography",
            citation_location=ReferenceCitationLocation.bibliography,
        )
    )
    section = next(s for s in _SECTIONS if s["name"] == "citation_usage_extract")

    _write_kg_rows(
        db,
        section,
        [
            {
                "marker": "(Doe 1999)",
                "cited_work": "Doe 1999",
                "stance": "extends_reading",
                "claim_text": "Smith extends Doe's account of archive formation.",
                "excerpt": "Smith extends earlier work (Doe 1999) on archives.",
                "confidence": 0.82,
            }
        ],
        source.id,
        page_label="Page 4",
        source_excerpt="Smith extends earlier work (Doe 1999) on archives.",
        provider="openai",
        model="gpt-4o-mini",
    )

    citations = db.query(DocumentCitation, detector="llm-usage")
    assert len(citations) == 1
    citation = citations[0]
    assert citation.source_document_id == source.id
    assert citation.target_document_id == target.id
    assert citation.metadata["matched_reference_id"] == reference.id
    assert citation.metadata["predicate_canonical"] == "extends_reading"

    claims = db.query(KnowledgeClaim, source_document_id=source.id)
    assert len(claims) == 1
    claim = claims[0]
    assert claim.metadata["citation_id"] == citation.id
    assert claim.metadata["reference_id"] == reference.id
    assert claim.predicate_canonical == "extends_reading"
    assert citation.metadata["claim_id"] == claim.id


def test_citation_usage_endpoint_filters_by_reference(client, db):
    source = Document(name="Citing Doc")
    db.save(source)
    reference = Reference(title="The Cited Work", authors=["Doe, Jane"], year=1999)
    db.save(reference)
    section = next(s for s in _SECTIONS if s["name"] == "citation_usage_extract")

    _write_kg_rows(
        db,
        section,
        [
            {
                "marker": "(Doe 1999)",
                "cited_work": "The Cited Work",
                "stance": "critiques",
                "claim_text": "The author critiques Doe's chronology.",
                "excerpt": "The author critiques Doe's chronology (Doe 1999).",
            }
        ],
        source.id,
        source_excerpt="The author critiques Doe's chronology (Doe 1999).",
    )

    response = client.get(f"/api/citation-usages?reference_id={reference.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 1
    assert data["items"][0]["reference_id"] == reference.id
    assert data["items"][0]["stance"] == "critiques"
    assert data["items"][0]["claim"]["metadata"]["reference_id"] == reference.id
