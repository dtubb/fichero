#!/usr/bin/env python3
"""Soak: a recipe over N page images on the REAL engine, minute by minute (`runner.soak.drives-the-real-engine`, #6732).

    python scripts/soak_run.py IMAGE_FOLDER [--limit N] [--steps segment|regions|read] [--place local|mlx|google-dry]
                               [--kill-at N] [--out soak.json] [--hours 14]

Starts `python -m fichero_server` (uvicorn) on a Unix socket with a scratch state dir and a scratch library (never the app's), imports
the images, starts the recipe through the fichero CLI and polls the run. Every minute it records pages done, pages/hour, the RSS of the
engine and its children, swap, failures by kind and the model loads. `--kill-at N` kills the engine once N pages are done, starts it
again and checks that the run carries on from where it was. `--place google-dry` never starts the run: it reads the plan's estimate and
prints the cost per 1000 pages, so nothing is sent to Google.

Writes one JSON and a Markdown summary. Exit 1 when a page is lost or done twice, memory grows past its bound, or 5000 pages would take
over 10 hours; 0 otherwise; 2 when the run could not be driven.

A page is counted from the run's own per-step account (done + failed + left == total, never more than total, never fewer than before a
restart): the API names no page ids. ponytail: a per-page ledger, if the API grows one, replaces `account_problems`.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable

REPO = Path(__file__).resolve().parents[1]
STEPS = {"segment": ["find-lines"], "regions": ["find-regions"], "read": ["read-a-line"]}
PLACES = ("local", "mlx", "google-dry")
ENDED = ("done", "failed", "cancelled")
PROJECT_PAGES = 5000
MAX_HOURS_FOR_5000 = 10.0
LEAK_MB_PER_HOUR = 100.0  # engine+children RSS growth after warm-up that counts as a leak
RSS_BOUND_MB = 5500.0  # an 8 GB M1 with the OS and the app beside the engine
WARMUP_FRACTION = 0.2
MIN_SAMPLES_FOR_LEAK = 10
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp")
# A fresh scratch library has no recipe, so Start refuses every step. The recipe is assembled from these purposes, the first
# one whose recipe has every asked step: transcribe has the line finder and the reader, tables adds the region finder.
RECIPE_PURPOSES = ("transcribe", "tables")


def page_images(folder: Path, limit: int | None) -> list[Path]:
    """Page images under `folder`, subfolders included, sorted; a `*.fichero` package and a `thumbnails` folder are skipped."""
    found = (p for p in folder.rglob("*") if p.suffix.lower() in IMAGE_SUFFIXES and p.is_file()
             and not any(part.endswith(".fichero") or part.lower() == "thumbnails" for part in p.relative_to(folder).parts[:-1]))
    return sorted(found)[:limit]


# ── What the Mac says ────────────────────────────────────────────────────────────────────────────────────────


def tree_rss_mb(ps_text: str, root: int) -> float:
    """RSS in MB of `root` and every descendant, from `ps -axo pid=,ppid=,rss=` output (rss in KiB)."""
    rows = [tuple(int(x) for x in line.split()) for line in ps_text.splitlines() if len(line.split()) == 3]
    members, grew = {root}, True
    while grew:
        grew = False
        for pid, ppid, _ in rows:
            if ppid in members and pid not in members:
                members.add(pid)
                grew = True
    return round(sum(rss for pid, _, rss in rows if pid in members) / 1024, 1)


def parse_swap_mb(text: str) -> float | None:
    """`used` of `sysctl -n vm.swapusage` ("total = 2048.00M  used = 1023.25M  free = ..."), in MB."""
    m = re.search(r"used = ([\d.]+)([MG])", text)
    return None if not m else round(float(m.group(1)) * (1024 if m.group(2) == "G" else 1), 1)


def sh(argv: list[str]) -> str:
    return subprocess.run(argv, capture_output=True, text=True).stdout


# ── One minute's reading, and the verdict over all of them ───────────────────────────────────────────────────


def reading(status: dict[str, Any], *, minute: float, rss_mb: float, swap_mb: float | None, previous: dict | None) -> dict[str, Any]:
    """One sample from a run-status answer: pages done (the step furthest behind is the run's), failures by kind, model loads."""
    steps = status.get("steps") or []
    accounts = [s["account"] for s in steps if s.get("account")]
    done = min((a["pages_done"] for a in accounts), default=0)
    failed: dict[str, int] = {}
    for s in steps:
        for kind, n in (s.get("failures_by_kind") or {}).items():
            failed[kind] = failed.get(kind, 0) + int(n)
    loads = sum(int(s.get("model_loads") or 0) for s in steps)
    per_hour = 0.0
    if previous and minute > previous["minute"]:
        per_hour = round((done - previous["done"]) / (minute - previous["minute"]) * 60, 1)
    return {"minute": round(minute, 2), "state": status.get("state"), "done": done, "pages_per_hour": per_hour, "rss_mb": rss_mb,
            "swap_mb": swap_mb, "failures_by_kind": failed, "model_loads": loads,
            "accounts": [{k: a[k] for k in ("pages_done", "pages_failed", "pages_left", "pages_total")} for a in accounts]}


def account_problems(samples: list[dict[str, Any]], total: int) -> list[str]:
    """A page lost or done twice, from the accounts: more done than pages, a step whose parts do not add up, a count that went down."""
    reds: list[str] = []
    last = 0
    for s in samples:
        for a in s["accounts"]:
            if a["pages_done"] > a["pages_total"]:
                reds.append(f"minute {s['minute']}: {a['pages_done']} done of {a['pages_total']} pages: a page was done twice")
            if s["state"] in ENDED and a["pages_done"] + a["pages_failed"] + a["pages_left"] != a["pages_total"]:
                reds.append(f"minute {s['minute']}: {a['pages_done']} done + {a['pages_failed']} failed + {a['pages_left']} left != {a['pages_total']}")
        if s["done"] < last:
            reds.append(f"minute {s['minute']}: pages done fell from {last} to {s['done']}: pages were lost")
        last = max(last, s["done"])
    final = samples[-1] if samples else None
    if final and final["state"] == "done" and final["done"] + sum(final["failures_by_kind"].values()) < total:
        reds.append(f"the run ended done with {final['done']} of {total} pages read and {sum(final['failures_by_kind'].values())} failed: pages were lost")
    return reds


def leak_slope_mb_per_hour(samples: list[dict[str, Any]]) -> float | None:
    """Least-squares slope of RSS over the samples after warm-up; None when there are too few to say."""
    tail = samples[int(len(samples) * WARMUP_FRACTION):]
    if len(tail) < MIN_SAMPLES_FOR_LEAK:
        return None
    xs, ys = [s["minute"] / 60 for s in tail], [s["rss_mb"] for s in tail]
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    var = sum((x - mx) ** 2 for x in xs)
    return None if var == 0 else round(sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / var, 1)


def projected_hours(samples: list[dict[str, Any]], pages: int = PROJECT_PAGES, down_minutes: float = 0.0) -> float | None:
    """Hours `pages` would take at the rate the run held while the engine was up; None before a page is done."""
    last = samples[-1] if samples else None
    if not last or last["done"] <= 0 or last["minute"] - down_minutes <= 0:
        return None
    return round(pages / (last["done"] / ((last["minute"] - down_minutes) / 60)), 2)


def judge(samples: list[dict[str, Any]], total: int, *, resume: dict[str, Any] | None, down_minutes: float = 0.0,
          leak_mb_per_hour: float = LEAK_MB_PER_HOUR, rss_bound_mb: float = RSS_BOUND_MB) -> dict[str, Any]:
    reds = account_problems(samples, total)
    if resume and resume.get("problem"):
        reds.append(resume["problem"])
    slope = leak_slope_mb_per_hour(samples)
    if slope is not None and slope > leak_mb_per_hour:
        reds.append(f"memory grows {slope} MB/hour after warm-up (bound {leak_mb_per_hour}): a leak")
    peak = max((s["rss_mb"] for s in samples), default=0.0)
    if peak > rss_bound_mb:
        reds.append(f"peak RSS {peak} MB is over the {rss_bound_mb} MB bound")
    hours = projected_hours(samples, down_minutes=down_minutes)
    if hours is not None and hours > MAX_HOURS_FOR_5000:
        reds.append(f"5000 pages would take {hours} h, over {MAX_HOURS_FOR_5000} h")
    return {"ok": not reds, "reds": reds, "leak_mb_per_hour": slope, "peak_rss_mb": peak, "projected_hours_for_5000": hours}


def resume_check(before_kill: dict[str, Any], after_restart: dict[str, Any]) -> dict[str, Any]:
    """The first reading after the engine came back against the last one before it was killed: no fewer pages done (none lost)."""
    problem = None
    if after_restart["done"] < before_kill["done"]:
        problem = (f"after the restart {after_restart['done']} pages were done, {before_kill['done']} before the kill: "
                   f"{before_kill['done'] - after_restart['done']} pages were lost")
    return {"done_before_kill": before_kill["done"], "done_after_restart": after_restart["done"], "problem": problem}


def cost_per_1000(plan: dict[str, Any], pages: int) -> dict[str, Any]:
    """The start plan's cloud estimate as dollars per 1000 pages; `usd_per_1000` None when a model has no listed price."""
    cap = plan.get("cloud_cap") or {}
    estimate = cap.get("estimate_usd")
    return {"pages": pages, "estimate_usd": estimate,
            "usd_per_1000": None if estimate is None or not pages else round(estimate / pages * 1000, 2)}


def markdown(report: dict[str, Any]) -> str:
    v = report["verdict"]
    lines = [f"# Soak: {report['pages']} pages, steps {report['steps']}, place {report['place']}", "",
             f"- verdict: **{'ok' if v['ok'] else 'RED'}**", f"- peak RSS: {v['peak_rss_mb']} MB; growth {v['leak_mb_per_hour']} MB/hour",
             f"- projected for 5000 pages: {v['projected_hours_for_5000']} h"]
    if report.get("cost"):
        lines.append(f"- cost per 1000 pages: {report['cost']['usd_per_1000']} USD ({report['cost']['estimate_usd']} USD for {report['cost']['pages']} pages)")
    if report.get("resume"):
        lines.append(f"- kill and resume: {report['resume']['done_before_kill']} done before, {report['resume']['done_after_restart']} after")
    lines += [f"- RED: {r}" for r in v["reds"]]
    lines += ["", "| minute | done | pages/h | RSS MB | swap MB | failures | loads |", "|---|---|---|---|---|---|---|"]
    lines += [f"| {s['minute']} | {s['done']} | {s['pages_per_hour']} | {s['rss_mb']} | {s['swap_mb']} | "
              f"{json.dumps(s['failures_by_kind'])} | {s['model_loads']} |" for s in report["samples"]]
    return "\n".join(lines) + "\n"


# ── The engine ───────────────────────────────────────────────────────────────────────────────────────────────


class Engine:
    """`python -m fichero_server` on a socket in a scratch dir, and the fichero CLI on that socket."""

    def __init__(self, root: Path):
        self.root = root
        self.socket = root / "engine.sock"
        self.library = root / "library" / "Soak.fichero"
        self.proc: subprocess.Popen | None = None
        self.env = {**os.environ, "FICHERO_BASE_PATH": str(root / "state"), "FICHERO_UDS_PATH": str(self.socket),
                    "PYTHONPATH": os.pathsep.join([str(REPO / "fichero-server/src"), str(REPO / "fichero-cli/src")])}
        sys.path.insert(0, str(REPO / "fichero-server/src"))
        from fichero_server.security.real_data_guard import refuse_real_base

        refuse_real_base(root / "state")  # a soak engine never writes into the owner's real libraries
        (root / "state").mkdir(parents=True, exist_ok=True)
        self.library.parent.mkdir(parents=True, exist_ok=True)

    def start(self) -> None:
        self.socket.unlink(missing_ok=True)
        log = open(self.root / "engine.log", "ab")
        self.proc = subprocess.Popen([sys.executable, "-m", "fichero_server"], env=self.env, stdout=log, stderr=log, cwd=REPO)
        deadline = time.monotonic() + 180
        while not self.socket.exists():
            if self.proc.poll() is not None or time.monotonic() > deadline:
                raise RuntimeError(f"the engine did not come up; see {self.root / 'engine.log'}")
            time.sleep(0.5)

    def kill(self) -> None:
        if self.proc:
            self.proc.kill()
            self.proc.wait()

    def rss_mb(self) -> float:
        return tree_rss_mb(sh(["ps", "-axo", "pid=,ppid=,rss="]), self.proc.pid) if self.proc else 0.0

    def cli(self, *args: str) -> Any:
        env = {k: v for k, v in self.env.items() if k not in ("FICHERO_API_URL", "FICHERO_LIBRARY_PATH")} | {"FICHERO_UDS": str(self.socket)}
        done = subprocess.run([sys.executable, "-m", "fichero_cli", "--json", *(["--library", str(self.library)] if self.library.exists() else []), *args],
                              env=env, capture_output=True, text=True, timeout=600)
        if done.returncode != 0:
            raise RuntimeError(f"fichero {' '.join(args)} failed: {(done.stderr or done.stdout).strip()[:400]}")
        return json.loads(done.stdout or "null")

    def save_recipe(self, steps: str, place: str) -> None:
        """Save the project recipe the soak runs: the first of RECIPE_PURPOSES whose recipe has every step STEPS[steps] names."""
        want = STEPS[steps]
        for purpose in RECIPE_PURPOSES:
            answers = {"languages": ["en"], "scripts": ["Latn"], "purposes": [purpose], "cloud_allowed": place == "google-dry"}
            recipe = self.cli("recipes", "assemble", "--languages", "en", "--scripts", "Latn", "--purposes", purpose,
                              *(["--cloud-allowed"] if place == "google-dry" else []))
            if set(want) <= {s["id"] for s in recipe["steps"]}:
                self.cli("recipes", "save-project-setup", "--answers", json.dumps(answers), "--recipe", json.dumps(recipe))
                return
        raise RuntimeError(f"no recipe from {', '.join(RECIPE_PURPOSES)} has the step {', '.join(want)}")

    def prepare(self, images: list[Path], place: str, steps: str, batch: int = 100) -> None:
        self.cli("library", "create", str(self.library))
        self.cli("recipes", "put-places", "--places", "this-mac,cloud" if place == "google-dry" else "this-mac")
        for i in range(0, len(images), batch):
            self.cli("docs", "import-files-together", *[a for p in images[i:i + batch] for a in ("--upload", f"files={p}")])
        self.save_recipe(steps, place)  # after the import: assemble refuses a project with no pages

    def start_run(self, steps: str) -> dict[str, Any]:
        return self.cli("recipes", "start-project", *[a for s in STEPS[steps] for a in ("--steps", s)])

    def status(self, job_id: str) -> dict[str, Any]:
        return self.cli("recipes", "run-status", job_id)


# ── The soak ─────────────────────────────────────────────────────────────────────────────────────────────────


def soak(engine: Any, job_id: str, total: int, *, kill_at: int | None, every: float, hours: float,
         clock: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] = time.sleep) -> dict[str, Any]:
    """Poll the run every `every` seconds; kill and restart the engine once `kill_at` pages are done. Returns samples, resume and down minutes."""
    t0, samples, resume, down = clock(), [], None, 0.0
    killed = False
    while True:
        minute = (clock() - t0) / 60
        s = reading(engine.status(job_id), minute=minute, rss_mb=engine.rss_mb(), swap_mb=parse_swap_mb(sh(["/usr/sbin/sysctl", "-n", "vm.swapusage"])),
                    previous=samples[-1] if samples else None)
        samples.append(s)
        if s["state"] in ENDED or minute > hours * 60:
            return {"samples": samples, "resume": resume, "down_minutes": down}
        if kill_at is not None and not killed and s["done"] >= kill_at:
            killed, before, gone = True, s, clock()
            engine.kill()
            engine.start()
            down = (clock() - gone) / 60
            after = reading(engine.status(job_id), minute=(clock() - t0) / 60, rss_mb=engine.rss_mb(), swap_mb=None, previous=None)
            samples.append(after)
            resume = resume_check(before, after)
        sleep(every)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder", type=Path)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--steps", choices=list(STEPS), default="segment")
    ap.add_argument("--place", choices=PLACES, default="local")
    ap.add_argument("--kill-at", type=int, default=None)
    ap.add_argument("--every", type=float, default=60.0, help="seconds between readings")
    ap.add_argument("--hours", type=float, default=14.0, help="give up after this long")
    ap.add_argument("--out", type=Path, default=Path("soak.json"))
    a = ap.parse_args(argv)
    images = page_images(a.folder, a.limit)
    if not images:
        print(f"no page images in {a.folder}", file=sys.stderr)
        return 2
    with tempfile.TemporaryDirectory(prefix="soak-") as tmp:
        engine = Engine(Path(tmp))
        try:
            engine.start()
            engine.prepare(images, a.place, a.steps)
            if a.place == "google-dry":
                report = {"pages": len(images), "steps": a.steps, "place": a.place, "samples": [], "resume": None,
                          "cost": cost_per_1000(engine.cli("recipes", "get-start-plan", *[f for s in STEPS[a.steps] for f in ("--steps", s)]), len(images)),
                          "verdict": {"ok": True, "reds": [], "leak_mb_per_hour": None, "peak_rss_mb": engine.rss_mb(), "projected_hours_for_5000": None}}
            else:
                started = engine.start_run(a.steps)
                job_id = ((started or {}).get("started") or {}).get("job_id")
                if not job_id:
                    raise RuntimeError(f"Start queued no run: {json.dumps(started)[:400]}")
                got = soak(engine, job_id, len(images), kill_at=a.kill_at, every=a.every, hours=a.hours)
                report = {"pages": len(images), "steps": a.steps, "place": a.place, "samples": got["samples"], "resume": got["resume"], "cost": None,
                          "verdict": judge(got["samples"], len(images), resume=got["resume"], down_minutes=got["down_minutes"])}
        except RuntimeError as exc:
            print(f"soak could not run: {exc}", file=sys.stderr)
            return 2
        finally:
            engine.kill()
    a.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    a.out.with_suffix(".md").write_text(markdown(report), encoding="utf-8")
    print(markdown(report))
    return 0 if report["verdict"]["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
