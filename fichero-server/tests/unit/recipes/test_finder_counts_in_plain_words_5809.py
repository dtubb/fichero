"""The finder's counts are plain words from the engine, and Transkribus says why it is not searched (#5809).

WHY: the Find a Reader sheet said "14 ship with Fichero" and "0 on this Mac", which does not say which shipped models are
installed and which still need a download; Transkribus read 'not searched' with no reason and nothing to do.
"""

from __future__ import annotations

from fichero_server.recipes import discovery
from fichero_server.recipes.assemble import Card


def _card(name: str, installed: bool | None) -> Card:
    return Card(name, {"hf": f"x/{name}", "revision": "main"}, frozenset({"read-a-line"}), None, None, frozenset(),
                installed=installed)


def test_shipped_models_say_how_many_are_here_and_how_many_need_a_download():
    said = discovery.shipped_words([_card("a", True), _card("b", False), _card("c", False)])
    assert said == "3 available: 1 here, 2 to download"  # "Available" since #5812


def test_all_shipped_models_here_says_so():
    assert discovery.shipped_words([_card("a", True)]) == "1 available, all on this Mac"
    assert discovery.shipped_words([_card("a", True), _card("b", True)]) == "2 available, all on this Mac"


def test_a_model_that_needs_no_download_counts_as_on_this_mac():
    assert "all on this Mac" in discovery.shipped_words([_card("a", None), _card("b", True)])


def test_nothing_shipped_says_so():
    assert discovery.shipped_words([]) == "Nothing available for this step"


def test_your_own_models_are_counted_in_words_not_as_a_bare_zero():
    assert discovery.installed_words(0, text=False) == "None of your own on this Mac"
    assert discovery.installed_words(2, text=False) == "2 of your own on this Mac"
    assert "server" in discovery.installed_words(1, text=True)


def test_every_line_stays_one_short_sentence():
    """The finder's rule (test_reader_finder_5660): each source's line is at most 48 characters."""
    lines = [discovery.shipped_words([_card(str(i), False) for i in range(14)]), discovery.TRANSKRIBUS_NOT_SEARCHED,
             discovery.installed_words(12, text=True), discovery.installed_words(0, text=False)]
    assert all(len(line) <= 48 for line in lines), lines


def test_transkribus_says_why():
    assert discovery.TRANSKRIBUS_NOT_SEARCHED == "Transkribus: Fichero can't list its models"


def test_discover_uses_those_words():
    from fichero_server.recipes.assemble import Answers

    _cards, sources = discovery.discover(Answers(), online=False, job="read-a-line")
    by = {s["source"]: s["detail"] for s in sources}
    assert " available" in by["shipped"]
    assert by["transkribus"] == discovery.TRANSKRIBUS_NOT_SEARCHED
