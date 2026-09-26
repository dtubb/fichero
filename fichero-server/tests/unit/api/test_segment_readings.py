"""Source-model slice 8, part 3 (#4934, #4929, #4932) -- readings written,
chosen, and read back from BOTH stores.

Spec: `build-notes-readings-cascade-orders.md`, "Slice 8", sections "Where
readings actually live today", "Actions", "Routes" and "Refusals".

Behaviours pinned:
* `source.reading.set` / `.corrections-are-new` -- three readings coexist;
  adding one changes no other row; a correction leaves its target's text alone.
* `source.reading.read-from`, `.written-read-pair`, `.level-recorded`.
* `source.reading.maker-set-by-engine` -- the engine decides who wrote it.
* `source.reading.chosen-is-worked-out` -- a person's choice, recorded; the
  counting answer rides on the list read.
* `source.one-store` / `source.seam.provisional-ids-refused` -- a provisional
  reading read out of an artifact is offered like any other, and its id is
  refused on every write.
* "Audit payloads of every action contain no `content`."

Everything is asserted through the REAL route or the REAL action registry
against REAL converted rows -- the page is converted by the same
`PUT /api/artifacts/{id}/regions` the unchanged app uses, so a provisional
reading here is one the seam actually built, not a fixture pretending to be one.
"""

from __future__ import annotations

import pytest

from fichero_server.actions.registry import ActionContext, registry
from fichero_server.api.routes.document.segment_conversion import (
    converted_pass_id,
    live_rows_in_order,
)
from fichero_server.media.ocr_geometry import OCRGeometryBox, OCRGeometryResult
from fichero_server.models import (
    ActionAudit,
    Artifact,
    ContentRepresentation,
    DocType,
    Document,
    FileType,
    ReadingChoice,
    Status,
)
from fichero_server.models.anchors import SourceAnchor
from fichero_server.models.knowledge import ProvenanceKind
from fichero_server.api.routes.document.segment_readings import readings_of_segment
from fichero_server.models.readings import CountingBasis, legacy_reading_segment_id

pytestmark = pytest.mark.source_model

#: The artifact's own text; each box names its stretch of it (#4309), which is
#: what lets a line's provisional reading be that line's words and not the
#: whole page's.
PAGE_TEXT = "en el nombre de dios amen"
#: Worked out from the text rather than written by hand, so a span can never
#: silently stop naming the word it is supposed to name.
SPANS = [
    (PAGE_TEXT.index(word), PAGE_TEXT.index(word) + len(word))
    for word in PAGE_TEXT.split()
]


def _make_doc(db, name: str = "page.jpg") -> Document:
    doc = Document(
        name=name, doc_type=DocType.file, file_type=FileType.image,
        path=f"/path/{name}", status=Status.completed,
    )
    db.save(doc)
    return doc


def _artifact(db, doc, *, artifact_type: str = "transcription", spans: bool = True) -> Artifact:
    artifact = Artifact(
        document_id=doc.id, artifact_type=artifact_type, provider="qwen", model="qwen-vl",
        content=PAGE_TEXT,
        ocr_geometry=OCRGeometryResult(
            provider="qwen", text=PAGE_TEXT,
            boxes=[
                OCRGeometryBox(
                    text=PAGE_TEXT[start:end],
                    bbox=[0.1, 0.1 + index * 0.12, 0.4, 0.05],
                    level="line",
                    char_start=start if spans else None,
                    char_end=end if spans else None,
                    confidence=0.8,
                )
                for index, (start, end) in enumerate(SPANS)
            ],
        ),
    )
    db.save(artifact)
    return artifact


def _convert(client, artifact_id: str) -> None:
    """Convert the page the way the app does: its first edit."""
    response = client.put(
        f"/api/artifacts/{artifact_id}/regions",
        json={"op": "move", "indices": [0], "bbox": [0.11, 0.1, 0.4, 0.05]},
    )
    assert response.status_code == 200, response.text


def _person() -> ActionContext:
    return ActionContext(actor="historian", library_path=None, is_bootstrap=True)


def _converted_segments(db, artifact_id: str):
    return live_rows_in_order(db, converted_pass_id(artifact_id))


def _write(db, segment, *, content: str, ctx: ActionContext | None = None, **extra):
    return registry.invoke(
        db,
        "representation.create",
        {
            "document_id": segment.document_id,
            "segment_id": segment.id,
            "kind": extra.pop("kind", "transcription"),
            "content": content,
            **extra,
        },
        ctx or _person(),
    )


class TestReadingsAreWritten:
    """`source.reading.set` and `.corrections-are-new`."""

    def test_three_readings_of_one_line_coexist_and_adding_one_changes_no_other(
        self, db, client
    ):
        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        _convert(client, artifact.id)
        segment = _converted_segments(db, artifact.id)[1]

        # Conversion already wrote this line's machine reading (slice 8b), so
        # this test asserts a DELTA: three more, and nothing existing touched.
        # An absolute count would now be a count of two different things.
        from_conversion = len(db.query(ContentRepresentation, segment_id=segment.id))
        assert from_conversion == 1, "conversion should have written exactly one"

        first = _write(db, segment, content="nombre")
        second = _write(db, segment, content="nõbre", level="as_written")
        before = {
            row["id"]: db.get(ContentRepresentation, row["id"]).model_dump(mode="json")
            for row in (first.result, second.result)
        }

        third = _write(db, segment, content="nomine", language="la")

        rows = db.query(ContentRepresentation, segment_id=segment.id)
        assert len(rows) == from_conversion + 3
        for rid, snapshot in before.items():
            assert db.get(ContentRepresentation, rid).model_dump(mode="json") == snapshot
        assert db.get(ContentRepresentation, third.result["id"]).language == "la"

    def test_a_correction_names_its_target_and_leaves_its_text_alone(self, db, client):
        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        _convert(client, artifact.id)
        segment = _converted_segments(db, artifact.id)[1]

        original = _write(db, segment, content="nõbre")
        correction = _write(
            db, segment, content="nombre",
            corrects_representation_id=original.result["id"],
            level="expanded",
        )

        corrected = db.get(ContentRepresentation, correction.result["id"])
        assert corrected.corrects_representation_id == original.result["id"]
        assert corrected.level == "expanded"
        # A correction is a NEW reading. The thing it corrects is untouched.
        assert db.get(ContentRepresentation, original.result["id"]).content == "nõbre"

    def test_the_anchor_is_worked_out_from_the_segment_when_none_is_given(self, db, client):
        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        _convert(client, artifact.id)
        segment = _converted_segments(db, artifact.id)[3]

        result = _write(db, segment, content="de")

        stored = db.get(ContentRepresentation, result.result["id"])
        assert stored.source_anchor.rect == segment.anchor.rect
        assert stored.source_anchor.document_id == doc.id

    def test_the_image_it_was_read_from_is_recorded(self, db, client):
        """`source.reading.read-from`. Two people reading the same line off a
        colour scan and a microfilm are not disagreeing."""
        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        _convert(client, artifact.id)
        segment = _converted_segments(db, artifact.id)[1]

        result = _write(
            db, segment, content="nombre",
            read_from_rendition_id="rend-colour", guideline="Leiden",
        )

        stored = db.get(ContentRepresentation, result.result["id"])
        assert stored.read_from_rendition_id == "rend-colour"
        assert stored.guideline == "Leiden"

    def test_the_maker_is_the_engines_answer_not_the_callers(self, db, client):
        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        _convert(client, artifact.id)
        segment = _converted_segments(db, artifact.id)[1]

        by_person = _write(db, segment, content="nombre")
        by_agent = _write(
            db, segment, content="nomine",
            ctx=ActionContext(actor="historian", via_mcp=True, is_bootstrap=True),
        )
        by_run = _write(
            db, segment, content="nõbre",
            ctx=ActionContext(actor="runner", run_id="run-1", is_bootstrap=True),
        )

        assert db.get(ContentRepresentation, by_person.result["id"]).provenance_kind is (
            ProvenanceKind.human
        )
        assert db.get(ContentRepresentation, by_agent.result["id"]).provenance_kind is (
            ProvenanceKind.agent
        )
        assert db.get(ContentRepresentation, by_run.result["id"]).provenance_kind is (
            ProvenanceKind.workflow
        )

    def test_a_reading_names_its_author_not_only_the_kind_of_author(self, db, client):
        """`source.reading.author-and-guideline`: "a reading names its author
        (person, or model and run)".

        `provenance_kind` says a PERSON read this line. In a library two people
        transcribe in, an apparatus has to say WHICH -- and a reading exported
        to an edition carries its own record or carries nothing.
        """
        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        _convert(client, artifact.id)
        segment = _converted_segments(db, artifact.id)[1]

        by_maria = _write(
            db, segment, content="nombre",
            ctx=ActionContext(actor="maria", is_bootstrap=True), guideline="Leiden",
        )
        by_juan = _write(
            db, segment, content="nomine",
            ctx=ActionContext(actor="juan", is_bootstrap=True),
        )

        assert db.get(ContentRepresentation, by_maria.result["id"]).created_by == "maria"
        assert db.get(ContentRepresentation, by_juan.result["id"]).created_by == "juan"
        assert db.get(ContentRepresentation, by_maria.result["id"]).guideline == "Leiden"

        # And the read seam reports it, so a client can show the apparatus
        # without a second lookup per reading.
        items = client.get(f"/api/segments/{segment.id}/readings").json()["items"]
        authors = {item["created_by"] for item in items if not item["provisional"]}
        # Two people and the machine, each named. That the machine's conversion
        # reading sits beside theirs with its OWN author is the behaviour, not
        # noise: an apparatus has to say who read each way.
        assert {"maria", "juan"} <= authors
        assert "qwen" in authors, "the machine's own reading lost its author"
        # A provisional reading's author is the run that produced it -- the only
        # author that text has.
        provisional = [item for item in items if item["provisional"]]
        assert [item["created_by"] for item in provisional] == ["qwen"]

    def test_a_written_and_read_pair_is_joined_and_can_be_undone(self, db, client):
        """`source.reading.written-read-pair` -- a different relation from
        error and correction."""
        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        _convert(client, artifact.id)
        segment = _converted_segments(db, artifact.id)[1]
        written = _write(db, segment, content="quiça")
        read = _write(db, segment, content="quizá", level="normalised")

        registry.invoke(
            db, "representation.pair",
            {"written_id": written.result["id"], "read_id": read.result["id"]},
            _person(),
        )

        written_row = db.get(ContentRepresentation, written.result["id"])
        read_row = db.get(ContentRepresentation, read.result["id"])
        assert written_row.pair_id and written_row.pair_id == read_row.pair_id
        assert (written_row.pair_role, read_row.pair_role) == ("written", "read")

        registry.invoke(
            db, "representation.unpair",
            {"written_id": written.result["id"], "read_id": read.result["id"]},
            _person(),
        )
        assert db.get(ContentRepresentation, written.result["id"]).pair_id is None


class TestPerCharacterDetailRidesOnTheLine:
    """`source.reading.char-confidence-on-line`: per-character positions and
    confidence ride on a LINE's reading, without character segments existing.

    The alternative -- a segment per glyph -- is what makes a dense page
    twenty thousand rows and every read of it slow. A list of floats on the
    line says the same thing and costs nothing.
    """

    def test_a_character_can_be_pointed_at_with_no_character_segment(self, db, client):
        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        _convert(client, artifact.id)
        segment = _converted_segments(db, artifact.id)[2]
        word = "nombre"

        created = _write(db, segment, content=word)
        stored = db.get(ContentRepresentation, created.result["id"])
        db.save(
            stored.model_copy(
                update={
                    "char_confidences": [0.99, 0.98, 0.5, 0.97, 0.96, 0.95],
                    "char_positions": [i / (len(word) - 1) for i in range(len(word))],
                }
            )
        )

        read_back = db.get(ContentRepresentation, created.result["id"])
        assert len(read_back.char_confidences) == len(word)
        assert len(read_back.char_positions) == len(word)
        # The doubtful character is findable, and its place on the line is
        # known -- with NO segment of its own anywhere in the library.
        worst = read_back.char_confidences.index(min(read_back.char_confidences))
        assert word[worst] == "m"
        assert read_back.char_positions[worst] == pytest.approx(0.4)
        from fichero_server.models import Segment

        assert [
            row for row in db.all(Segment) if row.kind in {"glyph", "character"}
        ] == []


class TestRetraction:
    """The inverse of a create is a retraction, and THE ROW STAYS."""

    def test_undoing_a_create_retracts_it_and_keeps_the_row(self, db, client):
        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        _convert(client, artifact.id)
        segment = _converted_segments(db, artifact.id)[1]
        created = _write(db, segment, content="nombre")

        registry.invoke(
            db, "representation.retract",
            {"representation_id": created.result["id"]}, _person(),
        )

        stored = db.get(ContentRepresentation, created.result["id"])
        assert stored is not None, "a withdrawn reading is still part of the record"
        assert stored.retracted_at is not None
        assert stored.content == "nombre"

    def test_a_retracted_reading_stops_counting(self, db, client):
        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        _convert(client, artifact.id)
        segment = _converted_segments(db, artifact.id)[1]
        created = _write(db, segment, content="nombre")

        response = client.get(f"/api/segments/{segment.id}/readings?kind=transcription")
        assert response.json()["counting"]["transcription"]["representation_id"] == (
            created.result["id"]
        )

        registry.invoke(
            db, "representation.retract",
            {"representation_id": created.result["id"]}, _person(),
        )

        after = client.get(f"/api/segments/{segment.id}/readings?kind=transcription").json()
        # The line still HAS a reading -- the machine's, which never went
        # away -- and with the person's withdrawn it is what is shown, labelled
        # and unchosen. The withdrawn row is still listed, marked retracted.
        answer = after["counting"]["transcription"]
        assert answer["basis"] == CountingBasis.newest_machine_unchosen.value
        assert answer["labelled_machine"] is True
        assert answer["representation_id"] != created.result["id"]
        # Two recorded readings now: conversion's machine one, and the person's
        # withdrawn one. Exactly one is retracted, and it is theirs.
        recorded = {i["id"]: i["retracted"] for i in after["items"] if not i["provisional"]}
        assert recorded[created.result["id"]] is True
        assert sum(1 for r in recorded.values() if r) == 1


class TestTheAuditChainCarriesNoText:
    """"Audit payloads of every action contain no `content`." A person's
    transcription of a line belongs in the row they wrote, once."""

    def test_a_create_audits_an_id_and_a_digest_never_the_words(self, db, client):
        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        _convert(client, artifact.id)
        segment = _converted_segments(db, artifact.id)[1]
        secret = "a reading nobody should find in the audit chain"

        _write(db, segment, content=secret)

        audits = [a for a in db.all(ActionAudit) if a.action_name == "representation.create"]
        assert len(audits) == 1
        blob = audits[0].model_dump_json()
        assert secret not in blob
        assert "content_sha256" in blob
        assert "content" not in (audits[0].after or {})


class TestTheReadSeamAnswersFromBothStores:
    """`source.one-store`: the caller cannot tell which store a reading came
    from."""

    def test_an_unconverted_page_still_offers_its_lines_readings(self, db, client):
        """Asking what a line says must work BEFORE anybody has edited the
        page -- that is the whole point of a provisional reading."""
        doc = _make_doc(db)
        artifact = _artifact(db, doc)

        response = client.get(f"/api/segments/legacy:{artifact.id}:2/readings")
        assert response.status_code == 200, response.text
        items = response.json()["items"]
        assert len(items) == 1
        assert items[0]["provisional"] is True
        assert items[0]["id"] == legacy_reading_segment_id(artifact.id, 2)
        # The stretch of the ARTIFACT'S OWN text, not the whole page.
        assert items[0]["content"] == "nombre"
        assert items[0]["derived_from_artifact_id"] == artifact.id
        assert items[0]["provenance_kind"] == ProvenanceKind.workflow.value

    def test_a_converted_line_keeps_its_provisional_reading(self, db, client):
        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        _convert(client, artifact.id)
        segment = _converted_segments(db, artifact.id)[2]

        items = client.get(f"/api/segments/{segment.id}/readings").json()["items"]
        provisional = [i for i in items if i["provisional"]]
        # The provisional reading is STILL offered after conversion -- the seam
        # does not stop answering from the block just because a record exists.
        assert [i["content"] for i in provisional] == ["nombre"]
        # And conversion's own recorded reading says the same words.
        recorded = [i for i in items if not i["provisional"]]
        assert [i["content"] for i in recorded] == ["nombre"]

    def test_a_real_reading_and_a_provisional_one_stand_side_by_side(self, db, client):
        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        _convert(client, artifact.id)
        segment = _converted_segments(db, artifact.id)[1]
        _write(db, segment, content="nombre (corrected)")

        payload = client.get(f"/api/segments/{segment.id}/readings").json()
        # Three: conversion's machine reading, the person's correction, and the
        # provisional one still read out of the block.
        assert payload["count"] == 3
        assert sorted(i["provisional"] for i in payload["items"]) == [False, False, True]
        # And the counting answer rides on the same read, so no client renders
        # a machine's guess unlabelled while it fetches the answer separately.
        answer = payload["counting"]["transcription"]
        assert answer["representation_id"] is not None

    def test_a_box_with_no_character_span_falls_back_to_its_own_text(self, db, client):
        doc = _make_doc(db)
        artifact = _artifact(db, doc, spans=False)

        items = client.get(f"/api/segments/legacy:{artifact.id}:1/readings").json()["items"]
        assert [item["content"] for item in items] == ["el"]

    def test_an_artifact_that_is_not_a_reading_offers_none(self, db, client):
        """`entities` and `grouping` artifacts are outputs of a run, not
        readings of a line. Offering them as readings would be a lie."""
        doc = _make_doc(db)
        artifact = _artifact(db, doc, artifact_type="entities")

        payload = client.get(f"/api/segments/legacy:{artifact.id}:1/readings").json()
        assert payload["items"] == []
        assert payload["counting"] == {}

    def test_in_a_strict_project_the_machines_reading_is_shown_labelled_unchosen(
        self, db, client
    ):
        doc = _make_doc(db)
        artifact = _artifact(db, doc)

        answer = client.get(
            f"/api/segments/legacy:{artifact.id}:1/readings"
        ).json()["counting"]["transcription"]
        assert answer["basis"] == CountingBasis.newest_machine_unchosen.value
        assert answer["labelled_machine"] is True


class TestChoosingWhatCounts:
    """`source.reading.chosen-is-worked-out`."""

    def test_a_persons_choice_is_recorded_and_the_counting_answer_follows(self, db, client):
        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        _convert(client, artifact.id)
        segment = _converted_segments(db, artifact.id)[1]
        first = _write(db, segment, content="nombre")
        second = _write(db, segment, content="nomine")

        response = client.post(
            f"/api/segments/{segment.id}/readings/choice",
            json={"kind": "transcription", "representation_id": first.result["id"]},
        )
        assert response.status_code == 200, response.text

        answer = client.get(
            f"/api/segments/{segment.id}/readings?kind=transcription"
        ).json()["counting"]["transcription"]
        assert answer["representation_id"] == first.result["id"]
        assert answer["basis"] == CountingBasis.chosen.value
        assert second.result["id"] != answer["representation_id"]

    def test_a_later_choice_supersedes_rather_than_replacing(self, db, client):
        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        _convert(client, artifact.id)
        segment = _converted_segments(db, artifact.id)[1]
        first = _write(db, segment, content="nombre")
        second = _write(db, segment, content="nomine")

        for target in (first, second):
            registry.invoke(
                db, "reading.choose",
                {
                    "segment_id": segment.id,
                    "kind": "transcription",
                    "representation_id": target.result["id"],
                },
                _person(),
            )

        rows = db.query(ReadingChoice, segment_id=segment.id)
        assert len(rows) == 2, "a superseded choice stays readable"
        live = [row for row in rows if row.superseded_at is None]
        assert [row.representation_id for row in live] == [second.result["id"]]

    def test_unchoosing_puts_the_segment_back_to_worked_out(self, db, client):
        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        _convert(client, artifact.id)
        segment = _converted_segments(db, artifact.id)[1]
        first = _write(db, segment, content="nombre")
        _write(db, segment, content="nomine")
        registry.invoke(
            db, "reading.choose",
            {
                "segment_id": segment.id, "kind": "transcription",
                "representation_id": first.result["id"],
            },
            _person(),
        )

        registry.invoke(
            db, "reading.unchoose",
            {"segment_id": segment.id, "kind": "transcription"},
            _person(),
        )

        answer = client.get(
            f"/api/segments/{segment.id}/readings?kind=transcription"
        ).json()["counting"]["transcription"]
        # Two people's readings and nobody has chosen: strict withholds.
        assert answer["basis"] == CountingBasis.none.value

    def test_a_working_pass_is_chosen_deliberately(self, db, client):
        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        _convert(client, artifact.id)

        result = registry.invoke(
            db, "pass.choose_working",
            {"document_id": doc.id, "pass_id": converted_pass_id(artifact.id)},
            _person(),
        )
        assert result.result["pass_id"] == converted_pass_id(artifact.id)


class TestRefusals:
    """Typed, each one tested. A refusal is a 4xx, never a 500."""

    def test_a_provisional_segment_id_is_refused_on_a_write(self, db, client):
        doc = _make_doc(db)
        artifact = _artifact(db, doc)

        response = client.post(
            "/api/content-representations",
            json={
                "document_id": doc.id,
                "segment_id": f"legacy:{artifact.id}:1",
                "kind": "transcription",
                "content": "el",
            },
        )
        assert response.status_code == 422
        assert "provisional" in response.text

    def test_a_provisional_reading_id_is_refused_as_a_correction_target(self, db, client):
        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        _convert(client, artifact.id)
        segment = _converted_segments(db, artifact.id)[1]

        response = client.post(
            "/api/content-representations",
            json={
                "document_id": doc.id,
                "segment_id": segment.id,
                "kind": "transcription",
                "content": "nombre",
                "corrects_representation_id": legacy_reading_segment_id(artifact.id, 1),
            },
        )
        assert response.status_code == 422
        assert "provisional" in response.text

    def test_a_segment_on_another_document_is_refused(self, db, client):
        doc = _make_doc(db)
        other = _make_doc(db, name="other.jpg")
        artifact = _artifact(db, doc)
        _convert(client, artifact.id)
        segment = _converted_segments(db, artifact.id)[1]

        response = client.post(
            "/api/content-representations",
            json={
                "document_id": other.id,
                "segment_id": segment.id,
                "kind": "transcription",
                "content": "nombre",
            },
        )
        assert response.status_code == 422
        assert other.id in response.text or "not" in response.text

    def test_an_anchor_naming_another_document_is_refused(self, db, client):
        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        _convert(client, artifact.id)
        segment = _converted_segments(db, artifact.id)[1]

        response = client.post(
            "/api/content-representations",
            json={
                "document_id": doc.id,
                "segment_id": segment.id,
                "kind": "transcription",
                "content": "nombre",
                "source_anchor": {"document_id": "some-other-doc"},
            },
        )
        assert response.status_code == 422
        assert "anchor" in response.text

    def test_an_unknown_kind_is_refused_and_names_the_list(self, db, client):
        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        _convert(client, artifact.id)
        segment = _converted_segments(db, artifact.id)[1]

        response = client.post(
            "/api/content-representations",
            json={
                "document_id": doc.id, "segment_id": segment.id,
                "kind": "transcript", "content": "nombre",
            },
        )
        assert response.status_code == 422
        assert "transcription" in response.text

    def test_a_machine_may_not_choose_what_counts(self, db, client):
        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        _convert(client, artifact.id)
        segment = _converted_segments(db, artifact.id)[1]
        reading = _write(db, segment, content="nombre")

        from fichero_server.models.readings import ChoiceNeedsAPerson

        with pytest.raises(ChoiceNeedsAPerson):
            registry.invoke(
                db, "reading.choose",
                {
                    "segment_id": segment.id, "kind": "transcription",
                    "representation_id": reading.result["id"],
                },
                ActionContext(actor="runner", run_id="run-1", is_bootstrap=True),
            )
        with pytest.raises(ChoiceNeedsAPerson):
            registry.invoke(
                db, "reading.choose",
                {
                    "segment_id": segment.id, "kind": "transcription",
                    "representation_id": reading.result["id"],
                },
                ActionContext(actor="agent", via_mcp=True, is_bootstrap=True),
            )

    def test_pairing_two_readings_of_different_segments_is_refused(self, db, client):
        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        _convert(client, artifact.id)
        rows = _converted_segments(db, artifact.id)
        one = _write(db, rows[1], content="nombre")
        two = _write(db, rows[3], content="de")

        with pytest.raises(ValueError):
            registry.invoke(
                db, "representation.pair",
                {"written_id": one.result["id"], "read_id": two.result["id"]},
                _person(),
            )

    def test_a_body_that_names_its_own_maker_is_refused(self, db, client):
        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        _convert(client, artifact.id)
        segment = _converted_segments(db, artifact.id)[1]

        response = client.post(
            "/api/content-representations",
            json={
                "document_id": doc.id, "segment_id": segment.id,
                "kind": "transcription", "content": "nombre",
                "provenance_kind": "human",
            },
        )
        assert response.status_code == 422


class TestConversionWritesReadings:
    """Slice 8b: each converted segment's words become a READING on it (#4924).

    Spec: `build-notes-readings-cascade-orders.md`, "Slice 8b" — "With readings
    on segments (why 8 comes first)". Until this, a converted page's shapes lived
    in rows and its WORDS lived only in the artifact's kept block: one home for
    the geometry, another for the text.
    """

    def test_every_converted_line_gets_a_reading_of_its_own_words(self, db, client):
        doc = _make_doc(db)
        artifact = _artifact(db, doc)

        _convert(client, artifact.id)

        rows = _converted_segments(db, artifact.id)
        for row in rows:
            real = [
                item
                for item in readings_of_segment(db, row.id)
                if not item.provisional
            ]
            assert len(real) == 1, f"segment {row.id} has {len(real)} recorded readings"
            # The words are the box's own, taken from the SAME answer the rows
            # came from rather than re-derived.
            assert real[0].content
            assert real[0].segment_id == row.id

    def test_the_words_match_the_boxes_they_came_from(self, db, client):
        doc = _make_doc(db)
        artifact = _artifact(db, doc)

        _convert(client, artifact.id)

        for index, row in enumerate(_converted_segments(db, artifact.id)):
            real = [i for i in readings_of_segment(db, row.id) if not i.provisional]
            start, end = SPANS[index]
            assert real[0].content == PAGE_TEXT[start:end]

    def test_converting_is_not_authorship_and_the_reading_inherits_that(self, db, client):
        """`source.store.converted-boxes-keep-their-maker`, extended to the
        words: the machine wrote these, and converting them does not make them
        the person whose project happened to be open."""
        doc = _make_doc(db)
        artifact = _artifact(db, doc)

        _convert(client, artifact.id)

        for row in _converted_segments(db, artifact.id):
            real = [i for i in readings_of_segment(db, row.id) if not i.provisional]
            assert real[0].provenance_kind is row.provenance_kind
            assert real[0].provenance_kind is ProvenanceKind.workflow
            assert real[0].created_by == row.created_by == "qwen"

    def test_the_reading_names_the_artifact_it_came_from(self, db, client):
        """The one link between the two stores, pointing from the new record to
        the old output — never a copy of the words in the other direction."""
        doc = _make_doc(db)
        artifact = _artifact(db, doc)

        _convert(client, artifact.id)

        row = _converted_segments(db, artifact.id)[0]
        real = [i for i in readings_of_segment(db, row.id) if not i.provisional][0]
        assert real.derived_from_artifact_id == artifact.id
        # `producer_model` is on the stored row; `ReadingRead` deliberately does
        # not carry it, so this asserts where the field actually lives.
        assert db.get(ContentRepresentation, real.id).producer_model == "qwen-vl"

    def test_a_translation_results_boxes_become_translations_not_transcriptions(
        self, db, client
    ):
        doc = _make_doc(db)
        artifact = _artifact(db, doc, artifact_type="translation")

        _convert(client, artifact.id)

        row = _converted_segments(db, artifact.id)[0]
        real = [i for i in readings_of_segment(db, row.id) if not i.provisional][0]
        assert real.kind == "translation"

    def test_a_result_whose_type_is_not_a_reading_kind_still_gets_transcriptions(
        self, db, client
    ):
        """A PDF's own text layer arrives as `text_geometry`, which is not a kind
        of reading — but its words are still what the line says."""
        doc = _make_doc(db)
        artifact = _artifact(db, doc, artifact_type="text_geometry")

        _convert(client, artifact.id)

        row = _converted_segments(db, artifact.id)[0]
        real = [i for i in readings_of_segment(db, row.id) if not i.provisional][0]
        assert real.kind == "transcription"

    def test_an_empty_box_gets_no_reading(self, db, client):
        """An empty reading would assert that a machine read this line and found
        nothing, which is not the same as the line not having been read."""
        doc = _make_doc(db)
        artifact = Artifact(
            document_id=doc.id, artifact_type="transcription", provider="qwen",
            content="en",
            ocr_geometry=OCRGeometryResult(
                provider="qwen", text="en",
                boxes=[
                    OCRGeometryBox(text="en", bbox=[0.1, 0.1, 0.2, 0.05], level="line",
                                   char_start=0, char_end=2),
                    OCRGeometryBox(text="", bbox=[0.1, 0.3, 0.2, 0.05], level="line"),
                ],
            ),
        )
        db.save(artifact)

        _convert(client, artifact.id)

        rows = _converted_segments(db, artifact.id)
        assert [i for i in readings_of_segment(db, rows[0].id) if not i.provisional]
        assert [i for i in readings_of_segment(db, rows[1].id) if not i.provisional] == []

    def test_the_derived_page_text_now_comes_from_records_not_the_block(self, db, client):
        """The point of the whole step: a converted page's text is the join of
        readings that exist as rows, rather than of words that live only inside
        an artifact."""
        from fichero_server.api.routes.document.segment_readings import document_text

        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        _convert(client, artifact.id)

        derived = document_text(db, doc.id)

        assert derived.text == PAGE_TEXT
        assert len(derived.spans) == len(SPANS)
        # Every span names a REAL reading, not a provisional one read out of the
        # artifact.
        for span in derived.spans:
            assert span.representation_id is not None
            assert not span.representation_id.startswith("legacy-reading:")
