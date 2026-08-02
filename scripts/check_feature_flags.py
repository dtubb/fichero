#!/usr/bin/env python3
"""Feature-flag release-default guardrail.

Rule: work-in-progress feature flags must default off for release; see agents/ROADMAP.md.

Scans FeatureManager for AppStorage feature booleans that default ON directly or
are set ON in release-default reset paths. KNOWN_VIOLATIONS is the current list
of on-by-default flags, so this script passes today and fails when a new WIP flag
is enabled by default without being explicitly ratcheted.

Usage:
    scripts/check_feature_flags.py
    scripts/check_feature_flags.py --list
    scripts/check_feature_flags.py --help
"""
from __future__ import annotations

import hashlib
import re
import sys

from _check_floor import require_scan_floor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# #3743 split FeatureManager into FeatureManager.swift (the flag declarations) +
# FeatureManager+Tiers.swift (resetToV001 / release-default assignments), so scan
# the whole FeatureManager* unit, not just the one file.
FEATURE_MANAGER_FILES = sorted(
    (ROOT / "fichero" / "fichero" / "Models").glob("FeatureManager*.swift")
)
RULE_DOC = "agents/ROADMAP.md"

# Signatures are opaque, so every entry names the flag it grandfathers. Without
# that, a dead entry cannot be told from a live one by reading the file.
KNOWN_VIOLATIONS: dict[str, str] = {
    # --- defaults true at declaration ---
    "fichero/fichero/Models/FeatureManager.swift#1a6957a210": "#1922 baseline: search (declaration)",
    "fichero/fichero/Models/FeatureManager.swift#c31882dbfb": "#1922 baseline: library_advanced_views (declaration)",
    "fichero/fichero/Models/FeatureManager.swift#33b51f405c": "#1922 baseline: search_advanced_views (declaration)",
    "fichero/fichero/Models/FeatureManager.swift#db4b2c3292": "#1922 baseline: library_search_split_layouts (declaration)",
    "fichero/fichero/Models/FeatureManager.swift#2bf2895804": "shipped on in release profile v31: settings_general_tab (declaration)",
    "fichero/fichero/Models/FeatureManager.swift#5425a7c5e9": "shipped on in release profile v31: settings_engine_tab (declaration)",
    "fichero/fichero/Models/FeatureManager.swift#ee5015342c": "shipped on in release profile v31: settings_share_tab (declaration)",
    "fichero/fichero/Models/FeatureManager.swift#d6e549395d": "shipped on in release profile v31: settings_users_tab (declaration)",
    "fichero/fichero/Models/FeatureManager.swift#134dc4a6ac": "shipped on in release profile v31: settings_capture_tab (declaration)",
    "fichero/fichero/Models/FeatureManager.swift#291b07362d": "#3087 cutover, default-on RealityKit-ortho 2D renderer: canvas_realitykit_2d (declaration)",
    "fichero/fichero/Models/FeatureManager.swift#b402ce445f": "#3087 cutover, default-on contract RealityKit 3D renderer: canvas_realitykit_3d (declaration)",
    "fichero/fichero/Models/FeatureManager.swift#1377d97839": "shipped on in release profile v31: research (declaration)",
    "fichero/fichero/Models/FeatureManager.swift#6416ed9d9d": "#1922 baseline: knowledge_graph (declaration)",
    # --- set true in resetToV001() release defaults ---
    "fichero/fichero/Models/FeatureManager+Tiers.swift#6549e3bd15": "#1922 baseline: library_advanced_views (resetToV001)",
    "fichero/fichero/Models/FeatureManager+Tiers.swift#20213d49ea": "#1922 baseline: search (resetToV001)",
    "fichero/fichero/Models/FeatureManager+Tiers.swift#75ebc78947": "#1922 baseline: search_advanced_views (resetToV001)",
    "fichero/fichero/Models/FeatureManager+Tiers.swift#61bb9b568c": "#1922 baseline: library_icon_zoom_controls (resetToV001)",
    "fichero/fichero/Models/FeatureManager+Tiers.swift#8d6717ab7d": "#1922 baseline: workflows (resetToV001)",
    "fichero/fichero/Models/FeatureManager+Tiers.swift#caee915430": "#1922 baseline: workflow_editor_advanced_views (resetToV001)",
    "fichero/fichero/Models/FeatureManager+Tiers.swift#caa37e8508": "#1922 baseline: workflow_chains (resetToV001)",
    "fichero/fichero/Models/FeatureManager+Tiers.swift#ef77c099ff": "#1922 baseline: batches (resetToV001)",
    "fichero/fichero/Models/FeatureManager+Tiers.swift#173a3a2ca0": "#3365 review alpha/default surface: mcp (resetToV001)",
    "fichero/fichero/Models/FeatureManager+Tiers.swift#6d0c7c33c8": "#3365 review alpha/default surface: integrations (resetToV001)",
    "fichero/fichero/Models/FeatureManager+Tiers.swift#d01726468f": "#3365 review alpha/default surface: activity (resetToV001)",
    "fichero/fichero/Models/FeatureManager+Tiers.swift#5a48f8dbeb": "#3365 review alpha/default surface: settings_general_tab (resetToV001)",
    "fichero/fichero/Models/FeatureManager+Tiers.swift#72aecbc44a": "#3365 review alpha/default surface: settings_backend_tab (resetToV001)",
    "fichero/fichero/Models/FeatureManager+Tiers.swift#6932b9e151": "#3365 review alpha/default surface: settings_models_tab (resetToV001)",
    "fichero/fichero/Models/FeatureManager+Tiers.swift#277be999a1": "#3365 review alpha/default surface: settings_engine_tab (resetToV001)",
    "fichero/fichero/Models/FeatureManager+Tiers.swift#9ebf668b6b": "shipped on in release profile v31: settings_share_tab (resetToV001)",
    "fichero/fichero/Models/FeatureManager+Tiers.swift#16fbdfae71": "shipped on in release profile v31: settings_users_tab (resetToV001)",
    "fichero/fichero/Models/FeatureManager+Tiers.swift#276153fd1c": "shipped on in release profile v31: settings_capture_tab (resetToV001)",
    "fichero/fichero/Models/FeatureManager+Tiers.swift#3ab4c9e236": "#1922 baseline: workflow_tools_files (resetToV001)",
    "fichero/fichero/Models/FeatureManager+Tiers.swift#a381bd0df3": "#1922 baseline: workflow_import_export (resetToV001)",
    "fichero/fichero/Models/FeatureManager+Tiers.swift#7ef8e97466": "#1922 baseline: workflow_langgraph_preview (resetToV001)",
    "fichero/fichero/Models/FeatureManager+Tiers.swift#ca1127921a": "#1922 baseline: workflow_files_toolbar_button (resetToV001)",
    "fichero/fichero/Models/FeatureManager+Tiers.swift#04dca90e13": "#1922 baseline: workflow_run_on_selection (resetToV001)",
    "fichero/fichero/Models/FeatureManager+Tiers.swift#06113c2e9b": "#3087 cutover, default-on: canvas_realitykit_2d (resetToV001)",
    "fichero/fichero/Models/FeatureManager+Tiers.swift#984039bf73": "#3087 cutover, default-on: canvas_realitykit_3d (resetToV001)",
    "fichero/fichero/Models/FeatureManager+Tiers.swift#10d60de58d": "shipped on in release profile v31: research (resetToV001)",
    "fichero/fichero/Models/FeatureManager+Tiers.swift#3e90ccfee5": "#1922 baseline: knowledge_graph (resetToV001)",
}
# #3743: flags are no longer @AppStorage; each is a stored `var … = <default> {`
# whose `didSet` persists to UserDefaults `forKey: "fichero.features.*"`. Detect the
# declaration (default value) and read the key off the didSet within the next lines.
_FLAG_DECL = re.compile(
    r'(?:(?:private|public|internal)\s+)?var\s+(?P<name>\w+)\s*:\s*Bool\s*=\s*(?P<value>true|false)\s*\{'
)
_DIDSET_KEY = re.compile(r'forKey:\s*"(?P<key>fichero\.features\.[^"]+)"')
_ASSIGN_TRUE = re.compile(r"^\s*(?P<name>\w+)\s*=\s*true\b")


def _normalized_snippet(snippet: str) -> str:
    return re.sub(r"\s+", " ", snippet).strip()


def _signature_key(rel: str, snippet: str) -> str:
    digest = hashlib.sha1(_normalized_snippet(snippet).encode("utf-8")).hexdigest()[:10]
    return f"{rel}#{digest}"


def _window_snippet(lines: list[str], line_no: int, radius: int = 1) -> str:
    start = max(0, line_no - 1 - radius)
    end = min(len(lines), line_no + radius)
    return "\n".join(lines[start:end])


def _feature_vars(lines: list[str]) -> dict[str, tuple[str, int, bool]]:
    """Map flag name -> (persistence key, declaration line, defaults-true?).

    A flag is `var NAME: Bool = <default> {` whose `didSet` (on one of the next
    few lines) persists to `forKey: "fichero.features.*"`.
    """
    vars_by_name: dict[str, tuple[str, int, bool]] = {}
    for idx, line in enumerate(lines):
        decl = _FLAG_DECL.search(line)
        if not decl:
            continue
        key = None
        for probe in lines[idx : min(len(lines), idx + 4)]:
            key_match = _DIDSET_KEY.search(probe)
            if key_match:
                key = key_match.group("key")
                break
        if key:
            vars_by_name[decl.group("name")] = (key, idx + 1, decl.group("value") == "true")
    return vars_by_name


def scan() -> dict[str, str]:
    file_lines: dict[Path, list[str]] = {}
    for path in FEATURE_MANAGER_FILES:
        try:
            file_lines[path] = path.read_text(errors="ignore").splitlines()
        except OSError:
            continue

    # Declarations live in FeatureManager.swift; reset assignments (name = true)
    # live in FeatureManager+Tiers.swift — so build the name->key map globally.
    global_vars: dict[str, tuple[str, int, bool]] = {}
    for lines in file_lines.values():
        global_vars.update(_feature_vars(lines))

    found: dict[str, str] = {}
    for path, lines in file_lines.items():
        rel = path.relative_to(ROOT).as_posix()
        for name, (key, line_no, default_on) in _feature_vars(lines).items():
            if default_on:
                found[_signature_key(rel, _window_snippet(lines, line_no))] = (
                    f"{key} defaults true at declaration"
                )
        for line_no, line in enumerate(lines, 1):
            match = _ASSIGN_TRUE.search(line)
            if not match or match.group("name") not in global_vars:
                continue
            key = global_vars[match.group("name")][0]
            found[_signature_key(rel, _window_snippet(lines, line_no))] = (
                f"{key} is set true in release defaults"
            )
    return found


def main() -> int:
    if any(arg in ("-h", "--help") for arg in sys.argv[1:]):
        print(__doc__)
        return 0

    found = scan()
    # #4487: the FeatureManager* glob is a 3-file committed convention — the
    # masked-blind shape in miniature. Below 2, the convention moved.
    require_scan_floor(
        len(FEATURE_MANAGER_FILES), 2, "FeatureManager* files (3 on 2026-08-02)"
    )
    known = set(KNOWN_VIOLATIONS)

    if "--list" in sys.argv[1:]:
        print(f"Feature-flag guardrail offenders ({len(found)} locations):\n")
        for key, reason in found.items():
            tag = "known" if key in known else "NEW"
            print(f"  [{tag}] {key}  <-  {reason}")
        return 0

    new = sorted(set(found) - known)
    stale = sorted(known - set(found))

    print(f"Feature-flag guardrail: scanned {len(FEATURE_MANAGER_FILES)} FeatureManager* file(s)")
    print(f"  {len(found)} on-by-default flag location(s); {len(known)} known.")

    if stale:
        print(f"\n  {len(stale)} KNOWN_VIOLATIONS entries are now clean; remove them:")
        for key in stale:
            print(f"      {key}")

    if new:
        print(f"\n  {len(new)} new on-by-default flag location(s):")
        for key in new:
            print(f"      {key}  <-  {found[key]}")
        print(
            "\nFix: default WIP feature flags off for release, or add a tracked migration "
            f"entry if this is intentional. Rule pointer: {RULE_DOC}."
        )
        return 1

    if stale:
        print(
            "\nFix: remove the now-clean entries listed above from KNOWN_VIOLATIONS. A stale "
            "baseline entry leaves the ratchet green after the debt is gone; tighten it."
        )
        return 1
    print("\nOK: no new WIP feature flags default on.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
