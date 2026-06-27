#!/usr/bin/env bash
# Turn a machine-readable verify_all failure report into GitHub issues.
#
# Reads build/verify_all_report.json (produced by scripts/verify_all.sh) and,
# per failing check (and per failing pytest node), prints a `gh issue create`
# command routed to the right milestone.
#
#   Dry-run by default — it only PRINTS the commands.
#   --apply actually files them, de-duping against existing OPEN issues by exact
#           title, and writes a manager-flag at build/verify_all_needs_fixing.json
#           plus a loud MANAGER-ACTION line for the autonomous loop to poll.
#
# Category -> milestone routing (title prefix):
#   swift-lint   -> "SwiftUI App Structure & Naming"      lint(swift): <label> failing
#   python-lint  -> "Repo Hygiene & Structure"            lint(py): <label> failing
#   guardrail    -> "Programmatic Guardrails"             guardrail: <label> failing
#   contract     -> "API Surface & Test Harness"          contract: OpenAPI model sync drift
#   test         -> "Test Coverage"                        test failing: <node_id>  (one per node)
#   build(macos) -> "Mac App Shell"                        build(macOS) failing
#   build(ios)   -> "iOS/iPad Embedding & Multi-Library"   build(<platform>) failing
#   other        -> "Repo Hygiene & Structure"             verify_all: <label> failing
set -uo pipefail

cd "$(dirname "$0")/.." || exit 2

apply=0
report="build/verify_all_report.json"

show_help() {
  cat <<'EOF'
Usage:
  scripts/verify_to_issues.sh [--apply] [--report PATH]

  (default)        dry-run: print the gh issue create commands only
  --apply          file the issues (de-duped by exact open-issue title),
                   write build/verify_all_needs_fixing.json, print MANAGER-ACTION
  --report PATH    read a different report (default build/verify_all_report.json)
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --apply) apply=1 ;;
    --report) shift; report="${1:-}" ;;
    --report=*) report="${1#--report=}" ;;
    -h|--help) show_help; exit 0 ;;
    *) echo "verify_to_issues: unknown arg: $1" >&2; show_help >&2; exit 2 ;;
  esac
  shift
done

if [[ ! -f "$report" ]]; then
  echo "verify_to_issues: report not found: $report" >&2
  echo "  run scripts/verify_all.sh first (it always writes build/verify_all_report.json)" >&2
  exit 2
fi

PY_BIN="python3"
[[ -x ".venv/bin/python" ]] && PY_BIN=".venv/bin/python"
[[ -n "${PYTHON_BIN:-}" ]] && PY_BIN="$PYTHON_BIN"

APPLY="$apply" REPORT="$report" "$PY_BIN" - <<'PY'
import json
import os
import shlex
import subprocess
import sys

apply = os.environ.get("APPLY", "0") == "1"
report_path = os.environ["REPORT"]

with open(report_path) as handle:
    report = json.load(handle)

checks = report.get("checks", [])

# category -> (milestone, title-builder). build is resolved per-label.
STATIC = {
    "swift-lint": "SwiftUI App Structure & Naming",
    "python-lint": "Repo Hygiene & Structure",
    "guardrail": "Programmatic Guardrails",
    "contract": "API Surface & Test Harness",
    "test": "Test Coverage",
    "other": "Repo Hygiene & Structure",
}


def build_platform(label):
    low = label.lower()
    if "iphone" in low:
        return "iPhone", "iOS/iPad Embedding & Multi-Library"
    if "ipad" in low:
        return "iPad", "iOS/iPad Embedding & Multi-Library"
    if "visionos" in low:
        return "visionOS", "iOS/iPad Embedding & Multi-Library"
    if "macos" in low:
        return "macOS", "Mac App Shell"
    return "unknown", "Mac App Shell"


def body_for(check, extra=""):
    tail = check.get("output_tail", "").rstrip("\n")
    lines = [
        f"Filed automatically from `verify_all` ({check.get('tier', '?')} tier).",
        "",
        f"- check: `{check.get('label', '')}`",
        f"- category: `{check.get('category', '')}`",
        f"- command: `{check.get('command', '')}`",
    ]
    if extra:
        lines.append(extra)
    lines += ["", "Output tail:", "", "```", tail, "```"]
    return "\n".join(lines)


def issues_from_check(check):
    """Yield (title, milestone, body) tuples for one report record."""
    category = check.get("category", "other")
    label = check.get("label", "")
    if category == "test":
        nodes = check.get("failing_tests") or []
        if not nodes:
            # Pytest failed but no node IDs parsed — file one rollup issue.
            yield (
                f"test failing: {label}",
                STATIC["test"],
                body_for(check),
            )
        for node in nodes:
            yield (
                f"test failing: {node}",
                STATIC["test"],
                body_for(check, extra=f"- failing node: `{node}`"),
            )
        return
    if category == "build":
        platform, milestone = build_platform(label)
        yield (f"build({platform}) failing", milestone, body_for(check))
        return
    if category == "contract":
        yield ("contract: OpenAPI model sync drift", STATIC["contract"], body_for(check))
        return
    if category == "swift-lint":
        yield (f"lint(swift): {label} failing", STATIC["swift-lint"], body_for(check))
        return
    if category == "python-lint":
        yield (f"lint(py): {label} failing", STATIC["python-lint"], body_for(check))
        return
    if category == "guardrail":
        yield (f"guardrail: {label} failing", STATIC["guardrail"], body_for(check))
        return
    yield (f"verify_all: {label} failing", STATIC["other"], body_for(check))


units = []
for check in checks:
    for title, milestone, body in issues_from_check(check):
        units.append({"title": title, "milestone": milestone, "body": body,
                      "category": check.get("category", "other")})

if not units:
    print("verify_to_issues: no failures in report — nothing to file.")
    sys.exit(0)


def existing_open_issue(title):
    """Return issue number if an OPEN issue with this exact title exists."""
    try:
        out = subprocess.check_output(
            ["gh", "issue", "list", "--state", "open", "--search",
             f'{title} in:title', "--json", "number,title", "-L", "100"],
            text=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    for item in json.loads(out or "[]"):
        if item.get("title") == title:
            return item.get("number")
    return None


if not apply:
    print(f"# verify_to_issues (DRY-RUN): {len(units)} issue(s) from {report_path}")
    print("# category -> milestone routing shown below; re-run with --apply to file.\n")
    for unit in units:
        cmd = [
            "gh", "issue", "create",
            "--title", unit["title"],
            "--milestone", unit["milestone"],
            "--body", unit["body"],
        ]
        print(" ".join(shlex.quote(part) for part in cmd))
        print()
    sys.exit(0)

# --apply: file (de-duped), record results, flag the manager.
filed = []
for unit in units:
    existing = existing_open_issue(unit["title"])
    if existing is not None:
        print(f"SKIP (exists #{existing}): {unit['title']}")
        continue
    try:
        out = subprocess.check_output(
            ["gh", "issue", "create",
             "--title", unit["title"],
             "--milestone", unit["milestone"],
             "--body", unit["body"]],
            text=True,
        ).strip()
    except subprocess.CalledProcessError as exc:
        print(f"FAIL to file: {unit['title']} ({exc})", file=sys.stderr)
        continue
    # gh prints the issue URL; extract the trailing number.
    num = None
    tail = out.rstrip("/").rsplit("/", 1)[-1]
    if tail.isdigit():
        num = int(tail)
    print(f"FILED #{num}: {unit['title']}  [{unit['milestone']}]")
    filed.append({
        "issue": num,
        "title": unit["title"],
        "category": unit["category"],
        "milestone": unit["milestone"],
    })

ts = os.environ.get("VERIFY_ALL_TS", "")
flag = {"filed": filed, "ts": ts}
os.makedirs("build", exist_ok=True)
with open("build/verify_all_needs_fixing.json", "w") as handle:
    json.dump(flag, handle, indent=2)
    handle.write("\n")

if filed:
    nums = " ".join(f"#{f['issue']}" for f in filed if f["issue"] is not None)
    print(f"MANAGER-ACTION: {len(filed)} verify_all failures filed as issues "
          f"({nums}) — dispatch fix-workers")
else:
    print("verify_to_issues: all failures already had open issues — nothing newly filed.")
PY
