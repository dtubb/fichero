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


def test_repo_duplicate_gate_has_no_unallowlisted_concerns():
    violations = check_duplicate_paths.find_violations()
    assert violations == {}


def test_allowlist_has_only_known_concerns():
    payload = json.loads(check_duplicate_paths.ALLOWLIST.read_text(encoding="utf-8"))
    known = set(check_duplicate_paths.collect().keys())
    for concern in payload.get("concerns", {}):
        assert concern in known
