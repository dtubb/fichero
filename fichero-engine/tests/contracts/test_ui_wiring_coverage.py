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
_MATRIX = _ROOT / "fichero-engine" / "tests" / "contracts" / "coverage_matrix.json"

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
    openapi_data = _mod.json.loads(_mod.OPENAPI.read_text())
    miss = set(_mod.unwired(surface, openapi_data))
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


def test_per_domain_coverage_only_improves() -> None:
    baseline_rows = {
        row["domain"]: row for row in _mod.json.loads(_MATRIX.read_text()).get("rows", [])
    }
    current_rows = {
        row["domain"]: row
        for row in _mod.coverage_matrix(_mod.json.loads(_mod.OPENAPI.read_text())).get("rows", [])
    }

    assert baseline_rows.keys() == current_rows.keys(), (
        "coverage_matrix.json domains drifted; regenerate with "
        "`python scripts/check_ui_wiring.py --matrix`"
    )

    regressions = []
    for domain, baseline in baseline_rows.items():
        current = current_rows[domain]
        if current["swiftui_unwired"] > baseline["swiftui_unwired"]:
            regressions.append(
                f"{domain}: swiftui_unwired {current['swiftui_unwired']} > {baseline['swiftui_unwired']}"
            )
        if current["cli_untested"] > baseline["cli_untested"]:
            regressions.append(
                f"{domain}: cli_untested {current['cli_untested']} > {baseline['cli_untested']}"
            )

    assert not regressions, "Per-domain coverage regressed:\n  " + "\n  ".join(regressions)
