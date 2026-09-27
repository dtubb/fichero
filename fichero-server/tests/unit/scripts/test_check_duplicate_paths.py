from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


_SCRIPT = (
    Path(__file__).resolve().parents[4] / "scripts" / "check_duplicate_paths.py"
)
_SPEC = importlib.util.spec_from_file_location("check_duplicate_paths", _SCRIPT)
assert _SPEC and _SPEC.loader
check_duplicate_paths = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = check_duplicate_paths
_SPEC.loader.exec_module(check_duplicate_paths)  # type: ignore[attr-defined]


def test_duplicate_detector_flags_unallowlisted_duplicates(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "dupes.py").write_text(
        """
from fastapi import APIRouter
from fichero_server.models.knowledge import KnowledgeEntity
router = APIRouter(prefix="/dupes")

@router.post("/x")
def create_a():
    KnowledgeEntity(id="a", canonical_name="a", entity_type="person")

@router.post("/x")
def create_b():
    KnowledgeEntity(id="b", canonical_name="b", entity_type="person")
""",
        encoding="utf-8",
    )

    violations = check_duplicate_paths.find_violations(src)
    assert "route:POST /dupes/x" in violations
    assert "kg_write:KnowledgeEntity" in violations


def test_duplicate_detector_uses_application_mount_prefixes(tmp_path):
    src = tmp_path / "src"
    routes = src / "api" / "routes"
    routes.mkdir(parents=True)
    for name in ("chat", "documents"):
        (routes / f"{name}.py").write_text(
            """
from fastapi import APIRouter
router = APIRouter()

@router.get("/workspaces")
def list_workspaces():
    return {}
""",
            encoding="utf-8",
        )
    (src / "api" / "main.py").write_text(
        """
_CORE_ROUTE_SPECS = [
    (chat.router, "/api/chat", ["chat"]),
    (documents.router, "/api/documents", ["documents"]),
]
""",
        encoding="utf-8",
    )

    concerns = check_duplicate_paths.collect(src)
    assert len(concerns["route:GET /api/chat/workspaces"]) == 1
    assert len(concerns["route:GET /api/documents/workspaces"]) == 1


def test_mount_prefix_resolves_via_main_imports_without_flat_shim(tmp_path):
    """A route imported from its domain package (no flat shim file) still gets
    its mounted prefix — this is what the #4071-#4077 shim deletions rely on.
    Without alias-based resolution the two /notes handlers below would collide
    at the bare path (the guardrail FIRES); with it, they stay distinct."""
    src = tmp_path / "src"
    for pkg in ("document", "research"):
        d = src / "api" / "routes" / pkg
        d.mkdir(parents=True)
        (d / "notes.py").write_text(
            """
from fastapi import APIRouter
router = APIRouter()

@router.get("/notes")
def list_notes():
    return {}
""",
            encoding="utf-8",
        )
    main = """
from fichero_server.api.routes.document import notes
from fichero_server.api.routes.research import notes as research_notes

_CORE_ROUTE_SPECS = [
    (notes.router, "/api", ["notes"]),
    (research_notes.router, "/api/research", ["research"]),
]
"""
    (src / "api" / "main.py").write_text(main, encoding="utf-8")

    concerns = check_duplicate_paths.collect(src)
    assert len(concerns["route:GET /api/notes"]) == 1
    assert len(concerns["route:GET /api/research/notes"]) == 1
    assert check_duplicate_paths.find_violations(src) == {}

    # Prove the rule still fires when resolution cannot disambiguate: drop the
    # import lines and both modules collapse onto the same bare path.
    (src / "api" / "main.py").write_text(
        "_CORE_ROUTE_SPECS = [\n    (notes.router, \"\", [\"notes\"]),\n]\n",
        encoding="utf-8",
    )
    assert "route:GET /notes" in check_duplicate_paths.find_violations(src)


def _duplicated_concerns() -> list[str]:
    return sorted(
        concern
        for concern, occs in check_duplicate_paths.collect().items()
        if len(occs) > 1
    )


@pytest.mark.parametrize("concern", _duplicated_concerns())
def test_repo_concern_is_allowlisted(concern):
    """One node per duplicated concern, not one for the whole repo.

    A single aggregate test meant one known defect (#5099: two handlers on
    `POST /api/links`) held the whole gate red, and xfailing it would have hidden
    every NEW duplicate behind it. Per-concern, the known one is listed in
    known_specification_failures.txt and a new one still fails on its own.
    """
    assert concern not in check_duplicate_paths.find_violations()


def test_allowlist_has_no_stale_or_unexplained_entries():
    """The allowlist had rotted to 19 names, 13 of them code that no longer built a
    row. An excuse that outlives its code is how a list becomes unreadable."""
    assert check_duplicate_paths.find_allowlist_problems() == []


_CALLER_OF_THE_DOOR = """
from fichero_server.models.knowledge import KnowledgeEntity

def upsert_entity(db, name):
    return KnowledgeEntity(canonical_name=name)

def extractor_a(db):
    upsert_entity(db, "a")

def extractor_b(db):
    upsert_entity(db, "b")
"""


def test_calling_the_canonical_writer_is_not_a_duplicate(tmp_path):
    """Over-fire check. Every extractor that routes through `upsert_entity` was being
    reported as a second write path — punishing exactly the convergence this guard
    exists to ask for, and burying real constructors in a list of callers."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "writer.py").write_text(_CALLER_OF_THE_DOOR, encoding="utf-8")
    occs = check_duplicate_paths.collect(src)["kg_write:KnowledgeEntity"]
    assert [o.symbol for o in occs] == ["upsert_entity"]


def test_a_second_constructor_is_still_a_duplicate(tmp_path):
    """Fires check: a function that builds the row itself is a second door."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "writer.py").write_text(
        _CALLER_OF_THE_DOOR
        + "\ndef sneaky(db):\n    db.save(KnowledgeEntity(canonical_name='x'))\n",
        encoding="utf-8",
    )
    assert "kg_write:KnowledgeEntity" in check_duplicate_paths.find_violations(src)


def _two_constructors(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "w.py").write_text(
        "def a():\n    KnowledgeClaim()\n\ndef b():\n    KnowledgeClaim()\n",
        encoding="utf-8",
    )
    return src


def test_a_vanished_allowlisted_writer_is_reported(tmp_path):
    src = _two_constructors(tmp_path)
    payload = {
        "_reasons": {"kg_write:KnowledgeClaim": "two verbs"},
        "concerns": {"kg_write:KnowledgeClaim": ["w.py::a", "w.py::b", "w.py::gone"]},
    }
    problems = check_duplicate_paths.find_allowlist_problems(src, payload)
    assert problems == ["kg_write:KnowledgeClaim: w.py::gone is no longer an occurrence — drop it"]


def test_an_allowlisted_concern_without_a_reason_is_reported(tmp_path):
    src = _two_constructors(tmp_path)
    payload = {"concerns": {"kg_write:KnowledgeClaim": ["w.py::a", "w.py::b"]}}
    problems = check_duplicate_paths.find_allowlist_problems(src, payload)
    assert problems == ["kg_write:KnowledgeClaim: allowlisted without a reason in `_reasons`"]


def test_a_current_explained_allowlist_is_clean(tmp_path):
    """Over-fire check for the staleness rule."""
    src = _two_constructors(tmp_path)
    payload = {
        "_reasons": {"kg_write:KnowledgeClaim": "two verbs"},
        "concerns": {"kg_write:KnowledgeClaim": ["w.py::a", "w.py::b"]},
    }
    assert check_duplicate_paths.find_allowlist_problems(src, payload) == []
