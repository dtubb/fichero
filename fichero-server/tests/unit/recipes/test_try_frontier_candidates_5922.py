"""source.recipe.reader-tiers.frontier-on-the-try-pages (#5922), slice 2: the Try's default candidates include the
frontier readers from the person's provider rows when pages may leave; the limit of three stays, and a frontier reader
left out for it is said."""
from types import SimpleNamespace as Card

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
