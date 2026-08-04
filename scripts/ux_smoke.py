#!/usr/bin/env python3
"""Scripted UX smoke: drive the BUILT app's AppleScript dictionary against the
spawn-per-run engine harness (#4535, 2026-08-04 decisions).

This is the layer between unit tests and XCUITest: real app process, real
engine, real seeded library — driven through the app's own scriptable verbs
(open library, select document, run workflow on documents, stop run,
screenshot) rather than synthesized UI events. Raw UI events stay reserved for
what scripting can't reach (genuine Finder drags).

Flow (every step FAILS LOUDLY — a smoke with no engine or no app must never
read as green):
 1. start fichero-server/scripts/test_engine_harness.py (--full library, UDS
    socket in the app container so the sandboxed app can dial it, #4194);
 2. launch the built Fichero.app binary with the hermetic launch contract
    (--uitesting --fichero-library <lib>, FICHERO_FORCE_UDS_PATH,
    FICHERO_UITEST_HOME);
 3. drive verbs via osascript (application id "app.fichero.fichero");
 4. capture a whole-window screenshot (must produce a non-trivial PNG) and
    exercise the named-view capture path (success, or the verb's documented
    loud failure listing the identifiers actually present);
 5. run the seeded nodes-shape workflow scoped to the seeded letter, poll its
    status, stop the run;
 6. tear down app + harness (the harness reaps the engine; #4400).

Usage:
    python3 scripts/ux_smoke.py --app /path/to/Fichero.app [--out DIR] [--keep]

Exit codes: 0 all steps passed · 1 a step failed · 2 usage/missing app.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HARNESS = REPO / "fichero-server" / "scripts" / "test_engine_harness.py"
SERVER_SRC = REPO / "fichero-server" / "src"
BUNDLE_ID = "app.fichero.fichero"
CONTAINER_TMP = Path.home() / "Library" / "Containers" / BUNDLE_ID / "Data" / "tmp"


def fail(step: str, detail: str) -> None:
    print(f"UX SMOKE FAILED at {step}: {detail}", file=sys.stderr)
    raise SystemExit(1)


def osascript(*lines: str, timeout: float = 60.0) -> tuple[int, str, str]:
    args: list[str] = []
    for line in lines:
        args += ["-e", line]
    proc = subprocess.run(
        ["osascript", *args], capture_output=True, text=True, timeout=timeout
    )
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def tell(command: str, timeout: float = 60.0) -> tuple[int, str, str]:
    return osascript(
        f'tell application id "{BUNDLE_ID}" to {command}', timeout=timeout
    )


def start_harness() -> tuple[subprocess.Popen, dict]:
    CONTAINER_TMP.mkdir(parents=True, exist_ok=True)
    socket_path = CONTAINER_TMP / f"fus-{uuid.uuid4().hex[:10]}.sock"
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SERVER_SRC)
    proc = subprocess.Popen(
        [sys.executable, str(HARNESS), "--socket", str(socket_path),
         "--seed-mode", "full"],
        env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    line = proc.stdout.readline()
    if not line:
        stderr = proc.stderr.read()
        fail("harness start", f"no ready line; stderr:\n{stderr}")
    return proc, json.loads(line)


def launch_app(app: Path, ready: dict) -> subprocess.Popen:
    binary = app / "Contents" / "MacOS" / "Fichero"
    if not binary.is_file():
        fail("app launch", f"no executable at {binary}")
    env = dict(os.environ)
    env["FICHERO_FORCE_UDS_PATH"] = ready["socket"]
    env["FICHERO_UITEST_HOME"] = ready["app_home"]
    return subprocess.Popen(
        [str(binary), "--uitesting", "--fichero-library", ready["library"]],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def wait_scriptable(timeout: float = 60.0) -> None:
    deadline = time.monotonic() + timeout
    last = ""
    while time.monotonic() < deadline:
        code, out, err = tell("name", timeout=10.0)
        if code == 0 and out:
            return
        last = err or out
        time.sleep(1.0)
    fail("app scriptability", f"app never answered AppleScript: {last}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", required=True, help="Path to the built Fichero.app")
    parser.add_argument("--out", help="Directory for screenshots (default: temp)")
    parser.add_argument("--keep", action="store_true", help="Keep app + harness running on failure")
    args = parser.parse_args()

    app = Path(args.app).expanduser().resolve()
    if not app.is_dir():
        print(f"usage: --app does not exist: {app}", file=sys.stderr)
        return 2
    out_dir = Path(args.out).resolve() if args.out else Path(
        f"/tmp/fichero-ux-smoke-{uuid.uuid4().hex[:8]}")
    out_dir.mkdir(parents=True, exist_ok=True)

    harness = app_proc = None
    try:
        harness, ready = start_harness()
        print(f"[smoke] engine ready on {ready['socket']}")

        app_proc = launch_app(app, ready)
        wait_scriptable()
        print("[smoke] app is scriptable")

        # -- open library ---------------------------------------------------
        code, out, err = tell(f'open library "{ready["library"]}"')
        if code != 0:
            fail("open library", err)
        print("[smoke] open library ok")
        time.sleep(3)  # let the window populate before capturing

        # -- select the seeded letter --------------------------------------
        letter = ready["keys"].get("doc_letter")
        if not letter:
            fail("select document", f"seed keys carry no doc_letter: {ready['keys']}")
        code, out, err = tell(f'select document id "{letter}"')
        if code != 0:
            fail("select document", err)
        print("[smoke] select document ok")

        # -- whole-window screenshot (must be a real PNG) -------------------
        shot = out_dir / "window.png"
        code, out, err = tell(f'screenshot "{shot}"')
        if code != 0:
            fail("screenshot window", err)
        if not shot.is_file() or shot.stat().st_size < 1024:
            fail("screenshot window", f"{shot} missing or trivially small")
        print(f"[smoke] window screenshot ok ({shot.stat().st_size} bytes)")

        # -- named-view capture: success, or the verb's LOUD miss ----------
        pane = out_dir / "sidebar.png"
        code, out, err = tell(f'screenshot "{pane}" of view "sidebar"')
        if code == 0 and pane.is_file() and pane.stat().st_size >= 1024:
            print("[smoke] sidebar screenshot ok")
        elif "Identifiers present:" in err:
            # The verb failed the WAY it promises to fail — naming what exists.
            # First-class per-pane identifiers are #4536's deliverable.
            print(f"[smoke] named-view capture reported its miss loudly: {err[:160]}")
        else:
            fail("screenshot named view", f"neither a capture nor a loud miss: {err}")

        # -- run the seeded nodes workflow on the letter, then stop it ------
        workflow = ready["full_ids"].get("workflow-nodes")
        if not workflow:
            fail("run workflow", f"seed carries no workflow-nodes id: {ready['full_ids']}")
        code, thread_id, err = tell(
            f'run workflow "{workflow}" on documents {{"{letter}"}}'
        )
        if code != 0 or not thread_id:
            fail("run workflow", err or "no thread id returned")
        print(f"[smoke] run workflow ok (thread {thread_id})")

        code, status, err = tell(f'get workflow status "{thread_id}"')
        if code != 0:
            fail("workflow status", err)
        print(f"[smoke] workflow status: {status}")

        code, outcome, err = tell(f'stop run "{thread_id}"')
        if code != 0:
            fail("stop run", err)
        print(f"[smoke] stop run ok (engine said: {outcome})")

        print(f"UX SMOKE PASSED — screenshots in {out_dir}")
        return 0
    finally:
        if not args.keep:
            for proc in (app_proc, harness):
                if proc is not None and proc.poll() is None:
                    proc.send_signal(signal.SIGTERM)
                    try:
                        proc.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        proc.kill()


if __name__ == "__main__":
    raise SystemExit(main())
