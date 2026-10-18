"""A missing source image is reported with the file and the folder, not just "not found" (#5019).

Spec: docs/contributor_manual/specs/ui/workflows.md, `workflows.run.missing-source-says-which-and-why`.
WHY: a Kraken run failed on Marshall Diaries pages and the message said only that a file could not be
found; the person could not tell which page or which folder the engine had lost.
"""
from __future__ import annotations

from fichero_server.execution.runner import _classify_provider_error


def test_a_missing_file_names_the_file_and_its_folder():
    out = _classify_provider_error("[Errno 2] No such file or directory: '/Users/x/Diaries/f. 12r.jpg'")
    assert out["category"] == "file_unavailable"
    assert "f. 12r.jpg" in out["message"]
    assert "/Users/x/Diaries" in out["message"]


def test_an_empty_path_names_nothing_it_does_not_know():
    out = _classify_provider_error("[Errno 2] No such file or directory: ''")
    assert out["category"] == "file_unavailable"
    assert "''" not in out["message"]
