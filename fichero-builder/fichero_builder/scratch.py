"""`builder sweep-scratch` (dev-workflows.run.scratch-sweep, manager 2026-11-03: about 780 check-* scratch dirs, 1.6 GiB, were left in the
jail's workroot by ladders a loop restart or a kill stopped): the ladders' own scratch dirs only, by prefix, older than a retention age,
never one a running process names. LIST and DELETE are separate steps (hard rule 2026-10-27: a list and an rm in one command wiped a
whole dir): `--list` writes the list to a file, `--delete FILE` removes exactly the dirs that file names, re-checking each first."""
from __future__ import annotations

import subprocess
import time
import tomllib
from pathlib import Path

from fichero_builder import journal

PREFIXES = ("check-tree-", "check-base-tree-", "check-base-", "check-home-")  # what check_tool._mkdtemp makes; nothing else is touched
RETAIN_H = 6.0  # a ladder runs at most a few hours (build 3600 s); anything this old is no live ladder's


def _rules(root) -> dict:
    f = Path(root) / "harness.toml"
    return tomllib.loads(f.read_text()) if f.is_file() else {}


def _held() -> str:
    """Every running process's command line: a dir named there is in use (a ladder's pytest, xcodebuild, a guard)."""
    return subprocess.run(["ps", "-axww", "-o", "command="], capture_output=True, text=True).stdout


def _kb(p: Path) -> int:
    r = subprocess.run(["du", "-sk", str(p)], capture_output=True, text=True)
    return int(r.stdout.split()[0]) if r.returncode == 0 and r.stdout.split() else 0


def candidates(workroot, retain_h: float = RETAIN_H, now: float | None = None, held: str | None = None) -> list[Path]:
    """The ladders' scratch dirs directly under `workroot`, older than `retain_h` hours, named by no running process."""
    now, held = now or time.time(), _held() if held is None else held
    out = []
    for p in sorted(Path(workroot).iterdir()) if Path(workroot).is_dir() else []:
        if not p.name.startswith(PREFIXES) or p.is_symlink() or not p.is_dir():
            continue
        if now - p.lstat().st_mtime < retain_h * 3600 or str(p) in held:
            continue
        out.append(p)
    return out


def list_step(root, retain_h: float = RETAIN_H) -> tuple[Path, int, int]:
    """Step 1: the list, written to `<state>/scratch-sweep-<ts>.txt` (one path a line); (file, count, KiB). Deletes nothing."""
    workroot = _rules(root).get("jail", {}).get("workroot", "")
    paths = candidates(workroot, retain_h) if workroot else []
    kb = sum(_kb(p) for p in paths)
    journal.STATE.mkdir(parents=True, exist_ok=True)
    f = journal.STATE / f"scratch-sweep-{time.strftime('%Y%m%d-%H%M%S')}.txt"
    f.write_text("".join(f"{p}\n" for p in paths))
    journal.append("sweep-scratch", state="listed", file=str(f), count=len(paths), kib=kb, retain_h=retain_h)
    return f, len(paths), kb


def delete_step(root, listed, retain_h: float = RETAIN_H) -> tuple[int, int, list[str]]:
    """Step 2: exactly the dirs `listed` names, each re-checked (still a scratch prefix directly under the workroot, still old
    enough, still unheld); a check tree leaves through `git worktree remove`, what the jail user wrote goes as that user.
    (removed, KiB freed, what it could not remove)."""
    from fichero_builder import jail as jail_mod

    rules = _rules(root)
    workroot = Path(rules.get("jail", {}).get("workroot", "") or "/nonexistent").resolve()
    repo = rules.get("check", {}).get("engine_repo", "")
    j = jail_mod.load(root)
    held, now = _held(), time.time()
    removed, freed, left = 0, 0, []
    for line in Path(listed).read_text().splitlines():
        p = Path(line.strip())
        if not line.strip() or p.is_symlink() or p.resolve().parent != workroot or not p.name.startswith(PREFIXES):
            left.append(f"{line.strip()}: not a scratch dir directly under the workroot")
            continue
        if not p.exists():
            continue
        if now - p.lstat().st_mtime < retain_h * 3600 or str(p) in held:
            left.append(f"{p}: in use or too new now")
            continue
        kb = _kb(p)
        if p.name.startswith("check-tree-") and repo:
            subprocess.run(["git", "-C", repo, "worktree", "remove", "--force", str(p)], capture_output=True, text=True)
        if p.exists() and j is not None:
            subprocess.run(j.argv(["rm", "-rf", str(p)]), capture_output=True, text=True, timeout=600)
        if p.exists():
            subprocess.run(["rm", "-rf", str(p)], capture_output=True, text=True, timeout=600)
        if p.exists():
            left.append(f"{p}: still there")
            continue
        removed, freed = removed + 1, freed + kb
    if repo:
        subprocess.run(["git", "-C", repo, "worktree", "prune"], capture_output=True, text=True)
    journal.append("sweep-scratch", state="deleted", file=str(listed), removed=removed, kib=freed, left=left[:20])
    return removed, freed, left


def main(a) -> int:
    if a.list:
        f, n, kb = list_step(a.root, a.retain_h)
        print(f"{n} scratch dir(s), {kb / 1048576:.2f} GiB, older than {a.retain_h:g} h: listed in {f} (nothing deleted; then: --delete {f})")
        return 0
    n, kb, left = delete_step(a.root, a.delete, a.retain_h)
    print(f"removed {n} scratch dir(s), freed {kb / 1048576:.2f} GiB" + (f"; left {len(left)}:\n" + "\n".join(left[:20]) if left else ""))
    return 1 if left else 0



EVERY_H = 6.0


def when_idle(root) -> None:
    """The loop's step: at most every EVERY_H hours, when no lane is busy, the list and then the delete from that list (two steps,
    each a row). A failure is a row, never the loop's death."""
    mark = journal.STATE / "scratch-sweep.last"
    if mark.is_file() and time.time() - mark.stat().st_mtime < EVERY_H * 3600:
        return
    mark.parent.mkdir(parents=True, exist_ok=True)
    mark.write_text(time.strftime("%Y-%m-%dT%H:%M:%S"))
    try:
        f, n, _kb = list_step(root)
        if n:
            delete_step(root, f)
    except Exception as e:  # noqa: BLE001 - housekeeping never stops the loop
        journal.append("sweep-scratch", state="error", detail=str(e)[-300:])
