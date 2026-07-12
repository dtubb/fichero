from fichero.models import (
    ContentRepresentation,
    ContentRepresentationKind,
    ContentRepresentationRevision,
    ContentSourceAnchor,
)
from fichero.actions.registry import ActionContext, registry
import fichero.api.routes.content_representations  # noqa: F401


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


def test_revision_action_preserves_source_representation(db):
    representation = ContentRepresentation(
        document_id="doc-1",
        kind=ContentRepresentationKind.transcription,
        content="immutable source",
        source_anchor=ContentSourceAnchor(document_id="doc-1"),
    )
    db.save(representation)
    result = registry.invoke(
        db,
        "representation.revise",
        {"representation_id": representation.id, "content": "reader correction"},
        ActionContext(actor="reviewer"),
    )
    revision = db.get(ContentRepresentationRevision, result.result["id"])
    assert revision.reviewer == "reviewer"
    assert db.get(ContentRepresentation, representation.id).content == "immutable source"


def test_representation_read_routes(client, db):
    representation = ContentRepresentation(
        document_id="doc-api",
        kind=ContentRepresentationKind.markdown,
        content="# source",
        source_anchor=ContentSourceAnchor(document_id="doc-api"),
    )
    db.save(representation)
    response = client.get(f"/api/content-representations/document/{representation.document_id}")
    assert response.status_code == 200
    assert response.json()[0]["id"] == representation.id


def test_revision_routes_reject_missing_representation_and_empty_content(client):
    missing = client.get("/api/content-representations/missing/revisions")
    empty = client.post(
        "/api/content-representations/missing/revisions", json={"content": ""}
    )

    assert missing.status_code == 404
    assert empty.status_code == 422
