#!/usr/bin/env python3
"""Feature-flag release-default guardrail.

Rule: work-in-progress feature flags must default off for release; see docs/ROADMAP.md.

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

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FEATURE_MANAGER = ROOT / "fichero" / "fichero" / "Models" / "FeatureManager.swift"
RULE_DOC = "docs/ROADMAP.md"

KNOWN_VIOLATIONS: dict[str, str] = {
    'fichero/fichero/Models/FeatureManager.swift:34:searchEnabledInternal': '#1922 baseline',
    'fichero/fichero/Models/FeatureManager.swift:36:libraryAdvancedViewsEnabledInternal': '#1922 baseline',
    'fichero/fichero/Models/FeatureManager.swift:38:searchAdvancedViewsEnabledInternal': '#1922 baseline',
    'fichero/fichero/Models/FeatureManager.swift:40:librarySearchSplitLayoutsEnabledInternal': '#1922 baseline',
    'fichero/fichero/Models/FeatureManager.swift:62:settingsGeneralTabEnabledInternal': '#1922 baseline',
    'fichero/fichero/Models/FeatureManager.swift:110:researchEnabledInternal': '#1922 baseline',
    'fichero/fichero/Models/FeatureManager.swift:111:knowledgeGraphEnabledInternal': '#1922 baseline',
    'fichero/fichero/Models/FeatureManager.swift:198:libraryAdvancedViewsEnabledInternal': '#1922 baseline',
    'fichero/fichero/Models/FeatureManager.swift:199:searchEnabledInternal': '#1922 baseline',
    'fichero/fichero/Models/FeatureManager.swift:200:searchAdvancedViewsEnabledInternal': '#1922 baseline',
    'fichero/fichero/Models/FeatureManager.swift:203:libraryIconZoomControlsEnabledInternal': '#1922 baseline',
    'fichero/fichero/Models/FeatureManager.swift:204:workflowsEnabledInternal': '#1922 baseline',
    'fichero/fichero/Models/FeatureManager.swift:205:workflowEditorAdvancedViewsEnabled': '#1922 baseline',
    'fichero/fichero/Models/FeatureManager.swift:206:workflowChainsEnabledInternal': '#1922 baseline',
    'fichero/fichero/Models/FeatureManager.swift:207:batchesEnabledInternal': '#1922 baseline',
    'fichero/fichero/Models/FeatureManager.swift:213:activityEnabledInternal': '#1922 baseline',
    'fichero/fichero/Models/FeatureManager.swift:217:mindPalaceEnabledInternal': '#1922 baseline',
    'fichero/fichero/Models/FeatureManager.swift:219:settingsGeneralTabEnabledInternal': '#1922 baseline',
    'fichero/fichero/Models/FeatureManager.swift:220:settingsBackendTabEnabledInternal': '#1922 baseline',
    'fichero/fichero/Models/FeatureManager.swift:221:settingsModelsTabEnabledInternal': '#1922 baseline',
    'fichero/fichero/Models/FeatureManager.swift:231:workflowToolsFilesEnabledInternal': '#1922 baseline',
    'fichero/fichero/Models/FeatureManager.swift:235:workflowImportExportEnabledInternal': '#1922 baseline',
    'fichero/fichero/Models/FeatureManager.swift:236:workflowLangGraphPreviewEnabledInternal': '#1922 baseline',
    'fichero/fichero/Models/FeatureManager.swift:237:workflowFilesToolbarEnabledInternal': '#1922 baseline',
    'fichero/fichero/Models/FeatureManager.swift:238:workflowRunOnSelectionEnabledInternal': '#1922 baseline',
    'fichero/fichero/Models/FeatureManager.swift:241:researchEnabledInternal': '#1922 baseline',
    'fichero/fichero/Models/FeatureManager.swift:242:knowledgeGraphEnabledInternal': '#1922 baseline',
}
_APP_STORAGE_BOOL = re.compile(
    r'@AppStorage\("(?P<key>fichero\.features\.[^"]+)"\)\s*'
    r'(?:(?:private|public|internal)\s+)?var\s+(?P<name>\w+)\s*:\s*Bool\s*=\s*(?P<value>true|false)'
)
_APP_STORAGE_LINE = re.compile(r'@AppStorage\("(?P<key>fichero\.features\.[^"]+)"\)')
_VAR_LINE = re.compile(r'(?:(?:private|public|internal)\s+)?var\s+(?P<name>\w+)\s*:\s*Bool\s*=\s*(?P<value>true|false)')
_ASSIGN_TRUE = re.compile(r"^\s*(?P<name>\w+)\s*=\s*true\b")


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
            found[f"{rel}:{line_no}:{name}"] = f"{key} defaults true at declaration"

    for line_no, line in enumerate(lines, 1):
        match = _ASSIGN_TRUE.search(line)
        if not match:
            continue
        name = match.group("name")
        if name not in vars_by_name:
            continue
        key, _, _ = vars_by_name[name]
        found[f"{rel}:{line_no}:{name}"] = f"{key} is set true in release defaults"

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
        print("\n(KNOWN_VIOLATIONS has stale entries; clean them up when convenient.)")
    print("\nOK: no new WIP feature flags default on.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
