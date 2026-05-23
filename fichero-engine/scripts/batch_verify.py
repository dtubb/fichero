#!/usr/bin/env python3
"""Batch verification harness for paleography/legal PDF pipelines (#1177).

Imports 1-3 files, runs a workflow, and produces a Markdown pass/fail
report covering: import status, transcription artifact, extraction status,
KG entity/claim counts, and sample quote quality.

Usage:
    python scripts/batch_verify.py \
        --files "/path/a.pdf" "/path/b.pdf" \
        --workflow "Transcribe (Auto-Detect)" \
        --library "/path/to/library.fichero" \
        [--base-url http://127.0.0.1:8765] \
        [--output-md report.md] \
        [--timeout 600]

Defaults to FICHERO_LIBRARY_PATH env var for --library.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# CLI wrapper helpers
# ---------------------------------------------------------------------------

PYTHON = sys.executable
MODULE = [PYTHON, "-m", "fichero.cli"]

try:
    import fichero.cli  # noqa: F401
    _CLI_CMD = [PYTHON, "-m", "fichero.cli"]
except ImportError:
    _CLI_CMD = ["fichero"]


def _run(args: list[str], library: str, base_url: str) -> dict[str, Any]:
    """Run a fichero CLI command and return parsed JSON output."""
    env = os.environ.copy()
    env["FICHERO_LIBRARY_PATH"] = library
    cmd = _CLI_CMD + ["--json", "--library", library, "--base-url", base_url] + args
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"CLI error ({result.returncode}): {result.stderr.strip() or result.stdout.strip()}"
        )
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"raw": result.stdout.strip()}


def _run_checked(args: list[str], library: str, base_url: str) -> tuple[bool, Any, str]:
    """Run a CLI command; return (ok, data, error_message)."""
    try:
        data = _run(args, library, base_url)
        return True, data, ""
    except Exception as exc:
        return False, None, str(exc)


# ---------------------------------------------------------------------------
# Per-file verification
# ---------------------------------------------------------------------------

class FileResult:
    def __init__(self, path: str) -> None:
        self.path = path
        self.filename = Path(path).name
        self.doc_id: str | None = None
        self.import_ok = False
        self.import_error = ""
        self.workflow_name: str | None = None
        self.workflow_ok = False
        self.workflow_error = ""
        self.workflow_status = ""
        self.transcription_present = False
        self.transcription_sample = ""
        self.extraction_present = False
        self.entity_count = 0
        self.claim_count = 0
        self.sample_claim = ""
        self.auth_error = False
        self.notes: list[str] = []

    @property
    def passed(self) -> bool:
        return (
            self.import_ok
            and self.workflow_ok
            and self.transcription_present
        )


def verify_file(
    path: str,
    workflow_name: str,
    library: str,
    base_url: str,
    timeout: float,
) -> FileResult:
    result = FileResult(path)
    result.workflow_name = workflow_name

    # 1. Import
    ok, data, err = _run_checked(
        ["import", path],
        library, base_url,
    )
    if not ok:
        result.import_error = err
        if "401" in err or "403" in err or "Unauthorized" in err:
            result.auth_error = True
        return result

    # Extract doc_id from import response
    doc_id = (
        data.get("id")
        or data.get("document", {}).get("id")
        or (data.get("items") or [{}])[0].get("id")
    )
    if not doc_id:
        result.import_error = f"No doc_id in import response: {data}"
        return result

    result.doc_id = doc_id
    result.import_ok = True

    # 2. Run workflow
    ok, wf_data, err = _run_checked(
        ["workflow", "run", workflow_name, doc_id, "--wait", "--timeout", str(timeout)],
        library, base_url,
    )
    if not ok:
        result.workflow_error = err
        if "401" in err or "403" in err or "quota" in err.lower():
            result.auth_error = True
        return result

    status = wf_data.get("status", "")
    result.workflow_status = status
    if status not in ("completed", "success", "done"):
        result.workflow_error = f"Workflow ended with status '{status}'"
        result.notes.append(f"Workflow output: {wf_data.get('error') or wf_data.get('message', '')}")
        return result

    result.workflow_ok = True

    # 3. Check artifacts
    ok, art_data, err = _run_checked(
        ["artifacts", "list", "--doc-id", doc_id],
        library, base_url,
    )
    if ok:
        items = art_data.get("items") or art_data.get("artifacts") or []
        for art in items:
            atype = art.get("artifact_type") or art.get("type") or ""
            if atype == "transcription":
                result.transcription_present = True
                content = art.get("content") or ""
                result.transcription_sample = content[:200].replace("\n", " ")
            if atype in ("entities", "people", "extract"):
                result.extraction_present = True
    else:
        result.notes.append(f"Artifacts list failed: {err}")

    # 4. Check KG entities + claims
    ok, kg_data, err = _run_checked(
        ["docs", "kg", doc_id],
        library, base_url,
    )
    if ok:
        entities = kg_data.get("entities") or kg_data.get("items") or []
        result.entity_count = len(entities)
        claims = kg_data.get("claims") or []
        result.claim_count = len(claims)
        if claims:
            first = claims[0]
            subj = first.get("subject") or first.get("text") or ""
            verb = first.get("predicate_verb") or first.get("verb") or ""
            obj = first.get("object_phrase") or first.get("object") or ""
            src = (first.get("source_excerpt") or first.get("source_text") or "")[:100]
            result.sample_claim = f"{subj} {verb} {obj} | excerpt: {src}"
    else:
        result.notes.append(f"KG query failed: {err}")

    return result


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

PASS = "✅"
FAIL = "❌"
WARN = "⚠️"


def render_report(
    results: list[FileResult],
    workflow_name: str,
    library: str,
    elapsed: float,
) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines: list[str] = [
        f"# Batch Verification Report",
        f"",
        f"**Generated:** {now}  ",
        f"**Library:** `{library}`  ",
        f"**Workflow:** {workflow_name}  ",
        f"**Files:** {len(results)}  ",
        f"**Elapsed:** {elapsed:.1f}s",
        f"",
        f"## Summary",
        f"",
        f"| File | Import | Workflow | Transcription | Entities | Claims | Status |",
        f"|------|--------|----------|---------------|----------|--------|--------|",
    ]

    for r in results:
        imp = PASS if r.import_ok else FAIL
        wf = PASS if r.workflow_ok else (WARN if r.auth_error else FAIL)
        tx = PASS if r.transcription_present else FAIL
        ent = str(r.entity_count) if r.entity_count else "—"
        cl = str(r.claim_count) if r.claim_count else "—"
        status = PASS if r.passed else FAIL
        lines.append(
            f"| `{r.filename}` | {imp} | {wf} | {tx} | {ent} | {cl} | {status} |"
        )

    lines += ["", "## File Details", ""]

    for r in results:
        icon = PASS if r.passed else FAIL
        lines.append(f"### {icon} `{r.filename}`")
        lines.append(f"")
        if r.doc_id:
            lines.append(f"- **Doc ID:** `{r.doc_id}`")
        if not r.import_ok:
            lines.append(f"- **Import:** {FAIL} {r.import_error}")
        else:
            lines.append(f"- **Import:** {PASS}")
        if r.workflow_error:
            lines.append(f"- **Workflow ({r.workflow_name}):** {FAIL} {r.workflow_error}")
            if r.workflow_status:
                lines.append(f"  - Status: `{r.workflow_status}`")
        elif r.workflow_ok:
            lines.append(f"- **Workflow ({r.workflow_name}):** {PASS}")
        if r.transcription_present:
            lines.append(f"- **Transcription:** {PASS}")
            if r.transcription_sample:
                lines.append(f"  - Sample: _{r.transcription_sample}…_")
        else:
            lines.append(f"- **Transcription:** {FAIL} (no artifact found)")
        lines.append(f"- **Entities:** {r.entity_count} | **Claims:** {r.claim_count}")
        if r.sample_claim:
            lines.append(f"- **Sample claim:** _{r.sample_claim}_")
        if r.auth_error:
            lines.append(f"- {WARN} **Auth/quota error detected** — check OpenRouter/API key config")
        for note in r.notes:
            lines.append(f"- Note: {note}")
        lines.append("")

    passed = sum(1 for r in results if r.passed)
    total = len(results)
    lines += [
        "## Checklist",
        "",
        f"- [{'x' if passed == total else ' '}] All {total} files passed end-to-end",
        f"- [{'x' if all(r.transcription_present for r in results) else ' '}] All transcriptions present",
        f"- [{'x' if all(r.entity_count > 0 for r in results) else ' '}] All files have ≥1 KG entity",
        f"- [{'x' if not any(r.auth_error for r in results) else ' '}] No auth/quota errors",
        "",
    ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--files", nargs="+", required=True, help="Paths to PDF files to test (1-3 recommended)")
    parser.add_argument("--workflow", default="Transcribe (Auto-Detect)", help="Workflow name to run")
    parser.add_argument("--library", default=os.environ.get("FICHERO_LIBRARY_PATH", ""), help="Library path")
    parser.add_argument("--base-url", default=os.environ.get("FICHERO_API_URL", "http://127.0.0.1:8765"))
    parser.add_argument("--output-md", default="batch_verify_report.md", help="Output Markdown file path")
    parser.add_argument("--timeout", type=float, default=600.0, help="Per-file workflow timeout in seconds")
    args = parser.parse_args()

    if not args.library:
        parser.error("--library is required (or set FICHERO_LIBRARY_PATH)")

    if len(args.files) > 5:
        print(f"Warning: {len(args.files)} files requested — batch_verify is designed for 1-5 files. Consider splitting.")

    print(f"Batch verify: {len(args.files)} file(s) via '{args.workflow}'")
    print(f"Library: {args.library}")
    print(f"Backend: {args.base_url}")
    print()

    start = time.monotonic()
    results: list[FileResult] = []

    for i, path in enumerate(args.files, 1):
        print(f"[{i}/{len(args.files)}] {Path(path).name} ...", end=" ", flush=True)
        r = verify_file(path, args.workflow, args.library, args.base_url, args.timeout)
        results.append(r)
        status = "PASS" if r.passed else ("AUTH" if r.auth_error else "FAIL")
        print(f"{status} (entities={r.entity_count}, claims={r.claim_count})")
        if not r.import_ok:
            print(f"  Import error: {r.import_error}")
        if r.workflow_error:
            print(f"  Workflow error: {r.workflow_error}")

    elapsed = time.monotonic() - start
    report = render_report(results, args.workflow, args.library, elapsed)

    out_path = Path(args.output_md)
    out_path.write_text(report, encoding="utf-8")
    print(f"\nReport written to: {out_path}")

    passed = sum(1 for r in results if r.passed)
    print(f"Result: {passed}/{len(results)} passed")

    sys.exit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()
