"""An entity list under a document is the document's own entities, and an entity lists the pages it is named on."""

from fichero_server.models import Document
from fichero_server.models.knowledge import EntityType, KnowledgeClaim, KnowledgeEntity


def _entity(db, name, source_document_ids=()):
    entity = KnowledgeEntity(canonical_name=name, entity_type=EntityType.person, aliases=[],
                             source_document_ids=list(source_document_ids))
    db.save(entity)
    return entity


def test_an_entity_the_alias_scan_found_in_a_claim_is_not_listed_under_the_document(client, db):
    ours = _entity(db, "Lucas Pardo", ["doc-1"])
    elsewhere = _entity(db, "Rosa Vega", ["doc-2"])
    # The claim's subject is first; the alias scan appended a name of another page.
    db.save(KnowledgeClaim(text="Lucas Pardo firmó", source_document_id="doc-1",
                           entity_ids=[ours.id, elsewhere.id]))
    names = {e["canonical_name"] for e in client.get("/api/entities?document_id=doc-1").json()["items"]}
    assert names == {"Lucas Pardo"}


def test_an_entity_lists_a_page_it_is_named_on_that_no_claim_reaches(client, db):
    db.save(Document(id="page-1", name="Page 1"))
    named = _entity(db, "Lucas Pardo", ["page-1"])
    body = client.get(f"/api/entities/{named.id}/documents").json()
    assert [d["document_id"] for d in body["items"]] == ["page-1"]
