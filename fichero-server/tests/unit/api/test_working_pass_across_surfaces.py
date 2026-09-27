"""`source.pass.working`: "the Reader, search and export use one pass" -- settled per surface, from
the SURFACE, not from the ranking function (#5077). Built on `seeded_converted_page`.

Findings, in one place so the spec can be worded from evidence:

* **Page export** resolves its pass through `document_text`, so it follows the working pass, and it
  says which pass and why (`pass_basis`). Proven below.
* **Search and library export read `Document.page_content`** (embeddings, snippets, FTS scoring and
  `export_service._document_text` all take `page_content`; none consults the ranking). They use the
  working pass only as far as that cache is right, which is `page_text_cache`'s job. Proven below
  for the paths that keep it right, including the one that did not (deleting the working pass).
* **The Reader** reads `page_content` too, so it has the same dependence.
"""
from __future__ import annotations

import pytest

import fichero_server.api.routes.document.content_representations  # noqa: F401
from fichero_server.actions.registry import ActionContext, registry
from fichero_server.formats import read_page
from fichero_server.models import Document
from fichero_server.models.anchors import SourceAnchor

from .seeded_converted_page import seed_page

pytestmark = pytest.mark.source_model

CTX = ActionContext(actor="historian", library_path=None, is_bootstrap=True)
IMPORTED = "words only the newer pass has"


def _two_passes(db, client):
    """A page whose working pass is the OLD converted one (chosen by the first edit) and a NEWER
    pass beside it with different text."""
    _, page, art = seed_page(db)
    assert client.put(f"/api/artifacts/{art.id}/regions", json={"op": "move", "indices": [3], "bbox": [0.5, 0.9, 0.1, 0.05]}).status_code == 200
    old_pass = client.get(f"/api/segments/document/{page.id}/text").json()["pass_id"]
    new_pass = registry.invoke(db, "segment.pass_create", {"document_id": page.id, "name": "imported", "run_id": "run-x"}, CTX).result["id"]
    seg = registry.invoke(db, "segment.create", {
        "document_id": page.id, "pass_id": new_pass, "kind": "line",
        "anchor": SourceAnchor(document_id=page.id, rect=[0.1, 0.05, 0.5, 0.05]).model_dump(mode="json")}, CTX).result["segment_ids"][0]
    registry.invoke(db, "representation.create", {"document_id": page.id, "segment_id": seg,
                    "kind": "transcription", "content": IMPORTED}, CTX)
    return page, old_pass, new_pass


def _exported_texts(client, page, **params):
    body = client.get(f"/api/documents/{page.id}/export/tei", params=params).json()
    back = read_page("tei", body["content"].encode("utf-8"))
    return body, [s.readings[0][1] for s in back.segments if s.readings]


class TestPageExportFollowsTheWorkingPass:
    def test_the_chosen_older_pass_is_exported_not_the_newest(self, db, client):
        page, old_pass, new_pass = _two_passes(db, client)
        body, texts = _exported_texts(client, page)
        assert body["choices"]["pass_id"] == old_pass and body["choices"]["pass_basis"] == "chosen"
        assert "In the year of our Lord" in texts and IMPORTED not in texts

    def test_choosing_the_newer_pass_changes_what_is_exported(self, db, client):
        page, old_pass, new_pass = _two_passes(db, client)
        registry.invoke(db, "pass.choose_working", {"document_id": page.id, "pass_id": new_pass}, CTX)
        body, texts = _exported_texts(client, page)
        assert body["choices"]["pass_id"] == new_pass
        assert texts == [IMPORTED]

    def test_an_explicit_pass_overrides_the_working_one_and_says_so(self, db, client):
        page, old_pass, new_pass = _two_passes(db, client)
        body, texts = _exported_texts(client, page, pass_id=new_pass)
        assert body["choices"]["pass_id"] == new_pass and texts == [IMPORTED]


class TestTheCacheSearchReadsFollowsTheWorkingPass:
    def _cache(self, db, page):
        return db.get(Document, page.id).page_content

    def test_choosing_the_newer_pass_moves_the_text_search_indexes(self, db, client):
        page, old_pass, new_pass = _two_passes(db, client)
        assert IMPORTED not in self._cache(db, page)
        registry.invoke(db, "pass.choose_working", {"document_id": page.id, "pass_id": new_pass}, CTX)
        assert self._cache(db, page) == IMPORTED

    def test_choosing_back_restores_it(self, db, client):
        page, old_pass, new_pass = _two_passes(db, client)
        registry.invoke(db, "pass.choose_working", {"document_id": page.id, "pass_id": new_pass}, CTX)
        registry.invoke(db, "pass.choose_working", {"document_id": page.id, "pass_id": old_pass}, CTX)
        assert "In the year of our Lord" in self._cache(db, page)

    def test_deleting_the_working_pass_moves_the_cache_to_the_pass_that_becomes_working(self, db, client):
        """The path that DID leave them disagreeing: `pass_delete` names the pass it removed, the
        skip (#5086) then saw a pass that was not the NEW working one and skipped, so the cache kept
        the deleted pass's text. Found by asking what changes the working pass besides a choice."""
        page, old_pass, new_pass = _two_passes(db, client)
        registry.invoke(db, "pass.choose_working", {"document_id": page.id, "pass_id": new_pass}, CTX)
        assert self._cache(db, page) == IMPORTED
        registry.invoke(db, "segment.pass_delete", {"pass_id": new_pass}, CTX)
        derived = client.get(f"/api/segments/document/{page.id}/text").json()
        assert derived["pass_id"] == old_pass
        assert self._cache(db, page) == derived["text"]

    def test_restoring_a_deleted_pass_moves_it_back(self, db, client):
        page, old_pass, new_pass = _two_passes(db, client)
        registry.invoke(db, "pass.choose_working", {"document_id": page.id, "pass_id": new_pass}, CTX)
        registry.invoke(db, "segment.pass_delete", {"pass_id": new_pass}, CTX)
        registry.invoke(db, "segment.pass_restore", {"pass_id": new_pass}, CTX)
        derived = client.get(f"/api/segments/document/{page.id}/text").json()
        assert self._cache(db, page) == derived["text"]
