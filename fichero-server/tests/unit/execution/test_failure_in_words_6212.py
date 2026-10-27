"""`recipes-run.engine.failure-in-words` (#6212): a job whose body fails on a slip in Fichero's own code says so in words on
its row, never the bare exception text ("'x'" for a KeyError); a failure that already says why keeps its words."""
from __future__ import annotations

from fichero_server.execution import jobs


def test_a_key_error_reads_as_words():
    said = jobs.failed_reason("embed-page", KeyError("x"))
    assert said.startswith(f"{jobs.kind_name('embed-page')} could not finish: ")
    assert "KeyError" in said and "'x'" in said


def test_a_worded_failure_keeps_its_words():
    assert jobs.failed_reason("embed-page", RuntimeError("the model file is missing")) == "the model file is missing"


def test_an_empty_failure_is_never_blank():
    assert jobs.failed_reason("embed-page", TimeoutError()) == "TimeoutError (no message)"
