#!/usr/bin/env python
"""Opt-in end-to-end verification of the default workflows on a REAL local model (#4326).

Driven by scripts/verify_workflows.sh — read that header for scheduling
guidance. This driver:

1. Creates a DISPOSABLE state root (FICHERO_BASE_PATH=<tmp>) so the app DB,
   auth token, and the global library are all throwaway.
2. Seeds <tmp>/global.fichero with fichero-server/scripts/seed_test_library.py
   --with-files (real specimens from test-fixtures/files/). Naming the package
   global.fichero makes it the engine's global library, so the server's own
   first-open path seeds the shipped default workflows into it (#4102) and the
   keyless AI-defaults bootstrap points every tier at the on-device Apple
   provider (#4324/#4325). Nothing here is stubbed or monkeypatched.
3. Boots uvicorn on loopback and runs every DIRECT-RUNNABLE default workflow
   (every shipped preset except config.internal children) end-to-end through
   POST /api/workflow-execution/execute — the same path the app uses.
4. Asserts per run, using the #4316 status vocabulary:
   - terminal status == "completed";
   - artifacts written by the run (filtered by run_id == thread_id) carry the
     #4313 provenance fields (run_id, workflow_id, step_name);
   - transcription-family workflows land non-empty page_content on the target.
5. Emits ONE parseable summary line per workflow, e.g.:
       WORKFLOW-E2E | name=Catalogue | status=PASS | seconds=41.2 | ...
       WORKFLOW-E2E | name=Translate | status=FAIL | step=text_translate | error=...
       WORKFLOW-E2E | name=Describe (visual) | status=SKIP | reason=...
   and a final WORKFLOW-E2E-SUMMARY line. Exit 0 only when failed == 0.

Capability honesty: a workflow that needs a capability this host lacks
(Apple Intelligence text via fm-bridge, Apple Vision OCR via PyObjC) is
reported SKIP with a loud reason — it never silently passes. The driver
tries to build fm-bridge from source first (bin/fm-bridge/build.sh) unless
--no-build-bridge is given.

Usage:
    scripts/verify_workflows.sh                    # full sweep
    scripts/verify_workflows.sh --only 'Transcribe|Catalogue'
    scripts/verify_workflows.sh --timeout 300 --budget 1500
    scripts/verify_workflows.sh --list             # show plan, run nothing
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SERVER_SRC = REPO / "fichero-server" / "src"
PRESETS_DIR = SERVER_SRC / "fichero_server" / "resources" / "default_workflows"
SEED_SCRIPT = REPO / "fichero-server" / "scripts" / "seed_test_library.py"
BRIDGE_DIR = REPO / "fichero-server" / "bin" / "fm-bridge"

# Fixture doc ids seeded by seed_test_library.py --with-files, plus the two
# text-bearing pages this driver registers itself (Apple Vision returns an
# EMPTY transcription for the no-text sample.jpg, which fails every
# transcribe-family preset — the OCR target must actually contain text).
DOC_IMAGE = "e2e-text-image-1"
DOC_IMAGE_2 = "e2e-text-image-2"
DOC_TEXT = "test-doc-fixture-txt"
DOC_PDF = "test-doc-fixture-pdf"
DOC_LETTER = "test-doc-letter"  # carries page_content out of the box

# Presets whose input contract needs a specific target shape.
TARGET_OVERRIDES: dict[str, list[str]] = {
    "Group Same Documents": [DOC_IMAGE, DOC_IMAGE_2],  # similarity needs >=2 images
    "Split Chapters": [DOC_PDF],                       # chapter split needs a PDF
    "NER per-page (local)": [DOC_LETTER],              # aggregates existing page_content
}

_REGISTER_TEXT_IMAGES_SNIPPET = """
import shutil, sys
from pathlib import Path
from fichero_server.db import db_manager
from fichero_server.models import Document, DocType, FileType, Status

lib = Path(sys.argv[1])
fixtures = Path(sys.argv[2])
db = db_manager.get_database(lib)
for idx in (1, 2):
    src = fixtures / f"sample_text_page{idx}.png"
    dst = lib / "files" / f"e2e-text-image-{idx}.png"
    shutil.copyfile(src, dst)
    db.save(Document(
        id=f"e2e-text-image-{idx}",
        parent_id="test-collection",
        name=src.name,
        doc_type=DocType.file,
        file_type=FileType.image,
        status=Status.completed,
        path=str(dst.relative_to(lib)),
    ))
db_manager.close_all()
print("registered 2 text-image docs")
"""

# Tools whose canonical input is image files — presets containing any of these
# run against the seeded JPG fixture; everything else runs against the seeded
# text fixture. (Selection only; capability gating uses the live registry.)
IMAGE_INPUT_TOOLS = {
    "adaptive_binarize_images", "auto_crop_border_images", "caption",
    "classify_script", "denoise_images", "describe", "deskew_images",
    "enhance_images", "faces", "fuzzy_clean_images", "handwriting", "layout",
    "objects", "organize_same_documents", "prepare_images",
    "recombine_segments", "remove_background_images", "rotate_images",
    "scene", "segment_images", "similarity", "split_images", "sub_workflow",
    "transcribe", "transcribe_review", "zoom",
}

# Workflows in these families must land page_content on the target document.
TRANSCRIPTION_PREFIXES = ("Transcribe", "Capture OCR")


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def log(msg: str) -> None:
    print(msg, flush=True)


def find_python() -> str:
    for candidate in (
        os.environ.get("FICHERO_PYTHON_BIN"),
        os.environ.get("VIRTUAL_ENV") and os.path.join(os.environ["VIRTUAL_ENV"], "bin", "python"),
        str(REPO / ".venv" / "bin" / "python"),
        os.path.expanduser("~/code/fichero/.venv/bin/python"),
    ):
        if candidate and os.access(candidate, os.X_OK):
            return candidate
    return sys.executable


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def http(
    method: str,
    url: str,
    headers: dict[str, str] | None = None,
    payload: dict | None = None,
    timeout: float = 30.0,
):
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(url, data=data, method=method)
    for key, value in (headers or {}).items():
        request.add_header(key, value)
    if data is not None:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode()
            return response.status, (json.loads(body) if body else None)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode()
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            parsed = {"detail": body}
        return exc.code, parsed


def find_key(payload, key: str):
    """Depth-first search for a key anywhere in a JSON payload."""
    if isinstance(payload, dict):
        if key in payload:
            return payload[key]
        for value in payload.values():
            found = find_key(value, key)
            if found is not None:
                return found
    elif isinstance(payload, list):
        for value in payload:
            found = find_key(value, key)
            if found is not None:
                return found
    return None


def find_workflow_list(payload) -> list[dict]:
    """Locate the list of workflow dicts in whatever envelope the API uses."""
    if isinstance(payload, list):
        return [w for w in payload if isinstance(w, dict) and "name" in w]
    if isinstance(payload, dict):
        for key in ("workflows", "items", "data", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                return [w for w in value if isinstance(w, dict) and "name" in w]
        for value in payload.values():
            if isinstance(value, list) and value and isinstance(value[0], dict) and "name" in value[0]:
                return value
    return []


def truncate(text: str, limit: int = 220) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


# ---------------------------------------------------------------------------
# Capability probes (report honestly; never let a red probe pass silently)
# ---------------------------------------------------------------------------

def probe_apple_vision(python: str) -> tuple[bool, str]:
    proc = subprocess.run(
        [python, "-c", "import Quartz, Vision"],
        capture_output=True, text=True, timeout=120,
    )
    if proc.returncode == 0:
        return True, "PyObjC Quartz+Vision importable"
    return False, truncate(proc.stderr or "Quartz/Vision import failed")


def fm_bridge_binary() -> Path | None:
    for candidate in (
        BRIDGE_DIR / "fm-bridge",
        SERVER_SRC / "fichero_server" / "resources" / "bin" / "fm-bridge",
    ):
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    return None


def probe_apple_text(build_bridge: bool) -> tuple[bool, str]:
    binary = fm_bridge_binary()
    if binary is None and build_bridge and (BRIDGE_DIR / "build.sh").is_file():
        log("  fm-bridge missing — attempting one-time build (bin/fm-bridge/build.sh)")
        proc = subprocess.run(
            ["bash", str(BRIDGE_DIR / "build.sh")],
            capture_output=True, text=True, timeout=600,
        )
        if proc.returncode != 0:
            return False, truncate("fm-bridge build failed: " + (proc.stderr or proc.stdout))
        binary = fm_bridge_binary()
    if binary is None:
        return False, "fm-bridge binary not found (build with fichero-server/bin/fm-bridge/build.sh)"
    try:
        proc = subprocess.run([str(binary), "--probe"], capture_output=True, text=True, timeout=120)
        result = json.loads(proc.stdout or "{}")
    except (subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        return False, truncate(f"fm-bridge probe failed: {exc}")
    if result.get("available"):
        return True, "Apple Intelligence available (fm-bridge --probe)"
    return False, truncate(result.get("reason") or "fm-bridge probe reported unavailable")


# ---------------------------------------------------------------------------
# Plan
# ---------------------------------------------------------------------------

def load_presets() -> list[dict]:
    presets = []
    for path in sorted(PRESETS_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("name"):
            presets.append(data)
    return presets


def preset_tool_names(preset: dict) -> set[str]:
    return {str(node.get("tool")) for node in preset.get("nodes", []) if node.get("tool")}


def classify_needs(preset: dict, tool_defs: dict[str, dict]) -> tuple[bool, bool]:
    """(needs_vision_llm, needs_text_llm) from the live tool registry."""
    needs_vision = needs_text = False
    tools = preset_tool_names(preset)
    if "sub_workflow" in tools:
        # The only shipped sub_workflow preset wraps transcribe passes.
        needs_vision = True
    for tool in tools:
        tool_def = tool_defs.get(tool) or {}
        if not tool_def.get("uses_llm"):
            continue
        if tool_def.get("category") == "vision":
            needs_vision = True
        else:
            needs_text = True
    return needs_vision, needs_text


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--only", default="", help="regex of workflow names to run")
    parser.add_argument("--timeout", type=float, default=300.0, help="per-workflow seconds (default 300)")
    parser.add_argument("--budget", type=float, default=1500.0, help="total run budget seconds (default 1500 = 25 min)")
    parser.add_argument("--keep", action="store_true", help="keep the disposable state dir")
    parser.add_argument("--no-build-bridge", action="store_true", help="never try to build fm-bridge")
    parser.add_argument("--list", action="store_true", help="print the plan and exit")
    args = parser.parse_args()

    python = find_python()
    log(f"── verify_workflows: python={python}")

    presets = load_presets()
    runnable = [p for p in presets if not (p.get("config") or {}).get("internal")]
    if args.only:
        pattern = re.compile(args.only)
        runnable = [p for p in runnable if pattern.search(p["name"])]
    if args.list:
        for preset in runnable:
            log(f"  would run: {preset['name']}")
        return 0
    if not runnable:
        log("❌ no default workflows matched")
        return 2

    vision_ok, vision_why = probe_apple_vision(python)
    text_ok, text_why = probe_apple_text(build_bridge=not args.no_build_bridge)
    log(f"  capability: apple-vision      {'OK ' if vision_ok else 'UNAVAILABLE'} — {vision_why}")
    log(f"  capability: apple-intelligence {'OK ' if text_ok else 'UNAVAILABLE'} — {text_why}")

    tmp = Path(tempfile.mkdtemp(prefix="fichero-verify-workflows-"))
    library = tmp / "global.fichero"
    env = dict(os.environ)
    env.update({
        "FICHERO_BASE_PATH": str(tmp),
        "FICHERO_MULTIUSER": "0",
        # The workflow + workflow-execution API prefixes are beta-tier
        # (feature_tiers_generated.py); the default release tier would 404 them.
        "FICHERO_FEATURE_TIER": "beta",
        "PYTHONPATH": str(SERVER_SRC),
    })

    log(f"  state root: {tmp}")
    seed_proc = subprocess.run(
        [python, str(SEED_SCRIPT), str(library), "--with-files"],
        capture_output=True, text=True, env=env, timeout=600,
    )
    if seed_proc.returncode != 0:
        log(f"❌ seeding failed:\n{seed_proc.stderr}")
        return 2
    log("  seeded fixture library (global.fichero, --with-files)")

    register_proc = subprocess.run(
        [python, "-c", _REGISTER_TEXT_IMAGES_SNIPPET, str(library),
         str(REPO / "test-fixtures" / "files")],
        capture_output=True, text=True, env=env, timeout=300,
    )
    if register_proc.returncode != 0:
        log(f"❌ registering text-image fixtures failed:\n{register_proc.stderr}")
        return 2
    log("  registered text-bearing OCR fixture pages (e2e-text-image-1/2)")

    port = free_port()
    base = f"http://127.0.0.1:{port}"
    headers = {"X-Fichero-Library-Path": str(library)}
    # Auth: the server reuses (never rotates) the shared per-user token file at
    # startup (#1110), so reading it back after boot is safe and leaves the
    # user's running app untouched. NEVER pass FICHERO_BOOTSTRAP_TOKEN here —
    # that would persist a disposable token over the user's real one.
    token_file = Path.home() / "Library" / "Application Support" / "Fichero" / ".api-key"
    server = subprocess.Popen(
        [python, "-m", "uvicorn", "fichero_server.api.tcp_transport:app",
         "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
    )

    results: list[tuple[str, str, float, str]] = []  # (name, status, seconds, detail)
    started = time.monotonic()
    try:
        deadline = time.monotonic() + 180
        while True:
            if server.poll() is not None:
                log(f"❌ server exited early:\n{(server.stderr.read() or '')[-4000:]}")
                return 2
            try:
                status, _ = http("GET", f"{base}/api/health", timeout=5)
                if status == 200:
                    break
            except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
                pass
            if time.monotonic() > deadline:
                log("❌ server did not become healthy within 180s")
                return 2
            time.sleep(0.5)
        log(f"  server healthy on {base}")

        if token_file.is_file():
            headers["Authorization"] = f"Bearer {token_file.read_text().strip()}"
        else:
            log(f"⚠️  no token file at {token_file}; proceeding unauthenticated")

        _, tools_payload = http("GET", f"{base}/api/workflows/tools", headers=headers, timeout=60)
        tool_defs: dict[str, dict] = {}
        for tool in (find_key(tools_payload, "tools") or find_key(tools_payload, "items") or []):
            if isinstance(tool, dict) and tool.get("name"):
                tool_defs[tool["name"]] = tool

        _, workflows_payload = http("GET", f"{base}/api/workflows", headers=headers, timeout=60)
        seeded = {w["name"]: w.get("id") for w in find_workflow_list(workflows_payload)}
        if not seeded:
            log(f"❌ workflow list came back empty — raw response: {truncate(json.dumps(workflows_payload), 400)}")
            return 2
        log(f"  library holds {len(seeded)} workflows; sweeping {len(runnable)} direct-runnable presets")

        for preset in runnable:
            name = preset["name"]
            elapsed_total = time.monotonic() - started
            if elapsed_total > args.budget:
                results.append((name, "SKIP", 0.0, "budget-exhausted (raise --budget to cover the full sweep)"))
                log(f"WORKFLOW-E2E | name={name} | status=SKIP | seconds=0.0 | reason=budget-exhausted")
                continue

            needs_vision, needs_text = classify_needs(preset, tool_defs)
            skip_reason = None
            if needs_vision and not vision_ok:
                skip_reason = f"needs Apple Vision OCR — {vision_why}"
            elif needs_text and not text_ok:
                skip_reason = f"needs Apple Intelligence (fm-bridge) — {text_why}"
            if skip_reason:
                results.append((name, "SKIP", 0.0, skip_reason))
                log(f"WORKFLOW-E2E | name={name} | status=SKIP | seconds=0.0 | reason={truncate(skip_reason)}")
                continue

            workflow_id = seeded.get(name)
            if not workflow_id:
                results.append((name, "FAIL", 0.0, "preset not seeded into global library"))
                log(f"WORKFLOW-E2E | name={name} | status=FAIL | seconds=0.0 | step=seed | error=preset not seeded into global library")
                continue

            if name in TARGET_OVERRIDES:
                target_docs = TARGET_OVERRIDES[name]
            elif preset_tool_names(preset) & IMAGE_INPUT_TOOLS:
                target_docs = [DOC_IMAGE]
            else:
                target_docs = [DOC_TEXT]
            run_started = time.monotonic()
            try:
                _run_one(
                    args, base, headers, name, workflow_id, target_docs,
                    run_started, results,
                )
            except Exception as exc:  # noqa: BLE001 — harness must finish the sweep
                seconds = time.monotonic() - run_started
                detail = truncate(f"{type(exc).__name__}: {exc}")
                results.append((name, "FAIL", seconds, detail))
                log(f"WORKFLOW-E2E | name={name} | status=FAIL | seconds={seconds:.1f} | step=harness | error={detail}")
    finally:
        server.send_signal(signal.SIGTERM)
        try:
            server.wait(timeout=15)
        except subprocess.TimeoutExpired:
            server.kill()
        if args.keep:
            log(f"  kept state root: {tmp}")
        else:
            shutil.rmtree(tmp, ignore_errors=True)

    passed = sum(1 for _, status, _, _ in results if status == "PASS")
    failed = sum(1 for _, status, _, _ in results if status == "FAIL")
    skipped = sum(1 for _, status, _, _ in results if status == "SKIP")
    total_seconds = time.monotonic() - started
    log(
        f"WORKFLOW-E2E-SUMMARY | total={len(results)} | passed={passed} | "
        f"failed={failed} | skipped={skipped} | seconds={total_seconds:.1f}"
    )
    if skipped:
        log("⚠️  SKIPPED workflows above did NOT run — each line names the missing capability.")
    if failed:
        log("❌ verify_workflows: red — each FAIL line above names workflow, step, and error for filing.")
        return 1
    log("✅ verify_workflows: 0 failed")
    return 0


def _run_one(args, base, headers, name, workflow_id, target_docs, run_started, results):
    """Execute one preset end-to-end, appending exactly one result row."""
    status_code, accepted = http(
        "POST", f"{base}/api/workflow-execution/execute",
        headers=headers,
        payload={
            "workflow_id": workflow_id,
            "inputs": {"selected_doc_ids": target_docs},
            "skip_cache": True,
        },
        timeout=120,
    )
    if status_code != 202:
        detail = truncate(find_key(accepted, "detail") or accepted)
        lowered = str(detail).lower()
        if any(marker in lowered for marker in ("not configured", "credential", "api key", "unavailable")):
            results.append((name, "SKIP", 0.0, f"preflight capability gap: {detail}"))
            log(f"WORKFLOW-E2E | name={name} | status=SKIP | seconds=0.0 | reason=preflight capability gap: {detail}")
        else:
            results.append((name, "FAIL", 0.0, detail))
            log(f"WORKFLOW-E2E | name={name} | status=FAIL | seconds=0.0 | step=preflight | error={detail}")
        return

    thread_id = accepted["thread_id"]
    final = None
    while time.monotonic() - run_started < args.timeout:
        _, poll = http(
            "GET",
            f"{base}/api/workflow-execution/threads/{thread_id}/status",
            headers=headers, timeout=30,
        )
        if isinstance(poll, dict) and poll.get("status") in {"completed", "failed", "cancelled"}:
            final = poll
            break
        time.sleep(1.0)
    seconds = time.monotonic() - run_started

    if final is None:
        http("POST", f"{base}/api/workflow-execution/threads/{thread_id}/cancel",
             headers=headers, timeout=30)
        detail = f"timeout after {args.timeout:.0f}s (cancelled)"
        results.append((name, "FAIL", seconds, detail))
        log(f"WORKFLOW-E2E | name={name} | status=FAIL | seconds={seconds:.1f} | step=timeout | error={detail}")
        return

    if final.get("status") != "completed":
        state = final.get("current_state") or {}
        step = state.get("current_node") or "?"
        error = truncate(final.get("error") or state.get("error") or "no error text")
        # An EXTERNAL provider refusing service (quota, invalid key, 401/403)
        # is out of scope for the on-device lane — report SKIP, loudly, so a
        # red exit stays reserved for product bugs. On-device (Apple) errors
        # never match these markers and stay FAIL.
        lowered = error.lower()
        if any(marker in lowered for marker in ("quota", "rate limit", "forbidden", "(401", "(403", "api key", "credential")):
            results.append((name, "SKIP", seconds, f"external provider error at step {step}: {error}"))
            log(f"WORKFLOW-E2E | name={name} | status=SKIP | seconds={seconds:.1f} | reason=external provider error at step {step}: {error}")
            return
        results.append((name, "FAIL", seconds, f"step={step} error={error}"))
        log(f"WORKFLOW-E2E | name={name} | status=FAIL | seconds={seconds:.1f} | step={step} | error={error}")
        return

    # Provenance (#4313): every artifact this run wrote must carry the trio.
    problems = []
    _, artifacts_payload = http(
        "GET", f"{base}/api/artifacts/?run_id={thread_id}&limit=500",
        headers=headers, timeout=60,
    )
    artifacts = find_key(artifacts_payload, "items") or []
    for artifact in artifacts:
        missing = [f for f in ("run_id", "workflow_id", "step_name") if not artifact.get(f)]
        if missing:
            problems.append(
                f"artifact {artifact.get('id')} ({artifact.get('artifact_type')}) missing {'/'.join(missing)}"
            )

    page_note = ""
    if name.startswith(TRANSCRIPTION_PREFIXES):
        _, doc_payload = http(
            "GET", f"{base}/api/documents/{target_docs[0]}", headers=headers, timeout=60,
        )
        page_content = find_key(doc_payload, "page_content")
        if not (isinstance(page_content, str) and page_content.strip()):
            problems.append("transcription run left page_content empty on target doc")
        else:
            page_note = f" | page_content_chars={len(page_content)}"

    if problems:
        detail = "; ".join(problems)
        results.append((name, "FAIL", seconds, detail))
        log(f"WORKFLOW-E2E | name={name} | status=FAIL | seconds={seconds:.1f} | step=assertions | error={truncate(detail)}")
    else:
        results.append((name, "PASS", seconds, f"artifacts={len(artifacts)}"))
        log(
            f"WORKFLOW-E2E | name={name} | status=PASS | seconds={seconds:.1f} | "
            f"thread={thread_id} | artifacts={len(artifacts)}{page_note}"
        )


if __name__ == "__main__":
    raise SystemExit(main())
