"""Find the Documents takes no evidence from text the reader wasn't sure of (#5675), tested to the spec:
`finddocs.boundaries.proposed-with-evidence` (docs/contributor_manual/specs/source/finding-documents.md).

WHY: on CACIQUES_INDIOS,17,D.5, read by Kraken at ~70% CER, "a sentence runs over the break" fired on 30 joins
only because the noise starts in lower case and has no full stops: −3 each, burying every other cue.
"""

from __future__ import annotations

from fichero_server.finddocs.propose import TEXT_TOO_UNCERTAIN, PageInput, propose

NOISE = [
    "nou y^ 8r F 60535 nyi gil ditree delariadad\nconduiron temsdta qes le ganretoduy craj de le",
    "mecdes Pllibrause les desvaisrg de nuebr ondu\nquet Sege brs S Gmõi",
    "1\ndort rue neurs nt ypai\nurry Joce mn joet",
]


def _joins(uncertain: bool):
    pages = [PageInput(id=f"p{i}", text=text, text_uncertain=uncertain) for i, text in enumerate(NOISE)]
    return propose(pages, proposal_id="t").joins


def test_noise_read_uncertainly_says_nothing_for_or_against_a_boundary():
    joins = _joins(uncertain=True)
    cues = {s.cue for j in joins for s in j.signals}
    assert "sentence-runs-over" not in cues and "numbering-restarts" not in cues
    assert all(any(s.cue == "text-too-uncertain" and s.line == TEXT_TOO_UNCERTAIN and s.weight == 0 for s in j.signals)
               for j in joins)


def test_the_same_text_read_surely_is_judged_as_before():
    cues = [s.cue for j in _joins(uncertain=False) for s in j.signals]
    assert "sentence-runs-over" in cues and "numbering-restarts" in cues and "text-too-uncertain" not in cues


def test_the_page_inputs_carry_the_shared_certainty_bar(db, tmp_path):
    """A page's certainty is #5694's: below the bar its text is uncertain; with no stored certainty it is not."""
    from fichero_server.finddocs.job import page_inputs
    from fichero_server.models import DocType, Document
    from fichero_server.actions.registry import registry
    from tests.unit.recipes.test_names_on_unreadable_text_5694 import _read
    from tests.unit.training.test_kraken_training_set import BOOT, PAGE, _page

    folder = Document(name="F", doc_type=DocType.folder)
    db.save(folder)
    poor, unknown = (_page(db, tmp_path, name, folder, read_by=None) for name in ("1_Hoja", "2_Hoja"))
    registry.invoke(db, "format.import", {"document_id": poor.id, "path": str(PAGE)}, BOOT)
    _read(db, poor, 0.42)

    seen = {p.id: p.text_uncertain for p in page_inputs(db, [poor, unknown])}
    assert seen == {poor.id: True, unknown.id: False}
