"""The live cluster check (`compute.connect.check-really-checks`, #5454): the login node only, nothing submitted."""
from __future__ import annotations

from typing import Any

#: name → the command run on the login node (an Alliance cluster: `compute.connect.check-really-checks`).
STEPS: list[tuple[str, list[str]]] = [
    ("hostname", ["hostname"]),
    ("storage", ["diskusage_report"]),
    ("apptainer", ["module", "avail", "apptainer"]),
    ("gpus", ["sinfo", "-h", "-o", "%P|%a|%G"]),
    ("fair share", ["sshare", "-U", "-P", "-n"]),
]


def check_cluster(shell: Any) -> dict[str, Any]:
    """Run each step; the first failing login (hostname) leaves the rest `not tried`. `ok` is true only if
    every step passed just now."""
    steps: list[dict[str, str]] = []
    for name, argv in STEPS:
        if steps and steps[0]["state"] == "failed":
            steps.append({"name": name, "state": "not tried", "answer": ""})
            continue
        code, out, err = shell.run(argv)
        answer = (out if not code else (err or out)).strip()[:1000]
        steps.append({"name": name, "state": "passed" if code == 0 else "failed", "answer": answer})
    return {"ok": all(s["state"] == "passed" for s in steps), "steps": steps}
