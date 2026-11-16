"""Every failure kind the engine can name carries its words and its fix (#6354, #6584; owner 2026-11-13: error codes do not
help, every error needs a solution; `activity.pane.failure-with-its-fix-in-the-row`, `run-failure-alerts.md` decision 9).

Spec: docs/contributor_manual/specs/ui/activity-pane.md, docs/contributor_manual/specs/ai/run-failure-alerts.md.
"""
from __future__ import annotations

import re
import typing

from fichero_server.llm import failure

_WHERE = {"name": "OpenRouter", "stopped": "", "kept": "", "model": "Qwen 2 VL", "detail": "", "step": "Read lines",
          "kind_exc": "KeyError"}


def test_every_kind_in_the_table_has_words_and_a_fix():
    kinds = set(typing.get_args(failure.Kind))
    assert kinds <= set(failure._WORDS), f"kinds with no row in the table: {kinds - set(failure._WORDS)}"
    for kind, build in failure._WORDS.items():
        words, fix, acts = build(**_WHERE)
        assert words.strip() and fix.strip(), f"{kind}: no words or no fix"
        assert acts, f"{kind}: no action a person can take"
        assert all(a.kind for a in acts), kind


def test_every_kind_has_row_words_of_at_most_eight_tokens():
    kinds = set(typing.get_args(failure.Kind))
    assert kinds <= set(failure._ROW_WORDS), f"kinds with no row words: {kinds - set(failure._ROW_WORDS)}"
    for kind in kinds:
        words = failure.row_words(kind, name="OpenRouter", model="Qwen 2 VL")
        assert 1 <= len(words.split()) <= 8, f"{kind}: {words!r}"
        assert not words.endswith("."), f"{kind}: a row's words are not a sentence"
    built = failure._build("no-credit", None, None, "", step="Read", provider="openrouter")
    assert built.row_words == "Out of credit at OpenRouter"


def test_the_words_name_no_code_status_or_exception_type():
    for kind, build in failure._WORDS.items():
        words, fix, _ = build(**_WHERE)
        for text in (words, fix):
            assert not re.search(r"\b(?:4\d\d|5\d\d)\b", text), f"{kind}: an HTTP status in the words: {text}"
            assert "Traceback" not in text and "Error:" not in text, f"{kind}: exception text in the words: {text}"
        if kind != "unexpected":  # `unexpected` names the exception's type on purpose, as the bug report's handle
            assert "Error" not in words and "Exception" not in words, f"{kind}: {words}"


# --- the kinds the release showed bare (#6597, `activity.failure.no-raw-text-ever`) -------------------------------------------


def _stub_failures():
    import duckdb

    from fichero_server.kept_export import ExportFolderGone

    return {
        "model-broken": failure.ModelBrokenError("bge-m3"),
        "library-closed": duckdb.ConnectionException("Connection Error: Connection already closed: the library "
                                                     "/Volumes/Archive/Proj.fichero/fichero.duckdb was closed"),
        "export-folder-gone": ExportFolderGone("/Volumes/Archive/Letters is not there any more; choose the export's folder again."),
    }


def test_the_three_bare_kinds_list_with_their_words_and_their_fix():
    said = {"model-broken": "bge-m3 could not be loaded", "library-closed": "Paused: the project closed",
            "export-folder-gone": "The export folder is gone"}
    for kind, exc in _stub_failures().items():
        built = failure.classify(exc)
        assert built.kind == kind, (kind, built.kind)
        assert built.row_words == said[kind]
        assert built.fix.strip() and built.actions, kind
        for text in (built.row_words, built.words, built.fix):
            assert "Error" not in text and "/Users/" not in text and "[" not in text and "/Volumes/" not in text, (kind, text)
