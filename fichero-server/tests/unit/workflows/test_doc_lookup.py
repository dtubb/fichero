"""Document path-lookup tests (#2507).

`find_document_by_path` feeds the artifact-save path. A path that matches more
than one document is ambiguous — silently picking one is the #2430 class of bug
(artifact routed to the wrong doc). These tests pin the candidate-path forms and
assert the ambiguous case is logged loudly instead of resolved silently.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace

from fichero_server.workflows.tools._doc_lookup import (
    find_document_by_path,
    iter_document_lookup_paths,
    register_path_mapping,
    resolve_path_to_doc,
)


class _FakeDB:
    """Minimal stand-in: returns preset rows for an exact path= query."""

    def __init__(self, by_path: dict[str, list]):
        self._by_path = by_path

    def query(self, _model, path):
        return list(self._by_path.get(path, []))


def _doc(doc_id: str):
    return SimpleNamespace(id=doc_id)


# --- iter_document_lookup_paths ---------------------------------------------

def test_iter_paths_empty():
    assert iter_document_lookup_paths(None) == ()
    assert iter_document_lookup_paths("") == ()


def test_iter_paths_adds_relative_files_form():
    paths = iter_document_lookup_paths("/lib/x/files/a/b.pdf")
    assert paths == ("/lib/x/files/a/b.pdf", "files/a/b.pdf")


def test_iter_paths_no_files_segment_is_single():
    assert iter_document_lookup_paths("/tmp/loose.png") == ("/tmp/loose.png",)


# --- find_document_by_path ---------------------------------------------------

def test_find_single_match():
    db = _FakeDB({"files/a.pdf": [_doc("d1")]})
    assert find_document_by_path(db, object, "files/a.pdf").id == "d1"


def test_find_no_match_returns_none():
    assert find_document_by_path(_FakeDB({}), object, "files/missing.pdf") is None
    assert find_document_by_path(_FakeDB({}), object, None) is None


def test_find_falls_through_to_relative_candidate():
    # Absolute path misses, the derived files/... form hits.
    db = _FakeDB({"files/a/b.pdf": [_doc("d2")]})
    assert find_document_by_path(db, object, "/lib/files/a/b.pdf").id == "d2"


def test_ambiguous_path_logs_warning_and_returns_first(caplog):
    db = _FakeDB({"files/dup.pdf": [_doc("dA"), _doc("dB")]})
    with caplog.at_level(logging.WARNING):
        result = find_document_by_path(db, object, "files/dup.pdf")
    # Behaviour preserved: first match still returned...
    assert result.id == "dA"
    # ...but the ambiguity is now LOUD, naming the path and the shadowed id.
    assert any(
        rec.levelno == logging.WARNING
        and "share path" in rec.getMessage()
        and "dB" in rec.getMessage()
        for rec in caplog.records
    ), caplog.records


def test_single_match_does_not_warn(caplog):
    db = _FakeDB({"files/a.pdf": [_doc("d1")]})
    with caplog.at_level(logging.WARNING):
        find_document_by_path(db, object, "files/a.pdf")
    assert not caplog.records


# --- register_path_mapping ---------------------------------------------------

def test_register_first_mapping_is_silent(caplog):
    m: dict = {}
    with caplog.at_level(logging.WARNING):
        register_path_mapping(m, "files/a.pdf", "d1")
    assert m == {"files/a.pdf": "d1"}
    assert not caplog.records


def test_register_same_id_again_is_silent(caplog):
    m = {"files/a.pdf": "d1"}
    with caplog.at_level(logging.WARNING):
        register_path_mapping(m, "files/a.pdf", "d1")
    assert m == {"files/a.pdf": "d1"}
    assert not caplog.records


def test_register_conflicting_overwrite_warns_and_last_wins(caplog):
    m = {"files/a.pdf": "d1"}
    with caplog.at_level(logging.WARNING):
        register_path_mapping(m, "files/a.pdf", "d2")
    # Last-wins behaviour preserved...
    assert m == {"files/a.pdf": "d2"}
    # ...but the silent overwrite is now loud, naming both ids.
    assert any(
        rec.levelno == logging.WARNING
        and "already mapped to d1" in rec.getMessage()
        and "d2" in rec.getMessage()
        for rec in caplog.records
    ), caplog.records


# --- resolve_path_to_doc -----------------------------------------------------

def test_resolve_path_to_doc_both_forms():
    assert resolve_path_to_doc({"files/a.pdf": "d9"}, "/lib/files/a.pdf") == "d9"
    assert resolve_path_to_doc({"/lib/files/a.pdf": "d9"}, "/lib/files/a.pdf") == "d9"
    assert resolve_path_to_doc({}, "/lib/files/a.pdf") is None
