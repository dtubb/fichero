#!/usr/bin/env python3
"""SwiftLint warning-count ratchet (#4446): the total warning count may never
grow past its own best-ever value.

"if we run swiftlint, why do we not fix the warnings… otherwise we never get
to them" (Daniel). SwiftLint already gates on ERRORS (the plain `swiftlint
lint` step in scripts/verify_all.sh's --fast tier fails on any "serious"
violation) — warnings pass silently today, ~200 of them, and nothing ever
schedules the cleanup. A ratchet does: fixing one permanently lowers the bar
(free, automatic), and a new one has to be a decision, not an accident.

Held EXACTLY — no tolerance, no jitter allowance, same reasoning as the
query-count (#4443) and release-size (#4444) ratchets: SwiftLint's rule
engine is deterministic over a fixed source tree, so a warning count does not
vary with machine load. (It CAN legitimately move if the SwiftLint version
itself changes — a rule tightening or a new default-enabled rule — which is
exactly the kind of real, accepted increase --update-baseline exists for.)

Runs `swiftlint lint` a second time (the primary step already ran once) but
against the SAME --cache-path, so the second run is a cache hit and cheap.

--since <base> asks a second, narrower question, for one item (#5995): did this
item add any? It lints the Swift files the item changed, as committed at HEAD and
at its merge-base with <base>, and fails if any rule's count across those files
rose. It stays useful while the total is over its best, when the plain check is
red on every item and cannot tell one that adds ten from one that adds none. Per
rule across the changed files, not per file, so moving code into a new file
passes. It never reads or writes the baseline: the total's best is the plain
check's alone.

Exit codes:
    0  the warning count is at or below its best-ever value
    1  the warning count GREW past its best-ever value — the ratchet FIRED
    2  BLIND — could not run/parse SwiftLint at all (missing binary, missing
       source tree, unparseable output, or — for the DEFAULT baseline only —
       a missing baseline file, which is committed repo content and whose
       absence means the tree moved). Distinct from 1: "I could not measure"
       is not "no regression".
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BASELINE = ROOT / "scripts" / "swiftlint_warning_baseline.json"
SWIFT_DIR = "fichero/fichero"
SWIFT_SRC = ROOT / SWIFT_DIR
MEASUREMENT = "swift.lint_warnings"
CACHE_PATH = ROOT / ".swiftlint-cache"

BLIND_EXIT_CODE = 2
TOP_N_RULES = 10


class Blind(Exception):
    """Raised when the warning count cannot be measured at all."""


def _run_swiftlint() -> list[dict]:
    swiftlint = shutil.which("swiftlint")
    if swiftlint is None:
        raise Blind("swiftlint is not on PATH")
    if not SWIFT_SRC.is_dir():
        raise Blind(f"Swift source tree not found at {SWIFT_SRC}")
    try:
        # cwd=ROOT: the repo-root .swiftlint.yml is the real config. Running
        # from inside fichero/ would pick up the NESTED fichero/.swiftlint.yml
        # instead and silently measure a different (false) baseline — the
        # exact mistake docs/design/... "swiftlint-nested-config-false-
        # baseline" already burned this repo once.
        result = subprocess.run(
            [swiftlint, "lint", "--quiet", "--cache-path", str(CACHE_PATH),
             "--reporter", "json", str(SWIFT_SRC)],
            cwd=str(ROOT), capture_output=True, text=True, timeout=300,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise Blind(f"could not run swiftlint: {exc}") from None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        raise Blind(
            f"swiftlint produced unparseable output (exit {result.returncode}): "
            f"{(result.stderr or result.stdout)[:500]}"
        ) from None


def measure() -> tuple[int, list[tuple[str, int]]]:
    """(warning count, [(rule_id, count)] sorted worst-first)."""
    violations = _run_swiftlint()
    warnings = [v for v in violations if v.get("severity") == "Warning"]
    by_rule = Counter(v.get("rule_id", "?") for v in warnings)
    return len(warnings), by_rule.most_common(TOP_N_RULES)


def _load_baseline(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        raise Blind(
            f"{path} is not valid JSON — restore it from git rather than "
            f"deleting it, or the ratchet silently starts over at whatever "
            f"today's tree happens to have."
        ) from None


def _write_baseline(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _print_top_rules(top_rules: list[tuple[str, int]]) -> None:
    if not top_rules:
        return
    print(f"\n  top {len(top_rules)} rules (fix these next):")
    for rule_id, count in top_rules:
        print(f"    {count:4d}  {rule_id}")


def run(baseline_path: Path, update_baseline: bool) -> int:
    count, top_rules = measure()
    baseline = _load_baseline(baseline_path)  # raises Blind

    if update_baseline:
        baseline[MEASUREMENT] = {"count": count, "note": "manually updated"}
        _write_baseline(baseline_path, baseline)
        print(f"check_swiftlint_warning_ratchet: baseline updated -> {baseline_path}")
        print(f"  {MEASUREMENT}: {count} warnings")
        _print_top_rules(top_rules)
        return 0

    entry = baseline.get(MEASUREMENT)
    if entry is None:
        baseline[MEASUREMENT] = {"count": count, "note": "first recorded run"}
        _write_baseline(baseline_path, baseline)
        print(f"  {MEASUREMENT}: {count} warnings — baseline set")
        _print_top_rules(top_rules)
        return 0

    best = int(entry["count"])
    if count > best:
        print(f"  {MEASUREMENT}: {count} warnings vs best {best} -> GREW")
        _print_top_rules(top_rules)
        print(
            "\nswiftlint warning-count ratchet FAILED: the warning count grew "
            "past its best-ever value.\n"
            "\n"
            "Held EXACTLY, no tolerance — SwiftLint is deterministic over a "
            "fixed tree, so a rise here is a real new warning, not noise.\n"
            "\n"
            "Fix the new warning(s), or if this is a REAL and accepted "
            "increase (a SwiftLint upgrade tightened/added a rule), rerun "
            f"with --update-baseline and commit {_display_path(baseline_path)} "
            "— say what changed."
        )
        return 1

    if count < best:
        baseline[MEASUREMENT] = {"count": count, "note": f"tightened from {best}"}
        _write_baseline(baseline_path, baseline)
        print(
            f"  {MEASUREMENT}: {count} warnings — FEWER than best {best}. "
            f"Ratchet tightened; this is the bar now."
        )
        _print_top_rules(top_rules)
        return 0

    print(f"  {MEASUREMENT}: {count} warnings (best {best})")
    _print_top_rules(top_rules)
    print("\nswiftlint warning-count ratchet: OK")
    return 0


def _git(*args: str) -> str:
    try:
        return subprocess.run(
            ["git", *args], cwd=str(ROOT), capture_output=True, text=True, check=True, timeout=120,
        ).stdout
    except (OSError, subprocess.SubprocessError) as exc:
        raise Blind(f"git {args[0]} failed: {getattr(exc, 'stderr', '') or exc}") from None


def _changed_swift(merge_base: str) -> tuple[list[str], list[str]]:
    """(files to lint at the merge-base, files to lint at HEAD), the item's app Swift files."""
    fields = _git(
        "diff", "--no-renames", "--name-status", "-z", merge_base, "HEAD", "--", f"{SWIFT_DIR}/*.swift"
    ).split("\0")[:-1]
    before, after = [], []
    for status, name in zip(fields[::2], fields[1::2]):
        if status != "A":
            before.append(name)
        if status != "D":
            after.append(name)
    return before, after


def _count_by_rule(rev: str, files: list[str]) -> Counter:
    """Warnings and errors by rule in `files` as committed at `rev`. Errors count too, so a warning
    that grows into an error does not read as one fewer."""
    if not files:
        return Counter()
    swiftlint = shutil.which("swiftlint")
    if swiftlint is None:
        raise Blind("swiftlint is not on PATH")
    with tempfile.TemporaryDirectory() as tree:
        # Both configs: the nested one sets line_length, and the root one's excludes keep their paths.
        archive = subprocess.run(
            ["git", "archive", rev, ".swiftlint.yml", "fichero/.swiftlint.yml", *files],
            cwd=str(ROOT), capture_output=True, timeout=120,
        )
        if archive.returncode != 0:
            raise Blind(f"git archive {rev} failed: {archive.stderr.decode(errors='replace')[:300]}")
        subprocess.run(["tar", "-x", "-C", tree], input=archive.stdout, check=True, timeout=120)
        result = subprocess.run(
            [swiftlint, "lint", "--quiet", "--no-cache", "--reporter", "json", SWIFT_DIR],
            cwd=tree, capture_output=True, text=True, timeout=300,
        )
    try:
        violations = json.loads(result.stdout)
    except json.JSONDecodeError:
        raise Blind(
            f"swiftlint produced unparseable output (exit {result.returncode}): "
            f"{(result.stderr or result.stdout)[:500]}"
        ) from None
    return Counter(v.get("rule_id", "?") for v in violations)


def run_since(base: str) -> int:
    merge_base = _git("merge-base", base, "HEAD").strip()
    before_files, after_files = _changed_swift(merge_base)
    before = _count_by_rule(merge_base, before_files)
    after = _count_by_rule("HEAD", after_files)
    added = after - before
    if added:
        print(f"swiftlint --since {base}: this item adds warnings, in the {len(after_files)} Swift files it changes:")
        for rule_id, count in added.most_common():
            print(f"  +{count}  {rule_id} ({before[rule_id]} -> {after[rule_id]})")
        return 1
    print(
        f"swiftlint --since {base}: nothing added across {len(after_files)} changed Swift files "
        f"({sum(before.values())} -> {sum(after.values())})"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--baseline", type=Path, default=None,
        help=f"Baseline JSON to compare/update (default: {DEFAULT_BASELINE})",
    )
    parser.add_argument(
        "--update-baseline", action="store_true",
        help="Accept the measured count as the new baseline, no comparison",
    )
    parser.add_argument(
        "--since", metavar="BASE", default=None,
        help="Fail only if this item, measured from its merge-base with BASE, adds warnings of any rule",
    )
    args = parser.parse_args(argv)

    if args.since is not None:
        try:
            return run_since(args.since)
        except Blind as exc:
            print(f"check_swiftlint_warning_ratchet: BLIND — {exc}", file=sys.stderr)
            return BLIND_EXIT_CODE

    # The DEFAULT baseline is committed repo content — its absence means the
    # tree moved (scripts/verify_all.sh's guardrail-blindness sweep,
    # test_guardrails_fail_on_missing_input.py / #4382, runs every
    # scripts/check_*.py alone in an empty directory, where this file is also
    # absent). Two exemptions: an explicitly-passed --baseline (the legitimate
    # "no baseline yet" first-run case, not a moved tree), and --update-
    # baseline (whose entire point is to CREATE a missing baseline).
    baseline_path = args.baseline if args.baseline is not None else DEFAULT_BASELINE
    if args.baseline is None and not args.update_baseline and not baseline_path.is_file():
        print(
            f"check_swiftlint_warning_ratchet: BLIND — baseline missing at "
            f"{_display_path(baseline_path)} (the tree moved; restore it from git)",
            file=sys.stderr,
        )
        return BLIND_EXIT_CODE

    try:
        return run(baseline_path, args.update_baseline)
    except Blind as exc:
        print(f"check_swiftlint_warning_ratchet: BLIND — {exc}", file=sys.stderr)
        return BLIND_EXIT_CODE


if __name__ == "__main__":
    raise SystemExit(main())
