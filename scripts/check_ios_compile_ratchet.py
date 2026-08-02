#!/usr/bin/env python3
"""Hold the iOS compile to its best-ever wall time (#4466).

## Why iOS, and why compile time

Every ratchet this project has measures the Python side or the Mac: test
elapsed, query counts, DMG size, SwiftLint warnings, cold start, peak memory.
**iOS is where it has actually shipped broken builds** — #4418 failed on
compile time, #4331 crashed at launch on TestFlight.

Compile time is the one worth holding first because its failure mode is a
cliff, not a slope: the compiler does not get gradually slower until someone
notices, it gets slower and slower and then gives up. A creep toward that
ceiling is invisible until it is fatal, which is exactly what a ratchet is for.

## This script does NOT run the build

It reads a duration that the gate's existing iOS leg already produced. That is
deliberate, for three reasons:

1. **The build already runs.** `verify_all.sh` has a device-less `cmd_ios` leg
   (`generic/platform=iOS Simulator`). Timing it costs nothing; building a
   second time to measure would double the most expensive leg in the gate — on
   a machine that is known to shed builds under memory pressure.
2. **A measurement harness that re-runs the thing it measures is measuring a
   different thing** — a warm second build is not the build the gate ran.
3. It keeps this script pure and therefore testable. Every branch below is
   exercised by `test_check_ios_compile_ratchet.py` against synthesised
   durations, with no Xcode involved.

## Reuses the existing ratchet, does not reimplement it

The bar logic is `fichero-server/tests/perf_ratchet.record()` — the same
primitive holding the Python durations. It already knows how to: set a
baseline on a first run rather than fail, tighten when a run beats the bar,
refuse to record when another perf run is active (a contended number must not
become the bar in EITHER direction), and honour `FICHERO_PERF_NO_HISTORY` on a
thrashing machine.

A second baseline file or a second jitter allowance would be this project's
own defect class appearing in the tooling built to prevent it.

`TOLERANCE` is 1.35 — a 35% jitter allowance. For a multi-minute compile that
is wide, and wide is correct here: a flaky gate leg is worse than no gate leg,
and the failure being guarded against is a doubling, not a wobble.

## How the tolerance gets chosen — decided BEFORE the numbers exist

Three runs of the iOS leg on a quiet machine are coming. Writing the rule down
first is deliberate: choosing a tolerance after seeing the spread means fitting
the bar to whatever the machine happened to do, and any spread can be made to
look acceptable that way.

Let `spread = (max - min) / min` across the three runs.

- **spread < 0.10** — the leg is stable. Keep `TOLERANCE` at 1.35; it is
  already several times the observed jitter, and the failure being guarded
  against is a doubling toward the #4418 cliff, not a wobble.
- **0.10 <= spread < 0.25** — usable, but 1.35 is close to the noise. Set the
  baseline from the SLOWEST of the three, so the first honest run cannot fail.
- **spread >= 0.25** — **do not gate on it.** A quarter of a multi-minute
  compile is minutes of jitter, and no tolerance separates that from a real
  regression. Report it, leave the script unwired, and say the iOS compile is
  not measurable on this machine.

That last outcome is a result, not a failure to deliver. A flaky gate leg
trains everyone to re-run until green, which is the mechanism by which a real
regression gets waved through — so a ratchet nobody believes is worse than the
absence of one.

Whatever the numbers say, the baseline is seeded from a run nobody optimised
for and the note in `perf_baseline.json` records which of the three it was.

## Blindness

"I could not measure the compile" is **exit 2**, never a pass. A missing or
unreadable duration file means the gate leg did not run, or ran and did not
report — and a ratchet that silently passes when nothing was measured is the
failure this whole family of checks exists to prevent (#4487).

Exit codes:
    0   within the ratchet (or baseline recorded on a first run)
    1   slower than the bar
    2   BLIND -- no duration to judge

Usage:
    scripts/check_ios_compile_ratchet.py --seconds 214.7
    scripts/check_ios_compile_ratchet.py --from-file build/ios-compile-seconds
    scripts/check_ios_compile_ratchet.py --name ios.compile_ms --seconds 214.7
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PERF_DIR = ROOT / "fichero-server" / "tests"

#: The ratchet's identity. Renaming it resets the bar to whatever the next run
#: happens to manage, so it is a constant rather than an argument default that
#: a caller might drift.
DEFAULT_MEASUREMENT = "ios.compile_ms"

#: Below this, the number is not a compile. A device-less iOS build of this app
#: takes minutes; anything under a second means the leg failed instantly, was
#: skipped, or the file holds a stale zero — none of which is a fast build.
IMPLAUSIBLY_FAST_SECONDS = 1.0


def _load_recorder():
    """Import the existing perf ratchet rather than reimplementing its rules."""
    if str(PERF_DIR) not in sys.path:
        sys.path.insert(0, str(PERF_DIR))
    import perf_ratchet  # noqa: PLC0415  — path must be set first

    return perf_ratchet


def read_seconds(args: argparse.Namespace) -> float | None:
    """The measured duration, or None if there is nothing trustworthy to judge."""
    if args.seconds is not None:
        return args.seconds
    if args.from_file is None:
        return None
    path = Path(args.from_file)
    if not path.exists():
        return None
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=float, default=None)
    parser.add_argument("--from-file", default=None)
    parser.add_argument("--name", default=DEFAULT_MEASUREMENT)
    args = parser.parse_args(argv)

    seconds = read_seconds(args)

    if seconds is None:
        print(
            "check_ios_compile_ratchet: BLIND -- no compile duration to judge. "
            "The gate's iOS leg did not run, or ran without reporting its wall "
            "time. A ratchet that passes when nothing was measured is worse "
            "than no ratchet.",
            file=sys.stderr,
        )
        return 2

    if seconds < IMPLAUSIBLY_FAST_SECONDS:
        print(
            f"check_ios_compile_ratchet: BLIND -- measured {seconds:.3f}s, which "
            f"is not a compile of this app. The leg failed instantly, was "
            f"skipped, or the duration file holds a stale value. Refusing to "
            f"record it: a bogus fast number would become the bar and fail every "
            f"honest run afterwards.",
            file=sys.stderr,
        )
        return 2

    perf_ratchet = _load_recorder()

    try:
        perf_ratchet.record(args.name, seconds * 1000.0)
    except AssertionError as regression:
        print(f"check_ios_compile_ratchet: SLOWER than the bar\n\n{regression}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
