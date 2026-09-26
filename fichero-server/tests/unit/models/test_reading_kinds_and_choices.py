"""Source-model slice 8, part 1 (#4934, #4929) -- a reading IS the
representation record, grown; and the kinds list is OPEN.

Spec: `build-notes-readings-cascade-orders.md`, "Slice 8 -- readings on
segments, and 'which counts' worked out", sections "A reading IS this record,
grown", "`kind` opens" and "The revision's `reviewer` default is the same
defect as machine claims stored as human".

Behaviours pinned here:
* `source.reading.kinds` -- an unknown kind is refused with the list named; a
  project-added kind round-trips; a row stored under a kind since withdrawn
  still reads.
* `source.reading.level-recorded` -- `level` is stored and NEVER inferred.
* `source.reading.maker-set-by-engine` -- the maker comes from how the write
  arrived (#4868, #4869), not from what the body claimed.
* "Old library: existing representations read unchanged with every new field
  empty."

Asserted on real rows through the real `db` fixture and the real action
registry, never on the source of the models: a field that exists in the class
but never survives a DuckDB round-trip is not a stored field.
"""

from __future__ import annotations

import pytest

from fichero_server.actions.registry import ActionContext, registry
from fichero_server.models import (
    ContentRepresentation,
    ContentRepresentationKind,
    ContentRepresentationRevision,
    LibraryReadingKind,
    ReadingChoice,
)
from fichero_server.models.anchors import SourceAnchor
from fichero_server.models.knowledge import ProvenanceKind
from fichero_server.models.readings import (
    BUILTIN_READING_KINDS,
    UnknownReadingKind,
    artifact_id_for_provisional_reading,
    assert_known_reading_kind,
    legacy_reading_id,
    reading_kinds,
)
from fichero_server.models.segments import (
    ProvisionalSegmentIdError,
    assert_not_provisional,
)
import fichero_server.api.routes.document.content_representations  # noqa: F401

pytestmark = pytest.mark.source_model


def _reading(db, **kwargs) -> ContentRepresentation:
    row = ContentRepresentation(
        document_id=kwargs.pop("document_id", "doc-1"),
        kind=kwargs.pop("kind", "transcription"),
        content=kwargs.pop("content", "en el nombre de dios"),
        source_anchor=kwargs.pop("source_anchor", SourceAnchor(document_id="doc-1")),
        **kwargs,
    )
    db.save(row)
    return row


class TestTheKindsListIsOpen:
    """`source.reading.kinds`."""

    def test_opening_a_library_seeds_the_shipped_kinds(self, db):
        allowed = reading_kinds(db)
        for key, _label in BUILTIN_READING_KINDS:
            assert key in allowed, f"{key} was not seeded"
        # The seven that were the closed enum are all still there, so no
        # stored row changed meaning.
        for member in ContentRepresentationKind:
            assert member.value in allowed

    def test_seeding_twice_adds_nothing_and_keeps_a_relabelled_kind(self, db):
        rows = db.query(LibraryReadingKind, key="markdown")
        assert len(rows) == 1
        relabelled = rows[0].model_copy(update={"label": "Markdown (project)"})
        db.save(relabelled)

        db._seed_builtin_reading_kinds()

        rows = db.query(LibraryReadingKind, key="markdown")
        assert len(rows) == 1
        assert rows[0].label == "Markdown (project)"

    def test_an_unknown_kind_is_refused_and_the_list_is_named(self, db):
        with pytest.raises(UnknownReadingKind) as excinfo:
            assert_known_reading_kind(db, "transcript")
        message = str(excinfo.value)
        assert "transcript" in message
        # Naming the list is the behaviour: a caller should not have to read
        # the source to learn what it may send.
        assert "transcription" in message
        assert "coordinate" in message

    def test_a_project_added_kind_round_trips(self, db):
        db.save(LibraryReadingKind(key="shorthand", label="Shorthand", builtin=False))

        assert_known_reading_kind(db, "shorthand")
        row = _reading(db, kind="shorthand", content="pitman")
        assert db.get(ContentRepresentation, row.id).kind == "shorthand"

    def test_a_row_under_a_withdrawn_kind_still_reads(self, db):
        db.save(LibraryReadingKind(key="shorthand", label="Shorthand", builtin=False))
        row = _reading(db, kind="shorthand", content="pitman")

        for withdrawn in db.query(LibraryReadingKind, key="shorthand"):
            db.delete(withdrawn)
        assert "shorthand" not in reading_kinds(db)

        # The READ never checks the vocabulary. Refusing to read a row because
        # a project tidied its list would lose the text.
        assert db.get(ContentRepresentation, row.id).content == "pitman"
        with pytest.raises(UnknownReadingKind):
            assert_known_reading_kind(db, "shorthand")


class TestTheGrownRecord:
    """"A reading IS this record, grown. No second record.\""""

    def test_a_row_written_before_this_slice_reads_with_every_new_field_empty(self, db):
        row = _reading(db)

        stored = db.get(ContentRepresentation, row.id)
        assert stored.content == "en el nombre de dios"
        for field in (
            "segment_id", "level", "read_from_rendition_id", "guideline",
            "provenance_kind", "machine_confidence", "char_confidences",
            "char_positions", "corrects_representation_id",
            "derived_from_artifact_id", "pair_id", "pair_role", "campaign_ids",
            "sign_map", "retracted_at",
        ):
            assert getattr(stored, field) is None, f"{field} was invented on read"

    def test_every_new_field_survives_a_round_trip(self, db):
        row = _reading(
            db,
            segment_id="seg-1",
            level="expanded",
            read_from_rendition_id="rend-colour",
            guideline="Leiden",
            provenance_kind=ProvenanceKind.workflow,
            machine_confidence=0.87,
            char_confidences=[0.9, 0.8, 0.7],
            char_positions=[0.0, 0.5, 1.0],
            corrects_representation_id="rep-older",
            derived_from_artifact_id="art-1",
            pair_id="pair-1",
            pair_role="written",
            campaign_ids=["camp-1"],
            sign_map={"3": "abbreviation"},
        )

        stored = db.get(ContentRepresentation, row.id)
        assert stored.segment_id == "seg-1"
        assert stored.level == "expanded"
        assert stored.read_from_rendition_id == "rend-colour"
        assert stored.guideline == "Leiden"
        assert stored.provenance_kind == ProvenanceKind.workflow
        assert stored.machine_confidence == pytest.approx(0.87)
        assert stored.char_confidences == [0.9, 0.8, 0.7]
        assert stored.char_positions == [0.0, 0.5, 1.0]
        assert stored.corrects_representation_id == "rep-older"
        assert stored.derived_from_artifact_id == "art-1"
        assert (stored.pair_id, stored.pair_role) == ("pair-1", "written")
        assert stored.campaign_ids == ["camp-1"]
        assert stored.sign_map == {"3": "abbreviation"}

    def test_level_is_never_inferred(self, db):
        """`source.reading.level-recorded`. A transcription with no level is
        NOT "probably as written": that guess is how an edition loses the
        distinction it was made to record."""
        row = _reading(db, content="en el nõbre")

        assert db.get(ContentRepresentation, row.id).level is None


class TestTheMakerIsSetByTheEngine:
    """`source.reading.maker-set-by-engine` (#4868, #4869)."""

    def test_a_revision_through_the_mcp_surface_is_recorded_agent(self, db):
        representation = _reading(db)

        result = registry.invoke(
            db,
            "representation.revise",
            {"representation_id": representation.id, "content": "correction"},
            ActionContext(actor="historian", via_mcp=True),
        )

        revision = db.get(ContentRepresentationRevision, result.result["id"])
        assert revision.provenance_kind == ProvenanceKind.agent
        # `reviewer` still records WHO; it no longer decides WHAT KIND.
        assert revision.reviewer == "historian"

    def test_a_revision_by_a_person_is_recorded_human(self, db):
        representation = _reading(db)

        result = registry.invoke(
            db,
            "representation.revise",
            {"representation_id": representation.id, "content": "correction"},
            ActionContext(actor="historian"),
        )

        revision = db.get(ContentRepresentationRevision, result.result["id"])
        assert revision.provenance_kind == ProvenanceKind.human

    def test_a_workflow_revision_is_recorded_workflow_not_human(self, db):
        """The old `reviewer: str = "human"` default recorded a machine as a
        person by doing nothing at all -- the same defect as #4869's claims."""
        representation = _reading(db)

        result = registry.invoke(
            db,
            "representation.revise",
            {"representation_id": representation.id, "content": "machine pass"},
            ActionContext(actor="workflow-runner", run_id="run-1"),
        )

        revision = db.get(ContentRepresentationRevision, result.result["id"])
        assert revision.provenance_kind == ProvenanceKind.workflow

    def test_a_body_claiming_its_own_maker_is_refused(self, db):
        """`extra="forbid"` on the params model is what makes "engine-set"
        true rather than merely intended."""
        representation = _reading(db)

        with pytest.raises(Exception) as excinfo:
            registry.invoke(
                db,
                "representation.revise",
                {
                    "representation_id": representation.id,
                    "content": "correction",
                    "provenance_kind": "human",
                },
                ActionContext(actor="historian", via_mcp=True),
            )
        assert "provenance_kind" in str(excinfo.value)


class TestProvisionalReadingIdsAreRefusedOnWrites:
    """`source.seam.provisional-ids-refused`, extended to readings."""

    def test_a_provisional_reading_id_is_refused_like_a_provisional_segment_id(self):
        provisional = legacy_reading_id("art-1")
        assert provisional == "legacy-reading:art-1"

        with pytest.raises(ProvisionalSegmentIdError):
            assert_not_provisional(provisional, what="representation_id")
        # And the older prefix still is, so widening the rule broke nothing.
        with pytest.raises(ProvisionalSegmentIdError):
            assert_not_provisional("legacy:art-1:3", what="segment_id")

    def test_a_real_id_is_not_mistaken_for_a_provisional_one(self):
        assert_not_provisional("legacy_notes_import", what="representation_id")
        assert artifact_id_for_provisional_reading("legacy_notes_import") is None

    def test_the_artifact_behind_a_provisional_reading_is_recoverable(self):
        assert artifact_id_for_provisional_reading("legacy-reading:art-1") == "art-1"
        assert artifact_id_for_provisional_reading("legacy-reading:art-1:7") == "art-1"


class TestTheChoiceRecord:
    """The shape slice 6's `SegmentPassChoice` set, for readings."""

    def test_a_choice_persists_and_a_later_one_supersedes_rather_than_deletes(self, db):
        first = ReadingChoice(
            document_id="doc-1", segment_id="seg-1", kind="transcription",
            representation_id="rep-a", chosen_by="historian",
        )
        db.save(first)
        db.save(first.model_copy(update={"superseded_at": first.chosen_at}))
        db.save(
            ReadingChoice(
                document_id="doc-1", segment_id="seg-1", kind="transcription",
                representation_id="rep-b", chosen_by="historian",
            )
        )

        rows = db.query(ReadingChoice, segment_id="seg-1")
        assert len(rows) == 2, "a superseded choice must stay readable"
        live = [row for row in rows if row.superseded_at is None]
        assert [row.representation_id for row in live] == ["rep-b"]
