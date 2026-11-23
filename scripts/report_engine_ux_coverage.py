#!/usr/bin/env python3
"""Report which frozen engine operations have a spec, an app behaviour and a UX section (#7067).

For each operation in scripts/check_endpoint_coverage_matrix_known_gaps.json, find the spec that names it (its path or its
operation id) and whether a behaviour of that spec that names the app also names the operation. Prints:

  1. no spec names it
  2. a spec names it, but no app behaviour does
  3. an app behaviour names it and none is [OK]/[BUILT] with a Swift test (still a [GAP] or partial)
  4. app features (spec files with app behaviours) whose spec has no "What the person sees" section (check_spec_app_evidence)

and the first 20 operations of each of the first three. Read-only; exits 0.

    python scripts/report_engine_ux_coverage.py
    python scripts/report_engine_ux_coverage.py --top 50
"""
from __future__ import annotations

import argparse
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import check_spec_app_evidence as evidence  # noqa: E402
from matrix_guardrail_common import ROOT, HTTP_METHODS, endpoint_key, load_known_gaps, load_openapi  # noqa: E402

KNOWN_GAPS_FILE = pathlib.Path(__file__).with_name("check_endpoint_coverage_matrix_known_gaps.json")
BUCKETS = (
    ("no_spec", "no spec names it"),
    ("spec_no_app_behaviour", "spec but no app behaviour"),
    ("app_behaviour_still_gap", "app behaviour still [GAP]"),
)


def operation_ids(openapi: dict) -> dict[str, tuple[str, str]]:
    """endpoint key -> (path, operation id) for every operation."""
    out = {}
    for path, item in openapi.get("paths", {}).items():
        for method, op in (item or {}).items():
            if method.lower() in HTTP_METHODS and isinstance(op, dict):
                out[endpoint_key(method, path)] = (path, op.get("operationId", ""))
    return out


PATH_TOKEN_RE = re.compile(r"/api/[A-Za-z0-9_/{}.-]*")
WORD_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]+")


def _tokens(text: str) -> set[str]:
    """The paths and identifiers a text names; a path is a whole token, so `/api/a` is not named by `/api/a/b`."""
    return {m.rstrip(".-") for m in PATH_TOKEN_RE.findall(text)} | set(WORD_RE.findall(text))


def classify(root: pathlib.Path, endpoints, openapi: dict) -> dict[str, list[str]]:
    """Bucket each endpoint in `endpoints` (a mapping or iterable of endpoint keys)."""
    ids = operation_ids(openapi)
    spec_tokens = [_tokens(p.read_text(encoding="utf-8")) for p in evidence._spec_files(root)]
    app = [(tag, _tokens(scope), bool(evidence.SWIFT_TEST_RE.search(scope)))
           for _rel, _bid, tag, scope in evidence.behaviours(root) if evidence.APP_RE.search(scope)]
    result: dict[str, list[str]] = {k: [] for k, _ in BUCKETS}
    for key in sorted(endpoints):
        if key not in ids:
            continue
        names = {n for n in ids[key] if n}
        if not any(names & t for t in spec_tokens):
            result["no_spec"].append(key)
            continue
        mine = [(tag, swift) for tag, toks, swift in app if names & toks]
        if not mine:
            result["spec_no_app_behaviour"].append(key)
        elif not any(tag in ("OK", "BUILT") and swift for tag, swift in mine):
            result["app_behaviour_still_gap"].append(key)
    return result


def unnamed_operations(root: pathlib.Path, openapi: dict) -> list[str]:
    """Every operation of the schema that no spec names."""
    return classify(root, operation_ids(openapi), openapi)["no_spec"]


def no_ux_count(root: pathlib.Path) -> int:
    return len(evidence.no_ux_specs(root))


def render(result: dict[str, list[str]], ux_missing: int, top: int = 20) -> str:
    lines = []
    for key, label in BUCKETS:
        lines.append(f"{label}: {len(result[key])}")
    lines.append(f"app features whose spec has no UX section: {ux_missing}")
    for key, label in BUCKETS:
        lines.append(f"\n{label} (first {min(top, len(result[key]))} of {len(result[key])}):")
        lines += [f"  {k}" for k in result[key][:top]]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--top", type=int, default=20)
    args = ap.parse_args()
    _path, api = load_openapi()
    result = classify(ROOT, load_known_gaps(KNOWN_GAPS_FILE), api)
    print(render(result, no_ux_count(ROOT), top=args.top))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
