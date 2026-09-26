"""Source-model slice 8 — readings on segments, and "which counts" worked
out (spec: ``build-notes-readings-cascade-orders.md``, "Slice 8 — readings on
segments, and 'which counts' worked out"; #4934, #4929, #4932).

WHAT THIS MODULE IS FOR, and why it is not a second store. A reading is a
``ContentRepresentation`` -- the record that already exists in
``models/__init__.py`` -- grown by a handful of optional fields. Nothing here
introduces a rival record for "the text of this line". What lives here is
everything AROUND that record which does not belong on it:

* the **open kinds list** (`source.reading.kinds`): ``kind`` was a closed
  Python enum, so a project could not add "coordinate" or "music" without a
  code change. It becomes a string checked against a per-library vocabulary
  table, following the pattern ``LibraryEntityType`` already set.
* the **choice** a person makes about which reading counts
  (`source.reading.chosen-is-worked-out`) -- ``ReadingChoice``, shaped
  deliberately like slice 6's ``SegmentPassChoice`` because the two are read
  together.
* the **typed refusals** the readings routes owe their callers.

Sits below ``fichero_server.models`` the same way ``anchors.py`` and
``segments.py`` do: it imports ``segments`` (for the provisional-id rule) and
is imported BY ``models/__init__.py``, never the other way round.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from fichero_server.core.timeutil import utc_now
from fichero_server.models.knowledge import ProvenanceKind
from fichero_server.models.segments import LEGACY_READING_ID_PREFIX


def _new_id() -> str:
    """Same minting as every other model (see ``segments.py``)."""
    return uuid.uuid4().hex


# ---------------------------------------------------------------------------
# The kinds list, opened (`source.reading.kinds`)
# ---------------------------------------------------------------------------

#: The kinds that ship. The first seven are EXACTLY what the closed
#: ``ContentRepresentationKind`` enum held, so no stored row changes meaning;
#: the last five are the design's additions (a reading read aloud, a
#: description of a picture, a coordinate written on a map, music, a drawing).
#:
#: "as written / expanded / normalised" are deliberately NOT here: they are
#: ``level``s of a transcription, not kinds of reading, and conflating the two
#: is what made the old enum look closed-by-necessity.
BUILTIN_READING_KINDS: tuple[tuple[str, str], ...] = (
    ("transcription", "Transcription"),
    ("normalized_text", "Normalized text"),
    ("translation", "Translation"),
    ("transliteration", "Transliteration"),
    ("markdown", "Markdown"),
    ("html", "HTML"),
    ("svg", "SVG"),
    ("as_read_aloud", "As read aloud"),
    ("description", "Description"),
    ("coordinate", "Coordinate"),
    ("music", "Music"),
    ("drawing", "Drawing"),
)

#: The levels that ship (`source.reading.level-recorded`). An OPEN list, and
#: unlike ``kind`` it is NOT checked against a table: a level is never
#: inferred, so an unrecognised one is the project's business, and a reading
#: with no level reads back as none rather than as ``as_written``.
BUILTIN_READING_LEVELS: tuple[str, ...] = ("as_written", "expanded", "normalised")


class LibraryReadingKind(BaseModel):
    """One kind of reading this library allows. Table ``libraryreadingkinds``.

    Seeded idempotently when a library opens (``Database.
    _seed_builtin_reading_kinds``) with :data:`BUILTIN_READING_KINDS`.

    ponytail: seeded through the same ``query``/``save`` pattern
    ``_seed_builtin_node_classes`` uses rather than raw SQL in
    ``db/migrations/schema.py`` as the build notes suggested -- the table is a
    pydantic model, so ``_ensure_table`` already creates it at open, and a
    hand-written ``CREATE TABLE`` beside it would be a SECOND definition of
    one table: the exact duplication this programme exists to remove. If a
    library ever needs the table before any model is registered, that is when
    the schema.py function earns its place.
    """

    model_config = {"from_attributes": True}

    id: str = Field(default_factory=_new_id)
    #: The value stored in ``ContentRepresentation.kind``.
    key: str
    label: str
    #: True for the shipped twelve; False for a kind a project added. A
    #: builtin is never deleted, so a library that drops a project kind still
    #: reads every row it ever wrote.
    builtin: bool = False
    created_at: datetime = Field(default_factory=utc_now)


class UnknownReadingKind(ValueError):
    """Raised when a write names a kind this library does not have.

    Names the allowed list in the message: a caller that guessed "transcript"
    instead of "transcription" should not have to read the source to find
    out, and a project that MEANT to add a kind is told plainly that adding it
    is a thing it can do.
    """

    def __init__(self, kind: str, allowed: list[str]) -> None:
        self.kind = kind
        self.allowed = allowed
        super().__init__(
            f"unknown reading kind {kind!r}; this library allows: "
            + ", ".join(sorted(allowed))
        )


def reading_kinds(db: Any) -> list[str]:
    """Every kind key this library allows.

    Reads the table, never :data:`BUILTIN_READING_KINDS` -- a project's added
    kinds are as real as the shipped ones, and a reader that fell back to the
    constant would silently refuse them. Falls back to the shipped keys ONLY
    when the table is empty (a library opened by code older than the seed),
    so a read never refuses everything because a seed did not run.
    """
    rows = db.query(LibraryReadingKind)
    keys = [row.key for row in rows if row.key]
    if keys:
        return keys
    return [key for key, _label in BUILTIN_READING_KINDS]


def assert_known_reading_kind(db: Any, kind: str) -> None:
    """Refuse a kind outside this library's vocabulary.

    `source.reading.kinds`. Called on every write; never on a read, because a
    row stored under a kind since removed from the vocabulary must still read
    back (the test for that is the point of opening the list at all).
    """
    allowed = reading_kinds(db)
    if kind not in allowed:
        raise UnknownReadingKind(kind, allowed)


# ---------------------------------------------------------------------------
# Provisional readings (the read seam; `source.seam.provisional-ids-refused`)
# ---------------------------------------------------------------------------


def legacy_reading_id(artifact_id: str) -> str:
    """The provisional id of the reading that still lives in an artifact.

    Readings are where segments were before slice 1: every transcription and
    translation the engine makes today is an ``Artifact`` row, and nothing in
    the engine has ever created a ``ContentRepresentation``. So the readings
    call answers from BOTH stores and the caller cannot tell which it got --
    and a provisional id, like a provisional segment id, is refused on every
    write, because it names a run's output, not a record somebody can correct
    in place.
    """
    return f"{LEGACY_READING_ID_PREFIX}{artifact_id}"


def legacy_reading_segment_id(artifact_id: str, box_index: int) -> str:
    """The provisional id of one line's stretch of an artifact's text."""
    return f"{LEGACY_READING_ID_PREFIX}{artifact_id}:{box_index}"


def artifact_id_for_provisional_reading(reading_id: str) -> str | None:
    """The artifact behind a provisional reading id, or None if not one."""
    if not reading_id.startswith(LEGACY_READING_ID_PREFIX):
        return None
    rest = reading_id[len(LEGACY_READING_ID_PREFIX) :]
    return rest.split(":", 1)[0] or None


# ---------------------------------------------------------------------------
# "Which counts" — the record of a person's choice
# ---------------------------------------------------------------------------


class ReadingChoice(BaseModel):
    """"This is the reading that counts" -- a person's choice, recorded.

    Table ``readingchoices``. The SAME shape as slice 6's
    ``SegmentPassChoice``, on purpose: rows are never deleted, and a later
    choice supersedes an earlier one by stamping ``superseded_at``, so the
    history of what a historian decided stays readable.

    One choice is per (segment, kind): choosing which translation counts says
    nothing about which transcription does.

    NOTHING ELSE about counting is stored. The project rule, the dates and
    the makers are all read at the moment the question is asked
    (:func:`resolve_counting`), so flipping a project from strict to relaxed
    rewrites no row -- which is the test that proves it.
    """

    model_config = {"from_attributes": True}

    id: str = Field(default_factory=_new_id)
    document_id: str
    segment_id: str
    #: Which kind of reading this choice is about.
    kind: str
    representation_id: str
    #: Who chose it. A choice is always a person's -- see
    #: :class:`ChoiceNeedsAPerson`.
    chosen_by: str | None = None
    chosen_at: datetime = Field(default_factory=utc_now)
    #: Set when a later choice replaces this one. Never deleted.
    superseded_at: datetime | None = None


class ReadingAnchorMismatch(ValueError):
    """Raised when a reading's anchor cannot belong to its segment.

    A reading may carry its own anchor (a stretch of a line, a word inside
    it); it may not carry one that points at a different document or a
    different page than the segment it reads, because then two records
    disagree about where one piece of text is.
    """

    def __init__(self, representation_id: str | None, reason: str) -> None:
        self.reason = reason
        named = representation_id or "reading"
        super().__init__(f"{named}: anchor does not match its segment ({reason})")


class ChoiceNeedsAPerson(ValueError):
    """Raised when something other than a person tries to choose a reading.

    `source.reading.chosen-is-worked-out`: a machine produces candidates, it
    does not decide which one the record is. A workflow or an agent asking to
    choose is a bug in the caller, not a policy to soften -- the machine's
    answer is already shown, labelled, under the strict rule.
    """

    def __init__(self, what: str, provenance_kind: str) -> None:
        self.provenance_kind = provenance_kind
        super().__init__(
            f"{what} may only be chosen by a person; this call arrived as "
            f"{provenance_kind!r}"
        )


# ---------------------------------------------------------------------------
# "Which counts", worked out — never a stored flag
# ---------------------------------------------------------------------------
#
# TWO QUESTIONS, TWO FUNCTIONS, and they must not be folded into one:
#
#   "which READING of this line counts?"  -> resolve_counting
#   "which PASS is the person working on?" -> resolve_working_pass
#
# Showing a pass says NOTHING about who made its parts
# (`source.reading.machine-is-labelled`). A curated pass on top does not make
# its machine-made segments or readings a person's: each still carries its own
# `provenance_kind`, and in a strict project each machine reading is still
# reported unchosen until a person chooses it. One function answering both
# questions would lose exactly that distinction, which is why there are two.
#
# NOTHING about either answer is stored except a person's choices, so flipping
# a project from strict to relaxed rewrites no row. The test that asserts zero
# writes across a flip is the one that proves this design, not a comment.


class ProjectRecordRule(str, Enum):
    """How a project decides what the record is.

    `source.reading.chosen-follows-project-rule`. A NEW PROJECT IS STRICT: the
    cautious answer is the safe default for an edition, and a project that
    wants the newest machine pass to count says so deliberately.
    """

    #: Only a person chooses what counts. A machine's reading is shown,
    #: labelled, and is not the record.
    strict = "strict"
    #: The newest counts, and a person's outranks a machine's.
    relaxed = "relaxed"


class CountingBasis(str, Enum):
    """WHY a reading was returned -- the part a caller must show.

    A caller that only reads ``representation_id`` and drops the basis turns
    "a machine guessed this, nobody has checked it" into "this is the text",
    which is the single worst thing this programme could ship.
    """

    #: A person chose it, and that choice stands.
    chosen = "chosen"
    #: Nobody chose; this is the newest reading a person made.
    newest_human = "newest-human"
    #: Nobody chose; this is the newest reading and a machine made it. In a
    #: strict project it is SHOWN, LABELLED, and is not the record.
    newest_machine_unchosen = "newest-machine-unchosen"
    #: Nothing counts. Either there is no reading at all, or -- in a strict
    #: project -- people have recorded readings that disagree, and a date is
    #: not an argument for preferring one historian over another
    #: (`source.reading.equal-alternatives`).
    none = "none"


class ReadingCandidate(BaseModel):
    """One reading offered to :func:`resolve_counting`.

    A flat, store-agnostic shape ON PURPOSE: a candidate is either a real
    ``ContentRepresentation`` row or a provisional reading still living in an
    ``Artifact``, and the counting rule must not be able to tell, or it would
    quietly prefer one store over the other.
    """

    representation_id: str
    kind: str
    #: Who made it. Only ``human`` is a person: ``agent`` is a surface, not a
    #: principal (#4869), and a machine acting through an agent surface is
    #: still a machine.
    provenance_kind: ProvenanceKind
    created_at: datetime
    #: Withdrawn by ``representation.retract``. The row stays; it stops
    #: counting.
    retracted: bool = False
    #: True for a `legacy-reading:` candidate read out of an artifact.
    provisional: bool = False

    @property
    def by_a_person(self) -> bool:
        return self.provenance_kind is ProvenanceKind.human


class CountingAnswer(BaseModel):
    """Which reading counts, and why."""

    representation_id: str | None = None
    basis: CountingBasis = CountingBasis.none
    #: True whenever the reading returned was made by a machine -- including
    #: when a person CHOSE a machine's reading, because choosing it does not
    #: make a person its author (`source.reading.machine-is-labelled`).
    labelled_machine: bool = False


def _newest_first(rows: list[ReadingCandidate]) -> list[ReadingCandidate]:
    """Newest first, ties broken by id so the answer is deterministic.

    Two readings saved in the same transaction share a timestamp to the
    microsecond often enough that "whichever the database handed back first"
    would make this function's answer depend on row order. It must not.
    """
    return sorted(rows, key=lambda row: (row.created_at, row.representation_id), reverse=True)


def resolve_counting(
    project_rule: ProjectRecordRule,
    choices: list[ReadingChoice],
    candidates: list[ReadingCandidate],
) -> CountingAnswer:
    """Which reading of one kind counts (`source.reading.chosen-is-worked-out`).

    PURE: it reads its three arguments and nothing else -- no database, no
    clock, no settings. That is what makes "changing the project's rule
    rewrites nothing" true rather than aspirational, and it is why the truth
    table can be tested without a library at all.

    The rule, in order:

    1. **A live human choice wins, in any project.** A superseded choice does
       not; a choice naming a reading that has since been retracted, or that
       is not among the candidates, does not either -- it is skipped, not
       honoured, because pointing at something withdrawn is not a decision.
    2. **Relaxed project, no choice:** the newest counts, and a person's
       outranks a machine's however new the machine's is.
    3. **Strict project, no choice:** only a person chooses what counts. With
       ONE person's reading and no other, that reading is the answer. With
       SEVERAL people's readings the answer is ``none``
       (`source.reading.equal-alternatives`): two historians reading a line
       differently is the case this whole model exists to record, and settling
       it by timestamp would be the machine making an editorial decision.
       With only machines' readings the newest is returned, labelled, with
       basis ``newest-machine-unchosen`` -- shown, not the record.

    READING OF THE SPEC, stated because two sentences of the build notes pull
    against each other: "the newest reading is returned with basis
    newest-machine-unchosen (or newest-human)" and, for
    `.equal-alternatives`, "the counting answer is `none` until one is
    chosen". They reconcile only if a strict project withholds an answer when
    PEOPLE disagree, which is also the only reading under which "in a strict
    project only a person chooses the reading that counts" means anything.
    That is what is built.
    """
    live_choices = _newest_choices(choices)
    usable = [row for row in candidates if not row.retracted]
    if not usable:
        return CountingAnswer()

    by_id = {row.representation_id: row for row in usable}
    for choice in live_choices:
        chosen = by_id.get(choice.representation_id)
        if chosen is not None:
            return CountingAnswer(
                representation_id=chosen.representation_id,
                basis=CountingBasis.chosen,
                labelled_machine=not chosen.by_a_person,
            )

    people = _newest_first([row for row in usable if row.by_a_person])
    machines = _newest_first([row for row in usable if not row.by_a_person])

    if project_rule is ProjectRecordRule.relaxed:
        if people:
            return CountingAnswer(
                representation_id=people[0].representation_id,
                basis=CountingBasis.newest_human,
            )
        return CountingAnswer(
            representation_id=machines[0].representation_id,
            basis=CountingBasis.newest_machine_unchosen,
            labelled_machine=True,
        )

    if len(people) > 1:
        return CountingAnswer()
    if people:
        return CountingAnswer(
            representation_id=people[0].representation_id,
            basis=CountingBasis.newest_human,
        )
    return CountingAnswer(
        representation_id=machines[0].representation_id,
        basis=CountingBasis.newest_machine_unchosen,
        labelled_machine=True,
    )


def _newest_choices(choices: list[ReadingChoice]) -> list[ReadingChoice]:
    """Live choices, newest first. A superseded row is history, not a vote."""
    live = [row for row in choices if row.superseded_at is None]
    return sorted(live, key=lambda row: (row.chosen_at, row.id), reverse=True)


# ---------------------------------------------------------------------------
# Which pass the person is working on
# ---------------------------------------------------------------------------


class PassBasis(str, Enum):
    """WHY a pass was returned."""

    #: A person chose it.
    chosen = "chosen"
    #: Nobody chose; a person made this pass, or drew at least one segment in
    #: it. THE 2026-09-03 CASE: this is what stops a newer machine run hiding
    #: a region somebody drew by hand.
    human_touched = "human-touched"
    #: Nobody chose and nobody has touched any pass; this one came from the
    #: file's own text layer, which is at least the author's own words.
    text_layer = "text-layer"
    #: Nobody chose; this is simply the newest, and a machine made it. Strict
    #: project: shown, labelled unchosen, never the record.
    newest_machine_unchosen = "newest-machine-unchosen"
    #: Relaxed project: the newest machine pass counts outright.
    newest = "newest"
    #: There is no pass.
    none = "none"


class PassCandidate(BaseModel):
    """One pass offered to :func:`resolve_working_pass`.

    ``has_human_segment`` IS THE WHOLE POINT of this shape. A pass's own maker
    is not enough: a machine run that a historian then corrected by hand is,
    in every way that matters to the person looking at it, theirs. The caller
    must therefore work out "does any segment of this pass carry
    ``provenance_kind=human``" and pass it in; this function never reads a
    pass's maker alone, and it cannot, because it has nothing else to read.
    """

    pass_id: str
    provenance_kind: ProvenanceKind
    #: True when ANY segment in this pass was made by a person.
    has_human_segment: bool = False
    #: True when this pass was read out of the file's own embedded text layer
    #: rather than produced by a recogniser.
    from_text_layer: bool = False
    created_at: datetime

    @property
    def touched_by_a_person(self) -> bool:
        return self.provenance_kind is ProvenanceKind.human or self.has_human_segment


class PassAnswer(BaseModel):
    """Which pass is the working one, and why."""

    pass_id: str | None = None
    basis: PassBasis = PassBasis.none


def resolve_working_pass(
    project_rule: ProjectRecordRule,
    pass_choices: list[Any],
    passes_with_makers: list[PassCandidate],
) -> PassAnswer:
    """Which pass the Reader, search and export use (`source.pass.working`).

    PURE, like :func:`resolve_counting`, and deliberately NOT the same
    function: this ranking is the APP'S EXISTING ONE, ruled 2026-09-03 after a
    region somebody had drawn vanished behind a newer machine run. Working it
    out in the engine means the app's ranking can read this answer and delete
    its own copy, so the two can no longer disagree about which pass is shown.

    The order: a live human choice; then a pass a person made or touched; then
    a pass from the file's own text layer; then the newest.

    The project rule does NOT withhold a pass -- the Reader has to show
    something -- it decides what the answer MEANS. In a strict project the
    ranked machine pass comes back as ``newest-machine-unchosen``: shown,
    labelled, not the record until a person makes it so
    (`source.pass.working-follows-project-rule`). In a relaxed project the
    same pass comes back as ``newest`` and counts.

    ``pass_choices`` takes ``SegmentPassChoice`` rows (slice 6 already writes
    them); typed loosely to keep this module below the one that defines them.
    """
    if not passes_with_makers:
        return PassAnswer()

    live = [row for row in pass_choices if getattr(row, "superseded_at", None) is None]
    live.sort(key=lambda row: (row.chosen_at, row.id), reverse=True)
    by_id = {row.pass_id: row for row in passes_with_makers}
    for choice in live:
        if choice.pass_id in by_id:
            return PassAnswer(pass_id=choice.pass_id, basis=PassBasis.chosen)

    def newest(rows: list[PassCandidate]) -> PassCandidate:
        return sorted(rows, key=lambda row: (row.created_at, row.pass_id), reverse=True)[0]

    touched = [row for row in passes_with_makers if row.touched_by_a_person]
    if touched:
        return PassAnswer(pass_id=newest(touched).pass_id, basis=PassBasis.human_touched)

    text_layer = [row for row in passes_with_makers if row.from_text_layer]
    if text_layer:
        return PassAnswer(pass_id=newest(text_layer).pass_id, basis=PassBasis.text_layer)

    winner = newest(passes_with_makers)
    if project_rule is ProjectRecordRule.relaxed:
        return PassAnswer(pass_id=winner.pass_id, basis=PassBasis.newest)
    return PassAnswer(pass_id=winner.pass_id, basis=PassBasis.newest_machine_unchosen)


def project_record_rule(db: Any) -> ProjectRecordRule:
    """This project's rule for what the record is.

    ONE call, so that when project settings gain a real home (slice 9 and the
    projects work) exactly one function changes and every caller follows. Until
    then it answers ``strict`` -- `source.reading.chosen-follows-project-rule`
    says a new project is strict, and answering the cautious thing before the
    setting exists is the honest default, not a placeholder to be sorry about.

    ponytail: returns a constant. When project settings arrive this reads
    them; the signature already takes the database so no caller changes.
    """
    return ProjectRecordRule.strict


# ---------------------------------------------------------------------------
# A stretch of a reading (`source.reading.stretch-names-its-reading`)
# ---------------------------------------------------------------------------


class PlacedStretch(BaseModel):
    """Where a stretch of text sits after the reading beneath it changed."""

    representation_id: str | None = None
    char_start: int | None = None
    char_end: int | None = None
    placed: bool = False
    #: Why it could not be placed, in words a person can act on. None when it
    #: was placed.
    reason: str | None = None


def replace_stretch(
    *,
    old_text: str,
    char_start: int,
    char_end: int,
    new_text: str,
    new_representation_id: str,
) -> PlacedStretch:
    """Carry a stretch over to a new reading of the same line, or report it
    unplaced.

    NEVER RE-MEASURED BY POSITION ALONE, and this is the whole behaviour. A
    mark on characters 12 to 18 of one transcription lands on entirely
    different words in a transcription that expanded three abbreviations
    earlier in the line; keeping the offsets would silently move somebody's
    annotation onto text they never read. So the CHARACTERS are matched, and
    only when they occur EXACTLY ONCE: twice is ambiguous, and choosing the
    first would be a guess dressed as an answer.

    An unplaced pointer is REPORTED, not dropped and not repaired. Somebody has
    to look at it, and the only honest thing the engine can do is say so.
    """
    if not 0 <= char_start < char_end <= len(old_text):
        return PlacedStretch(
            reason=(
                f"the stretch {char_start}..{char_end} is not inside the old reading "
                f"(length {len(old_text)})"
            )
        )
    needle = old_text[char_start:char_end]
    occurrences = new_text.count(needle)
    if occurrences == 0:
        return PlacedStretch(reason=f"{needle!r} does not appear in the new reading")
    if occurrences > 1:
        return PlacedStretch(
            reason=f"{needle!r} appears {occurrences} times in the new reading; ambiguous"
        )
    found = new_text.index(needle)
    return PlacedStretch(
        representation_id=new_representation_id,
        char_start=found,
        char_end=found + len(needle),
        placed=True,
    )
