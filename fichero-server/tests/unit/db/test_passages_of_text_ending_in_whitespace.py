"""A page whose text ends in whitespace is cut into its real passages and no tail scraps (#6780)."""

from __future__ import annotations

import pytest

from fichero_server.db.embeddings import split_text_passages

# A transcribed diary page of about 1,000 characters, the shape the measured project's pages had.
_DIARY_PAGE = (
    "Monday the 3rd of March. Rose early and walked down to the harbour before the bell, the boats "
    "already out and the wind from the north. Mother asked me to fetch the letters from the post office, "
    "and there was one from Tomás at last, written in Valparaíso in January. He says the voyage was long "
    "and the food poor, but that he has found work with a merchant who trades in hides and copper.\n\n"
    "In the afternoon the priest came to see Father about the boundary of the lower field. They talked "
    "a long while in the kitchen and I could hear them through the wall. Father would not give way, and "
    "the priest left without taking his coffee. Afterwards Father sat by the window and said nothing "
    "until supper. I mended the net for Andrés and read two chapters of the book the schoolmaster lent me.\n\n"
    "Rain in the evening, heavy, and the road to the church is mud again. I must write to Tomás tomorrow "
    "and tell him about the field, and about Elena, who is to be married at Easter to the miller's son."
)


@pytest.mark.parametrize("tail", ["\n", " ", "\n\n", "  \n"])
def test_text_ending_in_whitespace_is_cut_into_its_real_passages(tail: str) -> None:
    text = _DIARY_PAGE + tail
    max_chars, overlap = 512, 80

    passages = split_text_passages(text, document_id="p", page_id="p", max_chars=max_chars, overlap_chars=overlap)
    without_tail = split_text_passages(
        _DIARY_PAGE, document_id="p", page_id="p", max_chars=max_chars, overlap_chars=overlap
    )

    assert len(passages) <= len(text) // (max_chars - overlap) + 1
    assert [(p.anchor.char_start, p.anchor.char_end) for p in passages] == [
        (p.anchor.char_start, p.anchor.char_end) for p in without_tail
    ]
    for passage in passages:
        assert passage.text == text[passage.anchor.char_start : passage.anchor.char_end]
    assert passages[-1].anchor.char_end == len(_DIARY_PAGE)
