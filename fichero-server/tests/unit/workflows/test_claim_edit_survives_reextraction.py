"""An edited claim must survive re-extraction (#4499).

``save_claim`` deduplicates on text + SVO. An edit changes exactly those
fields, so a re-extraction reproducing the *pre-edit* reading matched nothing
and was stored as a second claim: the correction survived alongside the thing
it corrected, and the archive asserted two contradictory readings of one span
while recording nothing about which one the historian rejected.

That is worse than a plain overwrite. An overwrite loses the edit visibly;
this keeps both and hides the disagreement.

The contract pinned here — the same one dates (#3322 5b) and catalogue re-runs
(#4415) already keep, through the same guard:

- an edit records the reading it corrected away from, on the row it governs;
- a re-run reproducing that reading is recognised and NOT re-added;
- a re-run offering a *third* reading of the same span leaves her value
  standing and records the candidate beside it, rather than duplicating or
  silently resolving;
- and the guard holds across repeated re-runs. One that decays after a single
  run is worse than none, because it looks like protection.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from fichero_server.api.routes.claim.claims import ClaimPatchRequest, patch_claim_impl
from fichero_server.db import Database
from fichero_server.models import DocType, Document
from fichero_server.models.knowledge import ClaimCurationState, KnowledgeClaim
from fichero_server.workflows.curation_guard import (
    CurationSource,
    has_conflict,
    read_curation,
    superseded_identities,
)
from fichero_server.workflows.tools._entity_writer import save_claim


ORIGINAL = "El acta fue firmado por Ospina."
CORRECTED = "El acta fue firmado por Ocampo."
THIRD_READING = "El acta fue firmado por Osorio."


def _setup(tmp: str) -> tuple[Database, Document]:
    db = Database(Path(tmp) / "test.fichero")
    doc = Document(name="acta", doc_type=DocType.file)
    db.save(doc)
    return db, doc


def _extract(db: Database, doc_id: str, text: str, object_phrase: str) -> str | None:
    """One extraction pass producing a claim about the signature line."""
    return save_claim(
        db,
        text,
        doc_id,
        source_page_label="1r",
        subject_canonical="el acta",
        predicate_verb="firmado por",
        object_phrase=object_phrase,
        provider="fixture",
        model="fixture-v1",
    )


def _edit(db: Database, claim_id: str, text: str, object_phrase: str) -> KnowledgeClaim:
    claim, _before = patch_claim_impl(
        db,
        claim_id,
        ClaimPatchRequest(text=text, object_phrase=object_phrase),
        actor="ann",
    )
    return claim


def _claims(db: Database) -> list[KnowledgeClaim]:
    return list(db.query(KnowledgeClaim))


# =============================================================================
# The edit records what it corrected away from
# =============================================================================


def test_edit_records_the_superseded_reading_and_who_corrected_it():
    with tempfile.TemporaryDirectory() as tmp:
        db, doc = _setup(tmp)
        claim_id = _extract(db, doc.id, ORIGINAL, "Ospina")
        assert claim_id is not None

        claim = _edit(db, claim_id, CORRECTED, "Ocampo")

        history = superseded_identities(claim)
        assert [entry["text"] for entry in history] == [ORIGINAL]
        assert history[0]["svo_object"] == "Ospina"

        record = read_curation(claim)
        assert record.source is CurationSource.user
        assert record.actor == "ann"
        assert record.is_protected


def test_patch_that_changes_no_reading_supersedes_nothing():
    # Filing a claim as reviewed is not a correction. If every save recorded a
    # superseded reading, the guard would start suppressing extractions the
    # user never disagreed with.
    with tempfile.TemporaryDirectory() as tmp:
        db, doc = _setup(tmp)
        claim_id = _extract(db, doc.id, ORIGINAL, "Ospina")

        claim, _ = patch_claim_impl(
            db,
            claim_id,
            ClaimPatchRequest(curation_state=ClaimCurationState.curated),
            actor="ann",
        )
        assert superseded_identities(claim) == []


def test_unauthenticated_single_user_edit_is_still_protected():
    # On a single-user library nobody is signed in, so the actor arrives as
    # "system". Reading that as a machine would leave the most common
    # configuration with no correction survival at all.
    with tempfile.TemporaryDirectory() as tmp:
        db, doc = _setup(tmp)
        claim_id = _extract(db, doc.id, ORIGINAL, "Ospina")

        claim = patch_claim_impl(
            db,
            claim_id,
            ClaimPatchRequest(text=CORRECTED, object_phrase="Ocampo"),
            actor="system",
        )[0]

        assert read_curation(claim).is_protected
        assert superseded_identities(claim)


# =============================================================================
# Re-extraction over an edited claim
# =============================================================================


def test_reextraction_of_the_pre_edit_reading_is_not_re_added():
    with tempfile.TemporaryDirectory() as tmp:
        db, doc = _setup(tmp)
        claim_id = _extract(db, doc.id, ORIGINAL, "Ospina")
        _edit(db, claim_id, CORRECTED, "Ocampo")

        returned = _extract(db, doc.id, ORIGINAL, "Ospina")

        claims = _claims(db)
        assert len(claims) == 1
        assert claims[0].id == claim_id
        assert returned == claim_id
        assert claims[0].text == CORRECTED
        assert claims[0].object_phrase == "Ocampo"


def test_the_guard_holds_across_repeated_re_runs():
    # A guard that works once and decays is worse than none: it reads as
    # protection right up to the run where the duplicate appears.
    with tempfile.TemporaryDirectory() as tmp:
        db, doc = _setup(tmp)
        claim_id = _extract(db, doc.id, ORIGINAL, "Ospina")
        _edit(db, claim_id, CORRECTED, "Ocampo")

        for _ in range(3):
            _extract(db, doc.id, ORIGINAL, "Ospina")

        claims = _claims(db)
        assert len(claims) == 1
        assert claims[0].text == CORRECTED


def test_a_second_edit_keeps_both_rejected_readings_out():
    with tempfile.TemporaryDirectory() as tmp:
        db, doc = _setup(tmp)
        claim_id = _extract(db, doc.id, ORIGINAL, "Ospina")
        _edit(db, claim_id, THIRD_READING, "Osorio")
        claim = _edit(db, claim_id, CORRECTED, "Ocampo")

        assert [entry["text"] for entry in superseded_identities(claim)] == [
            ORIGINAL,
            THIRD_READING,
        ]

        _extract(db, doc.id, ORIGINAL, "Ospina")
        _extract(db, doc.id, THIRD_READING, "Osorio")

        claims = _claims(db)
        assert len(claims) == 1
        assert claims[0].text == CORRECTED


def test_reextraction_agreeing_with_the_edit_records_no_disagreement():
    with tempfile.TemporaryDirectory() as tmp:
        db, doc = _setup(tmp)
        claim_id = _extract(db, doc.id, ORIGINAL, "Ospina")
        _edit(db, claim_id, CORRECTED, "Ocampo")

        _extract(db, doc.id, CORRECTED, "Ocampo")

        claims = _claims(db)
        assert len(claims) == 1
        assert not has_conflict(claims[0])


# =============================================================================
# Genuine disagreement is surfaced, not resolved behind her back
# =============================================================================


def test_a_third_reading_is_recorded_as_a_conflict_not_a_duplicate():
    with tempfile.TemporaryDirectory() as tmp:
        db, doc = _setup(tmp)
        claim_id = _extract(db, doc.id, ORIGINAL, "Ospina")
        _edit(db, claim_id, CORRECTED, "Ocampo")

        _extract(db, doc.id, THIRD_READING, "Osorio")

        claims = _claims(db)
        assert len(claims) == 1
        surviving = claims[0]

        # Her correction stands as the row's value...
        assert surviving.text == CORRECTED
        # ...and the extractor's candidate is kept beside it, in full.
        assert has_conflict(surviving)
        conflict = surviving.metadata["curation"]["extraction_conflict"]
        assert conflict["proposal"]["text"] == THIRD_READING
        assert conflict["proposal"]["svo_object"] == "Osorio"
        assert conflict["proposal"]["model"] == "fixture-v1"
        assert "disagrees" in conflict["reason"]


def test_a_later_run_agreeing_with_her_clears_a_recorded_disagreement():
    with tempfile.TemporaryDirectory() as tmp:
        db, doc = _setup(tmp)
        claim_id = _extract(db, doc.id, ORIGINAL, "Ospina")
        _edit(db, claim_id, CORRECTED, "Ocampo")
        _extract(db, doc.id, THIRD_READING, "Osorio")
        assert has_conflict(db.get(KnowledgeClaim, claim_id))

        # An improved extractor now reads it the way she does. The
        # disagreement no longer holds and must not haunt the row.
        _extract(db, doc.id, CORRECTED, "Ocampo")

        assert not has_conflict(db.get(KnowledgeClaim, claim_id))
        assert len(_claims(db)) == 1


def test_a_rejected_reading_reappearing_does_not_clear_a_disagreement():
    # The reading she already overruled turning up again settles nothing about
    # a different candidate, so it must not silently drop that candidate.
    with tempfile.TemporaryDirectory() as tmp:
        db, doc = _setup(tmp)
        claim_id = _extract(db, doc.id, ORIGINAL, "Ospina")
        _edit(db, claim_id, CORRECTED, "Ocampo")
        _extract(db, doc.id, THIRD_READING, "Osorio")

        _extract(db, doc.id, ORIGINAL, "Ospina")

        assert has_conflict(db.get(KnowledgeClaim, claim_id))
        assert len(_claims(db)) == 1


# =============================================================================
# The guard stays narrow
# =============================================================================


def test_an_unrelated_claim_on_the_same_page_is_still_added():
    # The guard protects one assertion, not a whole page. Suppressing genuine
    # new findings because some claim nearby was edited would trade one kind
    # of data loss for another.
    with tempfile.TemporaryDirectory() as tmp:
        db, doc = _setup(tmp)
        claim_id = _extract(db, doc.id, ORIGINAL, "Ospina")
        _edit(db, claim_id, CORRECTED, "Ocampo")

        save_claim(
            db,
            "El escribano registró la venta.",
            doc.id,
            source_page_label="1r",
            subject_canonical="el escribano",
            predicate_verb="registró",
            object_phrase="la venta",
            provider="fixture",
            model="fixture-v1",
        )

        assert len(_claims(db)) == 2


def test_an_unedited_claim_is_untouched_by_the_guard():
    with tempfile.TemporaryDirectory() as tmp:
        db, doc = _setup(tmp)
        _extract(db, doc.id, ORIGINAL, "Ospina")

        # A different reading of the same span, with nothing curated: ordinary
        # extraction behaviour, no conflict machinery.
        _extract(db, doc.id, THIRD_READING, "Osorio")

        claims = _claims(db)
        assert len(claims) == 2
        assert not any(has_conflict(claim) for claim in claims)
