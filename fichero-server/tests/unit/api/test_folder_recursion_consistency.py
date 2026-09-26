"""kg.tables.folder-recursion-inconsistent-across-routes (#4885, ruled in #5065):
one flag, one default. A folder query includes everything under the folder,
BY DEFAULT, on all three engine surfaces, and `include_descendants=false` asks
for the document alone.

History, because each test below says which switch it now describes:

* SWITCH 1, `/api/claims` `include_descendants`: was opt-in (default false,
  an exact-match restriction). Now default TRUE.
* SWITCH 2, the entities `document_id` filter: had NO flag and always
  recursed. Now it recurses by default AND has `include_descendants`, so a
  non-recursive query is expressible.
* SWITCH 3, `include_children` on the knowledge-graph route: was not dead (it
  was read) but was made a no-op wherever it mattered by an implicit
  `or len(descendant_ids) > 1`. Now REPLACED by `include_descendants`,
  default true, with no implicit fallback: false really means the document alone.

The walk itself (`_descendant_doc_ids`) is pinned in `test_descendant_doc_ids.py`
and is unchanged. Before #5065 this file pinned the OLD defaults, so the
edits below are deliberate, not a test bent until it passed.
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


def _kg_entity_ids(resp_json):
    return [item["entity_id"] for group in resp_json["groups"] for item in group["items"]]


class TestFolderQueriesRecurseByDefault:
    """SWITCHES 1, 2 and 3 all default to recursive now: a folder whose
    documents are all in subfolders answers the same on every route WITHOUT
    any flag."""

    def test_claims_route_default_recurses(self, client, db):
        """SWITCH 1: was `..._default_is_a_real_opt_in_exact_match_only`."""
        folder, _sub, _page, _entity, claim = _build_nested_folder(db)
        resp = client.get(f"/api/claims?source_document_id={folder.id}")
        assert resp.status_code == 200
        assert claim.id in [c["id"] for c in resp.json()["items"]]

    def test_entities_route_default_recurses(self, client, db):
        """SWITCH 2: unchanged answer, still true without a flag."""
        folder, _sub, _page, entity, _claim = _build_nested_folder(db)
        resp = client.get(f"/api/entities?document_id={folder.id}")
        assert resp.status_code == 200
        assert entity.id in [e["id"] for e in resp.json()["items"]]

    def test_knowledge_graph_route_default_recurses(self, client, db):
        """SWITCH 3: was `..._include_children_default_is_a_dead_flag`. The
        answer is the same, but it now comes from the DEFAULT, not from an
        implicit `or` that also overrode an explicit false."""
        folder, _sub, _page, entity, _claim = _build_nested_folder(db)
        resp = client.get(f"/api/documents/{folder.id}/knowledge-graph")
        assert resp.status_code == 200
        assert entity.id in _kg_entity_ids(resp.json())
        assert resp.json()["include_children"] is True

    def test_all_three_routes_agree_with_no_flags(self, client, db):
        """The consolidation claim: the exact same underlying claim's entity
        surfaces through all three routes, and none of them was asked to."""
        folder, _sub, _page, entity, claim = _build_nested_folder(db)
        claims_resp = client.get(f"/api/claims?source_document_id={folder.id}").json()
        entities_resp = client.get(f"/api/entities?document_id={folder.id}").json()
        kg_resp = client.get(f"/api/documents/{folder.id}/knowledge-graph").json()
        assert claim.id in [c["id"] for c in claims_resp["items"]]
        assert entity.id in [e["id"] for e in entities_resp["items"]]
        assert entity.id in _kg_entity_ids(kg_resp)

    def test_shared_query_functions_default_to_recursive(self, db):
        """The functions the routes AND the chat-agent actions share, so the
        chat `claim.list` / `entity.list` actions get the same default."""
        from fichero_server.api.routes.claim.claims import (
            ClaimListActionParams, list_claims_impl,
        )
        from fichero_server.api.routes.entity.entities import (
            EntityListActionParams, list_entities_impl,
        )
        folder, _sub, _page, entity, claim = _build_nested_folder(db)
        assert claim.id in [c.id for c in list_claims_impl(db, source_document_id=folder.id)]
        assert entity.id in [e.id for e in list_entities_impl(db, document_id=folder.id)]
        assert ClaimListActionParams().include_descendants is True
        assert EntityListActionParams().include_descendants is True


class TestNonRecursiveIsStillExpressible:
    """`include_descendants=false` asks for the document alone, on all three
    routes. Each test ALSO puts a claim on the folder itself, so a restriction
    that returns nothing because nothing is there cannot pass."""

    @staticmethod
    def _folder_with_its_own_claim(db):
        folder, sub, page, entity, claim = _build_nested_folder(db)
        own_entity = KnowledgeEntity(
            id="folder-owner", canonical_name="Folder Owner", entity_type=EntityType.person,
            source_document_ids=[folder.id],
        )
        db.save(own_entity)
        own_claim = KnowledgeClaim(
            id="c-own", text="Folder Owner kept the ledger.",
            source_document_id=folder.id, entity_ids=[own_entity.id],
        )
        db.save(own_claim)
        return folder, entity, claim, own_entity, own_claim

    def test_claims_route_false_is_the_folder_alone(self, client, db):
        """SWITCH 1: what `..._opt_in_exact_match_only` used to describe as the default."""
        folder, _entity, nested, _own_entity, own = self._folder_with_its_own_claim(db)
        ids = [c["id"] for c in client.get(
            f"/api/claims?source_document_id={folder.id}&include_descendants=false"
        ).json()["items"]]
        assert own.id in ids
        assert nested.id not in ids

    def test_entities_route_false_is_the_folder_alone(self, client, db):
        """SWITCH 2: new. This filter used to recurse with no way to turn it off."""
        folder, nested_entity, _claim, own_entity, _own = self._folder_with_its_own_claim(db)
        ids = [e["id"] for e in client.get(
            f"/api/entities?document_id={folder.id}&include_descendants=false"
        ).json()["items"]]
        assert own_entity.id in ids
        assert nested_entity.id not in ids

    def test_knowledge_graph_route_false_is_the_folder_alone(self, client, db):
        """SWITCH 3: `include_descendants=false` is honoured even on a folder
        with descendants. Under `include_children` the implicit `or` silently
        turned recursion back on, so this request could not be made at all."""
        folder, nested_entity, _claim, own_entity, _own = self._folder_with_its_own_claim(db)
        resp = client.get(f"/api/documents/{folder.id}/knowledge-graph?include_descendants=false").json()
        ids = _kg_entity_ids(resp)
        assert own_entity.id in ids
        assert nested_entity.id not in ids
        assert resp["include_children"] is False

    def test_the_retired_include_children_parameter_no_longer_selects_anything(self, client, db):
        """`include_children` was retired in favour of `include_descendants`.
        FastAPI ignores an unknown query parameter, so an OLD client sending
        `include_children=false` (the app's inspector does, by default) gets the
        recursive default, exactly what the old `or` gave it for any folder with
        contents, so the app's folder Inspector does not go blank. The old
        client's "this document only" toggle stays as ineffective as it was."""
        folder, _sub, _page, entity, _claim = _build_nested_folder(db)
        for legacy in ("false", "true"):
            resp = client.get(f"/api/documents/{folder.id}/knowledge-graph?include_children={legacy}")
            assert resp.status_code == 200
            assert entity.id in _kg_entity_ids(resp.json())

    def test_on_a_leaf_recursion_makes_no_difference(self, client, db):
        """Was `..._include_children_is_a_true_no_op_on_a_childless_leaf`: with
        nothing to recurse into, both settings give the same groups; only the
        echoed flag differs."""
        leaf = Document(name="lonely.txt", doc_type=DocType.file, page_content="Nothing to see.")
        db.save(leaf, auto_embed=False)
        default_resp = client.get(f"/api/documents/{leaf.id}/knowledge-graph").json()
        false_resp = client.get(f"/api/documents/{leaf.id}/knowledge-graph?include_descendants=false").json()
        assert default_resp["include_children"] is True
        assert false_resp["include_children"] is False
        assert default_resp["groups"] == false_resp["groups"] == []
