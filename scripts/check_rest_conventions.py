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
            if op in KNOWN_VIOLATIONS:
                continue
            for prefix, allowed in RULES.items():
                if op.startswith(prefix) and method not in allowed:
                    out.append(
                        f"{method} {ep.get('path')} — operation '{op}' should use "
                        f"{'/'.join(sorted(allowed))}"
                    )
    return out


def self_test() -> int:
    # The rule must FIRE on a synthetic offender and stay quiet on a clean one.
    firing = {"x": [{"operation_id": "create_thing", "method": "GET", "path": "/t"}]}
    clean = {"x": [{"operation_id": "create_thing", "method": "POST", "path": "/t"}]}
    assert violations(firing), "self-test: rule failed to fire on a GET create_*"
    assert not violations(clean), "self-test: rule fired on a clean endpoint"
    print("self-test OK: rules fire on offenders, stay quiet on clean input")
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
    bad = violations(groups)
    total = sum(len(g) for g in groups.values())
    if bad:
        print(f"✗ {len(bad)} REST-convention violation(s) across {total} endpoints:")
        for line in bad:
            print(f"    {line}")
        return 1
    print(f"REST conventions: {total} endpoints clean.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
