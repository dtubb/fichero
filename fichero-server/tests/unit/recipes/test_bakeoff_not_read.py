"""A reader that read nothing is not read, not 100% CER, and never the winner (#5531).

Corpus bake-offs 2026-10-06: PP-OCRv6 returned 0 characters on every Hebrew page, scored CER 100% and was
named the winner; in Czech two readers returned 26-29 characters over 8 pages and the third "won". The
evaluation's one judgement (`training.evaluation.judged`): a page a reader returned nothing, or far too
little, for is not read, with why; a candidate that read under `MEASURED_SHARE` of the pages is not measured;
a winner needs at least two measured candidates.

Everything through the routes (`/api/recipes/project/bakeoffs...`) and the job as the scheduler runs it, with
Kraken faked at its seam (`kraken_runtime.read_given_lines`), as `test_bakeoff_readers` does.
"""
from __future__ import annotations

import json

import pytest

from fichero_server.llm import kraken_runtime
from fichero_server.llm.kraken_runtime import KrakenSegmentationError
from fichero_server.training import evaluation
from fichero_server.workflows.transcription_accuracy import DEFAULT_POLICY_NAME
from tests.unit.recipes.test_bakeoff_readers import (  # noqa: F401  (fixtures)
    MCCATMUS,
    MEDIEVAL,
    PPOCR,
    READER_IDS,
    _corrected,
    _run,
    _set_up,
    folder,
    homes,
)

PAGES = 5  # 4 of 5 is the measured share (80%); 3 of 5 is under it


class Readers:
    """Kraken's reader, faked at the seam. Each installed reader has a behaviour: `read` reads every line
    right (CATMuS Medieval drops each line's last character so the two are told apart); `empty` returns
    nothing; `empty_on` returns nothing on the named photographs; `trickle` a few characters a page;
    `raise` raises what Kraken raises when it cannot read."""

    def __init__(self, paths: dict[str, str], how: dict[str, str]):
        self.by_path = {paths[card]: (card, how[card]) for card in how}
        self.empty_on: set[str] = set()

    def __call__(self, image_path, model_path, lines, **kw):
        card, how = self.by_path[str(model_path)]
        if how == "raise":
            raise KrakenSegmentationError("Kraken could not read the lines: no codec for this script")
        if how == "empty" or (how == "empty_on" and str(image_path) in self.empty_on):
            return ["" for _ in lines]
        if how == "trickle":
            return ["ab" if i == 0 else "" for i, _ in enumerate(lines)]
        return [ln["text"][:-1] if card == MEDIEVAL else ln["text"] for ln in lines]


def _install(tmp_path, monkeypatch, how: dict[str, str]) -> Readers:
    """The named readers installed on this (test) Mac; the others are not, so they are named, not scored."""
    paths = {}
    for card in how:
        weights = tmp_path / f"{READER_IDS[card]}.mlmodel"
        weights.write_bytes(b"weights")
        marker = kraken_runtime._marker_path(READER_IDS[card])
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(json.dumps({"model_path": str(weights)}), encoding="utf-8")
        paths[card] = str(weights)
    fake = Readers(paths, how)
    monkeypatch.setattr(kraken_runtime, "read_given_lines", fake)
    return fake


def _pages(db, tmp_path, folder):  # noqa: F811 (pytest fixture)
    return [_corrected(db, tmp_path, f"SM_NPQ_C01_00{i}", folder) for i in range(1, PAGES + 1)]


def _rows(done):
    return {r["card"]: r for r in done["rows"]}


def test_a_reader_that_returned_nothing_is_not_read_never_100_percent_and_never_wins(
        client, db, tmp_path, folder, monkeypatch):  # noqa: F811
    """#5531: "a reader that returns nothing for a page is recorded as 'not read' ..., never scored as 100%".
    WHY: Hebrew, 2026-10-06: PP-OCRv6 returned 0 characters on every page, scored 100% and was named the
    winner. An empty page measures the reader's failure, not its reading; it must not be a score and must
    never rank a reader that read nothing above two that read the pages."""
    _set_up(client)
    _install(tmp_path, monkeypatch, {PPOCR: "empty", MEDIEVAL: "read", MCCATMUS: "read"})
    _pages(db, tmp_path, folder)

    _, done = _run(client, db)

    rows = _rows(done)
    empty = rows[PPOCR]
    assert empty["cer"] is None and empty["measured"] is False and empty["scores"] == {}
    assert (empty["pages_read"], empty["pages_total"]) == (0, PAGES)
    assert empty["why"] == f"not measured: read 0 of {PAGES} pages (returned no text on {PAGES} pages)"
    assert all(p["read"] is False and p["cer"] is None and p["why"] == "returned no text" for p in empty["per_page"])
    assert done["winner"] == MCCATMUS and done["no_winner_why"] is None  # reads every line right, of the two
    assert [r["card"] for r in done["rows"]][-1] == PPOCR  # ranked after every measured reader
    # The card's own entry carries the same judgement: no 100% written as the reader's score.
    (kept,) = evaluation.model_evaluations(READER_IDS[PPOCR], "kraken")
    assert kept["measured"] is False and kept["scores"][DEFAULT_POLICY_NAME]["cer"] is None


def test_a_reader_below_the_page_share_is_not_measured_and_cannot_be_used(
        client, db, tmp_path, folder, monkeypatch):  # noqa: F811
    """#5531: "a candidate is measured only if it read at least a stated share of the pages"; Use This only
    for a measured candidate.
    WHY: Czech, 2026-10-06: readers that read 2 of 8 pages had a CER over whatever they happened to read;
    that is a different sample, not comparable with a reader that read them all, and choosing it from the
    table would put a reader that failed most pages into the recipe."""
    _set_up(client)
    fake = _install(tmp_path, monkeypatch, {PPOCR: "read", MEDIEVAL: "empty_on", MCCATMUS: "read"})
    pages = _pages(db, tmp_path, folder)
    fake.empty_on = {p.path for p in pages[:2]}  # CATMuS Medieval reads 3 of 5: under 80%

    started, done = _run(client, db)

    short = _rows(done)[MEDIEVAL]
    assert short["measured"] is False and short["cer"] is None and short["pages_read"] == 3
    assert short["why"] == "not measured: read 3 of 5 pages (returned no text on 2 pages)"
    assert sum(not p["read"] for p in short["per_page"]) == 2
    assert done["winner"] in (PPOCR, MCCATMUS)  # both read every line right: tied, split by the fixed order
    use =client.post(f"/api/recipes/project/bakeoffs/{started['id']}/use", json={"card": MEDIEVAL})
    assert use.status_code == 422 and "not measured" in use.json()["detail"]

    # One page short of all is still measured: its CER is over the pages it read, shown with that count.
    fake.empty_on = {pages[0].path}
    again, done = _run(client, db)
    kept = _rows(done)[MEDIEVAL]
    assert kept["measured"] is True and (kept["pages_read"], kept["pages_total"]) == (4, 5)
    assert kept["cer"] is not None and 0 < kept["cer"] < 0.1  # a dropped character a line, not 100% on a page
    used = client.post(f"/api/recipes/project/bakeoffs/{again['id']}/use", json={"card": MEDIEVAL})
    assert used.status_code == 200, used.text
    (o,) = used.json()["recipe"]["overrides"]
    assert "on the 4 of 5 pages it read" in o["because"]


def test_a_sole_measured_reader_gets_no_winner_and_the_sentence_says_why(
        client, db, tmp_path, folder, monkeypatch):  # noqa: F811
    """#5531: "the bake-off names a winner only if at least two candidates are measured; otherwise the result
    says plainly why".
    WHY: a "winner" of a race of one is no comparison: the screen would recommend a reader on no evidence
    that it is better than anything. With one reader downloaded, or the others failing, the person must
    read why there is no winner, not a crown."""
    _set_up(client)
    _install(tmp_path, monkeypatch, {MCCATMUS: "read"})  # the other two are not on this Mac
    _pages(db, tmp_path, folder)

    _, done = _run(client, db)

    assert _rows(done)[MCCATMUS]["measured"] is True and done["winner"] is None
    name = _rows(done)[MCCATMUS]["name"]
    assert done["no_winner_why"] == f"No winner: only one reader could be compared ({name})."
    assert "zenodo" not in done["no_winner_why"]  # the reader's name, never its card id


def test_no_reader_read_the_pages_says_so(client, db, tmp_path, folder, monkeypatch):  # noqa: F811
    """#5531: "no reader read these pages".
    WHY: when every reader returned nothing (a script none of them reads, or a failing engine), the table
    must not rank the failures; it says nothing was read, so the person knows to look at the readers."""
    _set_up(client)
    _install(tmp_path, monkeypatch, {PPOCR: "empty", MEDIEVAL: "empty", MCCATMUS: "trickle"})
    _pages(db, tmp_path, folder)

    _, done = _run(client, db)

    assert done["winner"] is None and done["no_winner_why"] == "No winner: no reader read these pages."
    trickle = _rows(done)[MCCATMUS]
    assert trickle["measured"] is False
    (page_why,) = {p["why"] for p in trickle["per_page"]}
    assert page_why.startswith("returned 2 characters against ") and page_why.endswith(" in the reference")


def test_the_readers_own_reason_surfaces(client, db, tmp_path, folder, monkeypatch):  # noqa: F811
    """#5531: "surface WHY a reader returned nothing where the reader reports it (an exception ...)".
    WHY: "returned nothing" alone sends the person hunting; Kraken's own error (it could not read the
    lines) says where to look. An error on a page is the page's reason, not the job's failure: the other
    readers' scores are kept."""
    _set_up(client)
    _install(tmp_path, monkeypatch, {PPOCR: "raise", MEDIEVAL: "read", MCCATMUS: "read"})
    _pages(db, tmp_path, folder)

    _, done = _run(client, db)

    assert _rows(done)[MEDIEVAL]["measured"] and _rows(done)[MCCATMUS]["measured"]  # the job carried on
    failed = _rows(done)[PPOCR]
    reason = "failed: Kraken could not read the lines: no codec for this script"
    assert {p["why"] for p in failed["per_page"]} == {reason}
    assert failed["why"] == f"not measured: read 0 of {PAGES} pages ({reason} on {PAGES} pages)"
    assert done["winner"] == MCCATMUS


def test_kraken_names_lines_with_no_geometry_and_a_vision_model_its_empty_answers(monkeypatch, tmp_path):
    """#5531: the reason, where the reader can know it.
    WHY: Kraken reads each line on its baseline and outline; lines imported without them read as nothing,
    and the person can fix that (import the geometry) only if the table says so. A vision model that
    answered nothing for every line is a model failure, not an unreadable page."""
    monkeypatch.setattr(kraken_runtime, "resolve_recognition_model", lambda model: ("/weights", None))
    monkeypatch.setattr(kraken_runtime, "read_given_lines", lambda photo, path, lines: ["" for _ in lines])
    bare = [{"id": "l1", "text": "Anno domini", "baseline": [], "polygon": []}]
    assert evaluation.read_with_kraken("p.jpg", "kraken-mccatmus", bare)[1] == (
        "its lines carry no baseline and outline for Kraken to read on")
    shaped = [{"id": "l1", "text": "x", "baseline": [[0, 5], [9, 5]], "polygon": [[0, 0], [9, 0], [9, 9]]}]
    assert evaluation.read_with_kraken("p.jpg", "kraken-mccatmus", shaped)[1] is None

    from PIL import Image

    photo = tmp_path / "page.png"
    Image.new("RGB", (20, 20), "white").save(photo)

    async def silent(candidate, image, prompt):
        return "  "

    monkeypatch.setattr(evaluation, "ask_vision", silent)
    candidate = evaluation.EvaluationCandidate(model="mlx-community/some-vl", reader="vision", provider="omlx")
    reads, why = evaluation.read_with_vision(str(photo), candidate, shaped, None)
    assert reads == [""] and why == "the model gave an empty answer for every line"


def test_a_comparison_kept_before_the_rule_is_judged_by_it(client, db, tmp_path, folder, monkeypatch):  # noqa: F811
    """#5531: "keep stored comparisons readable (old records without the new fields still load)".
    WHY: the Hebrew comparison is already kept, on the cards, in the old shape: every page scored, an empty
    one at 100%. It must still load, and read back by the same rule, so the table no longer names the
    reader that read nothing as the winner."""
    _set_up(client)
    _install(tmp_path, monkeypatch, {PPOCR: "empty", MEDIEVAL: "read"})
    pages = _pages(db, tmp_path, folder)
    started, _ = _run(client, db)

    # Rewrite each card's entry as an evaluation before #5531 kept it: every page scored, no read fields.
    for card in (PPOCR, MEDIEVAL):
        path = evaluation.card_path(READER_IDS[card], "kraken")
        kept = json.loads(path.read_text(encoding="utf-8"))
        (entry,) = kept["evaluations"]
        old_pages = []
        for p in pages:
            reference = [ln["text"] for ln in evaluation.reference_page(db, p.id, None)[0]["lines"]]
            reads = ["" for _ in reference] if card == PPOCR else [t[:-1] for t in reference]
            old_pages.append({"document_id": p.id, "name": p.name, "trust": "person", "lines": len(reference),
                              "scores": evaluation.score_page(reference, reads)})
        for field in ("measured", "pages_read", "pages_total", "why"):
            entry.pop(field)
        entry.update(per_page=old_pages, scores=evaluation.totals(old_pages))
        assert entry["scores"][DEFAULT_POLICY_NAME]["cer"] == (1.0 if card == PPOCR else entry["scores"][
            DEFAULT_POLICY_NAME]["cer"])  # the old shape: the empty reader at 100%
        path.write_text(json.dumps(kept), encoding="utf-8")

    later = client.get(f"/api/recipes/project/bakeoffs/{started['id']}")
    assert later.status_code == 200, later.text
    rows = _rows(later.json())
    assert rows[PPOCR]["measured"] is False and rows[PPOCR]["cer"] is None
    assert rows[MEDIEVAL]["measured"] is True and rows[MEDIEVAL]["pages_read"] == PAGES
    assert later.json()["winner"] is None and "only one reader could be compared" in later.json()["no_winner_why"]
    listed = client.get("/api/recipes/project/bakeoffs")
    assert listed.status_code == 200 and listed.json()["items"][0]["winner"] is None


@pytest.mark.parametrize("hypothesis_chars, read", [(0, False), (9, False), (10, True), (60, True)])
def test_the_read_share_is_a_tenth_of_the_reference(hypothesis_chars, read):
    """#5531: "far too little against the reference (define it)": under `READ_SHARE` (10%) of the
    reference's characters.
    WHY: the line between a bad reading and no reading must be stated and pinned: a reader at 60% CER still
    writes most of the page and is scored; one that wrote a tenth of it did not read it."""
    page = {"document_id": "d", "name": "p", "lines": 1,
            "scores": {DEFAULT_POLICY_NAME: {"cer": 0.9, "distance": 90, "reference_chars": 100,
                                             "hypothesis_chars": hypothesis_chars}}}
    assert evaluation.READ_SHARE == 0.10 and evaluation.MEASURED_SHARE == 0.80
    assert evaluation.judge_page(page)["read"] is read
