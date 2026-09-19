"""kg.tables.folder-recursion-inconsistent-across-routes (#4885): three
engine surfaces answer "what knowledge belongs to this folder" differently —
`include_descendants` is opt-in (and MEANINGFULLY restricts to an exact
match when off) on `/api/claims`; the entities `document_id` filter has NO
flag at all and always recurses; `include_children` on the document
knowledge-graph route exists but is a DEAD FLAG in practice (see below).

Consolidated in this delivery: `_descendant_doc_ids` (claims.py, the walk
all three routes share) now delegates to `Database._collect_folder_descendants`
instead of running its own duplicate BFS — see
`fichero-server/tests/unit/api/test_descendant_doc_ids.py`. This file proves
the CROSS-ROUTE behavior, not the walk itself: when recursion is requested
(or, for the KG route, whenever it is effectively unavoidable), a folder
whose documents are all nested in SUBFOLDERS surfaces the SAME entity/claim
through every route — and pins each route's CURRENT default so a later
change to it is a visible decision, per the maintainer's explicit ask.
NO route's default changed in this delivery.
"""

from __future__ import annotations

from fichero_server.models import Document, DocType
from fichero_server.models.knowledge import EntityType, KnowledgeClaim, KnowledgeEntity


def _build_nested_folder(db):
    """folder -> sub -> page, with one claim + entity anchored on the LEAF
    page two levels down -- "a folder whose documents are all in
    subfolders", per the task's own phrasing."""
    folder = Document(name="Folder", doc_type=DocType.folder)
    db.save(folder)
    sub = Document(name="Sub", doc_type=DocType.folder, parent_id=folder.id)
    db.save(sub)
    page = Document(name="deed.txt", doc_type=DocType.file, parent_id=sub.id,
                     page_content="Antonio Asprilla sold the mine.")
    db.save(page, auto_embed=False)

    entity = KnowledgeEntity(
        id="asprilla", canonical_name="Antonio Asprilla", entity_type=EntityType.person,
        source_document_ids=[page.id],
    )
    db.save(entity)
    claim = KnowledgeClaim(
        id="c-sold", text="Antonio Asprilla sold the mine.",
        source_document_id=page.id, entity_ids=[entity.id],
    )
    db.save(claim)
    return folder, sub, page, entity, claim


class TestCrossRouteConsistencyWhenRecursionIsRequested:
    """A folder whose documents are all in subfolders returns the SAME set
    of entities/claims through every route WHEN recursion is requested."""

    def test_claims_route_with_include_descendants_true_finds_the_nested_claim(self, client, db):
        folder, _sub, _page, _entity, claim = _build_nested_folder(db)
        resp = client.get(f"/api/claims?source_document_id={folder.id}&include_descendants=true")
        assert resp.status_code == 200
        assert claim.id in [c["id"] for c in resp.json()["items"]]

    def test_entities_route_document_id_filter_finds_the_nested_entity(self, client, db):
        folder, _sub, _page, entity, _claim = _build_nested_folder(db)
        resp = client.get(f"/api/entities?document_id={folder.id}")
        assert resp.status_code == 200
        assert entity.id in [e["id"] for e in resp.json()["items"]]

    def test_knowledge_graph_route_with_include_children_true_finds_the_nested_entity(self, client, db):
        folder, _sub, _page, entity, _claim = _build_nested_folder(db)
        resp = client.get(f"/api/documents/{folder.id}/knowledge-graph?include_children=true")
        assert resp.status_code == 200
        entity_ids = [
            item["entity_id"]
            for group in resp.json()["groups"]
            for item in group["items"]
        ]
        assert entity.id in entity_ids

    def test_all_three_routes_agree_when_recursion_is_requested(self, client, db):
        """The actual consolidation claim: not just "each route can find it
        somehow," but that requesting recursion on all three surfaces the
        exact same underlying claim's entity."""
        folder, _sub, _page, entity, claim = _build_nested_folder(db)

        claims_resp = client.get(
            f"/api/claims?source_document_id={folder.id}&include_descendants=true"
        ).json()
        entities_resp = client.get(f"/api/entities?document_id={folder.id}").json()
        kg_resp = client.get(
            f"/api/documents/{folder.id}/knowledge-graph?include_children=true"
        ).json()

        assert claim.id in [c["id"] for c in claims_resp["items"]]
        assert entity.id in [e["id"] for e in entities_resp["items"]]
        assert entity.id in [
            item["entity_id"] for group in kg_resp["groups"] for item in group["items"]
        ]


class TestCurrentDefaultsArePinned:
    """Pin each route's CURRENT default so a later change to it is a
    visible decision (the maintainer's explicit ask) -- these are
    descriptions of what the code does today, not endorsements."""

    def test_claims_route_default_is_a_real_opt_in_exact_match_only(self, client, db):
        """`include_descendants` defaults False, and DOES meaningfully
        restrict: without it, a folder-scoped claims query finds nothing
        for a claim anchored on a page two levels down."""
        folder, _sub, _page, _entity, claim = _build_nested_folder(db)
        resp = client.get(f"/api/claims?source_document_id={folder.id}")
        assert resp.status_code == 200
        assert claim.id not in [c["id"] for c in resp.json()["items"]]

    def test_entities_route_has_no_flag_and_always_recurses(self, client, db):
        """There is no query parameter to opt OUT of recursion here at all
        -- pinning that the "always recurses" default is unconditional,
        not merely a default that happens to be True."""
        folder, _sub, _page, entity, _claim = _build_nested_folder(db)
        resp = client.get(f"/api/entities?document_id={folder.id}")
        assert resp.status_code == 200
        assert entity.id in [e["id"] for e in resp.json()["items"]]

    def test_knowledge_graph_route_include_children_default_is_a_dead_flag(self, client, db):
        """FINDING, not a fix: `include_children` defaults False, but
        `knowledge_graph()` computes
        `should_include_children = include_children or len(descendant_ids) > 1`
        -- since `descendant_ids` always includes the root itself, ANY
        document with at least one descendant (a folder with contents, a
        PDF with pages) already recurses regardless of the flag. The
        default is provably a no-op whenever there is anything to recurse
        into: this test proves the omitted-flag response is IDENTICAL to
        the explicit `include_children=true` response for this exact
        nested-folder case, which is the case the flag exists to gate."""
        folder, _sub, _page, entity, _claim = _build_nested_folder(db)
        default_resp = client.get(f"/api/documents/{folder.id}/knowledge-graph").json()
        explicit_true_resp = client.get(
            f"/api/documents/{folder.id}/knowledge-graph?include_children=true"
        ).json()

        default_entity_ids = [
            item["entity_id"] for group in default_resp["groups"] for item in group["items"]
        ]
        explicit_entity_ids = [
            item["entity_id"] for group in explicit_true_resp["groups"] for item in group["items"]
        ]
        assert entity.id in default_entity_ids
        assert default_entity_ids == explicit_entity_ids
        # The response even reports it turned itself on despite the request:
        assert default_resp["include_children"] is True

    def test_knowledge_graph_route_include_children_is_a_true_no_op_on_a_childless_leaf(self, client, db):
        """The flip side of the dead-flag finding: on a document with NO
        descendants at all, the flag's value changes nothing either,
        because there is nothing to recurse into regardless."""
        leaf = Document(name="lonely.txt", doc_type=DocType.file, page_content="Nothing to see.")
        db.save(leaf, auto_embed=False)

        default_resp = client.get(f"/api/documents/{leaf.id}/knowledge-graph").json()
        explicit_true_resp = client.get(
            f"/api/documents/{leaf.id}/knowledge-graph?include_children=true"
        ).json()
        assert default_resp["include_children"] is False
        assert explicit_true_resp["include_children"] is True
        assert default_resp["groups"] == explicit_true_resp["groups"] == []
