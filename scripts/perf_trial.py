#!/usr/bin/env python3
"""The segment editor's speed trial: is this recorded run a pass? (slice 12, #4940)

    python scripts/perf_trial.py <results.json> [--baseline scripts/perf_trial_baseline.json] [--update]

The trial is a HARD GATE on the editor (`segment-editor.md`, "Slice 12: the speed trial,
and how it is measured"). This script is the METHOD that section writes down, so two people
following it reach the same answer. It does not take measurements -- the app's trial harness
and the engine's latency test do -- it decides whether what they recorded counts, and what it
says.

Every rule below has a measurement mistake from this programme behind it: a cause named from
one run, a 13% "regression" that was noise, a figure quoted from a comment.

Results file (one measurement):

    {
      "measurement": "frame" | "edit-undo" | "engine-edit-undo",
      "fixture": "<the committed fixture's name>",
      "shape_count": 20000,
      "machine": {"model": "iPhone12,8", "os": "iOS 26.0", "build_configuration": "Release"},
      "thermal_state": "nominal" | "fair" | "serious" | "critical" | null,
      "idle": true,
      "date": "2026-09-27",
      "runs": [ {"values_ms": [...], "peak_memory_mb": 412.0}, ... ],   # the FIRST is cold
      "memory_by_shape_count": {"5000": 300.0, "20000": 330.0}          # optional
    }

For `frame`, `values_ms` is every frame's duration in the run; for `edit-undo`, one value per
edit-and-undo in the run.

Verdicts, never collapsed:

* PASS         -- measured, idle, conclusive, inside the gate, not worse than the baseline.
* FAIL         -- measured properly and outside the gate, a regression, or memory growing
                  with the shape count.
* INCONCLUSIVE -- the five runs disagree by more than a tenth of their median. The answer is
                  more runs or a quieter machine, NEVER the best of the five.
* VOID         -- throttled or busy. Neither pass nor fail: recording it as a failure sends
                  somebody to optimise code that was never slow.
* REFUSED      -- the result cannot be read: no thermal state, no machine, a Debug build, too
                  few runs. A gate that cannot read its input fails rather than passing quietly.

Exit status: 0 PASS; 1 FAIL, INCONCLUSIVE or REFUSED; 2 VOID.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

#: The RULED numbers (segment-editor.md), not reopened here. Changing one is an edit to this
#: file in a reviewed commit -- the trial may conclude a target is WRONG, with its
#: measurements, but it may never pass by lowering one quietly.
GATES_MS = {
    # Sixty frames a second: 16.7 ms per frame, on the WORST frame -- a mean hides exactly
    # the dropped frame a person feels.
    "frame": 1000 / 60,
    # One edit through the engine and system undo in under a tenth of a second.
    "edit-undo": 100.0,
    # The ENGINE'S share of that: the edit and its undo through the HTTP stack, measured on
    # the Mac. A necessary condition, not the gate -- the app's UndoManager and redraw come on
    # top -- so it is its own measurement, against the same budget.
    "engine-edit-undo": 100.0,
}
#: Which build a measurement must be taken on. The app's numbers are a Release build; the
#: engine has no Release/Debug, and saying "Release" for it would be a false label.
BUILD_REQUIRED = {"frame": "Release", "edit-undo": "Release", "engine-edit-undo": "engine"}
#: Runs after the cold one.
RUNS = 5
#: The five runs may disagree by this fraction of their median and still be one answer.
NOISE = 0.10
THROTTLED = {"serious", "critical"}
READABLE_THERMAL = {"nominal", "fair", *THROTTLED}
#: Memory "grows in proportion to the count" when the peak at 20,000 shapes is at least this
#: fraction of the way from flat (x1) to proportional (x4). The spec rules the principle
#: (growth with the count fails regardless of the absolute figure) and not the line; this is
#: the line, named so it can be ruled rather than argued.
PROPORTIONAL_FRACTION = 0.5
DEFAULT_BASELINE = Path(__file__).with_name("perf_trial_baseline.json")


@dataclass
class Verdict:
    status: str
    reasons: list[str] = field(default_factory=list)
    median_ms: float | None = None
    worst_ms: float | None = None

    @property
    def exit_code(self) -> int:
        return {"PASS": 0, "VOID": 2}.get(self.status, 1)


def baseline_key(result: dict[str, Any]) -> str:
    machine = result.get("machine") or {}
    return f"{result.get('measurement')}|{machine.get('model')}|{result.get('fixture')}"


def judge(result: dict[str, Any], baseline: dict[str, Any] | None = None) -> Verdict:
    """The verdict on one recorded measurement."""
    refused = _unreadable(result)
    if refused:
        return Verdict("REFUSED", refused)

    thermal = result["thermal_state"]
    if thermal in THROTTLED or result.get("idle") is not True:
        why = f"thermal state {thermal!r}" if thermal in THROTTLED else "the machine was not idle"
        return Verdict("VOID", [f"{why}: neither a pass nor a fail -- rerun on a quiet, cool machine"])

    measured = result["runs"][1:]  # the first run is cold, and discarded
    per_run = [max(run["values_ms"]) for run in measured]
    median = statistics.median(per_run)
    worst = max(per_run)
    verdict = Verdict("PASS", median_ms=median, worst_ms=worst)

    spread = (max(per_run) - min(per_run)) / median if median else 0.0
    if spread > NOISE:
        verdict.status = "INCONCLUSIVE"
        verdict.reasons.append(
            f"the {RUNS} runs disagree by {spread:.0%} of their median (limit {NOISE:.0%}): "
            "more runs or a quieter machine, never the best of the five"
        )
        return verdict

    gate = GATES_MS[result["measurement"]]
    if worst > gate:
        verdict.status = "FAIL"
        verdict.reasons.append(
            f"worst {worst:.2f} ms is over the {gate:.2f} ms gate (median {median:.2f} ms)"
        )

    growth = _memory_growth(result)
    if growth:
        verdict.status = "FAIL"
        verdict.reasons.append(growth)

    entry = (baseline or {}).get(baseline_key(result))
    if entry is None:
        verdict.reasons.append("no baseline for this measurement, machine and fixture: recorded, not compared")
    elif median > entry["median_ms"] * (1 + NOISE):
        verdict.status = "FAIL"
        verdict.reasons.append(
            f"median {median:.2f} ms regressed past the baseline {entry['median_ms']:.2f} ms "
            f"(measured {entry.get('date')} on {entry.get('os')}) by more than the {NOISE:.0%} noise band"
        )
    elif median < entry["median_ms"] * (1 - NOISE):
        verdict.reasons.append(
            f"median {median:.2f} ms improves on the baseline {entry['median_ms']:.2f} ms: update the "
            "baseline IN THE SAME COMMIT as the change that earned it (--update)"
        )
    return verdict


def _unreadable(result: dict[str, Any]) -> list[str]:
    problems = []
    if result.get("measurement") not in GATES_MS:
        problems.append(f"measurement must be one of {sorted(GATES_MS)}")
    machine = result.get("machine") or {}
    missing = [k for k in ("model", "os", "build_configuration") if not machine.get(k)]
    if missing:
        problems.append(f"a number with no machine beside it cannot be compared: missing {missing}")
    elif machine["build_configuration"] != BUILD_REQUIRED.get(result.get("measurement"), "Release"):
        wanted = BUILD_REQUIRED.get(result.get("measurement"), "Release")
        problems.append(f"{machine['build_configuration']} is not the product: measure a {wanted} build")
    if not result.get("fixture"):
        problems.append("no fixture named: a result must say which committed page it measured")
    if result.get("thermal_state") not in READABLE_THERMAL:
        problems.append("the thermal state could not be read, and a gate that cannot read its input fails")
    runs = result.get("runs") or []
    if len(runs) < RUNS + 1:
        problems.append(f"{len(runs)} run(s): one cold run and {RUNS} measured runs are required")
    elif any(not run.get("values_ms") for run in runs):
        problems.append("a run with no values")
    return problems


def _memory_growth(result: dict[str, Any]) -> str | None:
    """Peak memory must not scale with the page's shape count (`source.perf.memory-growth`)."""
    by_count = {int(k): float(v) for k, v in (result.get("memory_by_shape_count") or {}).items()}
    if 5000 not in by_count or 20000 not in by_count or by_count[5000] <= 0:
        return None
    factor = by_count[20000] / by_count[5000]
    line = 1 + PROPORTIONAL_FRACTION * (20000 / 5000 - 1)
    if factor >= line:
        return (
            f"peak memory grows x{factor:.2f} from 5,000 to 20,000 shapes -- in proportion to the "
            f"count (line x{line:.2f}), whatever the absolute figure"
        )
    return None


def _record(result: dict[str, Any], verdict: Verdict) -> dict[str, Any]:
    machine = result["machine"]
    return {
        "median_ms": round(verdict.median_ms or 0.0, 3),
        "worst_ms": round(verdict.worst_ms or 0.0, 3),
        "machine": machine["model"],
        "os": machine["os"],
        "build_configuration": machine["build_configuration"],
        "fixture": result["fixture"],
        "shape_count": result.get("shape_count"),
        "date": result.get("date"),
        "peak_memory_mb": max((run.get("peak_memory_mb") or 0.0) for run in result["runs"][1:]),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("results", type=Path)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--update", action="store_true", help="write this PASS into the baseline")
    args = parser.parse_args(argv)

    result = json.loads(args.results.read_text(encoding="utf-8"))
    baseline = json.loads(args.baseline.read_text(encoding="utf-8")) if args.baseline.exists() else {}
    verdict = judge(result, baseline)

    print(f"{verdict.status}  {baseline_key(result)}")
    if verdict.median_ms is not None:
        gate = GATES_MS.get(result.get("measurement"), float("nan"))
        print(f"  median {verdict.median_ms:.2f} ms, worst {verdict.worst_ms:.2f} ms, gate {gate:.2f} ms")
    for reason in verdict.reasons:
        print(f"  {reason}")

    if args.update:
        if verdict.status != "PASS":
            print("  --update refused: only a PASS goes into the baseline", file=sys.stderr)
            return 1
        baseline[baseline_key(result)] = _record(result, verdict)
        args.baseline.write_text(json.dumps(baseline, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"  baseline updated: {args.baseline}")
    return verdict.exit_code


if __name__ == "__main__":
    sys.exit(main())
