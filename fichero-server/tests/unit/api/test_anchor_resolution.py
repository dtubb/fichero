"""Slice 6b (#4990) -- a mark follows its line when the line's box moves.

THE PROBLEM, which is older than the source model: a mark a person makes on
a line is stored with the rectangle that line had at that moment. Move the
line and the mark stays where the box used to be, because every rectangle a
mark draws comes from that stored one and nothing on the path ever asked
where the box went. Today's box move already does this; first-edit
conversion makes it matter, because curating boxes becomes ordinary.

THE WAY BACK, storing nothing: the KEPT BLOCK never changes, so it is a
permanent table from "the rectangle a box had" to "that box's position",
and a position plus the artifact gives the repeatable segment id. The stored
anchor is never rewritten.
"""

from __future__ import annotations

import pytest

from fichero_server.actions.registry import ActionContext, registry
from fichero_server.api.routes.document.segment_conversion import (
    AnchorBasis,
    live_rows_in_order,
    resolve_anchor,
)
from fichero_server.core.timeutil import utc_now
from fichero_server.media.ocr_geometry import OCRGeometryBox, OCRGeometryResult
from fichero_server.models import Artifact, DocType, Document, FileType, Status
from fichero_server.models.anchors import SourceAnchor
from fichero_server.models.knowledge import Annotation, AnnotationKind
from fichero_server.models.segments import converted_pass_id

pytestmark = pytest.mark.source_model


def _ctx() -> ActionContext:
    return ActionContext(actor="historian", library_path=None, is_bootstrap=True)


def _make_doc(db, name: str = "page.jpg") -> Document:
    doc = Document(
        name=name, doc_type=DocType.file, file_type=FileType.image,
        path=f"/path/{name}", status=Status.completed,
    )
    db.save(doc)
    return doc


def _artifact(db, doc, count: int = 3, rendition_id: str | None = None) -> Artifact:
    artifact = Artifact(
        document_id=doc.id, artifact_type="transcription", provider="qwen",
        ocr_geometry=OCRGeometryResult(
            provider="qwen", text=" ".join(f"w{i}" for i in range(count)),
            rendition_id=rendition_id,
            boxes=[
                OCRGeometryBox(
                    text=f"w{i}", bbox=[0.1, 0.1 + i * 0.2, 0.2, 0.05], level="line",
                )
                for i in range(count)
            ],
        ),
    )
    db.save(artifact)
    return artifact


def _mark(db, doc, rect, rendition_id=None) -> Annotation:
    ann = Annotation(
        kind=AnnotationKind.highlight, document_id=doc.id,
        anchor=SourceAnchor(
            document_id=doc.id, rect=list(rect), rendition_id=rendition_id
        ),
    )
    db.save(ann)
    return ann


def _convert(db, doc):
    registry.invoke(db, "segment.convert_and_edit", {"document_id": doc.id}, _ctx())


def _move(db, artifact, index, rect):
    row = live_rows_in_order(db, converted_pass_id(artifact.id))[index]
    row.anchor = row.anchor.model_copy(update={"rect": list(rect)})
    db.save(row)
    return row


class TestAMarkFollowsItsLine:
    def test_the_resolved_place_is_the_new_one_and_the_stored_one_is_unchanged(self, db):
        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        was = list(artifact.ocr_geometry.boxes[1].bbox)
        mark = _mark(db, doc, was)
        _convert(db, doc)
        row = _move(db, artifact, 1, [0.7, 0.7, 0.1, 0.05])

        resolved = resolve_anchor(db, db.get(Annotation, mark.id).anchor)
        assert resolved.basis is AnchorBasis.segment
        assert resolved.segment_id == row.id
        assert resolved.anchor.rect == [0.7, 0.7, 0.1, 0.05]
        # And the mark itself is untouched: nothing is rewritten.
        assert db.get(Annotation, mark.id).anchor.rect == was

    def test_it_still_follows_after_the_line_has_moved_twice(self, db):
        """The block never changes, so the way back does not decay."""
        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        mark = _mark(db, doc, list(artifact.ocr_geometry.boxes[0].bbox))
        _convert(db, doc)
        _move(db, artifact, 0, [0.5, 0.5, 0.1, 0.05])
        _move(db, artifact, 0, [0.8, 0.2, 0.15, 0.05])

        resolved = resolve_anchor(db, db.get(Annotation, mark.id).anchor)
        assert resolved.anchor.rect == [0.8, 0.2, 0.15, 0.05]

    def test_the_read_carries_the_resolved_place_beside_the_stored_one(self, db, client):
        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        was = list(artifact.ocr_geometry.boxes[1].bbox)
        mark = _mark(db, doc, was)
        _convert(db, doc)
        _move(db, artifact, 1, [0.7, 0.7, 0.1, 0.05])

        body = client.get(f"/api/annotations/{mark.id}").json()
        assert body["anchor"]["rect"] == was, "the stored place is never rewritten"
        assert body["resolved_anchor"]["anchor"]["rect"] == [0.7, 0.7, 0.1, 0.05]
        assert body["resolved_anchor"]["basis"] == "segment"

    def test_the_list_carries_it_too(self, db, client):
        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        _mark(db, doc, list(artifact.ocr_geometry.boxes[0].bbox))
        _convert(db, doc)
        _move(db, artifact, 0, [0.7, 0.7, 0.1, 0.05])

        body = client.get("/api/annotations", params={"document_id": doc.id}).json()
        assert body["count"] == 1
        assert body["items"][0]["resolved_anchor"]["anchor"]["rect"] == [0.7, 0.7, 0.1, 0.05]


class TestAMarkDrawnFreeStaysWhereItWasDrawn:
    def test_a_rectangle_matching_no_box_resolves_to_itself(self, db):
        """It was about a PLACE, not about a line."""
        doc = _make_doc(db)
        _artifact(db, doc)
        free = [0.44, 0.44, 0.07, 0.07]
        mark = _mark(db, doc, free)
        _convert(db, doc)

        resolved = resolve_anchor(db, db.get(Annotation, mark.id).anchor)
        assert resolved.basis is AnchorBasis.stored
        assert resolved.segment_id is None
        assert resolved.anchor.rect == free

    def test_a_rectangle_that_only_NEARLY_matches_stays_put(self, db):
        """Never by nearness: moving a historian's mark onto a line they
        never marked is worse than leaving it where they put it."""
        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        nearly = list(artifact.ocr_geometry.boxes[1].bbox)
        nearly[0] += 0.01
        mark = _mark(db, doc, nearly)
        _convert(db, doc)
        _move(db, artifact, 1, [0.7, 0.7, 0.1, 0.05])

        resolved = resolve_anchor(db, db.get(Annotation, mark.id).anchor)
        assert resolved.basis is AnchorBasis.stored
        assert resolved.anchor.rect == nearly

    def test_a_mark_on_an_unconverted_page_resolves_to_itself(self, db):
        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        mark = _mark(db, doc, list(artifact.ocr_geometry.boxes[0].bbox))

        resolved = resolve_anchor(db, db.get(Annotation, mark.id).anchor)
        assert resolved.basis is AnchorBasis.stored

    def test_a_rectangle_measured_on_another_picture_does_not_match(self, db):
        """The frame is part of the question, as it is in slice 4's rule: the
        same numbers on a crop and on the page are different places."""
        doc = _make_doc(db)
        artifact = _artifact(db, doc, rendition_id="rend-crop-1")
        mark = _mark(db, doc, list(artifact.ocr_geometry.boxes[0].bbox), rendition_id=None)
        _convert(db, doc)

        resolved = resolve_anchor(db, db.get(Annotation, mark.id).anchor)
        assert resolved.basis is AnchorBasis.stored


class TestAMarkOnADeletedLine:
    def test_it_keeps_its_place_and_says_the_line_is_gone(self, db):
        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        was = list(artifact.ocr_geometry.boxes[2].bbox)
        mark = _mark(db, doc, was)
        _convert(db, doc)
        row = live_rows_in_order(db, converted_pass_id(artifact.id))[2]
        row.deleted_at = utc_now()
        db.save(row)

        resolved = resolve_anchor(db, db.get(Annotation, mark.id).anchor)
        assert resolved.basis is AnchorBasis.segment_deleted
        assert resolved.segment_id == row.id
        assert resolved.anchor.rect == was, "shown where it was, not nowhere"


class TestTheResolverItself:
    def test_no_anchor_resolves_to_nothing_rather_than_raising(self, db):
        assert resolve_anchor(db, None) is None

    def test_an_anchor_with_no_rectangle_resolves_to_itself(self, db):
        doc = _make_doc(db)
        anchor = SourceAnchor(document_id=doc.id, char_start=0, char_end=4)
        resolved = resolve_anchor(db, anchor)
        assert resolved.basis is AnchorBasis.stored
        assert resolved.anchor is anchor

    def test_it_writes_nothing(self, db):
        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        mark = _mark(db, doc, list(artifact.ocr_geometry.boxes[0].bbox))
        _convert(db, doc)
        before = [
            db.get(Annotation, mark.id).model_dump(mode="json"),
            db.get(Artifact, artifact.id).model_dump(mode="json"),
            [r.model_dump(mode="json") for r in live_rows_in_order(db, converted_pass_id(artifact.id))],
        ]
        for _ in range(5):
            resolve_anchor(db, db.get(Annotation, mark.id).anchor)
        assert [
            db.get(Annotation, mark.id).model_dump(mode="json"),
            db.get(Artifact, artifact.id).model_dump(mode="json"),
            [r.model_dump(mode="json") for r in live_rows_in_order(db, converted_pass_id(artifact.id))],
        ] == before


class TestTheCropIsCutFromWhereTheLineIs:
    """A crop of the STORED rectangle after the box moved is a picture of the
    OLD place -- the same fault as the mark being drawn there, made permanent
    in an image. The only honest assertion is on the PIXELS that come back,
    so these paint the two places different colours and read the answer.
    """

    @staticmethod
    def _page(db, colours: dict[tuple[int, int, int], tuple[float, float, float, float]]):
        """A 200x200 page with each given colour filling its normalized rect."""
        from PIL import Image

        image = Image.new("RGB", (200, 200), (255, 255, 255))
        for colour, (x, y, w, h) in colours.items():
            block = Image.new("RGB", (round(w * 200), round(h * 200)), colour)
            image.paste(block, (round(x * 200), round(y * 200)))
        path = db.path.parent / "page.png"
        image.save(path)
        doc = Document(
            name="page.png", doc_type=DocType.file, file_type=FileType.image,
            path=str(path), status=Status.completed,
        )
        db.save(doc)
        return doc

    @staticmethod
    def _only_colour(png: bytes) -> tuple[int, int, int]:
        from io import BytesIO

        from PIL import Image

        colours = Image.open(BytesIO(png)).convert("RGB").getcolors(maxcolors=1 << 16)
        return max(colours)[1]

    RED = (255, 0, 0)
    BLUE = (0, 0, 255)

    def test_the_picture_is_of_the_new_place(self, db, client):
        was = (0.1, 0.3, 0.2, 0.05)
        now = (0.6, 0.7, 0.2, 0.05)
        doc = self._page(db, {self.RED: was, self.BLUE: now})
        artifact = _artifact(db, doc)
        mark = _mark(db, doc, list(was))
        _convert(db, doc)
        _move(db, artifact, 1, list(now))

        resp = client.get(f"/api/annotations/{mark.id}/crop")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/png"
        assert self._only_colour(resp.content) == self.BLUE

    def test_a_mark_drawn_free_is_still_cut_from_where_it_was_drawn(self, db, client):
        """Nothing resolved it, so nothing moves the knife."""
        free = (0.6, 0.7, 0.2, 0.05)
        doc = self._page(db, {self.BLUE: free})
        _artifact(db, doc)
        mark = _mark(db, doc, list(free))
        _convert(db, doc)

        resp = client.get(f"/api/annotations/{mark.id}/crop")
        assert resp.status_code == 200
        assert self._only_colour(resp.content) == self.BLUE

    def test_the_stored_anchor_is_not_rewritten_by_a_crop(self, db, client):
        was = (0.1, 0.3, 0.2, 0.05)
        doc = self._page(db, {self.RED: was, self.BLUE: (0.6, 0.7, 0.2, 0.05)})
        artifact = _artifact(db, doc)
        mark = _mark(db, doc, list(was))
        _convert(db, doc)
        _move(db, artifact, 1, [0.6, 0.7, 0.2, 0.05])

        client.get(f"/api/annotations/{mark.id}/crop")
        assert db.get(Annotation, mark.id).anchor.rect == list(was)


class TestAClaimIsNotWiredYetAndThatIsDeliberate:
    """A claim's source anchor has the SAME fault a mark does, and
    `resolve_anchor` answers it in one line. It is NOT wired into the claim
    reads yet, for two measured reasons, both recorded here so this reads
    as a decision rather than an oversight:

    * nothing consumes it -- the app half of #4990 is the annotation
      accessor and the PDF page view;
    * the claim LIST is fetched by the app with `limit: 500`, so resolving
      there would add an artifact query and a block parse per claim to the
      hottest knowledge read.

    And the Swift cost is real: 211 sites are typed on the generated claim
    schema, against 2 for the single GET.
    """

    def test_the_resolver_already_answers_for_a_claims_anchor(self, db):
        """What is owed is the WIRING, not the resolver -- so when a reader
        appears, this is all there is to it."""
        from fichero_server.models.knowledge import KnowledgeClaim

        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        was = list(artifact.ocr_geometry.boxes[1].bbox)
        claim = KnowledgeClaim(
            text="the alcalde signed here", source_document_id=doc.id,
            source_anchor=SourceAnchor(document_id=doc.id, rect=was),
        )
        db.save(claim)
        _convert(db, doc)
        _move(db, artifact, 1, [0.7, 0.7, 0.1, 0.05])

        resolved = resolve_anchor(db, db.get(KnowledgeClaim, claim.id).source_anchor)
        assert resolved.basis is AnchorBasis.segment
        assert resolved.anchor.rect == [0.7, 0.7, 0.1, 0.05]

    def test_the_claim_read_does_not_carry_it_yet(self, db, client):
        from fichero_server.models.knowledge import KnowledgeClaim

        doc = _make_doc(db)
        claim = KnowledgeClaim(text="asserted by hand", source_document_id=doc.id)
        db.save(claim)
        body = client.get(f"/api/claims/{claim.id}").json()
        assert "resolved_anchor" not in body
