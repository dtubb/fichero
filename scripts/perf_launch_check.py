#!/usr/bin/env python3
"""The app's launch budgets from one launch's log (#7105).

    python scripts/perf_launch_check.py LOG

LOG is the app's `LaunchProfile` lines: its stderr with `FICHERO_LAUNCH_PROFILE_STDOUT=1`, or a `log stream --style json` capture.
The launch must be a Dev Local build started with a scratch saved-libraries list, never a person's own libraries. Prints what is
over budget or missing, then one `LAUNCH-RESULT {json}` line (last) with the figures for the baseline. Exit 1 unless every
milestone was logged and every figure is inside its budget; this script launches nothing."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "fichero-builder"))
from fichero_builder import perf_log_readers  # noqa: E402


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    result = perf_log_readers.launch_budgets(Path(sys.argv[1]).read_text(errors="replace").splitlines())
    for name in result["missing"]:
        print(f"not logged: {name}")
    for line in result["over"]:
        print(f"over budget: {line}")
    print("LAUNCH-RESULT " + json.dumps(result, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
