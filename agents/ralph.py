#!/usr/bin/env python3
"""Ralph Loop — Iterative Claude runner with real-time streaming output.

Usage:
    ./agents/ralph.py                          # default: 10 iterations, uses loop-prompt.txt
    ./agents/ralph.py 5                        # 5 iterations
    ./agents/ralph.py 10 ./prd.md              # use custom prompt file
    ./agents/ralph.py 10 --force               # skip completion check
    ./agents/ralph.py 10 ./prd.md --force      # both
"""

import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# ── Config ──────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent.resolve()
PROJECT_DIR = SCRIPT_DIR.parent
LOG_DIR = SCRIPT_DIR / "logs"
DEFAULT_PROMPT_FILE = SCRIPT_DIR / "loop-prompt.txt"
PROGRESS_FILE = SCRIPT_DIR / "progress.md"

# ── Colors ──────────────────────────────────────────────
class C:
    BOLD = "\033[1m"
    BLUE = "\033[0;34m"
    CYAN = "\033[0;36m"
    GREEN = "\033[0;32m"
    YELLOW = "\033[1;33m"
    RED = "\033[0;31m"
    DIM = "\033[2m"
    RESET = "\033[0m"

def log(msg: str):
    print(msg, flush=True)

def header(text: str):
    width = 54
    log(f"\n{C.BOLD}{C.BLUE}{'═' * width}{C.RESET}")
    log(f"{C.BOLD}{C.BLUE}  {text}{C.RESET}")
    log(f"{C.BOLD}{C.BLUE}{'═' * width}{C.RESET}")

def iteration_header(i: int, total: int):
    log(f"\n{C.BOLD}{C.YELLOW}── Iteration {i} / {total} ──{C.RESET}")

# ── Progress check ──────────────────────────────────────
def check_all_done() -> bool:
    if not PROGRESS_FILE.exists():
        return False
    content = PROGRESS_FILE.read_text()
    match = re.search(r'^\| *Remaining *\| *(\d+)', content, re.MULTILINE)
    if match:
        return int(match.group(1)) == 0
    return False

def show_progress():
    if not PROGRESS_FILE.exists():
        return
    content = PROGRESS_FILE.read_text()
    log(f"  {C.CYAN}Progress:{C.RESET}")
    for line in content.splitlines():
        if re.match(r'^\| *(Completed|Remaining|Blocked|In Progress) *\|', line):
            log(f"    {line}")

# ── Stream Claude output ───────────────────────────────
def run_claude(prompt: str, log_file: Path, session_id: str | None = None) -> tuple[bool, str, str | None]:
    """Run Claude with streaming output. Returns (success, output_text, session_id)."""

    cmd = [
        "claude", "-p", prompt,
        "--dangerously-skip-permissions",
        "--verbose",
        "--output-format", "stream-json",
        "--include-partial-messages",
    ]

    # Resume existing session to reuse MCP connections (Xcode etc)
    if session_id:
        cmd.extend(["--resume", session_id])

    full_output = []
    text_output = []
    found_session_id = session_id

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(PROJECT_DIR),
            text=True,
            bufsize=1,
        )

        for line in proc.stdout:
            line = line.rstrip("\n")
            full_output.append(line)

            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue

            msg_type = msg.get("type", "")

            # Capture session ID for reuse (keeps MCP connections alive)
            if "session_id" in msg and not found_session_id:
                found_session_id = msg["session_id"]

            if msg_type == "stream_event":
                event = msg.get("event", {})
                evt_type = event.get("type", "")

                if evt_type == "content_block_delta":
                    delta = event.get("delta", {})
                    if delta.get("type") == "text_delta":
                        text = delta.get("text", "")
                        print(text, end="", flush=True)
                        text_output.append(text)

                elif evt_type == "content_block_start":
                    block = event.get("content_block", {})
                    if block.get("type") == "tool_use":
                        tool_name = block.get("name", "?")
                        print(f"\n  {C.CYAN}[{tool_name}]{C.RESET} ", end="", flush=True)

            elif msg_type == "result":
                is_error = msg.get("is_error", False)
                result_text = msg.get("result", "")
                if is_error:
                    print(f"\n  {C.RED}[ERROR]{C.RESET}", flush=True)
                else:
                    print(f"\n  {C.GREEN}[DONE]{C.RESET}", flush=True)
                text_output.append(result_text)

        proc.wait()

        # Write raw log
        log_file.write_text("\n".join(full_output))

        output_str = "".join(text_output)
        return proc.returncode == 0, output_str, found_session_id

    except FileNotFoundError:
        log(f"  {C.RED}Error: 'claude' not found in PATH{C.RESET}")
        return False, "", None
    except KeyboardInterrupt:
        proc.kill()
        raise

# ── Main ────────────────────────────────────────────────
def main():
    args = sys.argv[1:]

    max_iterations = 10
    prompt_file = DEFAULT_PROMPT_FILE
    force = "--force" in args
    dry_run = "--dry-run" in args
    args = [a for a in args if a not in ("--force", "--dry-run")]

    if args:
        try:
            max_iterations = int(args[0])
            args = args[1:]
        except ValueError:
            pass

    if args:
        pf = Path(args[0])
        if pf.exists():
            prompt_file = pf
        else:
            log(f"{C.RED}Prompt file not found: {pf}{C.RESET}")
            sys.exit(1)

    LOG_DIR.mkdir(exist_ok=True)

    # Load prompt
    if not prompt_file.exists():
        log(f"{C.YELLOW}No prompt file at {prompt_file}, creating default...{C.RESET}")
        prompt_file.write_text(
            "Read agents/plan.md for the overall project plan.\n\n"
            "Read agents/progress.md to check task status and identify the next uncompleted task.\n\n"
            "Complete one task at a time. After completing a task:\n"
            "1. Verify build passes (BuildProject)\n"
            "2. Commit and push to remote\n"
            "3. Update agents/progress.md with completion status\n"
            "4. Update GitHub issue status to done and close it\n"
            "5. Say DONE and exit\n\n"
            "If ALL remaining tasks are done (Remaining | 0), say ALL_COMPLETE and exit.\n"
        )

    prompt = prompt_file.read_text().strip()

    header(f"Ralph Loop — {max_iterations} iterations")
    log(f"  {C.DIM}Prompt: {prompt_file}{C.RESET}")
    log(f"  {C.DIM}Project: {PROJECT_DIR}{C.RESET}")
    log(f"  {C.DIM}Force: {force}  Dry run: {dry_run}{C.RESET}")

    last_iteration = 0
    session_id = None  # Reused across iterations to keep MCP connections alive

    try:
        for i in range(1, max_iterations + 1):
            last_iteration = i
            iteration_header(i, max_iterations)

            # Check completion
            if not force and check_all_done():
                log(f"  {C.GREEN}All tasks complete! (Remaining | 0){C.RESET}")
                break

            show_progress()

            # Run iteration
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            log_file = LOG_DIR / f"iteration_{i}_{timestamp}.jsonl"

            if dry_run:
                log(f"  {C.YELLOW}[DRY RUN] Would run claude -p with:{C.RESET}")
                for line in prompt.splitlines()[:5]:
                    log(f"    {C.DIM}{line}{C.RESET}")
                if len(prompt.splitlines()) > 5:
                    log(f"    {C.DIM}...{C.RESET}")
                output = ""
                continue

            if session_id:
                log(f"  {C.DIM}Resuming session (MCP reuse)...{C.RESET}\n")
            else:
                log(f"  {C.DIM}Starting Claude...{C.RESET}\n")

            success, output, session_id = run_claude(prompt, log_file, session_id)

            # Check for ALL_COMPLETE
            if "ALL_COMPLETE" in output:
                log(f"\n  {C.GREEN}Claude reports ALL_COMPLETE — stopping{C.RESET}")
                break

            # Check progress after iteration
            if not force and check_all_done():
                log(f"\n  {C.GREEN}All tasks complete after iteration {i}!{C.RESET}")
                break

            log(f"  {C.DIM}Log: {log_file}{C.RESET}")

            if i < max_iterations:
                log(f"\n  {C.DIM}Next iteration in 3s...{C.RESET}")
                time.sleep(3)
                # Clear screen for fresh iteration
                print("\033[2J\033[H", end="", flush=True)

    except KeyboardInterrupt:
        log(f"\n\n  {C.YELLOW}Interrupted at iteration {last_iteration}{C.RESET}")

    # Summary
    header(f"Finished after {last_iteration} iteration(s)")
    show_progress()
    log(f"  {C.DIM}Logs: {LOG_DIR}/{C.RESET}")

if __name__ == "__main__":
    main()
