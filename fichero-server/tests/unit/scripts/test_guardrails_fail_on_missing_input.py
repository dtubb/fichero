"""A guardrail whose input is missing must FAIL, never pass.

Every ``scripts/check_*.py`` resolves its scan roots from
``ROOT = Path(__file__).resolve().parent.parent`` and walks directories under
it — ``ROOT / "fichero" / "fichero" / "Views"``, ``ROOT / "fichero-server" /
"src"``, and so on. Almost all of them then report findings and exit non-zero
only when they *find* something.

The failure mode that creates: point the guardrail at a tree where those
directories do not exist and it walks nothing, finds nothing, and exits 0 —
a confident green tick for a scan that never happened. Nothing distinguishes
"I checked and the code is clean" from "I checked nothing".

That is not hypothetical in this repo. The recurring shape is a scan root
that moved or was never reachable from where the tool ran: a lint config
resolved against the wrong repo path, a backend gate run with the wrong
PYTHONPATH so it collected a different checkout, an OpenAPI spec left stale
after the engine reorg moved its source directory. In each case the tooling
kept reporting success. A guardrail is the one kind of program where "found
nothing" and "looked at nothing" must never produce the same exit code.

METHOD (mutation, not inspection): copy the guardrail alone into an empty
directory tree so its own ``ROOT`` resolves there, run it, and read the exit
code. Every scan root it depends on is now genuinely absent. A guardrail that
still exits 0 has demonstrated — not been suspected of — being unable to fail.

Each parametrised failure is one guardrail that is currently a no-op whenever
its subject tree is missing or has moved; the aggregate test names the whole
set in a single message. They are reported, not fixed: the fix belongs in each
script (assert the scan root exists and exit non-zero if it does not), which
is product code this lane does not touch.

This module is the standing rule that replaces the one-off audit (#4382). A
guardrail added next month inherits it automatically — the inventory is a
glob, so nobody has to remember to sweep again.

No test here skips. If a guardrail cannot even be executed that FAILS, which
is the correct outcome — an unrunnable guardrail is a guardrail that is not
guarding (#4365).
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPTS_DIR = REPO_ROOT / "scripts"

GUARDRAILS = sorted(p.name for p in SCRIPTS_DIR.glob("check_*.py"))


def test_the_guardrail_inventory_is_not_empty():
    """Guard the guard: an empty inventory would make the sweep vacuous.

    This module's whole value is the parametrised sweep below. If the glob
    ever resolved to nothing — scripts/ moved, this file relocated, the
    naming convention changed — pytest would report a tidy green run over
    zero parameters, which is the exact defect the module exists to hunt.
    """
    assert SCRIPTS_DIR.is_dir(), f"guardrail directory missing: {SCRIPTS_DIR}"
    assert len(GUARDRAILS) >= 50, (
        f"only {len(GUARDRAILS)} guardrails discovered under {SCRIPTS_DIR} — "
        "the sweep below is measuring almost nothing"
    )


def _run_in_empty_tree(script_name: str, root: Path) -> subprocess.CompletedProcess:
    """Run one guardrail alone in ``root`` so its own ROOT resolves there.

    Every ``scripts/check_*.py`` computes
    ``ROOT = Path(__file__).resolve().parent.parent``, so copying the script
    to ``root/scripts/`` and nothing else makes every scan root it derives
    genuinely absent — without touching the real tree.
    """
    sandbox_scripts = root / "scripts"
    sandbox_scripts.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SCRIPTS_DIR / script_name, sandbox_scripts / script_name)
    return subprocess.run(
        [sys.executable, str(sandbox_scripts / script_name)],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_no_guardrail_reports_success_against_an_empty_tree(tmp_path_factory):
    """The whole inventory in one verdict, naming every offender at once.

    The parametrised test below makes each guardrail individually
    addressable; this one answers "how bad is it right now" in a single
    message, which is the number that decides whether #4382 is a tidy-up or
    a latent P0.
    """
    assert GUARDRAILS, "no guardrails discovered — this sweep would be vacuous"

    offenders: list[str] = []
    for script_name in GUARDRAILS:
        root = tmp_path_factory.mktemp("empty-tree")
        if _run_in_empty_tree(script_name, root).returncode == 0:
            offenders.append(script_name)

    assert offenders == [], (
        f"{len(offenders)} of {len(GUARDRAILS)} guardrails exited 0 against an "
        "EMPTY tree — they scanned no files and reported success, so a moved "
        "or renamed directory silently disables them while the gate stays "
        "green (#4382):\n  " + "\n  ".join(offenders)
    )


@pytest.mark.parametrize("script_name", GUARDRAILS)
def test_guardrail_fails_when_its_scan_roots_are_absent(
    script_name: str, tmp_path: Path
):
    """Run the guardrail against an empty tree; it must not report success."""
    completed = _run_in_empty_tree(script_name, tmp_path)

    assert completed.returncode != 0, (
        f"{script_name} exited 0 against an EMPTY tree: it scanned no files "
        "and reported success. A missing scan root must fail, not pass — "
        "otherwise a moved or renamed directory silently disables this "
        "guardrail and the gate stays green.\n"
        f"--- stdout ---\n{completed.stdout[-1500:]}\n"
        f"--- stderr ---\n{completed.stderr[-1500:]}"
    )
