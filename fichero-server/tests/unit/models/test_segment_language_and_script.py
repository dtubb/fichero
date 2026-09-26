"""Source-model slice 9 (#4938) — a segment's own language and script.

Spec: `languages-scripts-signs.md` — `source.lang.three-facts`,
`source.lang.many-per-page`, `source.lang.says-where-from`,
`source.lang.unknown-is-not-unexamined`.

**THE MISSING MIDDLE.** Language and script already existed at the top
(`LanguagePolicy`), at the document (`Document.language` + `language_meta`) and
at the reading (`ContentRepresentation.language`/`.script` + their metas, slice 9
item 2). The segment had neither — so the cascade skipped the level the source
model is about.

A segment needs its own for a reason that is not symmetry: `many-per-page` says
one page can hold several languages at once, and the reading is too low a level
to carry that, because one line can have several readings in the SAME language.
The region is where "this part of the page is in this language" belongs.

These tests pin the STORED shape. The resolver walking the new level is a
separate step, held pending a ruling on whether `LanguageResolution` gains a
`level` field — so nothing here asserts a cascade, only that a segment can hold
the facts and their provenance, and that absence still means never determined.
"""

from __future__ import annotations

import pytest

from fichero_server.llm.language_policy import (
    LEVEL_DOCUMENT,
    LEVEL_SEGMENT,
    SOURCE_DETECTED,
    SOURCE_USER,
    STATUS_KNOWN,
    STATUS_UNKNOWN,
    build_language_meta,
)
from fichero_server.models import Segment
from fichero_server.models.anchors import SourceAnchor
from fichero_server.models.knowledge import ProvenanceKind

pytestmark = pytest.mark.source_model


def _segment(db, **kwargs) -> Segment:
    anchor = SourceAnchor(document_id="doc-1", rect=[0.1, 0.1, 0.2, 0.05])
    row = Segment(
        document_id="doc-1",
        pass_id="pass-1",
        kind=kwargs.pop("kind", "line"),
        anchor=anchor,
        bbox_x=0.1, bbox_y=0.1, bbox_w=0.2, bbox_h=0.05,
        tile="x0y0", doc_kind="doc-1:line",
        provenance_kind=ProvenanceKind.workflow,
        **kwargs,
    )
    db.save(row)
    return row


class TestASegmentCanHoldItsOwnLanguageAndScript:
    def test_language_and_script_round_trip_with_their_provenance(self, db):
        row = _segment(
            db,
            language="la",
            script="Latn",
            language_meta=build_language_meta(
                status=STATUS_KNOWN, source=SOURCE_USER, level=LEVEL_SEGMENT,
                basis="a historian marked this marginal note as Latin",
            ),
            script_meta=build_language_meta(
                status=STATUS_KNOWN, source=SOURCE_USER, level=LEVEL_SEGMENT,
            ),
        )

        stored = db.get(Segment, row.id)
        assert stored.language == "la"
        assert stored.script == "Latn"
        assert stored.language_meta["level"] == "segment"
        assert stored.language_meta["source"] == "user"
        assert "marginal note" in stored.language_meta["basis"]
        assert stored.script_meta["level"] == "segment"

    def test_a_segment_that_states_nothing_reads_back_never_determined(self, db):
        """`None` is not "unknown" — it is "nobody has looked". The cascade's job
        is to supply a value when a segment does not state one, never to write a
        guess into these fields."""
        row = _segment(db)

        stored = db.get(Segment, row.id)
        assert stored.language is None
        assert stored.script is None
        assert stored.language_meta is None
        assert stored.script_meta is None

    def test_examined_and_undetermined_is_a_third_state_here_too(self, db):
        row = _segment(
            db,
            language=None,
            language_meta=build_language_meta(
                status=STATUS_UNKNOWN, source=SOURCE_DETECTED, level=LEVEL_SEGMENT,
                basis="detection ran on this region and returned nothing above threshold",
            ),
        )

        stored = db.get(Segment, row.id)
        assert stored.language is None
        assert stored.language_meta["status"] == "unknown"
        # Distinguishable from the segment above, which has no meta at all.
        assert stored.language_meta is not None


class TestOnePageHoldsSeveralLanguagesAtOnce:
    """`source.lang.many-per-page` — the reason a segment needs its own, rather
    than inheriting the page's."""

    def test_two_regions_of_one_page_hold_different_languages(self, db):
        entry = _segment(
            db, kind="region", language="es", script="Latn",
            language_meta=build_language_meta(
                status=STATUS_KNOWN, source=SOURCE_USER, level=LEVEL_SEGMENT
            ),
        )
        marginalia = _segment(
            db, kind="marginalia", language="la", script="Latn",
            language_meta=build_language_meta(
                status=STATUS_KNOWN, source=SOURCE_USER, level=LEVEL_SEGMENT
            ),
        )

        rows = {row.id: row for row in db.query(Segment, document_id="doc-1")}
        assert rows[entry.id].language == "es"
        assert rows[marginalia.id].language == "la"
        # One page, one document id, two answers — which is the behaviour. A
        # single page-level language could not express this without being wrong
        # about one of the two regions.
        assert rows[entry.id].document_id == rows[marginalia.id].document_id

    def test_the_same_language_in_a_different_script_differs_in_one_fact_only(self, db):
        """Why language and script are recorded SEPARATELY
        (`source.lang.three-facts`): a transliterated passage shares the language
        and not the script, and one combined field could not say which changed."""
        latin = _segment(db, kind="line", language="es", script="Latn")
        transliterated = _segment(db, kind="line", language="es", script="Arab")

        rows = {row.id: row for row in db.query(Segment, document_id="doc-1")}
        assert rows[latin.id].language == rows[transliterated.id].language == "es"
        assert rows[latin.id].script != rows[transliterated.id].script


class TestTheProvenanceShapeIsTheSameEverywhere:
    def test_a_segment_can_record_that_its_language_came_from_the_document(self, db):
        """The stored shape has to be able to say a value was INHERITED, which is
        what `says-where-from` is for: a level recorded here with
        `level="document"` is a resolved answer cached at this level, not a claim
        that someone examined this region."""
        row = _segment(
            db,
            language="es",
            language_meta=build_language_meta(
                status=STATUS_KNOWN, source=SOURCE_USER, level=LEVEL_DOCUMENT,
                basis="inherited from the document's recorded language",
            ),
        )

        stored = db.get(Segment, row.id)
        assert stored.language_meta["level"] == "document"
        assert stored.language_meta["level"] != LEVEL_SEGMENT

    def test_it_is_the_same_keys_as_a_document_and_a_reading_use(self, db):
        from fichero_server.models import ContentRepresentation, Document

        meta = build_language_meta(
            status=STATUS_KNOWN, source=SOURCE_USER, level=LEVEL_SEGMENT, basis="b",
        )
        segment = _segment(db, language="es", language_meta=meta)
        document = Document(id="doc-lang", name="p.jpg", language="es", language_meta=meta)
        db.save(document)
        reading = ContentRepresentation(
            document_id="doc-lang", kind="transcription", content="x",
            source_anchor=SourceAnchor(document_id="doc-lang"),
            language="es", language_meta=meta,
        )
        db.save(reading)

        # ONE shape for one idea, at three levels. If any of these three drifted
        # to its own keys, a reader would need three parsers for one question.
        assert (
            db.get(Segment, segment.id).language_meta
            == db.get(Document, document.id).language_meta
            == db.get(ContentRepresentation, reading.id).language_meta
        )
