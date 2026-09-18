"""Unit tests for scripts/check_routes_use_action_layer.py (pins the
audited-action-layer rule, #4831).
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "check_routes_use_action_layer.py"
_SPEC = importlib.util.spec_from_file_location("check_routes_use_action_layer", _SCRIPT)
assert _SPEC and _SPEC.loader
_mod = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _mod
_SPEC.loader.exec_module(_mod)  # type: ignore[attr-defined]


ROUTE_COMPLIANT = '''
from fastapi import APIRouter, Depends

router = APIRouter()


@router.post("/thing")
async def create_thing(body: dict, db=Depends(get_db), ctx=Depends(action_context)):
    result = registry.invoke(db, "thing.create", body, ctx)
    return result
'''

ROUTE_BARE = '''
from fastapi import APIRouter, Depends

router = APIRouter()


@router.post("/thing")
async def create_thing(body: dict, db=Depends(get_db)):
    thing = Thing(**body)
    db.save(thing)
    return thing
'''

ROUTE_GET_NEVER_SCANNED = '''
from fastapi import APIRouter, Depends

router = APIRouter()


@router.get("/thing/{thing_id}")
async def get_thing(thing_id: str, db=Depends(get_db)):
    return db.get(Thing, thing_id)
'''

ROUTE_MULTI_ROUTER = '''
from fastapi import APIRouter, Depends

kg_entities_router = APIRouter()
bio_router = APIRouter()


@kg_entities_router.put("/entities/{entity_id}")
async def update_entity(entity_id: str, body: dict, db=Depends(get_db), ctx=Depends(action_context)):
    return registry.invoke(db, "entity.update", body, ctx)


@bio_router.delete("/entities/{entity_id}/bio")
async def delete_bio(entity_id: str, db=Depends(get_db)):
    entity = db.get(Entity, entity_id)
    entity.description = None
    db.save(entity)
    return {"ok": True}
'''

ROUTE_NESTED_ASYNC = '''
from fastapi import APIRouter, Depends

router = APIRouter()


def build_router():
    @router.patch("/nested-thing")
    async def patch_nested_thing(body: dict, db=Depends(get_db)):
        thing = db.get(Thing, body["id"])
        thing.name = body["name"]
        db.save(thing)
        return thing

    return patch_nested_thing
'''

ROUTE_UNRELATED_INVOKE_ELSEWHERE_IN_FILE = '''
from fastapi import APIRouter, Depends

router = APIRouter()


def some_helper(registry):
    return registry.invoke("unrelated", {}, None)


@router.post("/thing")
async def create_thing(body: dict, db=Depends(get_db)):
    thing = Thing(**body)
    db.save(thing)
    return thing
'''


def _write(tmp_path: Path, source: str, subdir: str = "kg", name: str = "thing.py") -> Path:
    root = (
        tmp_path
        / "fichero-server"
        / "src"
        / "fichero_server"
        / "api"
        / "routes"
        / subdir
    )
    root.mkdir(parents=True, exist_ok=True)
    path = root / name
    path.write_text(source, encoding="utf-8")
    return path


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(
        _mod,
        "ROOTS",
        [
            tmp_path / "fichero-server" / "src" / "fichero_server" / "api" / "routes" / "kg",
            tmp_path / "fichero-server" / "src" / "fichero_server" / "api" / "routes" / "entity",
        ],
    )
    monkeypatch.setattr(_mod, "ALLOWLIST_PATH", tmp_path / "allowlist.json")
    return tmp_path


def test_does_not_fire_on_a_route_that_calls_registry_invoke(tmp_path):
    _write(tmp_path, ROUTE_COMPLIANT)
    _, findings = _mod.scan_tree()
    assert findings == []


def test_fires_on_a_bare_mutating_route(tmp_path):
    _write(tmp_path, ROUTE_BARE)
    _, findings = _mod.scan_tree()
    assert any(f["function"] == "create_thing" for f in findings)


def test_get_routes_are_never_scanned(tmp_path):
    _write(tmp_path, ROUTE_GET_NEVER_SCANNED)
    total_routes, findings = _mod.scan_tree()
    assert total_routes == 0
    assert findings == []


def test_multi_router_file_scans_every_router_variable(tmp_path):
    """A file with more than one router variable (e.g. `kg_entities_router`,
    `bio_router`) must have EVERY router's decorated routes scanned, not just
    one hardcoded name."""
    _write(tmp_path, ROUTE_MULTI_ROUTER)
    total_routes, findings = _mod.scan_tree()
    assert total_routes == 2
    names = {f["function"] for f in findings}
    assert names == {"delete_bio"}
    assert "update_entity" not in names


def test_fires_on_a_decorator_on_a_nested_async_function(tmp_path):
    """A route handler decorated inside a nested (non-module-level) function
    body must still be found and scanned — the walk does not assume routes
    are only ever defined at module level."""
    _write(tmp_path, ROUTE_NESTED_ASYNC)
    total_routes, findings = _mod.scan_tree()
    assert total_routes == 1
    assert any(f["function"] == "patch_nested_thing" for f in findings)


def test_does_not_trace_through_helper_indirection(tmp_path):
    """An unrelated `registry.invoke(` call elsewhere in the same file (e.g.
    inside a helper function never called from the route) must NOT satisfy
    the route's own requirement — only a call inside the route's OWN body
    counts. This also proves the scan doesn't just grep the whole file."""
    _write(tmp_path, ROUTE_UNRELATED_INVOKE_ELSEWHERE_IN_FILE)
    _, findings = _mod.scan_tree()
    assert any(f["function"] == "create_thing" for f in findings)


def test_zero_routes_found_fails(tmp_path):
    (tmp_path / "fichero-server" / "src" / "fichero_server" / "api" / "routes" / "kg").mkdir(
        parents=True
    )
    (tmp_path / "fichero-server" / "src" / "fichero_server" / "api" / "routes" / "entity").mkdir(
        parents=True
    )
    rc = _mod.check()
    assert rc == 2


def test_allowlisted_violation_passes(tmp_path):
    path = _write(tmp_path, ROUTE_BARE)
    _mod.ALLOWLIST_PATH.write_text(json.dumps([
        {"file": str(path), "function": "create_thing", "class": "violation",
         "reason": "known, tracked", "issue": 4831},
    ]), encoding="utf-8")
    assert _mod.check() == 0


def test_allowlisted_by_design_passes_and_is_not_counted_as_debt(tmp_path, capsys):
    path = _write(tmp_path, ROUTE_BARE)
    _mod.ALLOWLIST_PATH.write_text(json.dumps([
        {"file": str(path), "function": "create_thing", "class": "by-design",
         "reason": "read-only: no db.save/delete anywhere in the body"},
    ]), encoding="utf-8")
    assert _mod.check() == 0
    out = capsys.readouterr().out
    assert "0 violation(s) [DEBT]" in out
    assert "1 by-design" in out


def test_by_design_entry_without_reason_fails(tmp_path):
    path = _write(tmp_path, ROUTE_BARE)
    _mod.ALLOWLIST_PATH.write_text(json.dumps([
        {"file": str(path), "function": "create_thing", "class": "by-design", "reason": ""},
    ]), encoding="utf-8")
    assert _mod.check() == 1


def test_violation_entry_without_issue_fails(tmp_path):
    path = _write(tmp_path, ROUTE_BARE)
    _mod.ALLOWLIST_PATH.write_text(json.dumps([
        {"file": str(path), "function": "create_thing", "class": "violation",
         "reason": "known, tracked"},
    ]), encoding="utf-8")
    assert _mod.check() == 1


def test_missing_class_field_fails(tmp_path):
    path = _write(tmp_path, ROUTE_BARE)
    _mod.ALLOWLIST_PATH.write_text(json.dumps([
        {"file": str(path), "function": "create_thing", "reason": "known", "issue": 4831},
    ]), encoding="utf-8")
    assert _mod.check() == 1


def test_stale_allowlist_entry_fails(tmp_path):
    _write(tmp_path, ROUTE_COMPLIANT)  # no findings at all
    _mod.ALLOWLIST_PATH.write_text(json.dumps([
        {"file": "fichero-server/src/fichero_server/api/routes/kg/gone.py",
         "function": "create_thing", "class": "violation", "reason": "no longer exists",
         "issue": 4831},
    ]), encoding="utf-8")
    assert _mod.check() == 1
