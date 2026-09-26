"""Source-model slice 8, part 2 (#4934, #4929) -- the truth tables of
"which reading counts" and "which pass am I working on".

Spec: `build-notes-readings-cascade-orders.md`, "Slice 8", section
`"Which counts" is worked out`. Behaviours pinned:
* `source.reading.chosen-is-worked-out`
* `source.reading.chosen-follows-project-rule`
* `source.reading.machine-is-labelled`
* `source.reading.equal-alternatives`
* `source.pass.working`
* `source.pass.working-follows-project-rule`

Both functions are PURE, so these tests need no library -- which is the point:
nothing about the answer is stored, so flipping the project rule can rewrite
nothing. The one test that DOES take the `db` fixture proves exactly that: it
flips the rule and asserts zero writes.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from fichero_server.core.timeutil import utc_now
from fichero_server.models.knowledge import ProvenanceKind
from fichero_server.models.readings import (
    CountingBasis,
    PassBasis,
    PassCandidate,
    ProjectRecordRule,
    ReadingCandidate,
    ReadingChoice,
    project_record_rule,
    resolve_counting,
    resolve_working_pass,
)

pytestmark = pytest.mark.source_model

NOW = utc_now()
STRICT = ProjectRecordRule.strict
RELAXED = ProjectRecordRule.relaxed


def _reading(
    rid: str,
    *,
    maker: ProvenanceKind = ProvenanceKind.workflow,
    age_minutes: int = 0,
    retracted: bool = False,
    provisional: bool = False,
) -> ReadingCandidate:
    return ReadingCandidate(
        representation_id=rid,
        kind="transcription",
        provenance_kind=maker,
        created_at=NOW - timedelta(minutes=age_minutes),
        retracted=retracted,
        provisional=provisional,
    )


def _choice(rid: str, *, age_minutes: int = 0, superseded: bool = False) -> ReadingChoice:
    chosen_at = NOW - timedelta(minutes=age_minutes)
    return ReadingChoice(
        document_id="doc-1",
        segment_id="seg-1",
        kind="transcription",
        representation_id=rid,
        chosen_by="historian",
        chosen_at=chosen_at,
        superseded_at=chosen_at if superseded else None,
    )


def _pass(
    pid: str,
    *,
    maker: ProvenanceKind = ProvenanceKind.workflow,
    human_segment: bool = False,
    text_layer: bool = False,
    age_minutes: int = 0,
) -> PassCandidate:
    return PassCandidate(
        pass_id=pid,
        provenance_kind=maker,
        has_human_segment=human_segment,
        from_text_layer=text_layer,
        created_at=NOW - timedelta(minutes=age_minutes),
    )


class TestNothingToCount:
    def test_no_candidate_is_none_not_a_guess(self):
        answer = resolve_counting(STRICT, [], [])
        assert answer.representation_id is None
        assert answer.basis is CountingBasis.none
        assert answer.labelled_machine is False

    def test_a_retracted_reading_stops_counting(self):
        answer = resolve_counting(STRICT, [], [_reading("rep-a", retracted=True)])
        assert answer.basis is CountingBasis.none


class TestALiveHumanChoiceWinsInAnyProject:
    """`source.reading.chosen-is-worked-out`, rule 1."""

    @pytest.mark.parametrize("rule", [STRICT, RELAXED])
    def test_a_choice_beats_a_newer_reading(self, rule):
        answer = resolve_counting(
            rule,
            [_choice("rep-old", age_minutes=30)],
            [
                _reading("rep-old", maker=ProvenanceKind.human, age_minutes=60),
                _reading("rep-new", maker=ProvenanceKind.human, age_minutes=1),
            ],
        )
        assert answer.representation_id == "rep-old"
        assert answer.basis is CountingBasis.chosen

    def test_choosing_a_machines_reading_does_not_make_it_a_persons(self):
        """`source.reading.machine-is-labelled`: a choice settles WHICH
        reading counts, never WHO wrote it."""
        answer = resolve_counting(STRICT, [_choice("rep-m")], [_reading("rep-m")])
        assert answer.basis is CountingBasis.chosen
        assert answer.labelled_machine is True

    def test_a_superseded_choice_is_history_not_a_vote(self):
        answer = resolve_counting(
            STRICT,
            [_choice("rep-a", age_minutes=30, superseded=True)],
            [_reading("rep-a"), _reading("rep-b", age_minutes=1)],
        )
        assert answer.basis is not CountingBasis.chosen

    def test_the_newest_of_two_live_choices_wins(self):
        answer = resolve_counting(
            STRICT,
            [_choice("rep-a", age_minutes=30), _choice("rep-b", age_minutes=2)],
            [_reading("rep-a"), _reading("rep-b")],
        )
        assert answer.representation_id == "rep-b"

    def test_a_choice_naming_a_retracted_reading_is_skipped_not_honoured(self):
        answer = resolve_counting(
            STRICT,
            [_choice("rep-gone", age_minutes=2), _choice("rep-here", age_minutes=30)],
            [_reading("rep-gone", retracted=True), _reading("rep-here")],
        )
        assert answer.representation_id == "rep-here"
        assert answer.basis is CountingBasis.chosen


class TestStrictProject:
    """`source.reading.chosen-follows-project-rule`: only a person chooses."""

    def test_machines_only_is_shown_labelled_and_unchosen(self):
        answer = resolve_counting(
            STRICT,
            [],
            [_reading("rep-old", age_minutes=60), _reading("rep-new", age_minutes=1)],
        )
        assert answer.representation_id == "rep-new"
        assert answer.basis is CountingBasis.newest_machine_unchosen
        assert answer.labelled_machine is True

    def test_one_persons_reading_counts_over_a_newer_machines(self):
        answer = resolve_counting(
            STRICT,
            [],
            [
                _reading("rep-h", maker=ProvenanceKind.human, age_minutes=60),
                _reading("rep-m", age_minutes=1),
            ],
        )
        assert answer.representation_id == "rep-h"
        assert answer.basis is CountingBasis.newest_human
        assert answer.labelled_machine is False

    def test_three_peoples_readings_coexist_and_nothing_counts_until_one_is_chosen(self):
        """`source.reading.equal-alternatives`. Two historians reading a line
        differently is the case this model exists to record; settling it by
        timestamp would be the machine making an editorial decision."""
        candidates = [
            _reading("rep-1", maker=ProvenanceKind.human, age_minutes=30),
            _reading("rep-2", maker=ProvenanceKind.human, age_minutes=20),
            _reading("rep-3", maker=ProvenanceKind.human, age_minutes=10),
        ]

        answer = resolve_counting(STRICT, [], candidates)
        assert answer.representation_id is None
        assert answer.basis is CountingBasis.none

        chosen = resolve_counting(STRICT, [_choice("rep-2")], candidates)
        assert chosen.representation_id == "rep-2"
        assert chosen.basis is CountingBasis.chosen

    def test_an_agent_is_not_a_person(self):
        """#4869: `agent` names the surface a write came through, not a
        verified principal. A machine acting through it is still a machine."""
        answer = resolve_counting(
            STRICT, [], [_reading("rep-a", maker=ProvenanceKind.agent)]
        )
        assert answer.basis is CountingBasis.newest_machine_unchosen
        assert answer.labelled_machine is True


class TestRelaxedProject:
    """The newest counts, and a person's outranks a machine's."""

    def test_the_newest_machine_counts_when_no_person_has_read_it(self):
        answer = resolve_counting(
            RELAXED,
            [],
            [_reading("rep-old", age_minutes=60), _reading("rep-new", age_minutes=1)],
        )
        assert answer.representation_id == "rep-new"
        assert answer.basis is CountingBasis.newest_machine_unchosen
        assert answer.labelled_machine is True

    def test_a_persons_reading_outranks_a_newer_machines(self):
        answer = resolve_counting(
            RELAXED,
            [],
            [
                _reading("rep-h", maker=ProvenanceKind.human, age_minutes=60),
                _reading("rep-m", age_minutes=1),
            ],
        )
        assert answer.representation_id == "rep-h"
        assert answer.basis is CountingBasis.newest_human

    def test_the_newest_of_several_peoples_readings_counts(self):
        """The one place relaxed and strict genuinely differ on people's
        readings: relaxed will settle a disagreement by date, strict will not."""
        candidates = [
            _reading("rep-1", maker=ProvenanceKind.human, age_minutes=30),
            _reading("rep-2", maker=ProvenanceKind.human, age_minutes=10),
        ]
        assert resolve_counting(RELAXED, [], candidates).representation_id == "rep-2"
        assert resolve_counting(STRICT, [], candidates).basis is CountingBasis.none


class TestFlippingTheRuleWritesNothing:
    """`source.reading.chosen-is-worked-out`: never a flag stored on a
    reading, so changing the project's rule rewrites nothing."""

    def test_the_answer_changes_and_no_row_is_touched(self, db):
        from fichero_server.models import ContentRepresentation
        from fichero_server.models.anchors import SourceAnchor

        rows = []
        for index, maker in enumerate((ProvenanceKind.human, ProvenanceKind.human)):
            row = ContentRepresentation(
                document_id="doc-1", kind="transcription", content=f"reading {index}",
                source_anchor=SourceAnchor(document_id="doc-1"),
                segment_id="seg-1", provenance_kind=maker,
            )
            db.save(row)
            rows.append(row)

        candidates = [
            _reading("rep-1", maker=ProvenanceKind.human, age_minutes=30),
            _reading("rep-2", maker=ProvenanceKind.human, age_minutes=10),
        ]
        before = {
            row.id: db.get(ContentRepresentation, row.id).model_dump(mode="json")
            for row in rows
        }

        strict_answer = resolve_counting(STRICT, [], candidates)
        relaxed_answer = resolve_counting(RELAXED, [], candidates)
        assert strict_answer.basis is CountingBasis.none
        assert relaxed_answer.representation_id == "rep-2"

        after = {
            row.id: db.get(ContentRepresentation, row.id).model_dump(mode="json")
            for row in rows
        }
        assert after == before
        assert db.query(ReadingChoice) == []

    def test_a_new_project_is_strict(self, db):
        assert project_record_rule(db) is ProjectRecordRule.strict


class TestTheWorkingPass:
    """`source.pass.working` / `.working-follows-project-rule`."""

    def test_no_pass_is_none(self):
        answer = resolve_working_pass(STRICT, [], [])
        assert answer.pass_id is None
        assert answer.basis is PassBasis.none

    def test_a_machine_pass_carrying_one_human_segment_outranks_a_newer_machine_pass(self):
        """THE 2026-09-03 CASE: a region somebody had drawn vanished behind a
        newer machine run. A pass's own maker is not enough to see that."""
        answer = resolve_working_pass(
            STRICT,
            [],
            [
                _pass("pass-corrected", human_segment=True, age_minutes=60),
                _pass("pass-fresh-machine", age_minutes=1),
            ],
        )
        assert answer.pass_id == "pass-corrected"
        assert answer.basis is PassBasis.human_touched

    def test_a_pass_a_person_made_ranks_the_same_way(self):
        answer = resolve_working_pass(
            STRICT,
            [],
            [
                _pass("pass-hand", maker=ProvenanceKind.human, age_minutes=60),
                _pass("pass-machine", age_minutes=1),
            ],
        )
        assert answer.pass_id == "pass-hand"
        assert answer.basis is PassBasis.human_touched

    def test_a_text_layer_pass_outranks_a_newer_machine_pass(self):
        answer = resolve_working_pass(
            STRICT,
            [],
            [
                _pass("pass-text-layer", text_layer=True, age_minutes=60),
                _pass("pass-machine", age_minutes=1),
            ],
        )
        assert answer.pass_id == "pass-text-layer"
        assert answer.basis is PassBasis.text_layer

    def test_a_human_choice_outranks_both(self):
        class _PassChoice:
            def __init__(self, pass_id: str):
                self.id = "choice-1"
                self.pass_id = pass_id
                self.chosen_at = NOW
                self.superseded_at = None

        answer = resolve_working_pass(
            STRICT,
            [_PassChoice("pass-machine")],
            [
                _pass("pass-corrected", human_segment=True, age_minutes=60),
                _pass("pass-text-layer", text_layer=True, age_minutes=30),
                _pass("pass-machine", age_minutes=1),
            ],
        )
        assert answer.pass_id == "pass-machine"
        assert answer.basis is PassBasis.chosen

    def test_untouched_machine_passes_fall_back_to_the_newest(self):
        strict = resolve_working_pass(
            STRICT, [], [_pass("pass-old", age_minutes=60), _pass("pass-new", age_minutes=1)]
        )
        assert strict.pass_id == "pass-new"
        assert strict.basis is PassBasis.newest_machine_unchosen

        relaxed = resolve_working_pass(
            RELAXED, [], [_pass("pass-old", age_minutes=60), _pass("pass-new", age_minutes=1)]
        )
        assert relaxed.pass_id == "pass-new"
        assert relaxed.basis is PassBasis.newest

    def test_showing_a_pass_says_nothing_about_who_made_its_parts(self):
        """The two questions are two functions. A curated pass winning does
        NOT make the machine readings inside it a person's."""
        pass_answer = resolve_working_pass(
            STRICT, [], [_pass("pass-mixed", human_segment=True)]
        )
        assert pass_answer.basis is PassBasis.human_touched

        reading_answer = resolve_counting(STRICT, [], [_reading("rep-machine")])
        assert reading_answer.basis is CountingBasis.newest_machine_unchosen
        assert reading_answer.labelled_machine is True


class TestDeterminism:
    def test_readings_saved_in_the_same_moment_resolve_the_same_way_every_time(self):
        """Two readings can share a timestamp to the microsecond. The answer
        must not depend on the order the database handed the rows back."""
        one = _reading("rep-a")
        two = _reading("rep-b")
        forwards = resolve_counting(STRICT, [], [one, two]).representation_id
        backwards = resolve_counting(STRICT, [], [two, one]).representation_id
        assert forwards == backwards == "rep-b"
