"""require_scan_floor — a guardrail must prove it measured something (#4487).

A check that discovers-then-asserts and finds nothing has two possible
meanings: the tree is clean, or the scanner is blind — roots moved, a parser
resolved nothing, an unset array, a matcher that no longer matches anything.
Those must never share an exit code. This primitive is the floor: below it
the check exits 2 (BLIND — never 1, which means "violation", and never 0,
which means "checked and clean").

THE PART SOMEONE WILL GET BACKWARDS: the floor belongs on what was EXAMINED
— files read, call sites parsed, routes enumerated — never on what was found
WRONG. A check with an allowlist reports "N known / M found", and both
numbers can go to zero together: the allowlist empties as debt is paid, the
matcher dies in the same month, and a dead scanner becomes indistinguishable
from a clean tree (check_accessibility's three blind spots; check_dead_files'
stale entries). A floor on the scan population keeps the proof of life even
when the violation count legitimately reaches zero — which is the goal state.

Floor values are TRIPWIRES, not ratchets: current population x 0.5 rounded
down, committed with the date and the observed count in a comment. They exist
to catch "suddenly zero-ish", not to creep upward with the codebase. Do not
"improve" this into a ratchet: a ratchet on scan population would fail every
legitimate refactor that removes files; a half-count tripwire only fires when
the scan has effectively collapsed.

WHY 45 SCRIPTS ALL NEEDED THE SAME PATCH (it is not that 45 authors were
careless): Python's glob/rglob/iterdir return an empty collection cheerfully,
so every assertion over their result vacuously passes when the scan finds
nothing. The Swift-side sweeps mostly read ONE NAMED FILE and
String(contentsOf:) THROWS when it is missing — the floor is free there
because the read is not optional (24 sweeps audited, only the 4 that
enumerate directories were floorless). A floor is what you add when the
primitive lets you not notice; where a check knows the exact file it wants,
reading it non-optionally is strictly better than globbing and floor-checking
(#4487 Phase 3).

Every floor ships a pointed-at-nothing test asserting the check FAILS (rc=2)
against an empty tree — a floor never observed to fire is the same defect one
level up (see tests/unit/scripts/test_guardrails_scan_floor.py).
"""

from __future__ import annotations

import sys


def require_scan_floor(count: int, floor: int, what: str) -> None:
    """Exit 2 (BLIND) when the scanned population is implausibly small.

    Args:
        count: how many things the check actually examined (NOT violations).
        floor: minimum plausible population (0.5x the count at commit time).
        what: human noun for the population, e.g. "Swift view files".
    """
    if count < floor:
        print(
            f"BLIND: scanned only {count} {what} (floor {floor}) — the "
            "scanner has gone blind or its roots moved; refusing to report "
            "a result it cannot stand behind (#4487). Exit 2 is 'could not "
            "check', which is neither 'violation' nor 'clean'.",
            file=sys.stderr,
        )
        sys.exit(2)
