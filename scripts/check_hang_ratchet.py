#!/usr/bin/env python3
"""Main-thread hang ratchet (#4550): stall must not grow.

Reads the ``potential-hangs`` table of an Instruments trace (or a
pre-exported XML) and holds three numbers to a committed baseline:
hang COUNT, TOTAL stall, and WORST single hang. Swiftlint warnings and
release size already ratchet; this gives main-thread stall the same floor,
so a regression fails while it is still attributable to one change.

The comparison is against the committed baseline, which only moves by
deliberate ``--update-baseline`` commits — never a rolling window, which
would absorb each regression and drift with the thing it is meant to catch.

IMPORTANT: numbers are only comparable across traces of the SAME
reproducible session shape (Daniel records these deliberately). Comparing
arbitrary traces is noise, not measurement.

Exit codes (AGENTS.md rule 0 — blind vs not-armed):
  0  pass, or NOT ARMED (no trace supplied and none at the default path —
     the thing measured does not exist on this machine)
  1  ratchet violation (stall grew)
  2  BLIND (input supplied but unreadable/empty, or committed baseline
     missing while a trace was supplied) — the check cannot judge

Usage:
  python3 scripts/check_hang_ratchet.py <trace.trace | hangs.xml>
  python3 scripts/check_hang_ratchet.py <input> --update-baseline
  python3 scripts/check_hang_ratchet.py --self-test
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BASELINE_PATH = REPO_ROOT / "scripts" / "hang_baseline.json"
# Any single measurement can wobble on a loaded machine; a violation is a
# >5% regression on any metric. Improvements only land via --update-baseline.
TOLERANCE = 1.05

XPATH = '/trace-toc/run[@number="1"]/data/table[@schema="potential-hangs"]'


def export_hangs_xml(trace: Path) -> str:
    """Export the potential-hangs table from a .trace via xctrace."""
    with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as handle:
        out = Path(handle.name)
    result = subprocess.run(
        [
            "xcrun", "xctrace", "export", "--input", str(trace),
            "--xpath", XPATH, "--output", str(out),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        print(f"BLIND: xctrace export failed for {trace}: {result.stderr.strip()}")
        sys.exit(2)
    return out.read_text()


def measure(xml_text: str) -> dict:
    """Sum the durations, count the rows, take the max — in nanoseconds."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        print(f"BLIND: hangs XML did not parse: {exc}")
        sys.exit(2)
    durations = []
    for row in root.iter("row"):
        node = row.find("duration")
        if node is not None and node.text and node.text.isdigit():
            durations.append(int(node.text))
    if not durations:
        # A trace with genuinely zero hangs still has the table with zero
        # rows; a missing table means the Hangs instrument never ran. Both
        # arrive here as "no durations" — an empty TABLE is a pass, an
        # absent one is blindness. Distinguish by the table element.
        if root.find(".//table") is None and root.tag != "table" and not list(root.iter("row")):
            print("BLIND: no potential-hangs rows or table found — was the Hangs instrument recording?")
            sys.exit(2)
    return {
        "hang_count": len(durations),
        "total_stall_ms": round(sum(durations) / 1e6, 1),
        "worst_hang_ms": round(max(durations, default=0) / 1e6, 1),
    }


def compare(current: dict, baseline: dict) -> list[str]:
    failures = []
    for key in ("hang_count", "total_stall_ms", "worst_hang_ms"):
        if key not in baseline:
            failures.append(f"baseline is missing '{key}' — re-commit it with --update-baseline")
            continue
        allowed = baseline[key] * TOLERANCE
        if current[key] > allowed:
            failures.append(
                f"{key} grew: {current[key]} > {baseline[key]} "
                f"(+{TOLERANCE:.0%}-tolerance cap {allowed:.1f})"
            )
    return failures


def self_test() -> None:
    """Prove the ratchet FIRES: a synthesized regression must fail."""
    rows = "".join(
        f"<row><start-time>1</start-time><duration>{d}</duration></row>"
        for d in (2_000_000_000, 3_000_000_000)  # 2s + 3s of stall
    )
    xml_text = f"<table>{rows}</table>"
    current = measure(xml_text)
    assert current["hang_count"] == 2, current
    assert current["total_stall_ms"] == 5000.0, current
    assert current["worst_hang_ms"] == 3000.0, current

    tight_baseline = {"hang_count": 1, "total_stall_ms": 100.0, "worst_hang_ms": 50.0}
    failures = compare(current, tight_baseline)
    assert len(failures) == 3, f"ratchet failed to fire: {failures}"

    ok_baseline = {"hang_count": 2, "total_stall_ms": 5000.0, "worst_hang_ms": 3000.0}
    assert compare(current, ok_baseline) == []

    print("[ok] self-test: ratchet fires on regression, passes at baseline")


def main() -> None:
    args = sys.argv[1:]
    if "--self-test" in args:
        self_test()
        return

    update = "--update-baseline" in args
    inputs = [a for a in args if not a.startswith("--")]
    if not inputs:
        # NOT ARMED: no trace on this machine — the thing measured does not
        # exist here yet. Never fail every developer's gate for that.
        print("[ok] hang ratchet not armed: no trace supplied")
        return

    source = Path(inputs[0])
    if not source.exists():
        print(f"BLIND: input {source} does not exist")
        sys.exit(2)
    xml_text = export_hangs_xml(source) if source.suffix == ".trace" else source.read_text()
    current = measure(xml_text)
    print(f"measured: {json.dumps(current)}")

    if update:
        BASELINE_PATH.write_text(json.dumps(current, indent=2) + "\n")
        print(f"[ok] baseline written to {BASELINE_PATH} — commit it, and say in the "
              f"commit message what bought the change")
        return

    if not BASELINE_PATH.exists():
        print(
            f"BLIND: a trace was supplied but no committed baseline exists at "
            f"{BASELINE_PATH}. First run: --update-baseline (the legitimate first run)."
        )
        sys.exit(2)
    baseline = json.loads(BASELINE_PATH.read_text())
    failures = compare(current, baseline)
    if failures:
        print("FAIL main-thread stall grew (#4550):")
        for failure in failures:
            print(f"  - {failure}")
        print("Re-run on a quiet machine, or raise the baseline with "
              "--update-baseline saying what bought the time.")
        sys.exit(1)
    print(f"[ok] within baseline ({json.dumps(baseline)})")


if __name__ == "__main__":
    main()
