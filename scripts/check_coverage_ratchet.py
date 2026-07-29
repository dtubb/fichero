#!/usr/bin/env python3
"""Coverage ratchet guardrail (#4249): coverage may never DROP below baseline.

Compares measured line coverage against the committed baseline
(``coverage-baseline.json`` at the repo root) and fails when any measured
stack has fallen more than ``tolerance_pct`` below its recorded value.
Raising the baseline is DELIBERATE: rerun with ``--update-baseline`` and
commit the diff.

Inputs (either or both; at least one required):
  --engine-json PATH   coverage.py JSON report
                       (coverage run -m pytest fichero-engine/tests/unit &&
                        coverage json -o coverage.json)
  --swift-json PATH    xccov JSON report
                       (xcrun xccov view --report --json Result.xcresult)

Also prints the top-20 least-covered production files per stack each run, so
the next test always has an obvious target.

Exit codes:
    0  every measured stack is at or above baseline (within tolerance)
    1  a stack dropped below baseline — the ratchet FIRED
    2  usage / malformed input
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BASELINE = ROOT / "coverage-baseline.json"
TOP_N = 20


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"coverage ratchet: cannot read {path}: {exc}")


def engine_rates(report: dict) -> tuple[float, list[tuple[float, str]]]:
    """(total percent, [(percent, file)]) from a coverage.py JSON report."""
    total = float(report["totals"]["percent_covered"])
    files = [
        (float(info["summary"]["percent_covered"]), path)
        for path, info in report.get("files", {}).items()
    ]
    return total, files


def swift_rates(report: dict) -> tuple[float, list[tuple[float, str]]]:
    """(total percent, [(percent, file)]) from an xccov JSON report.

    xccov reports fractions (0..1); normalized to percent here. Test bundles
    are excluded — the ratchet tracks PRODUCTION coverage.
    """
    total = float(report["lineCoverage"]) * 100.0
    files: list[tuple[float, str]] = []
    for target in report.get("targets", []):
        name = target.get("name", "")
        if "Tests" in name or ".xctest" in name:
            continue
        for f in target.get("files", []):
            files.append((float(f["lineCoverage"]) * 100.0, f["path"]))
    return total, files


def print_least_covered(stack: str, files: list[tuple[float, str]]) -> None:
    if not files:
        return
    print(f"\n  {stack}: top-{TOP_N} least-covered production files (add tests here next):")
    for pct, path in sorted(files)[:TOP_N]:
        print(f"    {pct:6.1f}%  {path}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine-json", type=Path)
    parser.add_argument("--swift-json", type=Path)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--update-baseline", action="store_true")
    args = parser.parse_args()

    if not args.engine_json and not args.swift_json:
        # Argless mode (the all-guardrails sweep): arm only when the standard
        # artifact locations exist. Without artifacts this is explicitly
        # NOT-ARMED, not silently green — the line below says so.
        default_engine = ROOT / "agent-work" / "coverage" / "engine.json"
        default_swift = ROOT / "agent-work" / "coverage" / "swift.json"
        args.engine_json = default_engine if default_engine.is_file() else None
        args.swift_json = default_swift if default_swift.is_file() else None
        if not args.engine_json and not args.swift_json:
            print(
                "coverage ratchet: NOT ARMED — no coverage artifacts at "
                "agent-work/coverage/{engine,swift}.json. Produce them "
                "(coverage json / xccov view --report --json) or pass "
                "--engine-json/--swift-json."
            )
            return 0

    baseline = _load_json(args.baseline)
    tolerance = float(baseline.get("tolerance_pct", 0.25))

    measured: dict[str, float] = {}
    if args.engine_json:
        total, files = engine_rates(_load_json(args.engine_json))
        measured["engine"] = total
        print_least_covered("engine", files)
    if args.swift_json:
        total, files = swift_rates(_load_json(args.swift_json))
        measured["swift"] = total
        print_least_covered("swift", files)

    if args.update_baseline:
        for stack, pct in measured.items():
            baseline.setdefault(stack, {})["line_rate_pct"] = round(pct, 2)
        args.baseline.write_text(json.dumps(baseline, indent=2) + "\n")
        print(f"\ncoverage ratchet: baseline updated -> {args.baseline}")
        return 0

    fired = False
    print()
    for stack, pct in measured.items():
        recorded = float(baseline.get(stack, {}).get("line_rate_pct", 0.0))
        floor = recorded - tolerance
        status = "OK" if pct >= floor else "DROP"
        print(
            f"  {stack}: measured {pct:.2f}% vs baseline {recorded:.2f}% "
            f"(floor {floor:.2f}%) -> {status}"
        )
        if pct < floor:
            fired = True

    if fired:
        print(
            "\ncoverage ratchet FAILED: coverage dropped below the recorded baseline.\n"
            "Add tests for what you changed. If a drop is genuinely intended\n"
            "(e.g. deleting well-tested code), rerun with --update-baseline and\n"
            "commit coverage-baseline.json with an explanation."
        )
        return 1
    print("\ncoverage ratchet: OK (coverage at or above baseline)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
