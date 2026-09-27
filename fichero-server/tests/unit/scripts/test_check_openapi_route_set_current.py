"""The committed OpenAPI contracts must list exactly the operations the engine serves.

On 2026-09-27 GET/PATCH /api/segments were served all day and absent from all three
contracts, while the only contract guard a lane runs compared `info.version` and printed
"All 3 contracts match the code". The Swift client is generated from those contracts, so a
route outside them is a route the app cannot call through the typed client.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[4]
_SCRIPT = ROOT / "scripts" / "check_openapi_route_set_current.py"
_SPEC = importlib.util.spec_from_file_location("check_openapi_route_set_current", _SCRIPT)
assert _SPEC and _SPEC.loader
route_set = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = route_set
_SPEC.loader.exec_module(route_set)  # type: ignore[attr-defined]

CODE = {("GET", "/api/segments"), ("PATCH", "/api/segments"), ("GET", "/api/health")}


def _contracts(root: Path, ops: set[tuple[str, str]]) -> None:
    paths: dict[str, dict] = {}
    for method, path in ops:
        paths.setdefault(path, {})[method.lower()] = {"responses": {}}
    paths.setdefault("/api/health", {})["parameters"] = []  # not an operation
    for relative in route_set.CONTRACTS:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({"paths": paths}))


def test_an_unchanged_tree_passes(tmp_path):
    """Over-fire check: a synced contract — including a path-level `parameters` key,
    which is not an operation — must not be reported."""
    _contracts(tmp_path, CODE)
    assert route_set.check(tmp_path, code=CODE) == 0


def test_a_route_served_but_absent_from_the_contract_fails(tmp_path, capsys):
    """The 2026-09-27 shape exactly: PATCH /api/segments served, not in the contract."""
    _contracts(tmp_path, CODE - {("PATCH", "/api/segments")})
    assert route_set.check(tmp_path, code=CODE) == 1
    assert "+ PATCH /api/segments" in capsys.readouterr().out


def test_a_route_no_longer_served_fails(tmp_path, capsys):
    """The other direction: a contract advertising a deleted route makes the generated
    client offer a call that 404s."""
    _contracts(tmp_path, CODE | {("DELETE", "/api/gone")})
    assert route_set.check(tmp_path, code=CODE) == 1
    assert "- DELETE /api/gone" in capsys.readouterr().out


def test_an_unreadable_contract_is_blind_not_a_pass(tmp_path):
    _contracts(tmp_path, CODE)
    (tmp_path / route_set.CONTRACTS[1]).write_text("{ not json")
    with pytest.raises(route_set.Blind):
        route_set.check(tmp_path, code=CODE)


def test_an_empty_route_set_is_blind_not_a_pass(tmp_path):
    """An app that served nothing is not the engine; an empty contract would 'match' it."""
    _contracts(tmp_path, set())
    with pytest.raises(route_set.Blind):
        route_set.check(tmp_path, code=set())


def test_the_real_contracts_match_the_real_routes():
    """Run as the gate runs it: a separate process, so the app import cannot leak into or
    borrow from this test session. Contracts were synced at c88c97763."""
    result = subprocess.run(
        [sys.executable, str(_SCRIPT)], cwd=ROOT, capture_output=True, text=True, timeout=300,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "matches all 3 contracts" in result.stdout


def test_the_version_guard_claims_only_what_it_checked():
    """`check_openapi_version_current` compares `info.version` only. Its old success line,
    "All 3 contracts match the code", was read as route freshness while three routes
    drifted. A success line that claims more than the check did is a false green."""
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_openapi_version_current.py")],
        cwd=ROOT, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "info.version matches pyproject" in result.stdout
    assert "contracts match the code" not in result.stdout
