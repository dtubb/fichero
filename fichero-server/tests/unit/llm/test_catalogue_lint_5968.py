"""Catalogue entries are concise and never analyse (`catalogue.model-entry-is-concise`, #5968)."""
from pathlib import Path

import pytest

from fichero_server.llm import catalogue_lint as lint
from fichero_server.llm.prompts import load_prompt

GOLDEN = sorted((Path(__file__).parent / "golden_catalogue").glob("*.txt"))
PHRASES = ("suggests", "likely", "appears to", "reveals", "highlights", "sheds light", "provides insight", "important", "notably")


def words(n: int) -> str:
    return " ".join(f"w{i}" for i in range(n))


def test_over_200_words_is_an_error():
    assert lint.check(words(201))[0]
    assert not lint.check(words(200))[0]


def test_under_150_is_a_warning_for_a_long_item_and_nothing_for_a_short_record():
    errors, warnings = lint.check(words(100))
    assert not errors and warnings
    assert lint.check(words(100), long_item=False) == ([], [])


@pytest.mark.parametrize("phrase", PHRASES)
def test_each_banned_phrase_is_an_error(phrase):
    assert lint.check(f"The deed {phrase} a debt. " + words(160))[0]


def test_a_repeated_sentence_is_padding():
    assert lint.check("The file holds letters. The file holds letters. " + words(150))[0]


def test_a_plain_entry_passes():
    assert lint.check(words(170)) == ([], [])


@pytest.mark.parametrize("path", GOLDEN, ids=lambda p: p.stem)
def test_recorded_outputs_pass_the_lint(path):
    errors, warnings = lint.check(path.read_text(), long_item=not path.stem.startswith("short-"))
    assert not errors and not warnings, (errors, warnings)


@pytest.mark.parametrize("tool, name", [("catalogue", "narrative"), ("catalogue", "folder")])
def test_every_catalogue_prompt_states_the_cap_and_bans_analysis(tool, name):
    text = load_prompt(tool, name, output_language="English")
    assert "NEVER longer than 200 words" in text and "NO ANALYSIS" in text
    assert all(p in text for p in ("suggests", "reveals", "notably"))


def test_the_folder_and_collection_summaries_use_the_folder_prompt():
    import inspect

    from fichero_server.workflows.tools import summarize

    source = inspect.getsource(summarize)
    assert source.count('load_prompt("catalogue", "folder"') == 2
    assert "common themes" not in source
