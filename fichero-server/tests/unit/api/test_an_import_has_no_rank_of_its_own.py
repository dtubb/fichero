"""An import has no rank of its own: it is just the first pass (`source.pass.working`, ruled
2026-10-04, #5443), so a run's newly landed pass is what a page shows when nobody chose (#5425), and
the Order tab lists the working pass's lines (#5450).

WHY: `resolve_working_pass` ranked an "imported" tier above every machine pass. On the Mosquera
notebooks a geometry-free TEI import of a Qwen-VL draft therefore stayed the working pass of 358 of
374 pages, over the Gemini reading of Kraken's lines that came later: Preview drew nothing, a new run
never showed without a manual promote, and the Order tab listed a third pass. If this regresses, a
file someone imported once outranks every later run for ever.

The ONE exception that must stay: an outside edit arriving through a synced folder (#4952) never
becomes working until a person chooses it -- however new it is.

Everything goes through the real actions (`format.import`, `segment.pass_create`,
`segment.create`, `pass.choose_working`) and the real routes the app reads.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_server.actions.registry import ActionContext, registry
from fichero_server.api.routes.document.segment_readings import document_text
from fichero_server.models import DocType, Document, FileType, Status
from fichero_server.models.anchors import SourceAnchor
from fichero_server.models.readings import OUTSIDE_FICHERO

pytestmark = pytest.mark.source_model

FIXTURES = Path(__file__).parents[1] / "formats" / "fixtures"
#: A TEI edition with no facsimile: every line's shape is unstated, like the Mosquera draft.
TEXT_ONLY_TEI = FIXTURES / "corpus" / "ddbdp_greek-papyrus_p.cair.zen.4.59742.tei.xml"
PAGE_A = FIXTURES / "ocrd_gt_aepinus_0020.page.xml"
PAGE_B = FIXTURES / "corpus" / "transkribus_german-fraktur_nzz-17840710.page.xml"

PERSON = ActionContext(actor="historian", library_path=None, is_bootstrap=True)
MACHINE = ActionContext(actor="kraken", run_id="run-1", library_path=None, is_bootstrap=True)
SYNCED = ActionContext(actor=OUTSIDE_FICHERO, library_path=None, is_bootstrap=True)


def _page(db) -> str:
    doc = Document(name="C01_005.jpg", doc_type=DocType.file, file_type=FileType.image,
                   path="/p/C01_005.jpg", status=Status.completed)
    db.save(doc)
    return doc.id


def _import(db, doc_id: str, path: Path, ctx: ActionContext = PERSON) -> str:
    return registry.invoke(db, "format.import", {"document_id": doc_id, "path": str(path)}, ctx).result["pass_id"]


def _machine_run(db, doc_id: str) -> str:
    """A recogniser's pass with one drawn line, made the way a run makes one (a run id: a machine)."""
    pass_id = registry.invoke(db, "segment.pass_create", {"document_id": doc_id, "name": "kraken"}, MACHINE).result["id"]
    registry.invoke(db, "segment.create", {
        "document_id": doc_id, "pass_id": pass_id, "kind": "line",
        "anchor": SourceAnchor(document_id=doc_id, rect=[0.1, 0.1, 0.6, 0.05]).model_dump(mode="json"),
    }, MACHINE)
    return pass_id


def _route_working(client, doc_id: str) -> tuple[str | None, str | None]:
    """The working pass as the app reads it: the segments route's `working` flag."""
    passes = client.get(f"/api/segments/document/{doc_id}").json()["passes"]
    working = [p for p in passes if p["working"]]
    assert len(working) <= 1
    return (working[0]["id"], working[0]["working_basis"]) if working else (None, None)


class TestSourcePassWorking:
    def test_a_newer_machine_pass_beats_an_older_import(self, db, client):
        """#5443/#5425, the Mosquera case: the import came first, a run landed after it. Newest wins,
        with no manual promote; in a strict project it is labelled unchosen, not hidden."""
        doc_id = _page(db)
        imported = _import(db, doc_id, TEXT_ONLY_TEI)
        machine = _machine_run(db, doc_id)

        answer = document_text(db, doc_id)
        assert (answer.pass_id, answer.pass_basis) == (machine, "newest-machine-unchosen"), (
            f"the import {imported} still outranks the newer run")
        assert _route_working(client, doc_id) == (machine, "newest-machine-unchosen"), "the app is told the same"

    def test_an_import_newer_than_a_machine_pass_wins_by_date_alone(self, db, client):
        """An import is just a pass: arriving later, it is the newest, ranked like any other."""
        doc_id = _page(db)
        _machine_run(db, doc_id)
        imported = _import(db, doc_id, PAGE_A)
        assert document_text(db, doc_id).pass_id == imported

    def test_a_persons_choice_beats_both(self, db, client):
        """A person's live choice always wins, here of the older import over the newer run."""
        doc_id = _page(db)
        imported = _import(db, doc_id, TEXT_ONLY_TEI)
        _machine_run(db, doc_id)
        registry.invoke(db, "pass.choose_working", {"document_id": doc_id, "pass_id": imported}, PERSON)

        assert (document_text(db, doc_id).pass_id, document_text(db, doc_id).pass_basis) == (imported, "chosen")
        assert _route_working(client, doc_id) == (imported, "chosen")

    def test_a_pass_a_person_touched_beats_a_newer_run_and_an_import(self, db, client):
        """The second rung: a person's own pass, older than both, still outranks them (2026-09-03)."""
        doc_id = _page(db)
        mine = registry.invoke(db, "segment.pass_create", {"document_id": doc_id, "name": "mine"}, PERSON).result["id"]
        _import(db, doc_id, TEXT_ONLY_TEI)
        _machine_run(db, doc_id)
        answer = document_text(db, doc_id)
        assert (answer.pass_id, answer.pass_basis) == (mine, "human-touched")

    def test_an_outside_edit_from_a_synced_folder_does_not_win_until_chosen(self, db, client):
        """Ruled 2026-10-04: newest-wins has ONE exception. A file edited outside Fichero arrives as
        the newest pass and still never becomes working by itself; choosing it does."""
        doc_id = _page(db)
        _import(db, doc_id, TEXT_ONLY_TEI)
        machine = _machine_run(db, doc_id)
        outside = _import(db, doc_id, PAGE_A, ctx=SYNCED)

        assert document_text(db, doc_id).pass_id == machine, "the outside edit took the record by itself"
        assert _route_working(client, doc_id)[0] == machine

        registry.invoke(db, "pass.choose_working", {"document_id": doc_id, "pass_id": outside}, PERSON)
        assert document_text(db, doc_id).pass_id == outside


class TestTheOrderTabListsTheWorkingPass:
    def test_the_working_passs_own_order_comes_first(self, db, client):
        """#5450: the Order tab shows the first `as-written` order the engine lists, and the engine
        listed them by name then id, so the tab showed whichever pass's order sorted first -- not the
        working pass's. The working pass is made the one whose order sorts LAST by id, so the old
        sort cannot pass this by luck."""
        doc_id = _page(db)
        first = _import(db, doc_id, PAGE_A)
        second = _import(db, doc_id, PAGE_B)
        orders = client.get(f"/api/reading-orders/document/{doc_id}").json()["orders"]
        as_written = {o["pass_id"]: o["id"] for o in orders if o["kind"] == "as-written"}
        assert set(as_written) == {first, second}, "both imports carry their file's order"
        working = max(as_written, key=lambda pass_id: as_written[pass_id])
        registry.invoke(db, "pass.choose_working", {"document_id": doc_id, "pass_id": working}, PERSON)

        listed = client.get(f"/api/reading-orders/document/{doc_id}").json()["orders"]
        assert listed[0]["pass_id"] == working == document_text(db, doc_id).pass_id
        assert listed[0]["kind"] == "as-written"
