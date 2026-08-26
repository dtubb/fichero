"""The prompt-requested "[Script: …]" line never reaches page_content.

The HTR/paleography prompts ask the model to open (some models: close) with a
single bracketed classification line. That line is metadata (Daniel,
2026-08-25: "it's not in the content text") — `split_script_classification`
is the one seam that pulls it out before content promotion in llm_base.
"""

from fichero_server.workflows.tools.llm_base import split_script_classification

NOTE = "[Script: itálica; century: 21st; language: English]"
BODY = "Primera línea del texto.\nSegunda línea."


def test_leading_note_is_stripped_and_returned():
    cleaned, note = split_script_classification(f"{NOTE}\n{BODY}")
    assert cleaned == BODY
    assert note == NOTE


def test_trailing_note_is_stripped_and_returned():
    cleaned, note = split_script_classification(f"{BODY}\n{NOTE}")
    assert cleaned == BODY
    assert note == NOTE


def test_text_without_note_is_untouched():
    cleaned, note = split_script_classification(BODY)
    assert cleaned == BODY
    assert note is None


def test_mid_document_bracket_line_is_document_text():
    text = f"Antes.\n{NOTE}\nDespués."
    cleaned, note = split_script_classification(text)
    assert cleaned == text
    assert note is None


def test_note_only_page_yields_empty_content():
    cleaned, note = split_script_classification(f"{NOTE}\n")
    assert cleaned == ""
    assert note == NOTE
