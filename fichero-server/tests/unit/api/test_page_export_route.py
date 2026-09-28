"""`GET /api/documents/{id}/export/{format}` (`source.format.everywhere`, `.export-choices`).

Built on `seeded_converted_page`: a real converted page with Kraken-shaped boxes, edited through the
real routes, exported through the real route, and the file read back through the format's own reader.
"""
from __future__ import annotations

import pytest

from fichero_server.formats import read_page

from .seeded_converted_page import seed_page

pytestmark = pytest.mark.source_model


def _converted(db, client):
    _, page, art = seed_page(db)
    r = client.put(f"/api/artifacts/{art.id}/regions", json={"op": "move", "indices": [1], "bbox": [0.5, 0.5, 0.3, 0.05]})
    assert r.status_code == 200
    return page, art


class TestExportingAPage:
    LINES = ["In the year of our Lord", "one thousand eight hundred", "and fifty two, the ship", "sailed from Cadiz"]

    @pytest.mark.parametrize("fmt", ["tei", "pagexml", "alto"])
    # The two strict xfails here are gone: both were fixed 2026-09-27 and both were
    # found by THIS test rather than by a round trip, which is why it is worth running
    # after any format change.
    #
    # PAGE XML and ALTO were writing our 32-character hex ids straight into `xs:ID` and
    # `xs:IDREF`, and roughly six in ten start with a digit, which an NCName forbids --
    # so the element and every reference to it were invalid. One `xml_id()` in the
    # harness now derives them, deterministically, so a reference still matches the
    # element it names. And ALTO refused a `TextLine` with no `String`, which is most
    # lines of a converted page (their text is on the line): the required child is
    # invented, marked, and dropped again on re-import, with the line's text handed
    # back to the LINE rather than to a word nobody segmented.
    def test_a_converted_page_exports_in_each_format_and_reads_back(self, db, client, fmt):
        page, _ = _converted(db, client)
        r = client.get(f"/api/documents/{page.id}/export/{fmt}")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["format"] == fmt and body["filename"].endswith(".xml")
        back = read_page(fmt, body["content"].encode("utf-8"))
        texts = [s.readings[0][1] for s in back.segments if s.kind == "line" and s.readings]
        assert sorted(texts) == sorted(self.LINES), "every line, with its reading; box order decides the sequence"

    def test_the_moved_boxs_new_place_is_what_is_exported(self, db, client):
        """The export reads the LIVE rows, not the machine's original block."""
        page, _ = _converted(db, client)
        body = client.get(f"/api/documents/{page.id}/export/tei").json()
        back = read_page("tei", body["content"].encode("utf-8"))
        moved = [s for s in back.segments if s.kind == "line" and s.readings[0][1] == "one thousand eight hundred"][0]
        assert moved.rect[1] == pytest.approx(0.5, abs=0.01)

    def test_the_choices_are_named_in_the_response(self, db, client):
        page, _ = _converted(db, client)
        body = client.get(f"/api/documents/{page.id}/export/tei").json()
        choices = body["choices"]
        assert choices["pass_id"] and choices["pass_basis"]
        assert choices["order_name"] == "as-written" and choices["reading_kind"] == "transcription"
        assert choices["segment_count"] == 4

    def test_the_loss_report_reaches_the_caller(self, db, client):
        page, _ = _converted(db, client)
        body = client.get(f"/api/documents/{page.id}/export/tei").json()
        assert isinstance(body["losses"], list)
        assert "page size" in {loss["what"] for loss in body["losses"]}, "the seeded page records no pixel size"

    def test_a_corrected_reading_is_what_is_exported(self, db, client):
        from fichero_server.actions.registry import ActionContext, registry
        from fichero_server.api.routes.document.segment_conversion import live_rows_in_order
        from fichero_server.models import Artifact

        page, art = _converted(db, client)
        row = live_rows_in_order(db, db.get(Artifact, art.id).geometry_superseded_by_pass_id)[0]
        ctx = ActionContext(actor="historian", library_path=None, is_bootstrap=True)
        rid = registry.invoke(db, "representation.create", {"document_id": page.id, "segment_id": row.id,
                              "kind": "transcription", "content": "In the year of Our Lord"}, ctx).result["id"]
        registry.invoke(db, "reading.choose", {"segment_id": row.id, "kind": "transcription", "representation_id": rid}, ctx)
        body = client.get(f"/api/documents/{page.id}/export/tei").json()
        back = read_page("tei", body["content"].encode("utf-8"))
        assert "In the year of Our Lord" in [s.readings[0][1] for s in back.segments if s.readings]

    def test_an_unknown_format_is_a_404_naming_what_there_is(self, db, client):
        page, _ = _converted(db, client)
        r = client.get(f"/api/documents/{page.id}/export/docx")
        assert r.status_code == 404 and "tei" in r.text

    def test_a_document_with_no_pass_is_refused_not_exported_empty(self, db, client):
        from fichero_server.models import DocType, Document, FileType, Status

        doc = Document(name="blank.jpg", doc_type=DocType.file, file_type=FileType.image, path="/b.jpg", status=Status.completed)
        db.save(doc)
        r = client.get(f"/api/documents/{doc.id}/export/tei")
        assert r.status_code == 404 and "no pass" in r.text

    def test_a_pass_that_is_not_this_documents_is_refused(self, db, client):
        page, _ = _converted(db, client)
        r = client.get(f"/api/documents/{page.id}/export/tei", params={"pass_id": "nope"})
        assert r.status_code == 404


class TestTheFormatList:
    def test_it_names_what_this_build_reads_and_writes(self, client):
        items = {i["name"]: i for i in client.get("/api/formats").json()["items"]}
        assert {"tei", "pagexml", "alto", "hocr", "yolo"} <= set(items)
        assert all(items[n]["reads"] and items[n]["writes"] for n in ("tei", "pagexml", "alto", "hocr", "yolo"))
        # A sidecar read only BESIDE its image (plain text, a Tesseract .box: #5174) is listed as
        # read, not written -- the app's Export menu offers only what `writes` says (PageExportChoice).
        assert all(i["reads"] for i in items.values())
        assert not items["plain-text"]["writes"]

        # `validated` is NOT true of every format, and saying so is the point of the list.
        # hOCR is HTML with an agreed microformat and YOLO is five numbers a line: neither
        # HAS a schema, which is a different fact from a schema missing off an install
        # (that raises). A caller choosing an export format needs to know which of its
        # outputs was checked against somebody else's rules and which was not.
        assert all(items[n]["validated"] for n in ("tei", "pagexml", "alto"))
        assert not any(items[n]["validated"] for n in ("hocr", "yolo"))


class TestTheDocumentsLanguageReachesTheFile:
    """`source.lang.says-where-from` meeting `source.format.everywhere`: a page whose language is
    recorded on the DOCUMENT, which is where a library normally records it.

    The three writers handle language well -- PAGE XML maps it to its closed 188-name enumeration,
    ALTO refuses a NAME where it wants a BCP 47 tag and says so, TEI builds an `xml:lang`. When this
    was written none of that ran: `page_export` read `row.language` off each segment row, a segment
    that states nothing stayed None, the cascade was never consulted, and the document's language
    reached no format while nothing reported it lost either. Silence, in all three.

    **Two of the three are fixed now** (#5085): `SourcePage` carries the page's own language, script
    and direction, `page_export` fills them from the Document, PAGE XML states them on `Page` and
    ALTO declares the loss. TEI is the remaining half and is the xfail below. This paragraph is
    written in the past tense on purpose -- a docstring that still described all three as broken
    would be the same stale claim this suite exists to catch, one file further in.

    The assertion is deliberately NOT "the file says Spanish": ALTO honestly cannot carry a language
    NAME, and demanding it could would be demanding a lie. It is the weaker, true rule -- **state it
    or declare it lost, never neither** -- so any of the honest fixes satisfies it.
    """

    @pytest.mark.parametrize(
        "fmt",
        [
            pytest.param(
                "tei",
                marks=pytest.mark.xfail(
                    strict=True,
                    reason=(
                        "#5085, TEI half. `SourcePage` now carries the page's own language, script "
                        "and direction, `page_export` fills them from the Document, PAGE XML states "
                        "them on `Page` (primaryLanguage / primaryScript / readingDirection) and "
                        "ALTO declares the loss (it has no page-level attribute, and copying a "
                        "page's fact onto every line would store a derived fact as a stated one). "
                        "`<text xml:lang=…>` is where it belongs, and until then TEI neither "
                        "states the language nor declares losing it"
                    ),
                ),
            ),
            "pagexml",
            "alto",
        ],
    )
    def test_it_is_stated_in_the_file_or_declared_lost(self, db, client, fmt):
        from fichero_server.models import Document

        page, _ = _converted(db, client)
        doc = db.get(Document, page.id)
        doc.language = "Spanish"
        db.save(doc)

        body = client.get(f"/api/documents/{page.id}/export/{fmt}").json()
        stated = "Spanish" in body["content"] or "es" in _lang_attributes(body["content"])
        # `in` rather than `==`: ALTO reports "the page's language", and merging that
        # with a segment's "language" would give a reader `language: 401` for one page
        # fact and four hundred line facts. The loss is declared either way, which is
        # what this test is about.
        declared = any("language" in loss["what"] for loss in body["losses"])
        assert stated or declared, (
            f"{fmt} export of a Spanish document neither states the language nor reports losing it"
        )


def _lang_attributes(content: str) -> set[str]:
    """Every language-ish attribute value in the file, so the check does not depend on which
    attribute a given format chose."""
    import re

    return set(re.findall(r'(?:xml:lang|LANG|primaryLanguage)="([^"]+)"', content))


class TestTheRefusalsAreDeclaredAndNotOnlyRaised:
    """#5089's SIBLING, swept rather than waited for.

    The import route declared its error bodies and this one did not, while raising 404 and 409
    with a sentence. The consequence was not theoretical: the generated Swift client saw them as
    undocumented, and `DocumentService.exportPage` turned *"document X has no pass to export:
    nothing has been segmented or imported"* into `unexpectedResponse` — a word that names
    nothing, in place of the one sentence that says what to do next.

    Asserted against `app.openapi()` AND against the wire, because the whole defect was a
    contract and a route disagreeing: checking either alone is checking the half that was right.
    """

    def _schema(self, client):
        from fichero_server.api.main import app

        return app.openapi()["paths"]["/api/documents/{doc_id}/export/{format_name}"]["get"]

    @pytest.mark.parametrize("status", ["404", "409", "422"])
    def test_each_refusal_declares_the_body_it_actually_sends(self, client, status):
        responses = self._schema(client)["responses"]
        assert status in responses, f"{status} is raised by this route and declared nowhere"
        ref = responses[status]["content"]["application/json"]["schema"]["$ref"]
        assert ref.endswith("/ErrorDetail"), ref

    def test_it_is_the_SAME_component_the_import_route_uses(self, client):
        """One shape, one component. Two classes named `ErrorDetail` would not be shared — FastAPI
        names a component after its class, so they would collide and both be emitted under long
        qualified names, handing the app two types for one thing."""
        from fichero_server.api.main import app

        schema = app.openapi()
        assert "ErrorDetail" in schema["components"]["schemas"]
        assert not [
            name for name in schema["components"]["schemas"] if name.endswith("__ErrorDetail")
        ], "a qualified ErrorDetail means two classes collided instead of one being shared"

    def test_detail_is_a_plain_required_string(self, client):
        """Not FastAPI's validation-error ARRAY, which is what an undeclared 422 documents and
        what the client could not decode. And required, so the app has no optional to unwrap and
        no placeholder to invent when the engine did write a sentence."""
        from fichero_server.api.main import app

        model = app.openapi()["components"]["schemas"]["ErrorDetail"]
        assert model["properties"]["detail"]["type"] == "string"
        assert model.get("required") == ["detail"]

    def test_a_document_with_no_pass_sends_that_sentence_on_the_wire(self, db, client):
        from fichero_server.models import DocType, Document, FileType, Status

        doc = Document(name="blank.jpg", doc_type=DocType.file, file_type=FileType.image, path="/b.jpg", status=Status.completed)
        db.save(doc)
        r = client.get(f"/api/documents/{doc.id}/export/tei")
        assert r.status_code == 404
        body = r.json()
        assert isinstance(body["detail"], str), "a string, as declared — not a list of field errors"
        assert "no pass" in body["detail"]

    def test_an_unknown_format_sends_a_string_detail_too(self, db, client):
        page, _ = _converted(db, client)
        r = client.get(f"/api/documents/{page.id}/export/docx")
        assert r.status_code == 404 and isinstance(r.json()["detail"], str)


class TestAnOrderOfAnotherPassIsRefusedNotA500:
    """Found by asking who ELSE calls `document_text` with an order, once the refusal existed.

    `document_text` began raising `OrderIsOfAnotherPass` where it used to return an empty text.
    Three callers exist: the derived-text route (mapped by the change that added it), the
    page-text cache (passes no order, unaffected), and THIS route, which passes `order_id`
    straight through. A `ValueError` nobody catches is a 500 — so a caller naming a mismatched
    order would have been told the engine broke, when the engine had caught their mistake and
    could name the pass to ask for instead.

    Same shape as #5089 and its export-route sibling: an engine refusal arriving as something
    that helps nobody. **A fix is not finished until every caller of the changed function has
    been looked at** — and the two suites that cover those callers were both green, because
    neither exercises an order from another pass through this route.
    """

    def _another_passs_order(self, db, page):
        from fichero_server.actions.registry import ActionContext, registry
        from fichero_server.models.reading_orders import ReadingOrder

        ctx = ActionContext(actor="historian", library_path=None, is_bootstrap=True)
        made = registry.invoke(db, "segment.pass_create", {
            "document_id": page.id, "name": "other", "run_id": "run-other"}, ctx).result
        other_pass = made.get("pass_id") or made.get("id")
        orders = list(db.query(ReadingOrder, pass_id=other_pass))
        assert orders, "pass_create seeds an as-written order (source.order.named-multiple)"
        return other_pass, orders[0].id

    def test_an_order_from_another_pass_is_a_422_naming_the_pass_to_ask_for(self, db, client):
        page, _ = _converted(db, client)
        other_pass, order_id = self._another_passs_order(db, page)

        r = client.get(f"/api/documents/{page.id}/export/tei", params={"order_id": order_id})
        assert r.status_code == 422, r.text
        detail = r.json()["detail"]
        assert isinstance(detail, str), "a sentence, as ErrorDetail declares — not a field-error list"
        assert other_pass in detail, "the sentence must name the pass the order belongs to"
        assert "pass_id=" in detail, "and say what to ask for instead"

    def test_the_documents_own_order_still_exports(self, db, client):
        """The guard must not refuse the ordinary case — the test I would want if somebody else
        had written this one."""
        page, _ = _converted(db, client)
        body = client.get(f"/api/documents/{page.id}/export/tei").json()
        assert body["choices"]["order_name"] == "as-written"


class TestAnExportThatDoesNotValidateIsA422:
    """The route DECLARED 422 for an export that fails its own schema and raised 500. A 500
    says the engine broke; the truth is that this page cannot be written validly in that
    format, and the sentence says which rule it broke."""

    def test_it_is_a_422_with_the_schemas_reason(self, db, client, monkeypatch):
        import fichero_server.api.routes.document.page_export as route
        from fichero_server.formats import InvalidExport

        page, _ = _converted(db, client)

        def refuse(*_args, **_kwargs):
            raise InvalidExport("alto", ["line 3: Element 'String': The attribute 'CONTENT' is required"])

        monkeypatch.setattr(route, "export_page", refuse)
        r = client.get(f"/api/documents/{page.id}/export/alto")
        assert r.status_code == 422, r.text
        assert "CONTENT" in r.json()["detail"]
