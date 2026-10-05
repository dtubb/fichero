"""`GET /api/stats/knowledge`: how many items each sidebar knowledge row holds (#5413).

Spec: `sidebar.knowledge.rows-only-when-non-empty` (docs/contributor_manual/specs/ui/sidebar-crud.md).

WHY: the app shows Entities, Claims, Citations and the hermeneutic rows only when they hold at
least one item. A count that is wrong in either direction is visible: an empty row that shows is
the clutter the ruling removes, and a row that stays hidden after its first item hides work. So
each count is pinned through the real route against items made through the real routes.
"""

from __future__ import annotations

from fichero_server.models.knowledge import KnowledgeEntity

_KEYS = {"entities", "claims", "citations", "references", "interpretations", "frameworks", "patterns"}


def test_an_empty_project_counts_zero_for_every_row(client):
    """WHY: a new project shows NO knowledge rows -- every count must be 0, and every row the app
    reads must be present (a missing key would decode as an error, not as hidden)."""
    response = client.get("/api/stats/knowledge")

    assert response.status_code == 200, response.text
    assert response.json() == {key: 0 for key in _KEYS}


def test_an_entity_and_a_claim_are_counted_once_added(client):
    """WHY: the row appears when its first item arrives -- after one entity and one claim, those
    two counts are 1 and the rest stay 0."""
    entity = client.post("/api/entities", json={"canonical_name": "Ysabel de Rojas", "entity_type": "person"})
    assert entity.status_code in (200, 201), entity.text
    claim = client.post("/api/claims", json={"text": "Ysabel de Rojas sold the house."})
    assert claim.status_code in (200, 201), claim.text

    counts = client.get("/api/stats/knowledge").json()

    assert counts["entities"] == 1
    assert counts["claims"] == 1
    assert {k: v for k, v in counts.items() if k not in ("entities", "claims")} == {
        key: 0 for key in _KEYS - {"entities", "claims"}
    }


def test_a_merged_away_entity_is_not_counted(client, db):
    """WHY: a merge keeps the merged-away entity as a row for undo; the Entities table hides it
    (#1849), so the count must too, or a project whose only entities were merged shows a row."""
    kept = KnowledgeEntity(canonical_name="Popayán", entity_type="location")
    gone = KnowledgeEntity(canonical_name="Popayan", entity_type="location", merged_into_id=kept.id)
    db.save(kept)
    db.save(gone)

    assert client.get("/api/stats/knowledge").json()["entities"] == 1
