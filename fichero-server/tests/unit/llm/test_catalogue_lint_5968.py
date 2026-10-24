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


# --- enforced at write time (## 724): retry once with the finding, cut at a sentence end, flag what remains ---

import asyncio  # noqa: E402


def sentences(n_words: int) -> str:
    """Sentences of ten words each, n_words in all."""
    return " ".join(f"{' '.join(['word'] * 9)} w{i}." for i in range(n_words // 10))  # nine words, then a tenth that ends it


def test_a_banned_word_inside_a_quotation_is_the_records_own():
    assert lint.check('The letter states "this is important" in the margin. ' + words(160))[0] == []


def test_a_260_word_answer_is_retried_then_cut_to_200_at_a_sentence_end():
    asked: list[str] = []

    async def ask(note):
        asked.append(note)
        return sentences(260)  # the model does it again

    entry, flags = asyncio.run(lint.enforce(sentences(260), ask))
    assert len(asked) == 1 and "260 words" in asked[0]
    assert len(entry.split()) <= 200 and entry.endswith(".") and flags == []


def test_a_retry_that_fixes_it_is_stored_as_it_came():
    async def ask(note):
        return sentences(180)

    entry, flags = asyncio.run(lint.enforce(sentences(260), ask))
    assert len(entry.split()) == 180 and flags == []


def test_a_reveals_answer_is_retried_then_flagged_never_dropped():
    async def ask(note):
        return "The deed reveals a debt. " + sentences(160)

    entry, flags = asyncio.run(lint.enforce("The deed reveals a debt. " + sentences(160), ask))
    assert "reveals" in entry and any("reveals" in f for f in flags)


def test_a_clean_entry_is_not_asked_again():
    async def ask(note):
        raise AssertionError("no retry for a clean entry")

    assert asyncio.run(lint.enforce(sentences(170), ask)) == (sentences(170), [])


def test_the_catalogue_narrative_is_held_to_the_cap_and_the_flag_is_reported(monkeypatch):
    from fichero_server.workflows.tools import catalogue

    calls: list[str] = []

    async def fake_chat(text, *, config, system, permissive_guardrails):
        calls.append(system)
        return "The file reveals much. " + sentences(250)

    sink: list[str] = []
    entry = asyncio.run(catalogue._enforced("source", None, "RULES", sink, ask=fake_chat))
    assert len(calls) == 2 and "RULES" in calls[0] and "broke the rules" in calls[1]
    assert len(entry.split()) <= 200 and any("reveals" in f for f in sink)


def test_the_live_narrative_uses_the_registered_prompt_not_an_inline_150_300():
    import inspect

    from fichero_server.workflows.tools import catalogue

    assert "150-300" not in inspect.getsource(catalogue)


def test_a_quoted_banned_word_is_the_records_only_if_verbatim_in_the_source():
    record = "The margin note reads: this debt is important to the heirs."
    own = 'The letter states "this debt is important to the heirs" in the margin. ' + words(160)
    framed = 'The letter calls the debt "a grave matter, and important" to its writer. ' + words(160)
    assert lint.check(own, source=record)[0] == []
    assert lint.check(framed, source=record)[0]  # the model's own framing in quote marks is still its analysis
    assert lint.check(framed)[0] == []  # no source to compare with: every quotation is taken as the record's


def test_a_chunked_retry_resends_the_synthesis_not_the_whole_text(monkeypatch):
    import asyncio as aio

    import fichero_server.llm as llm
    from fichero_server.llm import LLMConfig
    from fichero_server.workflows.tools import llm_base

    sent: list[str] = []

    async def fake_chat(prompt, *, config, system):
        sent.append(prompt)
        return "The file reveals much. " + sentences(170) if prompt.startswith("Section 1 notes") else "note"

    monkeypatch.setattr(llm, "chat", fake_chat)
    big = "x" * 300
    aio.run(llm_base.process_text(
        big, "PROMPT", LLMConfig(provider="p", model="m"), "", None, llm_base.LLMToolConfig(artifact_type="t"),
        chunk_size_chars=100, save_to_db=False, catalogue_entry=True))
    finals = [p for p in sent if p.startswith("Section 1 notes")]
    assert len(finals) == 2 and finals[0] == finals[1] and big not in sent[-1]
