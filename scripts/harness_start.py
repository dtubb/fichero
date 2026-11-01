#!/usr/bin/env python3
"""The only way a worker starts (dev-workflows run.slice-zero item 3, #6116). Run AS the worker user.

Usage: scripts/harness_start.py --worktree DIR --brief FILE [--root DIR] [--session S] [--name N] [--model sonnet] [--print]
Refuses (exit 1, reasons on stderr) unless: [jail] present, we are the worker user, the probe fails on every deny_read
path, the rules file loads with every rung declared. Then writes settings (policy hook, empty strict MCP), installs the
clone's commit-msg hook and opens a tmux window. `--print` prepares and prints the claude argv without opening a pane."""
import argparse
import json
import shlex
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "fichero-builder"))
from fichero_builder import jail as J  # noqa: E402
from fichero_builder import start_tool as S  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--worktree", required=True)
ap.add_argument("--brief", required=True, help="file holding the brief text")
ap.add_argument("--root", default=str(ROOT))
ap.add_argument("--session", default="harness")
ap.add_argument("--name", default=f"worker-{int(time.time())}")
ap.add_argument("--model", default="sonnet")
ap.add_argument("--print", dest="dry", action="store_true")
a = ap.parse_args()

jail = J.load(a.root)
problems = S.refusals(a.root, jail)
if problems:
    print("harness_start refuses:\n- " + "\n- ".join(problems), file=sys.stderr)
    sys.exit(1)
import shutil  # noqa: E402
claude = shutil.which("claude")
if not claude:
    print("harness_start refuses: no `claude` on the worker user's PATH (install it for that user)", file=sys.stderr)
    sys.exit(1)
tokfile = Path.home() / ".claude-token"  # the worker's own home, never the workroot; read by the pane's shell, not by us
tok = ""  # optional: without the file the worker's own /login session is used
if tokfile.exists():
    st = tokfile.stat()
    if (st.st_mode & 0o077) or not st.st_size:
        print(f"harness_start refuses: {tokfile} is empty or not mode 600", file=sys.stderr)
        sys.exit(1)
    tok = f'export CLAUDE_CODE_OAUTH_TOKEN="$(cat {shlex.quote(str(tokfile))})" && '
scratch = Path(jail.workroot or "/tmp") / a.name
argv = S.prepare(a.root, a.worktree, Path(a.brief).read_text(), scratch, model=a.model, claude_bin=claude)
if a.dry:
    print(json.dumps(argv))
    sys.exit(0)
S.trust_folder(a.worktree)
env = f"FICHERO_HARNESS_LOG={shlex.quote(str(Path(jail.workroot) / 'log.jsonl'))} FICHERO_BUILDER={shlex.quote(a.name)}"
cmd = f"cd {shlex.quote(a.worktree)} && {tok}{env} {' '.join(shlex.quote(x) for x in argv)}"
has = subprocess.run(["tmux", "has-session", "-t", a.session], capture_output=True).returncode == 0
r = subprocess.run(["tmux", "new-window" if has else "new-session", "-d", "-P", "-F", "#{pane_id}", "-t" if has else "-s", a.session, "-n", a.name, cmd],
                   capture_output=True, text=True)
if r.returncode:
    print(f"tmux failed: {r.stderr.strip()}", file=sys.stderr)
    sys.exit(1)
with open(Path(jail.workroot) / "log.jsonl", "a") as f:
    f.write(json.dumps({"at": time.time(), "started": a.name, "pane": r.stdout.strip()}) + "\n")
print(r.stdout.strip())
