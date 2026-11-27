#!/usr/bin/env python3
"""The four scanners over one batch, reading only what is NEW, and one table (#6600, Step 2.30, `dev-workflows.quality.security-scan-rung`).

    python scripts/security_scan_run.py --since <base> --head <head> --pins '{"bandit": "1.8.6", ...}'

Runs bandit (`-b` its baseline), semgrep (`--baseline-commit <since>`), gitleaks (over `<since>..<head>`'s commits, with its baseline
file) and, only when `osv-scanner-enabled`, osv-scanner; refuses a scanner that is missing or not at its pinned version (REFUSED by
name); hands their JSON to `fichero_builder.security_rung` and prints one `SECURITY-RESULT {json}` line (last). Exit 0: the rung
decides what a red means. Nothing here finds a vulnerability: the tools do."""
import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "fichero-builder"))
from fichero_builder import security_rung as sr  # noqa: E402

PY_DIRS = ["fichero-server/src", "fichero-cli/src", "fichero-mcp/src", "fichero-builder", "scripts"]
VERSION_CMD = {"bandit": ["bandit", "--version"], "semgrep": ["semgrep", "--version"], "gitleaks": ["gitleaks", "version"], "osv-scanner": ["osv-scanner", "--version"]}
MAX_ROWS = 25  # the rung reads the last 4000 characters of this line's stream


def version(name: str) -> str | None:
    try:
        r = subprocess.run(VERSION_CMD[name], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return None
    m = re.search(r"\d+\.\d+(?:\.\d+)?", r.stdout + r.stderr)
    return m.group(0) if r.returncode == 0 and m else None


def load(path: Path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def run(argv) -> None:
    subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, timeout=1200)  # exit codes 1 = "findings", read from the JSON, not the status


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", required=True)
    ap.add_argument("--head", required=True)
    ap.add_argument("--pins", default="{}")
    a = ap.parse_args()
    pins = json.loads(a.pins)
    osv_on = bool(pins.get("osv-scanner-enabled"))
    refused = sr.refused_tools({n: version(n) for n in sr.SCANNERS}, pins)
    broken = {r.split()[1] for r in refused}
    out = Path(tempfile.mkdtemp(prefix="security-"))
    rows: list[dict] = []
    if "bandit" not in broken:
        run(["bandit", "-r", *PY_DIRS, "-f", "json", "-o", str(out / "bandit.json"), "-b", "scripts/bandit_baseline.json",
             "--severity-level", "medium", "--confidence-level", "medium"])
        if (d := load(out / "bandit.json")) is not None:
            rows += sr.read_bandit(d, load(ROOT / "scripts/bandit_baseline.json"))
        else:
            refused.append("REFUSED: bandit wrote no JSON")
    if "semgrep" not in broken:
        for cfg, dirs, name in ((["--config", "p/python", "--config", "p/secrets", "--config", ".semgrep/"], PY_DIRS, "semgrep-py.json"),
                                (["--config", "p/swift", "--config", ".semgrep/"], ["fichero/"], "semgrep-swift.json")):
            run(["semgrep", "scan", *cfg, "--baseline-commit", a.since, "--json", "-o", str(out / name), "--metrics=off", *dirs])
            if (d := load(out / name)) is not None:
                rows += sr.read_semgrep(d)
            else:
                refused.append(f"REFUSED: semgrep wrote no JSON for {name}")
    if "gitleaks" not in broken:
        run(["gitleaks", "git", f"--log-opts={a.since}..{a.head}", "--redact", "--report-format", "json", "--report-path", str(out / "gitleaks.json"),
             "--baseline-path", "scripts/gitleaks_baseline.json", "--config", "scripts/gitleaks.toml"])
        rows += sr.read_gitleaks(load(out / "gitleaks.json") or [], None)
    if osv_on and "osv-scanner" not in broken:
        locks = ["fichero-server/uv.lock", "fichero/fichero.xcodeproj/project.xcworkspace/xcshareddata/swiftpm/Package.resolved", "fichero/fichero-api-client/Package.resolved"]
        run(["osv-scanner", "scan", *[x for p in locks if (ROOT / p).exists() for x in ("--lockfile", p)], "--config", "osv-scanner.toml", "--format", "json", "--output", str(out / "osv.json")])
        rows += sr.read_osv(load(out / "osv.json") or {})
    rows.sort(key=lambda r: not r["red"])
    print("SECURITY-RESULT " + json.dumps({"rows": rows[:MAX_ROWS], "refused": refused, "table": sr.table(rows[:MAX_ROWS]), "total": len(rows)}, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
