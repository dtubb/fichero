"""`recipes-run.engine.failure-in-words` (#6212): a job whose body fails on a slip in Fichero's own code says so in words on
its row, never the bare exception text ("'x'" for a KeyError); a failure that already says why keeps its words."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from fichero_server.core.failure_text import MissingInWords

from fichero_server.execution import jobs


def test_a_key_error_reads_as_words():
    said = jobs.failed_reason("embed-page", KeyError("x"))
    assert said.startswith(f"{jobs.kind_name('embed-page')} could not finish: ")
    assert "KeyError" in said and "'x'" in said


def test_a_worded_failure_keeps_its_words():
    assert jobs.failed_reason("embed-page", RuntimeError("the model file is missing")) == "the model file is missing"


def test_an_empty_failure_is_never_blank():
    assert jobs.failed_reason("embed-page", TimeoutError()) == "TimeoutError (no message)"


def test_a_worded_refusal_keeps_its_words_and_no_slip_label():
    # reviewer b23: local_model_catalog refuses "No local runtime installs model: X" in words; #6240: its own class
    said = jobs.failed_reason("embed-page", MissingInWords("No local runtime installs model: x"))
    assert said == "No local runtime installs model: x"


@pytest.mark.parametrize("key", ["Read each line", "Find the names on a page", "Read the diarist's hand.",
                                 "No local runtime installs model: x"])
def test_a_missing_key_is_a_slip_whatever_its_words(key):
    # reviewer b24/b25 (#6240): a plain KeyError is a missing key, a slip in Fichero, even when it reads like a sentence
    said = jobs.failed_reason("embed-page", KeyError(key))
    assert "could not finish" in said and "KeyError" in said


@pytest.mark.parametrize("words", ["no job 'j1' in this project", "Unknown managed MLX model: m"])
def test_the_engines_worded_refusals_keep_their_words_and_are_still_key_errors(words):
    assert jobs.failed_reason("embed-page", MissingInWords(words)) == words
    assert str(MissingInWords(words)) == words and isinstance(MissingInWords(words), KeyError)  # routes 404 on KeyError


def test_the_engine_raises_no_worded_key_error():
    """#6240: a refusal in words is a `MissingInWords`, never a `KeyError("...")` that could pass for a missing key."""
    src = Path(jobs.__file__).parents[1]
    worded = [f"{p.relative_to(src)}:{n}" for p in src.rglob("*.py")
              for n, line in enumerate(p.read_text().splitlines(), 1)
              if re.search(r"raise KeyError\(f?[\"']", line)]
    assert worded == []
