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
    figure = samples.cost_figure(a, 0.05, False, None)
    assert (figure["value"], figure["basis"], figure["measured"], figure["why"]) == (0.05, "upper bound", False, None)
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
        _column("anthropic:claude@x", {"value": 0.05, "basis": "measured", "measured": True, "from": "run"}, 0.020),
        _column("variant-a:anthropic:claude@x", {"value": 0.002, "basis": "measured", "measured": True, "from": "run"}, 0.021),
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


# -- review 630: the contract is `measured` and `why`, typed; English is never the contract --------------------------
def test_measured_is_the_flag_a_client_reads_not_the_wording():
    a = samples.variant_a_card(_real("anthropic:claude@x", "Claude", "cloud:anthropic"))
    assert samples.cost_figure(a, 0.05, False, {"model_calls": 3, "total_tokens": 9, "cost_usd": 0.002})["measured"] is True
    assert samples.cost_figure(a, 0.05, True, None)["measured"] is True  # free on this Mac
    lost = samples.cost_figure(a, 0.05, False, {"not_measured": "cost not measured: no record"})
    assert lost["measured"] is False and lost["why"] == "cost not measured: no record"


def test_the_try_result_is_a_typed_answer_that_keeps_what_it_does_not_name():
    from fichero_server.api.routes.system.recipes import StageTryResult

    answer = StageTryResult.model_validate({
        "state": "done", "stage": "read", "pages": ["p1"], "left_out": "Gemini was not tried: …",
        "per_page_extra": {"kept": 1},
        "candidates": [{"card": "variant-a:x", "local": False, "per_page": [{"id": "p1"}],
                        "cost_usd": {"value": 0.05, "basis": "upper bound", "from": "up to this", "measured": False,
                                     "why": "cost not measured: no record"}}],
        "recommendation": {"card": "c", "name": "n", "cer": 0.02, "local": True, "sentence": "s"}})
    dumped = answer.model_dump(by_alias=True)
    assert dumped["candidates"][0]["cost_usd"]["from"] == "up to this"
    assert dumped["candidates"][0]["cost_usd"]["measured"] is False
    assert dumped["candidates"][0]["per_page"] == [{"id": "p1"}] and dumped["per_page_extra"] == {"kept": 1}
    assert answer.recommendation.sentence == "s" and answer.left_out.startswith("Gemini")


# -- review 632 ------------------------------------------------------------------------------------------------------
def test_a_result_stored_before_the_flag_reads_measured_from_its_basis():
    from fichero_server.api.routes.system.recipes import TryCost

    assert TryCost.model_validate({"value": 0.04, "basis": "measured", "from": "run"}).measured is True
    assert TryCost.model_validate({"value": 0.04, "basis": "estimate", "from": "list"}).measured is False
    assert TryCost.model_validate({"value": None, "basis": "unknown", "from": "x"}).measured is False
    # a stored flag is never overridden by the basis
    assert TryCost.model_validate({"value": 0.04, "basis": "measured", "measured": False, "from": "x"}).measured is False


def test_the_try_route_answers_a_stored_result_typed_and_keeps_the_extras(client, db, with_material):
    """GET /api/recipes/stages/{stage}/try over a stored result file: the typed fields come back typed (an OLD
    candidate with no `measured` reads it from its basis), and what the model does not name passes through."""
    import json
    from pathlib import Path

    answers = {"purposes": ["transcribe"], "languages": ["es"], "scripts": ["Latn"], "materials": ["handwriting"],
               "jobs": ["find-regions"], "cloud_allowed": False}
    recipe = client.post("/api/recipes/assemble", json=answers).json()
    assert client.put("/api/recipes/project", json={"answers": answers, "recipe": recipe}).status_code == 200
    samples._write(Path(db.path).parent, "find-regions", {
        "stage": "find-regions", "pages": ["p1"], "tried_at": "2026-10-20T10:00:00", "state": "done",
        "left_out": "Gemini was not tried: a Try compares three readers.", "how": "its own steps on a copy of these pages",
        "per_page_extra": {"kept": 1},
        "candidates": [{"card": "c1", "name": "One", "local": False, "runs_on": "cloud:x", "state": "done", "cer": 0.02,
                        "seconds": 3.0, "per_page": [{"id": "p1"}],
                        "cost_usd": {"value": 0.04, "basis": "measured", "from": "run"}}],
        "recommendation": {"card": "c1", "name": "One", "cer": 0.02, "local": False, "sentence": "One reads best."}})

    got = client.get("/api/recipes/stages/find-regions/try")

    assert got.status_code == 200, got.text
    body = json.loads(got.text)
    assert body["left_out"].startswith("Gemini") and body["recommendation"]["sentence"] == "One reads best."
    column = body["candidates"][0]
    assert column["cost_usd"] == {"value": 0.04, "basis": "measured", "measured": True, "why": None, "from": "run"}
    assert column["seconds"] == 3.0 and column["per_page"] == [{"id": "p1"}] and body["per_page_extra"] == {"kept": 1}
