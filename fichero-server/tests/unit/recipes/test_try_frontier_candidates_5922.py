"""source.recipe.reader-tiers.frontier-on-the-try-pages (#5922), slice 2: the Try's default candidates include the
frontier readers from the person's provider rows when pages may leave; the limit of three stays, and a frontier reader
left out for it is said."""
from types import SimpleNamespace as Card

import pytest

from fichero_server.recipes import samples


def card(i, note=None):
    return Card(id=i, note=note or i)


OWN, KRAKEN, VISION = card("kraken:own"), card("kraken:other"), card("apple:vision")
CLAUDE, GEMINI = card("anthropic:claude@x", "Claude"), card("gemini:flash@y", "Gemini")


def test_the_first_frontier_reader_listed_takes_a_place_beside_the_steps_own_and_the_best_local_one():
    chosen, left_out = samples.choose_try_candidates(OWN, [KRAKEN, VISION], [CLAUDE], limit=3)

    assert [c.id for c in chosen] == ["kraken:own", "anthropic:claude@x", "kraken:other"]
    assert left_out == []


def test_with_no_frontier_reader_the_candidates_are_what_they_were():
    chosen, left_out = samples.choose_try_candidates(OWN, [KRAKEN, VISION], [], limit=3)
    assert [c.id for c in chosen] == ["kraken:own", "kraken:other", "apple:vision"]
    assert left_out == []


def test_the_limit_of_three_stays_and_the_frontier_reader_left_out_for_it_is_named():
    chosen, left_out = samples.choose_try_candidates(OWN, [KRAKEN], [CLAUDE, GEMINI], limit=3)

    assert len(chosen) == 3
    assert [c.id for c in chosen] == ["kraken:own", "anthropic:claude@x", "kraken:other"]
    assert [c.note for c in left_out] == ["Gemini"]


def test_no_own_card_still_leaves_room_for_a_frontier_reader():
    chosen, _ = samples.choose_try_candidates(None, [KRAKEN, VISION, card("x")], [CLAUDE], limit=3)
    assert chosen[0].id == "anthropic:claude@x" and len(chosen) == 3


def test_a_card_is_never_listed_twice():
    chosen, _ = samples.choose_try_candidates(OWN, [OWN, KRAKEN], [CLAUDE, CLAUDE], limit=3)
    assert [c.id for c in chosen] == ["kraken:own", "anthropic:claude@x", "kraken:other"]


def test_the_wording_says_who_was_left_out_and_why():
    assert samples.left_out_sentence([GEMINI]) == (
        "Gemini was not tried: a Try compares three readers. Tick it under Models for your pages to try it.")
    assert samples.left_out_sentence([CLAUDE, GEMINI]) == (
        "Claude and Gemini were not tried: a Try compares three readers. Tick them under Models for your pages to try them.")
    assert samples.left_out_sentence([]) is None


# -- slice 3: variant A, "Kraken reads, then a cloud model re-reads only the unsure lines" -----------------------------
def _real(i, note, runs_on="this-mac"):
    from fichero_server.recipes.assemble import Card

    return Card(id=i, pin={"model": i}, jobs=frozenset({"read-a-line", "correct"}), scripts=None, languages=None,
                material=frozenset({"handwriting"}), runs_on=runs_on, note=note)


def test_variant_a_is_the_frontier_card_under_a_name_that_says_what_it_is():
    a = samples.variant_a_card(_real("anthropic:claude@x", "Claude.", "cloud:anthropic"))
    assert a.id == "variant-a:anthropic:claude@x"
    assert a.note == "Kraken, then Claude on the unsure lines"
    assert a.runs_on == "cloud:anthropic"


def test_variant_a_takes_a_place_after_the_local_candidates_and_is_named_when_left_out():
    variant = samples.variant_a_card(_real("anthropic:claude@x", "Claude", "cloud:anthropic"))
    chosen, left_out = samples.choose_try_candidates(OWN, [KRAKEN], [CLAUDE], limit=3, variant_a=variant)
    assert [c.id for c in chosen] == ["kraken:own", "anthropic:claude@x", "kraken:other"]
    assert [c.note for c in left_out] == ["Kraken, then Claude on the unsure lines"]
    chosen, left_out = samples.choose_try_candidates(OWN, [], [CLAUDE], limit=3, variant_a=variant)
    assert chosen[-1] is variant and left_out == []


def test_variant_a_keeps_the_reader_and_adds_a_cloud_correction_of_the_unsure_lines_only_in_the_copy():
    setup = {"recipe": {"steps": [{"id": "read-a-line", "job": "read-a-line", "model": {"model": "kraken"}},
                                  {"id": "names", "job": "find-names-tag-words"}]}}
    step = setup["recipe"]["steps"][0]
    card = samples.variant_a_card(_real("anthropic:claude@x", "Claude", "cloud:anthropic"))

    changed = samples._with_card(setup, step, card)

    ids = [s["id"] for s in changed["recipe"]["steps"]]
    assert ids == ["read-a-line", "correct", "names"]
    fix = changed["recipe"]["steps"][1]
    assert fix["settings"] == {"only_below_confidence": samples.UNSURE_BELOW}
    assert fix["model"] == {"model": "anthropic:claude@x"} and fix["runs_on"] == "cloud:anthropic"
    assert changed["recipe"]["steps"][0]["model"] == {"model": "kraken"}
    assert [s["id"] for s in setup["recipe"]["steps"]] == ["read-a-line", "names"]  # the project's setup is untouched


# -- review 623: variant A is priced by what it sends, not by every line ------------------------------------------------
def _column(card_id, cost, cer, *, local=False, state="done"):
    return {"card": card_id, "name": card_id, "local": local, "runs_on": "cloud:x", "cer": cer, "state": state,
            "cost_usd": cost}


def test_before_the_try_variant_a_says_up_to_and_other_cloud_readers_say_estimate():
    a = samples.variant_a_card(_real("anthropic:claude@x", "Claude", "cloud:anthropic"))
    assert samples.cost_figure(a, 0.05, False, None) == {
        "value": 0.05, "basis": "upper bound", "from": "up to this: it re-reads only the unsure lines, so it costs less"}
    assert samples.cost_figure(CLAUDE, 0.05, False, None)["basis"] == "estimate"


def test_after_the_try_the_measured_usage_replaces_the_estimate():
    a = samples.variant_a_card(_real("anthropic:claude@x", "Claude", "cloud:anthropic"))
    figure = samples.cost_figure(a, 0.05, False, {"model_calls": 3, "total_tokens": 900, "cost_usd": 0.002})
    assert (figure["value"], figure["basis"]) == (0.002, "measured")
    unpriced = samples.cost_figure(a, 0.05, False, {"model_calls": 3, "total_tokens": 900, "cost_usd": None})
    assert unpriced["basis"] == "upper bound"  # a call nobody could price is never read as $0


def test_a_variant_that_sent_few_lines_wins_on_cost_when_it_reads_as_well():
    from fichero_server.recipes import bakeoff

    columns = [
        _column("anthropic:claude@x", {"value": 0.05, "basis": "measured", "from": "run"}, 0.020),
        _column("variant-a:anthropic:claude@x", {"value": 0.002, "basis": "measured", "from": "run"}, 0.021),
    ]
    rows = samples.recommendation_rows(columns, pages=10, volume=100)
    assert rows[1]["cost_usd"]["value"] == pytest.approx(0.02)  # 0.002 on 10 pages is $0.02 for 100

    chosen = bakeoff.recommend(rows, volume=100, noise_band=0.01)

    assert chosen["card"] == "variant-a:anthropic:claude@x"
    assert chosen["cost_set_usd"] == pytest.approx(0.02)


def test_a_price_list_figure_is_not_a_measured_row():
    rows = samples.recommendation_rows(
        [_column("variant-a:x", {"value": 0.05, "basis": "upper bound", "from": "p"}, 0.02)], pages=10, volume=100)
    assert rows[0]["measured"] is False


def test_variant_a_keeps_the_projects_own_correction_and_its_bar():
    setup = {"recipe": {"steps": [
        {"id": "read-a-line", "job": "read-a-line", "model": {"model": "kraken"}},
        {"id": "correct", "job": "correct", "model": {"model": "mlx"}, "settings": {"only_below_confidence": 0.6,
                                                                                   "lenses": ["names"]}}]}}
    card = samples.variant_a_card(_real("anthropic:claude@x", "Claude", "cloud:anthropic"))

    steps = samples._with_card(setup, setup["recipe"]["steps"][0], card)["recipe"]["steps"]

    assert [s["id"] for s in steps] == ["read-a-line", "correct"]
    assert steps[1]["settings"] == {"only_below_confidence": 0.6, "lenses": ["names"]}
    assert steps[1]["model"] == {"model": "anthropic:claude@x"}


# -- slice 4 and review 625: the sentences on the Try result; a cost that could not be measured says so --------------
def test_a_cost_that_could_not_be_measured_says_why_and_keeps_the_figure_that_is_left():
    a = samples.variant_a_card(_real("anthropic:claude@x", "Claude", "cloud:anthropic"))
    figure = samples.cost_figure(a, 0.05, False, {"not_measured": "cost not measured: no record"})
    assert (figure["value"], figure["basis"], figure["from"]) == (0.05, "upper bound", "cost not measured: no record")
    unpriced = samples.cost_figure(CLAUDE, 0.05, False, {"model_calls": 2, "total_tokens": 9, "cost_usd": None})
    assert unpriced["from"] == "cost not measured: a call could not be priced" and unpriced["basis"] == "estimate"


def test_spent_reads_no_usage_as_a_reason_never_silence(monkeypatch, caplog):
    import fichero_server.workflows.activity as activity

    def boom(path):
        raise RuntimeError("no activity store")

    monkeypatch.setattr(activity, "get_activity_tracker", boom)
    said = samples._spent(Card(path="x"), ["t1"])
    assert said == {"not_measured": "cost not measured: no activity store"}
    assert "could not be measured" in caplog.text


def test_cards_for_reports_the_frontier_readers_the_limit_left_out():
    chosen, left_out = samples.choose_try_candidates(OWN, [KRAKEN], [CLAUDE, GEMINI], limit=3)
    assert len(chosen) == 3 and samples.left_out_sentence(left_out).startswith("Gemini was not tried")
