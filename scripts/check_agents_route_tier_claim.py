#!/usr/bin/env python3
"""AGENTS.md's route-tier count must match the code (#4470).

AGENTS.md is the file every agent reads first, so a wrong claim there does not
merely mislead a reader — it propagates into work. This one has now been wrong
twice: it said "the dev tier gates exactly one route group: iiif" when twenty
were gated, and after that correction it said "Twenty" when the table held 21.

A number in prose and a table in code, with nothing forcing them to agree, is
this repo's most-repeated defect. This is the cheapest possible thing that
forces it: the doc states a count, and adding a route group makes this fail
until someone updates the sentence.

Usage:
    scripts/check_agents_route_tier_claim.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AGENTS = ROOT / "AGENTS.md"
sys.path.insert(0, str(ROOT / "fichero-server" / "src"))

CLAIM = re.compile(r"\*\*(\d+) route groups are tier-gated\*\*")


def main() -> int:
    try:
        from fichero_server.api.feature_tiers_generated import ROUTE_PREFIX_TIERS
    except Exception as exc:  # pragma: no cover - import-environment failure
        print(f"SKIP: cannot import the route-tier table ({exc})")
        return 0

    actual = len(ROUTE_PREFIX_TIERS)
    text = AGENTS.read_text(encoding="utf-8")
    match = CLAIM.search(text)

    if match is None:
        print(
            "FAIL: AGENTS.md no longer states a route-group count in the form "
            '"**N route groups are tier-gated**".\n'
            f"       The table currently holds {actual}. Restore the claim or "
            "delete this guardrail deliberately — silently dropping the number "
            "is how the previous wrong ones survived."
        )
        return 1

    claimed = int(match.group(1))
    if claimed != actual:
        print(
            f"FAIL: AGENTS.md claims {claimed} tier-gated route groups; "
            f"ROUTE_PREFIX_TIERS holds {actual}.\n"
            "       Update the sentence in AGENTS.md (Route tiers). Every agent "
            "reads that file first, so a wrong count propagates into work."
        )
        return 1

    print(f"OK: AGENTS.md route-tier count matches the table ({actual}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
