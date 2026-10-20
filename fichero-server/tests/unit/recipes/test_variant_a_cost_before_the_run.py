"""`source.recipe.kraken-then-cloud-unsure-lines`: the cost of variant A is shown BEFORE the run, from the most lines it
can send (Kraken has not read anything yet), with the bar and the basis in words; any other run says none of this (#5894)."""
from __future__ import annotations

import pytest

from fichero_server.recipes.start import ASSUMED_LINES_PER_PAGE, LINE_TOKENS_IN, estimate
from tests.unit.recipes.test_installed_model_first_to_spec import mac  # noqa: F401 (fixture)
from fichero_server.workflows import model_comparison

CORRECT = {"workflow": "Paleographer Review", "steps": ["correct"], "job": "correct", "runs_on": "cloud:anthropic",
           "provider_override": "anthropic", "model_override": "claude-x"}
A = {**CORRECT, "tool_config": {"transcribe_review": {"only_below_confidence": 0.6}}}


@pytest.fixture(autouse=True)
def a_cent_per_1200_tokens(monkeypatch):
    monkeypatch.setattr(model_comparison, "estimate_cost", lambda model, tokens_in, tokens_out, provider="":
                        round(tokens_in / 1200 * 0.01, 6))


def test_pages_with_no_lines_yet_are_an_estimate_that_says_what_it_assumes():
    [row] = estimate([A], 10)["runs"]
    guess = 10 * ASSUMED_LINES_PER_PAGE
    assert row["certainty_bar"] == 0.6 and row["lines_to_send"] == guess and row["lines_to_send_kind"] == "estimate"
    assert row["cost_usd"] == pytest.approx(guess * LINE_TOKENS_IN / 1200 * 0.01)
    assert f"about {guess} lines, assuming about {ASSUMED_LINES_PER_PAGE} a page" in row["lines_basis"]
    assert "really had" in row["lines_basis"], "the run reports the real figure afterwards"
    assert "at most" not in row["lines_basis"], "a guess is not worded as a bound"


def test_some_pages_segmented_adds_their_real_lines_to_the_guess_for_the_rest():
    known = {"pages": 10, "segmented": 4, "lines": 120, "sures": [0.9] * 120}
    [row] = estimate([A], 10, known)["runs"]
    assert row["lines_to_send"] == 120 + 6 * ASSUMED_LINES_PER_PAGE and row["lines_to_send_kind"] == "estimate"
    assert "for the 6 pages Kraken has not found lines on yet" in row["lines_basis"]


def test_every_page_segmented_but_not_every_certainty_stated_is_a_true_bound():
    known = {"pages": 10, "segmented": 10, "lines": 300, "sures": [None] + [0.9] * 299}
    [row] = estimate([A], 10, known)["runs"]
    assert (row["lines_to_send"], row["lines_to_send_kind"]) == (300, "at-most")
    assert row["lines_basis"].startswith("at most 300 lines: every line Kraken found")
    assert row["cost_usd"] == pytest.approx(300 * LINE_TOKENS_IN / 1200 * 0.01)


def test_every_page_segmented_and_every_certainty_stated_is_exact():
    known = {"pages": 10, "segmented": 10, "lines": 300, "sures": [0.1] * 42 + [0.9] * 258}
    [row] = estimate([A], 10, known)["runs"]
    assert (row["lines_to_send"], row["lines_to_send_kind"]) == (42, "exact")
    assert row["lines_basis"] == "42 of 300 lines are under 0.6 sure now"
    assert row["cost_usd"] == pytest.approx(42 * LINE_TOKENS_IN / 1200 * 0.01)


def _page_with(db, sures):
    """A page of Kraken lines, one per entry: its stated certainty, or None for a reading that states none."""
    from fichero_server.models import ContentRepresentation
    from tests.unit.recipes.test_unread_lines_not_read_5758 import _page

    page = _page(db, len(sures), len(sures))
    from fichero_server.models.segments import Segment

    segs = sorted((x for x in db.query(Segment, document_id=page) if x.kind == "line"), key=lambda x: x.bbox_y)
    for seg, sure in zip(segs, sures):
        for reading in db.query(ContentRepresentation, segment_id=seg.id):
            reading.machine_confidence = sure
            db.save(reading)
    return page


def test_the_project_scan_counts_real_lines_and_is_exact_only_when_each_has_its_certainty(db):
    from fichero_server.recipes.done import kraken_lines_known

    stated, bare = _page_with(db, (0.95, 0.30, 0.50, 0.99)), _page_with(db, ())
    got = kraken_lines_known(db, [stated, bare])
    assert (got["pages"], got["segmented"], got["lines"]) == (2, 1, 4) and sorted(got["sures"]) == [0.3, 0.5, 0.95, 0.99]
    mixed = _page_with(db, (0.95, None))
    assert None in kraken_lines_known(db, [stated, mixed])["sures"], "one unstated certainty: the count is not known"


def test_each_run_counts_the_lines_under_its_own_bar():
    known = {"pages": 2, "segmented": 2, "lines": 4, "sures": [0.95, 0.30, 0.50, 0.99]}
    low, high = ({**A, "tool_config": {"transcribe_review": {"only_below_confidence": b}}} for b in (0.4, 0.97))
    rows = estimate([low, high], 2, known)["runs"]
    assert [(r["lines_to_send"], r["lines_to_send_kind"]) for r in rows] == [(1, "exact"), (3, "exact")]
    assert "under 0.4 sure" in rows[0]["lines_basis"] and "under 0.97 sure" in rows[1]["lines_basis"]


def test_the_scan_is_one_read_for_all_the_pages(db, monkeypatch):
    from fichero_server.models.segments import Segment
    from fichero_server.recipes.done import kraken_lines_known

    pages = [_page_with(db, (0.5, 0.7)) for _ in range(3)]
    asked = []
    real = type(db).query_in
    monkeypatch.setattr(type(db), "query_in", lambda self, model, col, vals: (asked.append(model), real(self, model, col, vals))[1])
    kraken_lines_known(db, pages)
    assert asked.count(Segment) == 1, "one grouped read of the lines, not one a page"


def test_the_start_plan_route_builds_the_plan_off_the_event_loop(monkeypatch):
    import asyncio
    import threading

    from fichero_server.api.routes.system import recipes as route

    seen = []
    monkeypatch.setattr(route, "_cluster_names", lambda http: [])
    monkeypatch.setattr(route, "_start_plan", lambda db, folder, clusters=(): seen.append(threading.get_ident()) or {})
    monkeypatch.setattr(route, "StartPlan", lambda **kw: kw)
    asyncio.run(route.get_start_plan(None, None, None))
    assert seen and seen[0] != threading.get_ident()


def test_a_bad_bar_in_a_non_strict_answer_skips_the_step_in_words_instead_of_raising(mac):
    from fichero_server.recipes.start import plan_start
    from tests.unit.recipes.test_certainty_bar_in_set_up_2026_10_20 import _recipe
    from tests.unit.recipes.test_disagree_needs_no_model_5812 import CORRECT as C, KRAKEN_READS, LINES

    mac.installed.add("Qwen2.5-VL-7B")
    for bad in ("sure", "1.5", "0"):
        plan = plan_start(_recipe(LINES, KRAKEN_READS, C), stays_local=True, job_answers={"review_certainty_bar": bad})
        assert not [r for r in plan["runs"] if r["job"] == "correct"], bad
        [skipped] = [x for x in plan["skipped"] if "not a number above 0 and up to 1" in str(x)]


def test_a_whole_page_review_is_priced_as_before_and_without_a_bar():
    [whole] = estimate([CORRECT], 10)["runs"]
    [lines] = estimate([A], 10)["runs"]
    assert whole["certainty_bar"] is None and whole["lines_to_send"] is None and whole["lines_basis"] is None
    assert whole["calls_per_page"] == 3, "the whole-page review is priced as before"
    assert lines["cost_usd"] != whole["cost_usd"]


def test_variant_a_on_this_mac_costs_nothing_and_an_unpriced_place_is_unpriced():
    [here] = estimate([{**A, "runs_on": "this-mac", "provider_override": "omlx"}], 10)["runs"]
    assert here["cost_usd"] == 0.0 and here["lines_to_send"] == 330
    [other] = estimate([{**A, "runs_on": "cluster:acenet"}], 10)["runs"]
    assert other["cost_usd"] is None
