from fichero.models import (
    ContentRepresentation,
    ContentRepresentationKind,
    ContentRepresentationRevision,
    ContentSourceAnchor,
)


def test_representation_and_revision_persist(db):
    representation = ContentRepresentation(
        document_id="doc-1",
        kind=ContentRepresentationKind.transcription,
        content="diplomatic source",
        source_anchor=ContentSourceAnchor(document_id="doc-1", page_id="page-1", char_start=2, char_end=8),
    )
    db.save(representation)
    revision = ContentRepresentationRevision(
        representation_id=representation.id,
        content="reader correction",
    )
    db.save(revision)

    assert db.get(ContentRepresentation, representation.id).source_anchor.page_id == "page-1"
    assert db.get(ContentRepresentationRevision, revision.id).representation_id == representation.id
