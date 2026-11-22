"""/api/entities/top and /api/entities/claim-counts count with GROUP BY over `kg_mentions` (#6757).

Each test empties the statements' `entity_ids` column after saving, so only the link table can supply a count.
"""

from datetime import datetime

from fichero_server.models.knowledge import EntityType, KnowledgeClaim, KnowledgeEntity


def _entity(db, name, entity_type=EntityType.person):
    entity = KnowledgeEntity(
        canonical_name=name, entity_type=entity_type, aliases=[], created_at=datetime.now(), updated_at=datetime.now()
    )
    db.save(entity)
    return entity


def _claims(db, *id_lists):
    for i, ids in enumerate(id_lists):
        db.save(KnowledgeClaim(text=f"claim {i}", source_document_id="d", entity_ids=ids))
    db.conn.execute("UPDATE knowledgeclaims SET entity_ids = '[]'")


def test_claim_counts_come_from_the_link_table(client, db):
    a, b, c = _entity(db, "A"), _entity(db, "B"), _entity(db, "C")
    _claims(db, [a.id], [a.id, b.id], [a.id])
    counts = client.get("/api/entities/claim-counts").json()["counts"]
    assert counts == {a.id: 3, b.id: 1}
    assert c.id not in counts


def test_top_orders_by_count_and_honours_limit_and_type(client, db):
    a, b = _entity(db, "A"), _entity(db, "B")
    place = _entity(db, "P", EntityType.location)
    _claims(db, [a.id, place.id], [a.id, place.id], [a.id], [b.id])
    body = client.get("/api/entities/top?limit=2").json()
    assert [(r["entity_id"], r["claim_count"]) for r in body["items"]] == [(a.id, 3), (place.id, 2)]
    body = client.get("/api/entities/top?entity_type=location").json()
    assert [(r["entity_id"], r["claim_count"]) for r in body["items"]] == [(place.id, 2)]


def test_top_skips_a_name_with_no_entity_row_and_still_fills_the_limit(client, db):
    a = _entity(db, "A")
    _claims(db, ["ghost"], ["ghost"], [a.id])
    body = client.get("/api/entities/top?limit=1").json()
    assert [(r["entity_id"], r["claim_count"]) for r in body["items"]] == [(a.id, 1)]
