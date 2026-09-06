"""Coverage for document-inspector knowledge-graph helpers."""

from __future__ import annotations

from datetime import datetime, timedelta

from fichero_server.api.routes.document import inspector
from fichero_server.models.knowledge import KnowledgeEntity
from fichero_server.models import Artifact


def test_resolve_canonical_follows_merge_chain_and_stops_cycles():
    first = KnowledgeEntity(id="first", canonical_name="First", merged_into_id="second")
    second = KnowledgeEntity(id="second", canonical_name="Second", merged_into_id="third")
    third = KnowledgeEntity(id="third", canonical_name="Third")
    cycle = KnowledgeEntity(id="cycle", canonical_name="Cycle", merged_into_id="cycle")

    class DB:
        def get(self, _model, key):
            return {item.id: item for item in (first, second, third, cycle)}.get(key)

    db = DB()
    assert inspector._resolve_canonical(db, "first") is third
    assert inspector._resolve_canonical(db, "cycle") is cycle
    assert inspector._resolve_canonical(db, "missing") is None


def test_catalogue_artifacts_filter_and_order_by_type_then_newest():
    now = datetime.now()
    rows = [
        Artifact(document_id="doc", artifact_type="transcription", created_at=now),
        Artifact(document_id="doc", artifact_type="catalogue.keywords", created_at=now),
        Artifact(document_id="doc", artifact_type="catalogue.narrative", created_at=now - timedelta(days=1)),
        Artifact(document_id="doc", artifact_type="catalogue", created_at=now),
    ]

    class DB:
        def query(self, _model, **filters):
            assert filters == {"document_id": "doc"}
            return rows

    assert inspector._is_catalogue_artifact("catalogue.timeline")
    assert not inspector._is_catalogue_artifact("summary")
    result = inspector._catalogue_artifacts(DB(), "doc")

    assert [item.artifact_type for item in result] == [
        "catalogue",
        "catalogue.narrative",
        "catalogue.keywords",
    ]


# ---------------------------------------------------------------------------
# Page-level entities (#page-level-entities): a page's KG must surface entities
# linked via source_document_ids even before the SVO workflow writes claims.
# ---------------------------------------------------------------------------


def test_document_kg_surfaces_claimless_linked_entity(db):
    import asyncio

    from fichero_server.api.routes.document.inspector import knowledge_graph
    from fichero_server.models import Document, DocType
    from fichero_server.models.knowledge import EntityType

    page = Document(id="page-1", name="Page 1", doc_type=DocType.page)
    db.save(page)
    # Extract Entities linked this person to the page; no claim yet.
    db.save(
        KnowledgeEntity(
            id="e-alej",
            canonical_name="Alejandro Piedrahita",
            entity_type=EntityType.person,
            source_document_ids=["page-1"],
        )
    )

    resp = asyncio.run(knowledge_graph("page-1", include_children=False, db=db))

    names = [item.canonical_name for group in resp.groups for item in group.items]
    assert "Alejandro Piedrahita" in names, "page KG dropped a claim-less linked entity"
    assert resp.entity_count >= 1
    item = next(
        i for g in resp.groups for i in g.items if i.canonical_name == "Alejandro Piedrahita"
    )
    # Points back to the page so click-a-entity → jump-to-page works.
    assert item.source_document_id == "page-1"
    assert item.claim_ids == []  # surfaced by the link, not a claim


def test_claim_surfaced_entity_is_not_duplicated_by_the_link(db):
    import asyncio

    from fichero_server.api.routes.document.inspector import knowledge_graph
    from fichero_server.models import Document, DocType
    from fichero_server.models.knowledge import EntityType, KnowledgeClaim

    page = Document(id="page-2", name="Page 2", doc_type=DocType.page)
    db.save(page)
    db.save(
        KnowledgeEntity(
            id="e-dup",
            canonical_name="María García López",
            entity_type=EntityType.person,
            source_document_ids=["page-2"],
        )
    )
    db.save(
        KnowledgeClaim(
            id="c-dup",
            text="María García López signed the deed.",
            source_document_id="page-2",
            source_page_label="1",
            entity_ids=["e-dup"],
            subject_canonical="María García López",
            predicate_verb="signed",
            object_phrase="the deed",
        )
    )

    resp = asyncio.run(knowledge_graph("page-2", include_children=False, db=db))

    rows = [
        i for g in resp.groups for i in g.items if i.canonical_name == "María García López"
    ]
    assert len(rows) == 1, "entity surfaced twice — via claim AND via the link"
    assert rows[0].claim_ids == ["c-dup"]  # the claim row wins, keeps provenance
