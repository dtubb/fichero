"""`builder verify-all`: everything on a checkout's HEAD verified by the harness before a dev DMG (manager 2026-11-02, owner order).

One verdict row from three parts over a scratch tree of HEAD: every guard, the full engine suite (every package's tests, on
`[check].remote` when one is set), and the app's build rung. `--build` makes the dev DMG only after a green verdict; nothing is
pushed, nothing notarized. The guards run first; the suite and the build run beside each other, the build only while no check runs
(it takes every ladder slot)."""
from __future__ import annotations

import contextlib
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fichero_builder import check_tool, jail, journal


def _suite_dirs(root: Path, cfg) -> tuple[list[str], tuple]:
    """(the engine packages' tests dirs, the whole-tests dirs): every `<package>/tests` there is, a whole-tests one on its own."""
    # a whole_tests value may be a list of single test files (2026-11-08): those sit inside a package's tests dir, which verify runs
    # whole anyway, so only a dir value is a whole-tests suite here
    whole = tuple(sorted({v for v in cfg.whole_tests.values() if isinstance(v, str)}))
    dirs = sorted(f"{p.parent.name}/tests" for p in root.glob("*/tests") if p.is_dir() and f"{p.parent.name}/tests" not in whole)
    return dirs, whole


def verify(root, cfg=None, *, jail_required: bool = True) -> dict:
    """{ok, sha, parts: {name: {ok, seconds, detail}}}: the three parts over HEAD; the first red does not stop the others."""
    root = Path(root)
    cfg = cfg or check_tool.load(root)
    j = jail.load(root)
    if j is None and jail_required:
        raise jail.JailMissing("no [jail] in the rules file: the verification will not run as the owner")
    if j is not None:
        j.require()
    sha = check_tool._git(root, "rev-parse", "HEAD")["stdout_tail"].strip()
    key = f"verify {sha[:9]}"
    check_tool._jail_enter(j)
    check_tool._KEY[0] = key
    own = check_tool._scratch_tree(root, sha, root, cfg, overlay=False)   # the suite: HEAD as it is
    judged = check_tool._scratch_tree(root, sha, root, cfg)               # guards and build: the checkout's own check files over it
    parts: dict = {}

    def part(name: str, fn) -> None:
        journal.append("activity", kind="verify", key=key, state="rung-start", rung=name, load=check_tool._load())
        t = time.time()
        try:
            r = fn()
            ok, detail = bool(r.get("ok")), (r.get("stderr_tail") or r.get("reason") or "")[-300:] or "green"
            if not ok:  # a red part never says "green": name what failed (2026-11-08: guards and suite read RED ... green)
                bad = [x.get("name") or " ".join(x.get("argv") or ["?"])[-60:] for x in (r.get("results") or r.get("runs") or []) if not x.get("ok")]
                tail = (r.get("stdout_tail") or "").strip().splitlines()[-3:]
                detail = ("failed: " + ", ".join(bad) if bad else "failed") + (" | " + " / ".join(tail) if tail else "")
                detail = detail[-300:]
            if r.get("skipped"):
                detail = "skipped: no build rung configured"
        except (RuntimeError, OSError, ValueError) as e:
            ok, detail = False, str(e)[-300:]
        parts[name] = {"ok": ok, "seconds": int(time.time() - t), "detail": detail}
        journal.append("activity", kind="verify", key=key, state="rung", rung=name, ok=ok, seconds=parts[name]["seconds"],
                       wall_s=round(time.time() - t, 1), load=check_tool._load())

    def build_alone():  # only while no check runs: every ladder slot held
        with contextlib.ExitStack() as held:
            for slot in journal.ladder_slots(cfg.parallel):
                held.enter_context(journal.Lock(slot, what="the verification's app build"))
            return check_tool.build(judged, list(cfg.build_paths), cfg)

    journal.append("activity", kind="verify", key=key, state="start")
    try:
        part("guards", lambda: check_tool.guards(judged, cfg))
        dirs, whole = _suite_dirs(root, cfg)
        with ThreadPoolExecutor(max_workers=2) as pool:
            fs = [pool.submit(part, "suite", lambda: check_tool.green_runs(own, dirs, whole, cfg, 7200)),
                  pool.submit(part, "build", build_alone)]
            for f in fs:
                f.result()
    finally:
        check_tool._jail_exit()
        for t in (own, judged):
            check_tool._git(root, "worktree", "remove", "--force", t)
        if check_tool._SHIPPED or check_tool._DOWN:
            check_tool._drop_remote(cfg)
    ok = all(p["ok"] for p in parts.values())
    journal.append("activity", kind="verify", key=key, state="end", ok=ok)
    journal.append("verify", sha=sha, root=str(root), ok=ok, parts=parts, remote=cfg.remote or "here")
    return {"ok": ok, "sha": sha, "parts": parts}


def main(a) -> int:
    from fichero_builder import build

    r = verify(a.root)
    for name, p in r["parts"].items():
        print(f"{'GREEN' if p['ok'] else 'RED  '} {name}: {p['seconds']} s: {p['detail'].splitlines()[-1] if p['detail'] else ''}")
    print(f"{'VERIFIED' if r['ok'] else 'NOT VERIFIED'} {r['sha'][:9]}")
    if not r["ok"] or not a.build:
        return 0 if r["ok"] else 1
    return build.main(type("A", (), {"dev": True, "root": a.root, "state": None})())
