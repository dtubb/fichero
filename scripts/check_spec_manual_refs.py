#!/usr/bin/env python3
"""Every APPROVED design-led spec points at the USER-MANUAL section that explains it.

The rule (creative-director, 2026-09-17): a spec has THREE anchors and no orphans —
  1. a GitHub **milestone** (where its issues live)      -> check_spec_milestones.py
  2. a user-**manual** section (how a user is told)      -> THIS guardrail
  3. >=1 **test** citing its behavior ids (the proof)    -> check_specs_have_tests.py

A surface with no manual section is not finished: we shipped a capability nobody was told
about. Declaring `Manual: TBD — <what the section must explain>` is allowed on a DRAFT so the
gap is VISIBLE and filed, never silent — but TBD blocks APPROVED.

Enforcement is split so the gate stays deterministic while the manual is being reorganised:
  * HARD (offline): an APPROVED spec MUST declare `Manual: <path>` that is not TBD.
  * SOFT: the referenced path should exist on disk. The user manual is mid-move (authored in
    Tinderbox, exported into docs/user_manual), so a missing file WARNS rather than fails —
    a stale path is a docs bug to fix, not a reason to block the gate.

Run: python scripts/check_spec_manual_refs.py
"""

from __future__ import annotations

import pathlib
import re
import sys

SPECS_DIR = pathlib.Path("docs/contributor_manual/specs")
MANUAL_RE = re.compile(r"Manual:\s*(.+)")
TBD_RE = re.compile(r"^\s*TBD\b", re.IGNORECASE)

# Specs approved BEFORE the manual-reference rule (2026-09-17). They graduate off this list by
# gaining a `Manual:` header as their area is next worked — the same "sorted over time" pattern
# check_spec_milestones.py uses. Do NOT add new specs here; new APPROVED specs must declare one.
MANUAL_GRANDFATHERED = {
    "kg-tables",
    "kg-entity-inspector",
    "kg-readable-representation",
    "sidebar-crud",
    "workflow-node-config",
    "ui-test-harness",
    "xcode-build-configs",
    "transport-http-uds",
}


def _is_scaffold(p: pathlib.Path) -> bool:
    return p.name.startswith("_")


def _specs() -> list[pathlib.Path]:
    return [p for p in SPECS_DIR.rglob("*.md") if not _is_scaffold(p)]


def _is_approved(spec: pathlib.Path) -> bool:
    return bool(re.search(r"Status:\s*APPROVED", spec.read_text(encoding="utf-8")[:800]))


def _declared_manual(spec: pathlib.Path) -> str | None:
    m = MANUAL_RE.search(spec.read_text(encoding="utf-8")[:1200])
    return m.group(1).strip() if m else None


def main() -> int:
    if not SPECS_DIR.exists():
        print(f"FAIL: specs directory missing: {SPECS_DIR}")
        return 1

    hard_failures: list[str] = []
    warnings: list[str] = []
    approved_ok = 0
    draft_tbd = 0

    for spec in sorted(_specs()):
        rel = spec.relative_to(SPECS_DIR)
        ref = _declared_manual(spec)
        approved = _is_approved(spec)

        if ref is None:
            if approved and spec.stem not in MANUAL_GRANDFATHERED:
                hard_failures.append(
                    f"{rel}: APPROVED spec must declare `Manual: <path>` — the user-manual "
                    f"section that tells a user about this surface."
                )
            elif not approved:
                warnings.append(f"{rel}: DRAFT has no `Manual:` — add one (TBD is allowed).")
            continue

        if TBD_RE.match(ref):
            if approved and spec.stem not in MANUAL_GRANDFATHERED:
                hard_failures.append(
                    f"{rel}: `Manual: TBD` blocks APPROVED — write the manual section (or keep "
                    f"the spec DRAFT) before approving."
                )
            else:
                draft_tbd += 1
            continue

        # Soft: does the referenced section exist? The manual is mid-reorganisation, so a miss
        # is a warning — a stale pointer is a docs bug, not a gate failure.
        path = pathlib.Path(ref.split()[0])
        if not path.exists():
            warnings.append(f"{rel}: Manual path not found on disk: {path}")
        if approved:
            approved_ok += 1

    for w in warnings:
        print(f"WARN {w}")

    if hard_failures:
        print("FAIL check_spec_manual_refs:")
        for f in hard_failures:
            print(f"  - {f}")
        return 1

    print(
        f"OK check_spec_manual_refs: {approved_ok} approved specs reference a manual section"
        f"; {draft_tbd} draft(s) with a declared TBD gap"
        f"; {len(MANUAL_GRANDFATHERED)} grandfathered."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
