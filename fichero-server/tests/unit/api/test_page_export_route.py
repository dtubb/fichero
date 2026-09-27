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

    @pytest.mark.parametrize("fmt", [
        "tei",
        pytest.param("pagexml", marks=pytest.mark.xfail(strict=True, reason=(
            "found by exporting a real library page: the PAGE XML writer writes our hex ids as XML "
            "IDs/IDREFs (they can start with a digit, which is not a valid NCName) and puts a "
            "TextLine directly under Page when the page has lines and no regions, as Kraken's do. "
            "The other lane's writer; reported, not fixed here"))),
        pytest.param("alto", marks=pytest.mark.xfail(strict=True, reason=(
            "ALTO validates now (xlink vendored, #5082) and refuses this page: the writer emits a "
            "TextLine/String with no TextBlock above it when a page has lines and no regions, as "
            "Kraken's do. Same class as #5084, the other lane's writer"))),
    ])
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
        assert "page size" in {l["what"] for l in body["losses"]}, "the seeded page records no pixel size"

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
        assert all(i["reads"] and i["writes"] for i in items.values())

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
    ALTO refuses a NAME where it wants a BCP 47 tag and says so, TEI builds an `xml:lang`. None of
    that runs, because `page_export` reads `row.language` off each segment row and a segment that
    states nothing stays None. The cascade (slice 9) is never consulted, so the document's language
    reaches no format, and nothing reports it as lost either. Silence, in all three.

    The assertion is deliberately NOT "the file says Spanish": ALTO honestly cannot carry a language
    NAME, and demanding it could would be demanding a lie. It is the weaker, true rule -- **state it
    or declare it lost, never neither** -- so any of the honest fixes satisfies it.
    """

    @pytest.mark.xfail(strict=True, reason=(
        "#5085. page_export.py maps `language=row.language`, the segment's own column, and never resolves "
        "the cascade, so a document-level language is silently absent from every export. The fix is "
        "page-level, not per-segment: promoting the document's answer onto each line would store a "
        "derived fact as a stated one, and a re-import would read it back as 188 lines each "
        "independently declaring Spanish. PAGE XML's PageType carries primaryLanguage, "
        "readingDirection and textLineOrder for exactly this, so `SourcePage` needs the three fields "
        "PageSegment already has"))
    @pytest.mark.parametrize("fmt", ["tei", "pagexml", "alto"])
    def test_it_is_stated_in_the_file_or_declared_lost(self, db, client, fmt):
        from fichero_server.models import Document

        page, _ = _converted(db, client)
        doc = db.get(Document, page.id)
        doc.language = "Spanish"
        db.save(doc)

        body = client.get(f"/api/documents/{page.id}/export/{fmt}").json()
        stated = "Spanish" in body["content"] or "es" in _lang_attributes(body["content"])
        declared = any(l["what"] == "language" for l in body["losses"])
        assert stated or declared, (
            f"{fmt} export of a Spanish document neither states the language nor reports losing it"
        )


def _lang_attributes(content: str) -> set[str]:
    """Every language-ish attribute value in the file, so the check does not depend on which
    attribute a given format chose."""
    import re

    return set(re.findall(r'(?:xml:lang|LANG|primaryLanguage)="([^"]+)"', content))
