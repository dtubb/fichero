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
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FEATURE_MANAGER = ROOT / "fichero" / "fichero" / "Models" / "FeatureManager.swift"
RULE_DOC = "agents/ROADMAP.md"

# Signatures are opaque, so every entry names the flag it grandfathers. Without
# that, a dead entry cannot be told from a live one by reading the file.
KNOWN_VIOLATIONS: dict[str, str] = {
    # --- defaults true at declaration ---
    "fichero/fichero/Models/FeatureManager.swift#01f2f36004": "#1922 baseline: search (declaration)",
    "fichero/fichero/Models/FeatureManager.swift#a19c6d7750": "#1922 baseline: library_advanced_views (declaration)",
    "fichero/fichero/Models/FeatureManager.swift#9fc452b62d": "#1922 baseline: search_advanced_views (declaration)",
    "fichero/fichero/Models/FeatureManager.swift#9b7016be65": "#1922 baseline: library_search_split_layouts (declaration)",
    "fichero/fichero/Models/FeatureManager.swift#30ec8f1a58": "#1922 baseline: knowledge_graph (declaration)",
    "fichero/fichero/Models/FeatureManager.swift#cf51c23a39": "shipped on in release profile v31: settings_general_tab (declaration)",
    "fichero/fichero/Models/FeatureManager.swift#64535b1af0": "shipped on in release profile v31: settings_engine_tab (declaration)",
    "fichero/fichero/Models/FeatureManager.swift#6d899fe1a8": "shipped on in release profile v31: settings_share_tab (declaration)",
    "fichero/fichero/Models/FeatureManager.swift#c2da8d6ed5": "shipped on in release profile v31: settings_users_tab (declaration)",
    "fichero/fichero/Models/FeatureManager.swift#5dd332b721": "shipped on in release profile v31: settings_capture_tab (declaration)",
    "fichero/fichero/Models/FeatureManager.swift#2803a1d660": "shipped on in release profile v31: research (declaration)",
    # --- set true in resetToV001() release defaults ---
    "fichero/fichero/Models/FeatureManager.swift#6549e3bd15": "#1922 baseline: library_advanced_views (resetToV001)",
    "fichero/fichero/Models/FeatureManager.swift#20213d49ea": "#1922 baseline: search (resetToV001)",
    "fichero/fichero/Models/FeatureManager.swift#75ebc78947": "#1922 baseline: search_advanced_views (resetToV001)",
    "fichero/fichero/Models/FeatureManager.swift#61bb9b568c": "#1922 baseline: library_icon_zoom_controls (resetToV001)",
    "fichero/fichero/Models/FeatureManager.swift#8d6717ab7d": "#1922 baseline: workflows (resetToV001)",
    "fichero/fichero/Models/FeatureManager.swift#caee915430": "#1922 baseline: workflow_editor_advanced_views (resetToV001)",
    "fichero/fichero/Models/FeatureManager.swift#caa37e8508": "#1922 baseline: workflow_chains (resetToV001)",
    "fichero/fichero/Models/FeatureManager.swift#ef77c099ff": "#1922 baseline: batches (resetToV001)",
    "fichero/fichero/Models/FeatureManager.swift#3ab4c9e236": "#1922 baseline: workflow_tools_files (resetToV001)",
    "fichero/fichero/Models/FeatureManager.swift#a381bd0df3": "#1922 baseline: workflow_import_export (resetToV001)",
    "fichero/fichero/Models/FeatureManager.swift#7ef8e97466": "#1922 baseline: workflow_langgraph_preview (resetToV001)",
    "fichero/fichero/Models/FeatureManager.swift#ca1127921a": "#1922 baseline: workflow_files_toolbar_button (resetToV001)",
    "fichero/fichero/Models/FeatureManager.swift#04dca90e13": "#1922 baseline: workflow_run_on_selection (resetToV001)",
    "fichero/fichero/Models/FeatureManager.swift#3e90ccfee5": "#1922 baseline: knowledge_graph (resetToV001)",
    "fichero/fichero/Models/FeatureManager.swift#30894e7ab9": "shipped on in release profile v31: activity (resetToV001)",
    "fichero/fichero/Models/FeatureManager.swift#4712fd879e": "shipped on in release profile v31: settings_general_tab (resetToV001)",
    "fichero/fichero/Models/FeatureManager.swift#b59a81d537": "shipped on in release profile v31: settings_engine_tab (resetToV001)",
    "fichero/fichero/Models/FeatureManager.swift#9ebf668b6b": "shipped on in release profile v31: settings_share_tab (resetToV001)",
    "fichero/fichero/Models/FeatureManager.swift#16fbdfae71": "shipped on in release profile v31: settings_users_tab (resetToV001)",
    "fichero/fichero/Models/FeatureManager.swift#276153fd1c": "shipped on in release profile v31: settings_capture_tab (resetToV001)",
    "fichero/fichero/Models/FeatureManager.swift#25d21ce82a": "shipped on in release profile v31: research (resetToV001)",
}
_APP_STORAGE_BOOL = re.compile(
    r'@AppStorage\("(?P<key>fichero\.features\.[^"]+)"\)\s*'
    r'(?:(?:private|public|internal)\s+)?var\s+(?P<name>\w+)\s*:\s*Bool\s*=\s*(?P<value>true|false)'
)
_APP_STORAGE_LINE = re.compile(r'@AppStorage\("(?P<key>fichero\.features\.[^"]+)"\)')
_VAR_LINE = re.compile(r'(?:(?:private|public|internal)\s+)?var\s+(?P<name>\w+)\s*:\s*Bool\s*=\s*(?P<value>true|false)')
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
    vars_by_name: dict[str, tuple[str, int, bool]] = {}
    pending_key: tuple[str, int] | None = None
    for line_no, line in enumerate(lines, 1):
        inline = _APP_STORAGE_BOOL.search(line)
        if inline:
            vars_by_name[inline.group("name")] = (
                inline.group("key"),
                line_no,
                inline.group("value") == "true",
            )
            pending_key = None
            continue
        key_match = _APP_STORAGE_LINE.search(line)
        if key_match:
            pending_key = (key_match.group("key"), line_no)
            continue
        if pending_key:
            var_match = _VAR_LINE.search(line)
            if var_match:
                vars_by_name[var_match.group("name")] = (
                    pending_key[0],
                    pending_key[1],
                    var_match.group("value") == "true",
                )
            elif re.search(r"\bvar\s+\w+\s*:", line) or line.lstrip().startswith("@"):
                pending_key = None
            elif line.strip() and not line.lstrip().startswith("//"):
                pending_key = None
            else:
                continue
            pending_key = None
    return vars_by_name


def scan() -> dict[str, str]:
    try:
        lines = FEATURE_MANAGER.read_text(errors="ignore").splitlines()
    except OSError:
        return {}

    vars_by_name = _feature_vars(lines)
    found: dict[str, str] = {}
    rel = FEATURE_MANAGER.relative_to(ROOT).as_posix()

    for name, (key, line_no, default_on) in vars_by_name.items():
        if default_on:
            found[_signature_key(rel, _window_snippet(lines, line_no))] = f"{key} defaults true at declaration"

    for line_no, line in enumerate(lines, 1):
        match = _ASSIGN_TRUE.search(line)
        if not match:
            continue
        name = match.group("name")
        if name not in vars_by_name:
            continue
        key, _, _ = vars_by_name[name]
        found[_signature_key(rel, _window_snippet(lines, line_no))] = f"{key} is set true in release defaults"

    return found


def main() -> int:
    if any(arg in ("-h", "--help") for arg in sys.argv[1:]):
        print(__doc__)
        return 0

    found = scan()
    known = set(KNOWN_VIOLATIONS)

    if "--list" in sys.argv[1:]:
        print(f"Feature-flag guardrail offenders ({len(found)} locations):\n")
        for key, reason in found.items():
            tag = "known" if key in known else "NEW"
            print(f"  [{tag}] {key}  <-  {reason}")
        return 0

    new = sorted(set(found) - known)
    stale = sorted(known - set(found))

    print(f"Feature-flag guardrail: scanned {FEATURE_MANAGER.relative_to(ROOT)}")
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
