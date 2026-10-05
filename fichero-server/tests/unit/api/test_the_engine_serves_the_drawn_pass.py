"""The engine serves the pass the image draws (`ui.preview.draws-a-pass-with-shapes`, #5467).

WHY: Preview draws the best pass WITH SHAPES -- the working pass when it has shapes, otherwise the
next pass in the working-pass ranking that has them (ruled 2026-10-04, #5443, #5425, #5450). The
segments route marked only `working`, so the app kept its own fallback ranking (curated, other,
legacy, shapeless last) to find a pass to draw -- a second copy of the ladder that can disagree with
the engine's. On Mosquera a geometry-free TEI draft was the working pass and the image drew nothing.
Now every `PassRead` carries `drawn` and `rank`, worked out by `resolve_drawn_pass` over the SAME
ranking `resolve_working_pass` heads (`rank_passes`), so if these fail the app either draws nothing
over a page that has boxes, or draws a pass the engine's ranking would not.

Everything goes through the real actions and the real route the app reads.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_server.actions.registry import ActionContext, registry
from fichero_server.api.routes.document.segment_readings import working_pass
from fichero_server.models import DocType, Document, FileType, Status
from fichero_server.models.anchors import SourceAnchor

pytestmark = pytest.mark.source_model

FIXTURES = Path(__file__).parents[1] / "formats" / "fixtures"
#: A TEI edition with no facsimile: every line's shape is unstated, like the Mosquera draft.
TEXT_ONLY_TEI = FIXTURES / "corpus" / "ddbdp_greek-papyrus_p.cair.zen.4.59742.tei.xml"

PERSON = ActionContext(actor="historian", library_path=None, is_bootstrap=True)
MACHINE = ActionContext(actor="kraken", run_id="run-1", library_path=None, is_bootstrap=True)


def _page(db) -> str:
    doc = Document(name="C01_005.jpg", doc_type=DocType.file, file_type=FileType.image,
                   path="/p/C01_005.jpg", status=Status.completed)
    db.save(doc)
    return doc.id


def _import_text_only(db, doc_id: str) -> str:
    return registry.invoke(db, "format.import", {"document_id": doc_id, "path": str(TEXT_ONLY_TEI)}, PERSON).result["pass_id"]


def _pass(db, doc_id: str, ctx: ActionContext, *, with_a_line: bool = True) -> str:
    """A pass made the way `ctx` makes one; with one drawn line unless it is a run still going."""
    pass_id = registry.invoke(db, "segment.pass_create", {"document_id": doc_id, "name": ctx.actor}, ctx).result["id"]
    if with_a_line:
        registry.invoke(db, "segment.create", {
            "document_id": doc_id, "pass_id": pass_id, "kind": "line",
            "anchor": SourceAnchor(document_id=doc_id, rect=[0.1, 0.1, 0.6, 0.05]).model_dump(mode="json"),
        }, ctx)
    return pass_id


def _served(client, doc_id: str) -> list[dict]:
    """The page's passes as the app reads them, and the invariants every answer must keep: exactly
    one working pass at rank 0, ranks distinct and contiguous, at most one drawn."""
    passes = client.get(f"/api/segments/document/{doc_id}").json()["passes"]
    ranks = sorted(p["rank"] for p in passes if p["rank"] is not None)
    assert ranks == list(range(len(ranks))), f"ranks are not one order: {ranks}"
    assert [p["rank"] for p in passes if p["working"]] == [0], "the working pass is not the ranking's head"
    assert sum(p["drawn"] for p in passes) <= 1, "more than one pass drawn"
    return passes


def _drawn(passes: list[dict]) -> str | None:
    return next((p["id"] for p in passes if p["drawn"]), None)


def _first_shaped_by_rank(passes: list[dict], shaped: set[str]) -> str | None:
    """What the ranking says should be drawn, read off the served ranks: agreement, not a 2nd ladder."""
    return next((p["id"] for p in sorted(passes, key=lambda p: p["rank"]) if p["id"] in shaped), None)


class TestTheDrawnPass:
    def test_a_working_pass_with_shapes_is_the_one_drawn(self, db, client):
        """The common case: the page's text and its boxes come from the same pass."""
        doc_id = _page(db)
        _import_text_only(db, doc_id)
        machine = _pass(db, doc_id, MACHINE)

        passes = _served(client, doc_id)
        assert working_pass(db, doc_id).pass_id == machine
        assert _drawn(passes) == machine

    def test_a_shapeless_newer_import_is_working_but_the_ranked_pass_with_shapes_is_drawn(self, db, client):
        """The Mosquera case (#5425): the TEI draft (no coordinates) is the newest, so it is the
        working pass and its text shows, but the image draws the run's lines, not nothing."""
        doc_id = _page(db)
        machine = _pass(db, doc_id, MACHINE)
        imported = _import_text_only(db, doc_id)

        passes = _served(client, doc_id)
        assert working_pass(db, doc_id).pass_id == imported, "the import is newest, so it is working"
        assert _drawn(passes) == machine
        assert _drawn(passes) == _first_shaped_by_rank(passes, {machine})

    def test_a_run_still_going_draws_the_pass_before_it(self, db, client):
        """A run's pass exists before its boxes land: working (newest) but empty, so the image keeps
        the previous pass's boxes rather than blanking mid-run."""
        doc_id = _page(db)
        earlier = _pass(db, doc_id, MACHINE)
        running = _pass(db, doc_id, MACHINE, with_a_line=False)

        passes = _served(client, doc_id)
        assert working_pass(db, doc_id).pass_id == running
        assert _drawn(passes) == earlier

    def test_the_fallback_follows_the_ranking_not_the_date(self, db, client):
        """With the chosen pass shapeless, a person's older pass outranks a newer machine run (the
        2026-09-03 rung) -- so the person's boxes are drawn. A date-only or app-side fallback would
        draw the run's."""
        doc_id = _page(db)
        mine = _pass(db, doc_id, PERSON)
        newer_machine = _pass(db, doc_id, MACHINE)
        imported = _import_text_only(db, doc_id)
        registry.invoke(db, "pass.choose_working", {"document_id": doc_id, "pass_id": imported}, PERSON)

        passes = _served(client, doc_id)
        rank = {p["id"]: p["rank"] for p in passes}
        assert (rank[imported], rank[mine], rank[newer_machine]) == (0, 1, 2)
        assert _drawn(passes) == mine == _first_shaped_by_rank(passes, {mine, newer_machine})

    def test_no_pass_with_shapes_draws_none(self, db, client):
        """A text-only page: there is a working pass for its text and nothing to draw."""
        doc_id = _page(db)
        imported = _import_text_only(db, doc_id)

        passes = _served(client, doc_id)
        assert working_pass(db, doc_id).pass_id == imported
        assert _drawn(passes) is None

    def test_a_filtered_read_names_the_same_drawn_pass(self, db, client):
        """Like `working` (#5467), `drawn` is judged over the whole page, not the passes a filtered
        read happens to hold, so filtering by pass cannot move the drawing elsewhere."""
        doc_id = _page(db)
        machine = _pass(db, doc_id, MACHINE)
        imported = _import_text_only(db, doc_id)

        only_import = client.get(f"/api/segments/document/{doc_id}", params={"pass_id": imported}).json()["passes"]
        assert [p["drawn"] for p in only_import] == [False], f"{machine} is the drawn pass, not the import"
