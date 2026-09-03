#!/usr/bin/env python3
"""Exercise DEFAULT workflows end-to-end through the engine's HTTP API.

`exercise_tools.py` proves each TOOL against a real model in-process; this
script proves each shipped WORKFLOW PRESET the way a user runs it — via the
API, on a real (scratch) library, with the library's AI-default settings —
and writes down a workflow × model matrix of what actually happened.

    scripts/exercise_workflows.py \
        --base-url https://127.0.0.1:8767 \
        --library ~/scratch/Scratch.fichero \
        --doc 77dd3c89 --pass-name apple \
        --workflows "Transcribe,Clean Up Text" \
        --out agent-work/design/workflow-exercise/apple.json

A "pass" = one model configuration (the library AI defaults are set BEFORE
invoking this script, via `fichero settings set`). The script only runs and
records; it never changes settings itself, so the report can't lie about
which settings a row ran under — it snapshots them from the engine per pass.

Rows record: workflow, docs, status, wall seconds, error text, error_kind
(the engine emits one since 2026-09), and the first activity line naming the
failed node. Everything goes through the CLI client (no raw curl).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def fcli(args: argparse.Namespace, *cmd: str, timeout: float = 60.0):
    """Run the fichero CLI with --json and parse its output."""
    full = [
        sys.executable, "-m", "fichero_cli",
        "--base-url", args.base_url, "--json",
        "-l", args.library, *cmd,
    ]
    env = dict(__import__("os").environ)
    env["PYTHONPATH"] = (
        f"{REPO / 'fichero-cli' / 'src'}:{REPO / 'fichero-server' / 'src'}"
    )
    proc = subprocess.run(
        full, capture_output=True, text=True, timeout=timeout, env=env,
    )
    out = proc.stdout.strip()
    try:
        payload = json.loads(out) if out else None
    except json.JSONDecodeError:
        payload = out
    return proc.returncode, payload, proc.stderr.strip()


def snapshot_settings(args) -> dict:
    rc, payload, _ = fcli(args, "settings", "list")
    return payload if isinstance(payload, dict) else {"raw": payload}


def run_workflow(args, name: str, doc_id: str) -> dict:
    row: dict = {"workflow": name, "doc": doc_id}
    started = time.monotonic()
    try:
        rc, payload, err = fcli(
            args, "workflow", "run", name, doc_id,
            "--wait", "--timeout", str(args.timeout),
            timeout=args.timeout + 60,
        )
    except subprocess.TimeoutExpired:
        row.update(status="driver_timeout", seconds=round(time.monotonic() - started, 1))
        return row
    row["seconds"] = round(time.monotonic() - started, 1)
    if not isinstance(payload, dict):
        row.update(status="cli_error", error=(err or str(payload))[:800])
        return row
    row["status"] = payload.get("status") or ("ok" if rc == 0 else "failed")
    if payload.get("error"):
        row["error"] = str(payload["error"])[:800]
    # error_kind: surfaced on the checkpoint state or top level, engine-version
    # dependent — look in both places rather than guessing wrong.
    for source in (payload, payload.get("current_state") or {}):
        if isinstance(source, dict) and source.get("error_kind"):
            row["error_kind"] = source["error_kind"]
            break
    state = payload.get("current_state") or {}
    if isinstance(state, dict):
        row["completed_nodes"] = state.get("completed_nodes")
        row["failed_node"] = state.get("current_node")
    return row


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--library", required=True)
    ap.add_argument("--doc", action="append", required=True,
                    help="document id; repeatable — each workflow runs on each doc")
    ap.add_argument("--workflows", required=True,
                    help="comma-separated workflow display names or ids")
    ap.add_argument("--pass-name", required=True,
                    help="label for this model pass, e.g. apple / omlx-qwen3vl")
    ap.add_argument("--timeout", type=float, default=600.0)
    ap.add_argument("--out", help="append JSON rows here (one file per pass)")
    args = ap.parse_args()

    workflows = [w.strip() for w in args.workflows.split(",") if w.strip()]
    settings = snapshot_settings(args)
    rows = []
    for wf in workflows:
        for doc in args.doc:
            print(f"→ [{args.pass_name}] {wf} on {doc[:8]} …", flush=True)
            row = run_workflow(args, wf, doc)
            row["pass"] = args.pass_name
            rows.append(row)
            state = row.get("status")
            err = (row.get("error") or "")[:100]
            print(f"   {state} in {row.get('seconds', '?')}s"
                  + (f" — {err}" if err else ""), flush=True)

    report = {"pass": args.pass_name, "settings": settings, "rows": rows}
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2, default=str))
        print(f"report: {out}")
    failed = [r for r in rows if r.get("status") not in ("completed", "ok")]
    print(f"\n{len(rows) - len(failed)}/{len(rows)} succeeded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
