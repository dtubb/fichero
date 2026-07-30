from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


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


def test_repo_duplicate_gate_has_no_unallowlisted_concerns():
    violations = check_duplicate_paths.find_violations()
    assert violations == {}


def test_allowlist_has_only_known_concerns():
    payload = json.loads(check_duplicate_paths.ALLOWLIST.read_text(encoding="utf-8"))
    known = set(check_duplicate_paths.collect().keys())
    for concern in payload.get("concerns", {}):
        assert concern in known
