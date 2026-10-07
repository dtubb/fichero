"""Find the Documents against boxes with a known answer (spec: docs/contributor_manual/specs/source/finding-documents.md).

`finddocs.known-answer-first`, `finddocs.scored`, `finddocs.leaves-first`, `finddocs.boundaries.proposed-with-evidence`,
`finddocs.kinds.prototypes` (the kind only) and `finddocs.groups.and-order`, on the pure proposer
(`finddocs/propose.py`): the Istmina '1948 Sentencias' structure rebuilt without its text (`boxes.py`), and a
bundle of letters, cables and a receipt. Boundary precision and recall are measured, not assumed.
"""
from __future__ import annotations

import pytest

from fichero_server.finddocs.propose import PageInput, propose, score
from tests.unit.finddocs.boxes import correspondence_box, istmina_box


def _inputs(pages):
    return [PageInput(id=p.id, text=p.text, ink=p.ink) for p in pages]


@pytest.fixture(scope="module")
def istmina():
    pages, truth = istmina_box()
    return pages, truth, propose(_inputs(pages))


def test_istmina_eight_judgments_with_their_page_ranges(istmina):
    pages, truth, proposal = istmina
    assert len(proposal.documents) == 8
    assert [d.page_ids for d in proposal.documents] == truth
    positions = {p.id: i for i, p in enumerate(pages)}
    assert [(d.first_position, d.last_position) for d in proposal.documents] == [
        (positions[doc[0]], positions[doc[-1]]) for doc in truth]
    scored = score(proposal, truth)
    assert scored == {"precision": 1.0, "recall": 1.0, "exact_documents": 8, "documents": 8}


def test_istmina_kinds_are_sentencia_with_dates_in_order(istmina):
    _pages, _truth, proposal = istmina
    assert {d.kind for d in proposal.documents} == {"Sentencia"}
    assert {d.prototype_key for d in proposal.documents} == {"sentencia"}
    dates = [d.date for d in proposal.documents]
    assert dates == sorted(dates) and dates[0] == "1948-01-12" and dates[-1] == "1948-06-18"


def test_istmina_blank_versos_pair_with_their_rectos_and_duplicates_are_findings(istmina):
    pages, _truth, proposal = istmina
    by_id = {p.id: p for p in pages}
    versos = [f for f in proposal.findings if f.kind == "blank-verso"]
    blanks = [p for p in pages if p.blank]
    assert len(versos) == len(blanks) == 34
    for finding in versos:
        # Each verso is paired with the written page shot just before it (its recto, or that recto's second shot).
        before = pages[[p.id for p in pages].index(finding.page_id) - 1]
        assert finding.of_page_id == before.id and not by_id[finding.of_page_id].blank
    duplicates = {(f.page_id, f.of_page_id) for f in proposal.findings if f.kind == "duplicate-shot"}
    assert duplicates == {(p.id, p.repeats) for p in pages if p.repeats}
    # Leaves: every written page that is not a second shot, each with its verso.
    assert proposal.leaves == sum(1 for p in pages if not p.blank and not p.repeats)
    assert not any(f.kind in ("blank-page", "no-reading") for f in proposal.findings)


def test_istmina_boundaries_carry_their_evidence_and_no_case_group(istmina):
    _pages, truth, proposal = istmina
    starts = {d.page_ids[0] for d in proposal.documents[1:]}
    for join in proposal.joins:
        cues = {s.cue for s in join.signals}
        if join.page_id in starts:
            assert {"court-caption", "judgment-vistos", "place-and-date", "copy-and-notify"} <= cues
            assert join.probability > 0.95
        else:
            assert join.probability < 0.5
    # A judgment's first body page runs on from its caption page mid-sentence.
    assert any(s.cue == "sentence-runs-over" for j in proposal.joins for s in j.signals)
    # Four cases are against the same company: one shared party is not a case.
    assert proposal.groups == []
    assert all(d.confidence >= 0.95 for d in proposal.documents)


def test_letters_and_cables_score_and_group_the_correspondences():
    pages, truth, groups = correspondence_box()
    proposal = propose(_inputs(pages))
    scored = score(proposal, truth)
    assert scored["precision"] == 1.0 and scored["recall"] == 1.0 and scored["exact_documents"] == len(truth)
    assert [d.kind for d in proposal.documents] == ["Carta", "Cable", "Carta", "Letter", "Cable", "Letter", "Recibo"]
    assert [g.document_indexes for g in proposal.groups] == groups
    reply = proposal.groups[1]
    assert any("Brown" in p for p in reply.parties) and any("Smith" in p for p in reply.parties)
    # A cable that opens with no closing before it is proposed, but less surely than a letter after a letter.
    assert proposal.documents[2].confidence < proposal.documents[0].confidence
    assert [f.kind for f in proposal.findings].count("duplicate-shot") == 1


def test_a_sentence_running_over_the_break_keeps_two_pages_together():
    pages = [PageInput("a", "Istmina, 3 de marzo de 1948.\nSeñor Juez:\nLe escribo para decirle que la casa"),
             # A date line near the head of page b is outweighed by the sentence running onto it.
             PageInput("b", "que compramos está en buen estado.\nQuibdó, 4 de marzo de 1948")]
    proposal = propose(pages)
    assert len(proposal.documents) == 1
    assert {s.cue for s in proposal.joins[0].signals} >= {"sentence-runs-over", "place-and-date"}


def test_folio_numbers_restarting_open_a_document():
    pages = [PageInput("a", "- 1 -\nel texto del expediente sigue sin encabezado alguno."),
             PageInput("b", "- 2 -\nlas cuentas de la tienda quedaron saldadas en mayo."),
             PageInput("c", "- 1 -\nuna relación de los jornales pagados en la mina.")]
    proposal = propose(pages)
    assert [d.page_ids for d in proposal.documents] == [["a", "b"], ["c"]]
    cues = [{s.cue for s in j.signals} for j in proposal.joins]
    assert "numbering-continues" in cues[0] and "numbering-restarts" in cues[1]


def test_a_page_with_ink_but_no_reading_is_reported_not_called_blank():
    pages = [PageInput("a", "TELEGRAMA\nLLEGO MARTES STOP", ink=0.05), PageInput("b", "", ink=0.07)]
    proposal = propose(pages)
    assert [(f.kind, f.page_id) for f in proposal.findings] == [("no-reading", "b")]
    assert proposal.leaves == 2


def test_nothing_to_propose_for_no_pages():
    proposal = propose([])
    assert proposal.documents == [] and proposal.findings == [] and score(proposal, []) == {
        "precision": 1.0, "recall": 1.0, "exact_documents": 0, "documents": 0}
