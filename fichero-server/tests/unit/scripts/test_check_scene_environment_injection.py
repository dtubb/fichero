"""Unit tests for scripts/check_scene_environment_injection.py (#4513 guardrail).

The point of this file is the NEGATIVE fixture. A guardrail that has never been
observed to fail on its own bad case proves nothing about the tree it guards
(guardrails-must-match-granularity), so every rule here is asserted to FIRE on a
constructed violation as well as stay quiet on the clean shape.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[4] / "scripts"
_SCRIPT = _SCRIPTS / "check_scene_environment_injection.py"
sys.path.insert(0, str(_SCRIPTS))  # the script imports its sibling `_check_floor`
_SPEC = importlib.util.spec_from_file_location("check_scene_environment_injection", _SCRIPT)
assert _SPEC and _SPEC.loader
_mod = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _mod
_SPEC.loader.exec_module(_mod)  # type: ignore[attr-defined]

scan = _mod.scan
CONTRACTS = _mod.FIXTURE_CONTRACTS


def _fixture(tmp_path: Path):
    workspace, manager = _mod.build_fixture(tmp_path)
    return tmp_path, workspace, manager


# ---------------------------------------------------------------------------
# Rule 1 — the static walk FIRES on a scene missing an injection
# ---------------------------------------------------------------------------

def test_scene_missing_injection_is_reported(tmp_path):
    app_dir, workspace, manager = _fixture(tmp_path)
    found, _ = scan(app_dir, workspace, manager, detached=CONTRACTS)
    assert "bad (Window) needs ArtifactService" in found


def test_scene_that_injects_is_not_reported(tmp_path):
    app_dir, workspace, manager = _fixture(tmp_path)
    found, _ = scan(app_dir, workspace, manager, detached=CONTRACTS)
    assert not [key for key in found if key.startswith("good (Window)")]


def test_optional_read_is_not_required(tmp_path):
    """`@Environment(T.self) private var t: T?` is a deliberate opt-out."""
    app_dir, workspace, manager = _fixture(tmp_path)
    (app_dir / "Panes.swift").write_text(
        "struct ArtifactsInspectorPane: View {\n"
        "  @Environment(ArtifactService.self) private var artifactService: ArtifactService?\n"
        '  var body: some View { Text("x") }\n}\n',
        encoding="utf-8",
    )
    found, _ = scan(app_dir, workspace, manager, detached=CONTRACTS)
    assert "bad (Window) needs ArtifactService" not in found


def test_reader_in_a_shared_file_is_not_credited_to_a_sibling_type(tmp_path):
    """Type granularity, not file granularity.

    `ArtifactDetailWindow` and `ArtifactsInspectorPane` really do share a file
    in this repo; a per-file scan reported a crash for a window that mounts
    neither the pane nor anything reading the service.
    """
    app_dir, workspace, manager = _fixture(tmp_path)
    (app_dir / "Panes.swift").write_text(
        "struct ArtifactsInspectorPane: View {\n"
        "  @Environment(ArtifactService.self) private var artifactService\n"
        '  var body: some View { Text("x") }\n}\n'
        'struct ArtifactDetailView: View { var body: some View { Text("y") } }\n',
        encoding="utf-8",
    )
    (app_dir / "Windows.swift").write_text(
        "struct GoodWindow: View { var body: some View { ArtifactsInspectorPane() } }\n"
        "struct BadWindow: View { var body: some View { ArtifactDetailView() } }\n",
        encoding="utf-8",
    )
    found, _ = scan(app_dir, workspace, manager, detached=CONTRACTS)
    assert "bad (Window) needs ArtifactService" not in found


def test_re_injecting_ancestor_prunes_the_requirement(tmp_path):
    app_dir, workspace, manager = _fixture(tmp_path)
    (app_dir / "Windows.swift").write_text(
        "struct GoodWindow: View { var body: some View { ArtifactsInspectorPane() } }\n"
        "struct BadWindow: View {\n"
        "  var body: some View { ArtifactsInspectorPane().environment(library.artifactService) }\n"
        "}\n",
        encoding="utf-8",
    )
    found, _ = scan(app_dir, workspace, manager, detached=CONTRACTS)
    assert "bad (Window) needs ArtifactService" not in found


# ---------------------------------------------------------------------------
# Rule 2 — the declared-contract tripwire
# ---------------------------------------------------------------------------

def test_undeclared_detached_scene_is_reported(tmp_path):
    app_dir, workspace, manager = _fixture(tmp_path)
    found, _ = scan(app_dir, workspace, manager, detached={})
    assert "good (Window) needs a declared environment contract" in found
    assert "bad (Window) needs a declared environment contract" in found


def test_stale_contract_entry_is_reported(tmp_path):
    app_dir, workspace, manager = _fixture(tmp_path)
    found, _ = scan(app_dir, workspace, manager, detached=CONTRACTS | {"ghost (Window)": "gone"})
    assert "ghost (Window) is a stale DETACHED_SCENES entry" in found


# ---------------------------------------------------------------------------
# Derivation + scene enumeration
# ---------------------------------------------------------------------------

def test_canonical_list_is_derived_from_the_workspace_root(tmp_path):
    app_dir, workspace, manager = _fixture(tmp_path)
    assert _mod.canonical_services(workspace, manager) == {"ArtifactService"}


def test_every_scene_is_examined(tmp_path):
    app_dir, workspace, manager = _fixture(tmp_path)
    _, examined = scan(app_dir, workspace, manager, detached=CONTRACTS)
    # 3 since the 2026-08-09 helper-credit rule: good, bad, and the scene
    # injecting via the shared libraryServiceEnvironment helper.
    assert examined == 3


def test_helper_injected_scene_stays_quiet(tmp_path):
    """A scene applying the shared helper is credited with exactly the
    services the helper's own .environment calls name (2026-08-09) — the
    Swift-side fix for the 13 document-detail gaps must not re-fire."""
    app_dir, workspace, manager = _fixture(tmp_path)
    found, _ = scan(
        app_dir, workspace, manager, detached=CONTRACTS,
        helper_env_file=app_dir / "LibraryServiceEnvironment.swift",
    )
    assert not any(key.startswith("helper (Window)") for key in found), sorted(found)


def test_helper_function_roots_are_inlined(tmp_path):
    """A `WindowGroup { libraryWindowRoot() }` root must resolve, not fall through."""
    app_dir, workspace, manager = _fixture(tmp_path)
    (app_dir / "App.swift").write_text(
        "struct DemoApp: App {\n"
        "  func windowRoot() -> some View { BadWindow() }\n"
        "  var body: some Scene {\n"
        '    Window("Bad", id: "bad") { windowRoot() }\n'
        "  }\n}\n",
        encoding="utf-8",
    )
    found, _ = scan(app_dir, workspace, manager, detached=CONTRACTS)
    assert "bad (Window) needs ArtifactService" in found
    assert "bad (Window) needs a resolvable root view" not in found


# ---------------------------------------------------------------------------
# Real repo gate
# ---------------------------------------------------------------------------

def test_repo_is_clean():
    found, examined = scan()
    assert examined >= 7, f"scanner went blind: only {examined} scenes"
    assert not found, f"scene environment-injection violations: {sorted(found)}"


def test_self_test_mode_passes():
    assert _mod._self_test() == 0
