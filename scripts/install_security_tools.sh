#!/bin/bash
# Installs the security rung's scanners and the perf rung's Python tools on a runner, then confirms the REAL installed versions
# and (with --write-pins) writes them into harness.toml's [check.security].pins. (#6600, Step 2.30)
#
#   scripts/install_security_tools.sh [--write-pins] [--check]
#
#   (default)     install: brew semgrep gitleaks osv-scanner, uv tool bandit, pip pytest-benchmark pyinstrument into $FICHERO_RUNNER_VENV
#   --check       install nothing; print the version of each tool and whether it equals the pin in harness.toml (exit 1 on any mismatch)
#   --write-pins  after installing, write the versions found into harness.toml (a pin is never typed by hand, never guessed)
#
# A pin that is empty or differs from what is installed makes the rung print REFUSED naming the tool (report-only until measured).
set -euo pipefail
cd "$(dirname "$0")/.."
WRITE=0; CHECK=0
for a in "$@"; do case "$a" in --write-pins) WRITE=1;; --check) CHECK=1;; *) echo "unknown argument: $a" >&2; exit 2;; esac; done

if [ "$CHECK" = 0 ]; then
  brew install semgrep gitleaks osv-scanner
  uv tool install bandit
  VENV="${FICHERO_RUNNER_VENV:-$HOME/fichero-gate/venv}"
  "$VENV/bin/python" -m pip install pytest-benchmark==5.3.1 pyinstrument==5.1.3
fi

PY="${FICHERO_PYTHON:-python3}"
exec "$PY" - "$WRITE" "$CHECK" <<'PYEOF'
import re, subprocess, sys, tomllib
from pathlib import Path
write, check = sys.argv[1] == "1", sys.argv[2] == "1"
sys.path.insert(0, "scripts")
from security_scan_run import version  # the same reader the rung uses, so the pin and the check agree
found = {n: version(n) for n in ("bandit", "semgrep", "gitleaks", "osv-scanner")}
toml = Path("harness.toml")
pins = tomllib.loads(toml.read_text())["check"]["security"].get("pins", {})
bad = 0
for n, v in found.items():
    state = "NOT INSTALLED" if v is None else ("matches the pin" if pins.get(n) == v else f"pin is {pins.get(n) or 'empty'!r}")
    print(f"{n}: {v or '-'} ({state})")
    bad += v is None or pins.get(n) != v
if write:
    missing = [n for n, v in found.items() if v is None and n != "osv-scanner"]
    if missing:
        sys.exit(f"not writing pins: {', '.join(missing)} not installed")
    key = lambda n: f'"{n}"' if "-" in n else n
    line = "pins = { " + ", ".join(f'{key(n)} = "{v or ""}"' for n, v in found.items()) + " }"
    text, n = re.subn(r"^pins = \{.*\}$", line, toml.read_text(), count=1, flags=re.M)
    if n != 1:
        sys.exit("harness.toml has no one-line [check.security] pins to rewrite")
    toml.write_text(text)
    print("wrote", line)
    bad = 0
sys.exit(1 if check and bad else 0)
PYEOF
