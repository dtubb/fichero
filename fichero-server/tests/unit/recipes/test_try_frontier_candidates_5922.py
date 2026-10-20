"""source.recipe.reader-tiers.frontier-on-the-try-pages (#5922), slice 2: the Try's default candidates include the
frontier readers from the person's provider rows when pages may leave; the limit of three stays, and a frontier reader
left out for it is said."""
from types import SimpleNamespace as Card

from fichero_server.recipes import samples


def card(i, note=None):
    return Card(id=i, note=note or i)


OWN, KRAKEN, VISION = card("kraken:own"), card("kraken:other"), card("apple:vision")
CLAUDE, GEMINI = card("anthropic:claude@x", "Claude"), card("gemini:flash@y", "Gemini")


def test_a_frontier_reader_takes_a_place_beside_the_steps_own_and_the_best_local_one():
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
        "Gemini was not tried: a Try compares three readers. Name it to try it.")
    assert samples.left_out_sentence([CLAUDE, GEMINI]) == (
        "Claude and Gemini were not tried: a Try compares three readers. Name them to try them.")
    assert samples.left_out_sentence([]) is None
