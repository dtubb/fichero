#!/usr/bin/env python3
"""REST-convention guardrail over the exported endpoint contract (#4265).

Replaces the deleted Swift `EndpointValidationTests.swift`, which linted the
same JSON from inside the hosted app — the most expensive possible place —
with assertions that were circular (filter by method, assert that method),
compile-time truths re-asserted at runtime, or vacuous when endpoints.json
was missing (it returned an empty list and passed). Its path walk also never
terminated outside the repo and leaked 13.6 GB (#4264).

Rules enforced here, on the actual source of truth, in milliseconds:
  * operations named create_* use POST
  * operations named update_* use PUT or PATCH
  * operations named delete_* use DELETE
  * operations named list_*/get_* use GET (side-effect-free by naming)

Usage:
    scripts/check_rest_conventions.py              # gate mode
    scripts/check_rest_conventions.py --self-test  # prove the rules FIRE

Exit codes: 0 clean, 1 violations (or a missing/empty contract file — a
missing contract must be loud, never a silent pass).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENDPOINTS = ROOT / "fichero-server" / "tests" / "contracts" / "endpoints.json"

# Grandfathered offenders (predate this guardrail; changing a live method is
# a breaking client change). Fix tracked in #4266 — remove entries as fixed.
KNOWN_VIOLATIONS: set[str] = {
    "update_library_access_api_registry_update_access_post",
    "get_tool_prompt_api_workflows_tools__tool_name__prompt_post",
}

# Endpoints where the RULE is wrong and POST is correct, each with the reason IN the
# entry (#5098). Not the same list as `KNOWN_VIOLATIONS`, which is debt to be paid: these
# are decisions, and nothing is owed. The rule "delete_* uses DELETE" assumes a delete
# addresses ONE resource by its path. These do not — they carry a body the path cannot
# express — and `DELETE` with a request body is poorly carried by intermediaries and
# dropped by some client generators, so the body would arrive empty at the worst moment.
#
# The reason is the point. An entry reading "allowlisted" is a placeholder, and #5095 is
# what a file of placeholders becomes: 551 of 569 paths excused by one pasted sentence.
# `self_test` refuses an empty reason, and `main` fails on an entry whose operation no
# longer exists, so an excuse cannot outlive the endpoint it excused.
RULE_IS_WRONG: dict[str, str] = {
    "delete_segments_api_segments_delete_post": (
        "Bulk, and versioned: the body carries `expected_versions`, a compare-and-set "
        "map of segment id to the version the caller believes it is deleting. That is "
        "optimistic concurrency, not an address, and it cannot go in a path. A DELETE "
        "whose body an intermediary dropped would delete without checking versions, "
        "which is the one thing this route exists to prevent."
    ),
    "delete_workflow_runs_route_api_workflow_execution_runs_delete_post": (
        "Bulk, and by FILTER: the body takes either explicit `thread_ids` or `statuses` "
        "— 'Clear Failed' is `statuses=['failed']` through this same action. A filter "
        "is not a resource address, so there is no path for DELETE to address."
    ),
}

# operation_id prefix -> allowed HTTP methods
RULES: dict[str, set[str]] = {
    "create_": {"POST"},
    "update_": {"PUT", "PATCH"},
    "delete_": {"DELETE"},
    "list_": {"GET"},
    "get_": {"GET"},
}


def violations(endpoint_groups: dict[str, list[dict]]) -> list[str]:
    out: list[str] = []
    for group in endpoint_groups.values():
        for ep in group:
            op = ep.get("operation_id") or ""
            method = (ep.get("method") or "").upper()
            if op in KNOWN_VIOLATIONS or op in RULE_IS_WRONG:
                continue
            for prefix, allowed in RULES.items():
                if op.startswith(prefix) and method not in allowed:
                    out.append(
                        f"{method} {ep.get('path')} — operation '{op}' should use "
                        f"{'/'.join(sorted(allowed))}"
                    )
    return out


def stale_exemptions(endpoint_groups: dict[str, list[dict]]) -> list[str]:
    """Exempted operations the contract no longer has.

    An excuse that outlives its endpoint is how an allowlist rots into a wall of
    permissions nobody can audit. Both lists are checked: a paid-off grandfathered
    violation should leave `KNOWN_VIOLATIONS`, and a deleted route should take its
    `RULE_IS_WRONG` entry with it.
    """
    live = {
        ep.get("operation_id") or ""
        for group in endpoint_groups.values()
        for ep in group
    }
    return sorted((KNOWN_VIOLATIONS | set(RULE_IS_WRONG)) - live)


def self_test() -> int:
    # The rule must FIRE on a synthetic offender and stay quiet on a clean one.
    firing = {"x": [{"operation_id": "create_thing", "method": "GET", "path": "/t"}]}
    clean = {"x": [{"operation_id": "create_thing", "method": "POST", "path": "/t"}]}
    assert violations(firing), "self-test: rule failed to fire on a GET create_*"
    assert not violations(clean), "self-test: rule fired on a clean endpoint"

    # An exemption must say WHY, in the entry. A blank or token reason is the
    # placeholder shape this list exists to avoid.
    for op, why in RULE_IS_WRONG.items():
        assert len(why.strip()) >= 40, f"self-test: {op} is exempted without a reason"
        assert why.strip().lower() != "allowlisted", f"self-test: {op} has a placeholder"

    # A stale exemption must be REPORTED, not silently carried.
    assert stale_exemptions({"x": []}), "self-test: stale exemptions went unnoticed"
    assert not stale_exemptions(
        {"x": [{"operation_id": op} for op in KNOWN_VIOLATIONS | set(RULE_IS_WRONG)]}
    ), "self-test: a live exemption was called stale"

    print("self-test OK: rules fire on offenders, exemptions must give reasons")
    return 0


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()
    if not ENDPOINTS.exists():
        print(f"✗ {ENDPOINTS} missing — regenerate with export_openapi_schema.py.")
        print("  A missing contract is a FAILURE, not a skip (#4265).")
        return 1
    data = json.loads(ENDPOINTS.read_text())
    groups = data.get("endpoints", {})
    if not groups:
        print("✗ endpoints.json holds no endpoints — stale or truncated export.")
        return 1
    stale = stale_exemptions(groups)
    if stale:
        print(f"✗ {len(stale)} exemption(s) name an operation the contract no longer has:")
        for op in stale:
            print(f"    {op} — remove it, or the excuse outlives the endpoint")
        return 1
    bad = violations(groups)
    total = sum(len(g) for g in groups.values())
    if bad:
        print(f"✗ {len(bad)} REST-convention violation(s) across {total} endpoints:")
        for line in bad:
            print(f"    {line}")
        return 1
    print(
        f"REST conventions: {total} endpoints clean "
        f"({len(KNOWN_VIOLATIONS)} grandfathered, {len(RULE_IS_WRONG)} where the rule is "
        "wrong and the reason is written down)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
