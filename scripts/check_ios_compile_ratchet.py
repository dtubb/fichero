#!/usr/bin/env python3
"""MEASURED AND REJECTED: the iOS compile is not ratchetable on this machine.

**Do not wire this in. The experiment was run; these are the numbers.**

    run 1   341 s     (cold DerivedData)
    run 2    32 s     (warm)
    run 3    27 s     (warm)

    spread = (max - min) / min = 11.63

The pre-registered rule below said "do not gate at >= 0.25". This is 11.63.

But the number is not the finding — **the shape is.** That is not jitter, it is
bimodal with a known cause: a 12x difference that tracks DerivedData warmth and
nothing about the code. A wall-time ratchet here would measure WHETHER THE
BUILD CACHE WAS WARM and nothing else: firing on every cold build, passing on
every warm one, with uninformative failures and meaningless passes. That trains
everyone to re-run until green, which is the mechanism by which a real
regression gets waved through.

## What WOULD work, and why it is not an engineering decision

A COLD-build time is a real number — it is what #4418 actually hit. Measuring
it honestly means clearing DerivedData first, which costs roughly six minutes
per gate run. Whether that is worth a ratchet on the number that killed #4418
is a cost question for Daniel, not a design question. It is on the decisions
list rather than decided here.

## What was done instead

**iOS app SIZE**, in `check_release_size_ratchet.py --ios-app`. A byte count
does not care whether the cache was warm, so it is held EXACTLY, with no jitter
allowance at all — the query-count/DMG-size shape. That is the iOS ratchet this
project actually has.

## Why this file stays in the tree

A measured negative result is worth keeping. The next person to propose an iOS
time ratchet should find the data and the reasoning, not repeat the experiment
— and the machinery below is correct and tested, so if the cold-build question
is ever answered yes, it is ready.

---

Original design notes follow.

Hold the iOS compile to its best-ever wall time (#4466).

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

#: Where the gate's iOS leg would write its wall time if it were wired to.
#: Argless invocation (the `verify_all` sweep over every `scripts/check_*.py`)
#: falls back to this, and its ABSENCE is NOT ARMED rather than blind.
DEFAULT_DURATION_FILE = ROOT / "build" / "verify-all-derived" / "ios-compile-seconds"


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

    # The distinction this project's own EPIC established (#4487), which the
    # first version of this script got wrong and failed every full gate for:
    #
    #   BLIND     — I TRIED to measure and could not. Something is broken.
    #   NOT ARMED — the input legitimately does not exist in this context.
    #
    # `verify_all` runs every `scripts/check_*.py` automatically, so merely
    # existing in this directory arms a check. A Mac verify-all never runs the
    # iOS leg, so an argless invocation has nothing to judge and that is not a
    # fault — it is the ordinary case. Reporting BLIND there fails every full
    # gate, which trains everyone to ignore the one voice that is supposed to
    # mean something.
    #
    # Explicit `--seconds` / `--from-file` is an assertion that the leg RAN, so
    # those are held to full rigor: a missing or unreadable duration is BLIND.
    # Same two-tier shape as `check_release_size_ratchet`'s --app/--dmg.
    explicit = args.seconds is not None or args.from_file is not None

    # NOT ARMED is a VERIFIED claim, not a default (#4487 follow-up, caught
    # by the empty-tree sweep the day this file landed): "the iOS leg did
    # not run in this REAL repo" and "my ROOT resolved somewhere that is not
    # the repo at all" must not share an exit code. If the repo landmarks
    # are gone, the timing file's absence proves nothing — that is BLIND.
    if not explicit and not (ROOT / "fichero-server" / "src").is_dir():
        print(
            "check_ios_compile_ratchet: BLIND — repo landmarks missing at "
            f"{ROOT} (no fichero-server/src). The timing file's absence "
            "cannot be read as NOT ARMED when the scan root itself is gone "
            "(#4487).",
            file=sys.stderr,
        )
        return 2

    if not explicit and not DEFAULT_DURATION_FILE.is_file():
        print(
            "iOS compile ratchet: NOT ARMED — no iOS build timing at "
            f"{DEFAULT_DURATION_FILE}. This is the ordinary case on a Mac "
            "verify-all, which does not run the iOS leg.\n"
            "  (And it is currently unwired by design: the compile proved "
            "unratchetable — 341s cold vs ~30s warm. See this file's docstring.)"
        )
        return 0

    if not explicit:
        args.from_file = str(DEFAULT_DURATION_FILE)

    seconds = read_seconds(args)

    if seconds is None:
        print(
            "check_ios_compile_ratchet: BLIND -- a compile duration was asked "
            "for and could not be read. The iOS leg ran without reporting its "
            "wall time, or the duration file is unreadable. A ratchet that "
            "passes when nothing was measured is worse than no ratchet.",
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
