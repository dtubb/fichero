"""Programmatic UI/CLI wiring-coverage gate (runs in CI via pytest).

Asserts every backend endpoint in openapi.json is either CALLED from the
hand-written SwiftUI app and CLI command layers (by raw URL path), or is
explicitly listed in that surface's allowlist with a reason.

This is the same deterministic, token-free philosophy as the OpenAPI drift
check: a NEW endpoint added without wiring it into a surface — or allowlisting
it — fails CI. The allowlist files double as the frontend/CLI wiring backlog.

Caveat: detection is by raw URL path (the app/CLI build requests by path). An
endpoint called only via a generated-client METHOD name would read as
"unwired" — that just means an extra (harmless) allowlist entry; it never
hides a real new endpoint.

To refresh the baseline after intentionally wiring/​adding endpoints:
    python scripts/check_ui_wiring.py --write-allowlist
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
_CHECKER = _ROOT / "scripts" / "check_ui_wiring.py"

_spec = importlib.util.spec_from_file_location("check_ui_wiring", _CHECKER)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

_CLI_INTENTIONAL_ALLOWLIST = {
    "/api/activity/stream",
    "/api/storage/debug/{doc_id}",
    "/api/tasks/tasks/health",
    "/api/workflow-execution/stream/{thread_id}",
}


@pytest.mark.parametrize("surface_name", list(_mod.SURFACES.keys()))
def test_no_unwired_unallowlisted_endpoints(surface_name: str) -> None:
    surface = _mod.SURFACES[surface_name]
    miss = set(_mod.unwired(surface))
    allow = _mod.load_allowlist(surface, surface_name)
    allowed = set(allow.get("paths", {}).keys())
    drift = sorted(miss - allowed)
    assert not drift, (
        f"{len(drift)} endpoint(s) are not called from the {surface_name} surface "
        f"and not allowlisted — wire them in, or add to the {surface_name} allowlist "
        f"with a reason:\n  " + "\n  ".join(drift)
    )


def test_cli_allowlist_stays_small_and_intentional() -> None:
    allow = _mod.load_allowlist(_mod.SURFACES["cli"], "cli")
    allowed = set(allow.get("paths", {}).keys())
    assert allowed <= _CLI_INTENTIONAL_ALLOWLIST
    assert len(allowed) <= len(_CLI_INTENTIONAL_ALLOWLIST)
