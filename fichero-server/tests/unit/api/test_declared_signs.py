"""Declared signs on a real MUFI page (slice 14, #4939; `languages-scripts-signs.md`).

The real data: eScriptorium's ALTO of Clm 13027 fol. 38r (Medieval Latin, MUFI) carries U+F1AC
-- a private-use character MUFI assigns -- 50 times in 40 of its strings. A reading's text keeps
the character (the ruled default); the declared sign is what it MEANS.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException

import fichero_server.api.routes.document.format_import  # noqa: F401
import fichero_server.api.routes.document.signs  # noqa: F401
from fichero_server.actions.registry import ActionContext, registry
from fichero_server.models import ActionAudit, ContentRepresentation, DocType, Document, FileType, Status
from fichero_server.models.signs import DeclaredSign

pytestmark = pytest.mark.source_model

CTX = ActionContext(actor="palaeographer", library_path=None, is_bootstrap=True)
MUFI_PAGE = Path(__file__).resolve().parents[1] / "formats" / "fixtures" / "corpus" / "escriptorium_latin-mufi_clm13027-38r.alto.xml"
SIGN = ""


@pytest.fixture
def mufi_page(db):
    doc = Document(name="clm13027-38r.jpg", doc_type=DocType.file, file_type=FileType.image,
                   path="/p/clm13027-38r.jpg", status=Status.completed)
    db.save(doc)
    registry.invoke(db, "format.import", {"document_id": doc.id, "path": str(MUFI_PAGE)}, CTX)
    first = next(
        r for r in db.all(ContentRepresentation) if r.document_id == doc.id and SIGN in (r.content or "")
    )
    return doc, first.segment_id


def _declare(db, segment_id, **extra):
    params = {"name": "MUFI abbreviation sign", "picture_segment_id": segment_id, "code_point": "U+F1AC", **extra}
    return registry.invoke(db, "sign.declare", params, CTX)


class TestDeclaringASign:
    def test_a_sign_is_declared_from_the_segment_it_was_met_on(self, db, mufi_page):
        """`source.sign.declared`: a name, and a picture cut from a real page."""
        doc, segment_id = mufi_page
        result = _declare(db, segment_id, list_references=[{"authority": "MUFI", "number": "F1AC"}])
        sign = db.get(DeclaredSign, result.result["sign_id"])
        assert (sign.name, sign.picture_segment_id, sign.code_point) == ("MUFI abbreviation sign", segment_id, "U+F1AC")
        assert sign.list_references == [{"authority": "MUFI", "number": "F1AC"}]
        assert sign.created_by == "palaeographer", "the maker is the engine's answer, not the caller's"

    def test_a_sign_known_only_by_its_list_number_needs_no_code_point(self, db, mufi_page):
        """`source.sign.list-authority`: "number 561 in this catalogue", no code point at all."""
        doc, segment_id = mufi_page
        result = registry.invoke(db, "sign.declare", {
            "name": "T561", "picture_segment_id": segment_id,
            "list_references": [{"authority": "Thompson", "number": "561"}]}, CTX)
        assert db.get(DeclaredSign, result.result["sign_id"]).code_point is None

    def test_a_code_point_names_one_sign(self, db, mufi_page):
        doc, segment_id = mufi_page
        _declare(db, segment_id)
        with pytest.raises(HTTPException) as refused:
            _declare(db, segment_id, name="another name")
        assert refused.value.status_code == 409
        assert "already the declared sign" in refused.value.detail

    def test_a_picture_must_come_from_a_real_segment(self, db, mufi_page):
        with pytest.raises(HTTPException) as refused:
            _declare(db, "no-such-segment")
        assert refused.value.status_code == 404

    def test_a_malformed_code_point_is_refused(self, db, mufi_page):
        doc, segment_id = mufi_page
        with pytest.raises(Exception):
            _declare(db, segment_id, code_point="F1AC")

    def test_a_variant_says_both_what_it_varies_and_which_variant(self, db, mufi_page):
        """`source.sign.variants`: the character, plus which variant."""
        doc, segment_id = mufi_page
        result = registry.invoke(db, "sign.declare", {
            "name": "long s", "picture_segment_id": segment_id, "variant_of": "s", "variant": "long"}, CTX)
        sign = db.get(DeclaredSign, result.result["sign_id"])
        assert (sign.variant_of, sign.variant) == ("s", "long")
        with pytest.raises(HTTPException) as refused:
            registry.invoke(db, "sign.declare", {"name": "half", "picture_segment_id": segment_id, "variant_of": "r"}, CTX)
        assert refused.value.status_code == 422


class TestTheSignListAndItsInstances:
    def test_every_instance_on_the_real_page_is_gathered_by_one_query(self, db, client, mufi_page):
        """`source.sign.gather-instances`: all 50 occurrences of U+F1AC on fol. 38r, from one search."""
        doc, segment_id = mufi_page
        sign_id = _declare(db, segment_id).result["sign_id"]
        body = client.get(f"/api/signs/{sign_id}/instances").json()
        stored = [r for r in db.all(ContentRepresentation) if r.document_id == doc.id and SIGN in (r.content or "")]
        assert body["total"] == sum(r.content.count(SIGN) for r in stored)
        assert body["total"] >= 50
        assert {i["representation_id"] for i in body["items"]} == {r.id for r in stored}

    def test_the_project_sign_list_is_the_exportable_record(self, db, client, mufi_page):
        """`source.sign.project-list`: the list, as a client can export and share it."""
        doc, segment_id = mufi_page
        _declare(db, segment_id)
        items = client.get("/api/signs").json()["items"]
        assert [(i["code_point"], i["name"]) for i in items] == [("U+F1AC", "MUFI abbreviation sign")]

    def test_withdrawing_is_undoable_and_leaves_the_readings_alone(self, db, client, mufi_page):
        doc, segment_id = mufi_page
        before = sum((r.content or "").count(SIGN) for r in db.all(ContentRepresentation))
        declared = _declare(db, segment_id)
        withdrawn = registry.invoke(db, "sign.withdraw", {"sign_id": declared.result["sign_id"]}, CTX)
        assert client.get("/api/signs").json()["items"] == []
        assert sum((r.content or "").count(SIGN) for r in db.all(ContentRepresentation)) == before

        assert client.post(f"/api/actions/audit/{withdrawn.audit_id}/undo").status_code == 200
        assert [i["code_point"] for i in client.get("/api/signs").json()["items"]] == ["U+F1AC"]

    def test_undoing_a_declaration_withdraws_it(self, db, client, mufi_page):
        doc, segment_id = mufi_page
        declared = _declare(db, segment_id)
        assert db.get(ActionAudit, declared.audit_id).action_name == "sign.declare"
        assert client.post(f"/api/actions/audit/{declared.audit_id}/undo").status_code == 200
        assert client.get("/api/signs").json()["items"] == []
