"""The bug report for a failed run (`run.fail.bug-report-route`, `run.fail.bug-report-contents`, #6354): built by the engine, so the
app, the CLI and an agent send the same report and the redaction is tested once (`llm/failure.redact`)."""

from __future__ import annotations

import json
import os
import platform
import subprocess
from typing import Any, Optional

from pydantic import BaseModel, Field

from fichero_server.llm.failure import redact


class BugReportAttachment(BaseModel):
    name: str = Field(description="`run.json` (the run's fields) or `log.txt` (its Problems lines)")
    text: str


class BugReport(BaseModel):
    title: str = Field(description='"<kind>: <the words\' first sentence>"')
    body: str = Field(description="plain text: what stopped, where, and on what; nothing private (`llm/failure.redact`)")
    attachments: list[BugReportAttachment]


def environment() -> dict[str, Optional[str]]:
    """The engine's version and tier, macOS and the Mac model: what a report needs to say what ran, none of it private."""
    from fichero_server.api.main import _ENGINE_VERSION

    try:
        model = subprocess.run(["sysctl", "-n", "hw.model"], capture_output=True, text=True, timeout=2).stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        model = None
    return {"engine_version": _ENGINE_VERSION, "tier": os.environ.get("FICHERO_FEATURE_TIER", "release").strip().lower(),
            "macos": platform.mac_ver()[0] or platform.platform(), "arch": platform.machine(), "mac_model": model}


def _first_sentence(words: str) -> str:
    end = words.find(". ")
    return words if end < 0 else words[: end + 1]


def build_report(run: Any, problem_lines: list[str], *, traceback: str | None, env: dict[str, Optional[str]]) -> BugReport:
    """The report for a failed run (`run.failure` set): title, plain-text body and two attachments, every text through `redact`."""
    failure = run.failure or {}
    fields: dict[str, Any] = {
        "run_id": run.thread_id, "workflow": run.workflow_name, "step": failure.get("step"),
        "failure": {"kind": failure.get("kind"), "words": failure.get("words"), "exception_type": failure.get("exception_type"),
                    "detail": failure.get("detail")},
        "provider": failure.get("provider"), "model": failure.get("model"),
        "pages_done": failure.get("pages_done"), "pages_total": failure.get("pages_total"),
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "ended_at": run.completed_at.isoformat() if run.completed_at else None,
        "duration_ms": run.duration_ms, **env}
    lines = [f"{k}: {v}" for k, v in fields.items() if k != "failure" and v is not None]
    lines.insert(0, f"{failure.get('kind')}: {failure.get('words')}")
    lines.append(f"exception: {failure.get('exception_type')}: {failure.get('detail')}")
    if traceback:
        lines += ["", "traceback:", traceback]
    run_json = json.dumps(fields, indent=2, default=str)
    return BugReport(
        title=redact(f"{failure.get('kind')}: {_first_sentence(failure.get('words') or '')}"),
        body=redact("\n".join(lines)),
        attachments=[BugReportAttachment(name="run.json", text=redact(run_json)),
                     BugReportAttachment(name="log.txt", text=redact("\n".join(problem_lines)))])
