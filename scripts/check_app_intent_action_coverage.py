#!/usr/bin/env python3
"""App Intents → action-registry reachability guardrail (#2281, §6b.6).

Reform master plan §6e + §6b.6: every audited action-registry action (#1848)
should be reachable from the four surfaces — UI + in-app chat + App Intents/Siri
+ MCP. Two of those are structural and need no guardrail:

  • chat — `actions/chat_tools.py::action_tools` is `[action_tool(a) for a in
    reg.all()]`, strictly 1:1 with the registry by construction; it cannot drop
    an action.
  • UI (Mac affordances) — covered by `scripts/check_action_surface_matrix.py`.

App Intents and MCP are CURATED subsets (not every action should be a Siri
shortcut), so forward "every action has an App Intent" coverage needs a per-
action surface POLICY (a design decision — #2281 is `[design]`). What is exactly
enforceable today, with no policy, is the REVERSE integrity of the App Intents
surface:

    every action name an App Intent invokes must EXIST in the action registry.

App Intents reference actions by string — `invokeAuditedAction("entity.merge",
…)`. There is no compile-time link to the backend `@action("entity.merge")`
registration, so if the backend renames/removes an action the Intent silently
fails at runtime with ActionNotFoundError (same drift class as #2660's wrapper
references). This guardrail closes that: it resolves every App Intent action
string against the registered `@action(...)` names. Baseline is CLEAN.

Usage:
    scripts/check_app_intent_action_coverage.py
    scripts/check_app_intent_action_coverage.py --list
    scripts/check_app_intent_action_coverage.py --help
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENGINE_DIR = ROOT / "fichero-server" / "src" / "fichero_server"
INTENTS_DIR = ROOT / "fichero" / "fichero" / "Intents"
RULE_DOC = "docs/contributor/architecture/fichero/reform_masterplan_2026-06.md"

_ACTION_DECL_RE = re.compile(r"@action\(\s*\"([a-zA-Z0-9_.]+)\"")
_INTENT_REF_RE = re.compile(r"invokeAuditedAction\(\s*\"([a-zA-Z0-9_.]+)\"")

# Clean: every App Intent action string resolves to a registered action.
KNOWN_VIOLATIONS: dict[str, str] = {}


def registered_actions(engine_dir: Path = ENGINE_DIR) -> set[str]:
    names: set[str] = set()
    for path in engine_dir.rglob("*.py"):
        names.update(_ACTION_DECL_RE.findall(path.read_text(errors="ignore")))
    return names


def intent_action_refs(intents_dir: Path = INTENTS_DIR) -> dict[str, str]:
    """Map `relpath::action_name` -> action_name for each App Intent reference."""
    refs: dict[str, str] = {}
    if not intents_dir.exists():
        return refs
    for path in sorted(intents_dir.rglob("*.swift")):
        rel = path.name
        for name in _INTENT_REF_RE.findall(path.read_text(errors="ignore")):
            refs[f"{rel}::{name}"] = name
    return refs


def violations(
    *, engine_dir: Path = ENGINE_DIR, intents_dir: Path = INTENTS_DIR
) -> dict[str, str]:
    registered = registered_actions(engine_dir)
    refs = intent_action_refs(intents_dir)
    return {key: name for key, name in refs.items() if name not in registered}


def main() -> int:
    argv = sys.argv[1:]
    if any(a in ("-h", "--help") for a in argv):
        print(__doc__)
        return 0

    registered = registered_actions()
    refs = intent_action_refs()
    bad = violations()
    known = set(KNOWN_VIOLATIONS)

    if "--list" in argv:
        print(f"Registered actions: {len(registered)}; App Intent references: {len(refs)}\n")
        for key, name in sorted(refs.items()):
            tag = "DRIFT" if key in bad else "ok"
            print(f"  [{tag}] {key}")
        return 0

    new = sorted(set(bad) - known)
    stale = sorted(known - set(bad))

    print("App Intents → action-registry reachability (#2281):")
    print(f"  {len(registered)} registered action(s); {len(refs)} App Intent reference(s)")
    print(f"  {len(bad)} unresolved; {len(known)} known.")

    if new:
        print(f"\n  ✗ {len(new)} App Intent(s) invoke a non-existent action:")
        for key in new:
            print(f"      {key}  ←  no @action(\"{bad[key]}\") in the registry")
        print(
            "\nFix: the backend action was renamed/removed. Update the App Intent's "
            f"invokeAuditedAction(\"…\") string to the current action name. Rule: {RULE_DOC}."
        )
        return 1

    if stale:
        print(f"\n  ✓ {len(stale)} KNOWN_VIOLATIONS entr(ies) now resolve — drop them:")
        for key in stale:
            print(f"      {key}")

    print("\n✓ Every App Intent action reaches a registered action.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
