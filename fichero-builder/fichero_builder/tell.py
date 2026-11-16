"""`builder tell <pane> <message>`: a message into a Claude Code pane, submitted (the tracked port of the manager's tell.sh,
2026-11-02). A message over 400 characters goes to a file under <state>/tells/ and the pane gets `Read <path>` (a long one
arrived as its last line only). It waits up to five minutes for someone's unsent draft to leave the input box, types the
text, presses Enter, and presses it again (up to three times) while the text still sits in the box."""
from __future__ import annotations

import re
import subprocess
import time

from fichero_builder import journal

LONG = 400
ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _tmux(*a: str) -> subprocess.CompletedProcess:
    return subprocess.run(["tmux", *a], capture_output=True, text=True)


def send(pane: str, msg: str, sleep=time.sleep) -> tuple[int, str]:
    if pane not in _tmux("list-panes", "-a", "-F", "#{pane_id}").stdout.split():
        return 1, f"ERROR: no pane {pane}"
    if len(msg) > LONG:
        d = journal.STATE / "tells"
        d.mkdir(parents=True, exist_ok=True)
        f = d / f"tell-{time.strftime('%Y%m%d-%H%M%S')}-{abs(hash(msg)) % 10 ** 6}.txt"
        f.write_text(msg + "\n")
        msg = f"Read {f}"
    for _ in range(60):  # an unsent draft (typed text, not a dim suggestion) is never typed into
        box = next((ln for ln in reversed(_tmux("capture-pane", "-e", "-p", "-t", pane).stdout.splitlines()) if "❯" in ln), "")
        if "\x1b[2m" in box or not re.sub(r"[│|].*$", "", ANSI.sub("", box).split("❯", 1)[-1]).strip():
            break
        sleep(5)
    _tmux("send-keys", "-t", pane, "-l", msg)
    sleep(1)
    _tmux("send-keys", "-t", pane, "C-m")
    for _ in range(3):
        sleep(3)
        tail = "\n".join(_tmux("capture-pane", "-p", "-t", pane).stdout.splitlines()[-6:])
        if msg[:40] not in tail:
            return 0, f"submitted to {pane}"
        _tmux("send-keys", "-t", pane, "C-m")
    return 0, f"WARNING: {pane} may not have submitted"


def main(a) -> int:
    rc, out = send(a.pane, " ".join(a.message))
    print(out)
    return rc
