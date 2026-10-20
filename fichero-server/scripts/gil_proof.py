#!/usr/bin/env python3
"""Is Python's GIL what caps Kraken at about two pages at once? (owner's doubt, 2026-10-20; briefs/gil-proof-2026-10-20.md)

A MEASUREMENT for the tester on the M4 (on AC, one heavy job, the dev corpus pages). Not a test. It never runs on the
Pro. Every mode prints one markdown table row per N, and with --out appends the same as JSON lines.

  ceiling   the plain `kraken` CLI in N separate processes, torch/BLAS threads 1 each: pages/minute and CPU%. What the
            app should reach. Segment + recognise together (the CLI does both).
  threads   blla.segment alone in N THREADS of one process, one shared model (as the engine does), threads 1.
  procs     blla.segment alone in N PROCESSES, a model each, threads 1 (--pools one: every native pool 1 thread; the
            first M4 run used --pools default and burned ~110% CPU a process at N=1 and twice the CPU a page at N=4:
            hidden threads, so cpu_s_per_page is in every row). threads vs procs on the same stage and pages is
            the GIL test with nothing of ours in between: if procs scale and threads do not, it is the GIL.
  engine    the engine's own seam (kraken_runtime._kraken_call) with N pages at once, the cap lifted to N, run twice
            (--threads one: 1 torch thread a page; --threads default: the engine's own split). Per stage seconds, wall,
            CPU%, and the wait at each lock the seam takes (the page gate, the memory guard).
  spy-top   summarise py-spy output (see the run brief): the top 10 functions and the share of samples holding the GIL.

  python fichero-server/scripts/gil_proof.py ceiling --images DIR --model reader.safetensors --pages 20 --n 1,2,4,8,10
  python fichero-server/scripts/gil_proof.py threads  --images DIR --pages 20 --n 1,2,4,8
  python fichero-server/scripts/gil_proof.py procs    --images DIR --pages 20 --n 1,2,4,8
  python fichero-server/scripts/gil_proof.py engine   --images DIR --model reader.safetensors --pages 20 --n 1,2,4,8 --threads one
  python fichero-server/scripts/gil_proof.py spy-top gil.raw --all all.raw

`threads`, `procs` and `engine` need the engine's venv (kraken, torch); `ceiling` needs the `kraken` command of it.
"""

from __future__ import annotations

import argparse
import collections
import contextlib
import json
import multiprocessing as mp
import os
import resource
import shutil
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

#: One thread in every pool a page can start, so N pipelines never oversubscribe the cores (brief, point 4).
ONE_THREAD = {k: "1" for k in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "VECLIB_MAXIMUM_THREADS",
                               "NUMEXPR_NUM_THREADS")}
CORES = os.cpu_count() or 1


def pages_in(images: Path, count: int) -> list[Path]:
    files = sorted(p for p in images.glob("*.*") if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".tif", ".tiff"})
    if len(files) < count:
        sys.exit(f"{images} holds {len(files)} images, {count} wanted")
    return files[:count]


def shards(files: list[Path], n: int) -> list[list[Path]]:
    return [files[i::n] for i in range(n) if files[i::n]]


def cpu_seconds(who: int) -> float:
    use = resource.getrusage(who)
    return use.ru_utime + use.ru_stime


def row(mode: str, n: int, pages: int, wall: float, cpu: float, extra: dict | None = None, out: Path | None = None) -> dict:
    """One line of the table: pages a minute, seconds a page (wall), and CPU as % of ONE core and of the whole Mac."""
    record = {"mode": mode, "n": n, "pages": pages, "wall_s": round(wall, 1), "s_per_page": round(wall / pages, 2),
              "pages_per_min": round(60 * pages / wall, 1), "cpu_s_per_page": round(cpu / pages, 2),
              "cpu_pct_of_one_core": round(100 * cpu / wall),
              "cpu_pct_of_mac": round(100 * cpu / wall / CORES), **(extra or {})}
    print("| " + " | ".join(f"{k}={v}" for k, v in record.items()) + " |", flush=True)
    if out:
        with out.open("a") as handle:
            handle.write(json.dumps(record) + "\n")
    return record


# -- ceiling: the plain CLI in N processes ----------------------------------------------------------------------------
def ceiling(args) -> None:
    beside = Path(sys.executable).parent / "kraken"  # the venv python's own `kraken` command
    kraken = args.kraken or (str(beside) if beside.exists() else shutil.which("kraken")) or sys.exit(
        "no `kraken` command: pass --kraken <engine venv>/bin/kraken")
    files = pages_in(args.images, args.pages)
    for n in args.n:
        with tempfile.TemporaryDirectory() as scratch:  # the CLI writes beside its input: never in the corpus
            procs = []
            for i, shard in enumerate(shards(files, n)):
                folder = Path(scratch) / str(i)
                folder.mkdir()
                inputs: list[str] = []
                for page in shard:
                    (folder / page.name).symlink_to(page.resolve())
                    inputs += ["-I", str(folder / page.name)]
                procs.append(subprocess.Popen([kraken, "-f", "image", *inputs, "-o", ".gilproof.txt", "segment", "-bl",
                                               "ocr", "-m", str(args.model)], env={**os.environ, **ONE_THREAD},
                                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
            began, cpu0 = time.perf_counter(), cpu_seconds(resource.RUSAGE_CHILDREN)
            codes = [p.wait() for p in procs]
            wall, cpu = time.perf_counter() - began, cpu_seconds(resource.RUSAGE_CHILDREN) - cpu0
        row("ceiling", n, len(files), wall, cpu, {"exit": max(codes), "note": "includes each process loading its model once"},
            args.out)


# -- threads / procs: blla alone ---------------------------------------------------------------------------------------
def _segment_all(model, paths: list[str]) -> None:
    from kraken import blla
    from PIL import Image

    for path in paths:
        with Image.open(path) as image:
            blla.segment(image.convert("RGB"), model=model)


def _load_blla():
    from importlib import resources

    from kraken.lib import vgsl

    return vgsl.TorchVGSLModel.load_model(resources.files("kraken").joinpath("blla.mlmodel"))


def threads(args) -> None:
    import torch

    torch.set_num_threads(1)
    model = _load_blla()
    files = [str(p) for p in pages_in(args.images, args.pages)]
    _segment_all(model, files[:1])  # warm: the first page pays the lazy imports
    for n in args.n:
        pool = [threading.Thread(target=_segment_all, args=(model, [str(p) for p in shard]))
                for shard in shards([Path(f) for f in files], n)]
        began, cpu0 = time.perf_counter(), cpu_seconds(resource.RUSAGE_SELF)
        for t in pool:
            t.start()
        for t in pool:
            t.join()
        row("threads", n, len(files), time.perf_counter() - began, cpu_seconds(resource.RUSAGE_SELF) - cpu0, out=args.out)


def _proc(paths: list[str], ready, go, done) -> None:
    import torch

    torch.set_num_threads(1)
    model = _load_blla()
    _segment_all(model, paths[:1])
    ready.put(os.getpid())
    go.wait()
    began = time.time()
    _segment_all(model, paths)
    done.put((began, time.time(), cpu_seconds(resource.RUSAGE_SELF)))


def procs(args) -> None:
    files = [str(p) for p in pages_in(args.images, args.pages)]
    context = mp.get_context("spawn")  # a forked child of a process that has run torch crashes (the spec's note)
    for n in args.n:
        parts = [[str(p) for p in shard] for shard in shards([Path(f) for f in files], n)]
        ready, done, go = context.Queue(), context.Queue(), context.Event()
        workers = [context.Process(target=_proc, args=(part, ready, go, done)) for part in parts]
        for w in workers:
            w.start()
        for _ in workers:
            ready.get()  # every model loaded and warm: the clock starts when all are ready
        go.set()
        results = [done.get() for _ in workers]
        for w in workers:
            w.join()
        wall = max(r[1] for r in results) - min(r[0] for r in results)
        row("procs", n, len(files), wall, sum(r[2] for r in results), {"note": "model load and warm-up excluded"}, args.out)


# -- engine: the seam, N pages at once --------------------------------------------------------------------------------
class Waits:
    """Seconds spent waiting at each lock the seam takes, per page."""

    def __init__(self) -> None:
        self.by_lock: dict[str, list[float]] = collections.defaultdict(list)

    def timed(self, name: str, enter):
        began = time.perf_counter()
        try:
            return enter()
        finally:
            self.by_lock[name].append(time.perf_counter() - began)


def engine(args) -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import bench_reading
    from fichero_server.core import compute_preferences
    from fichero_server.llm import kraken_runtime

    if args.threads == "one":  # 1 torch thread a page, whatever the number of pages inside
        compute_preferences.apply_to_this_thread = lambda priority: 1
    waits = Waits()
    gate = kraken_runtime._INFERENCE_LOCK
    real_page = gate.page

    @contextlib.contextmanager
    def timed_page(allowed: int = 1):
        began = time.perf_counter()
        with real_page(allowed):
            waits.by_lock["page gate"].append(time.perf_counter() - began)
            yield

    gate.page = timed_page
    real_memory = kraken_runtime.assert_memory_available_for_kraken
    kraken_runtime.assert_memory_available_for_kraken = lambda *a, **k: waits.timed("memory guard", lambda: real_memory(*a, **k))
    for n in args.n:
        kraken_runtime.pages_at_once = lambda person=False, _n=n: _n  # the cap lifted to N: the thing under test
        waits.by_lock.clear()
        cpu0 = cpu_seconds(resource.RUSAGE_SELF)
        began = time.perf_counter()
        try:
            pages, _lane = bench_reading.run(args.model, args.pages, args.images, n)
        except Exception as exc:  # noqa: BLE001 -- the memory guard refusing is a result, said in words
            print(f"| engine n={n}: stopped: {exc} |")
            continue
        wall = time.perf_counter() - began
        stage = {s: round(statistics.mean(p[s] for p in pages), 2) for s in ("segment", "recognise", "total") if pages}
        lock = {k: {"mean_s": round(statistics.mean(v), 3), "max_s": round(max(v), 3), "n": len(v)}
                for k, v in waits.by_lock.items() if v}
        row("engine", n, len(pages), wall, cpu_seconds(resource.RUSAGE_SELF) - cpu0,
            {"torch_threads": args.threads, "stage_mean_s": stage, "lock_waits": lock}, args.out)


# -- spy-top: py-spy's folded output ------------------------------------------------------------------------------------
def _folded(path: Path) -> collections.Counter:
    """(stack -> samples) from py-spy `--format raw` (one `a;b;c count` per line)."""
    stacks: collections.Counter = collections.Counter()
    for line in path.read_text(errors="replace").splitlines():
        stack, _, count = line.rpartition(" ")
        if stack and count.isdigit():
            stacks[stack] += int(count)
    return stacks


def spy_top(args) -> None:
    gil = _folded(args.file)
    held = sum(gil.values())
    leaf = collections.Counter()
    package = collections.Counter()
    for stack, count in gil.items():
        frames = stack.split(";")
        leaf[frames[-1]] += count
        owner = next((f for f in reversed(frames) if "site-packages/" in f or "fichero_server" in f), frames[-1])
        key = owner.split("site-packages/")[-1].split("/")[0] if "site-packages/" in owner else (
            "fichero_server" if "fichero_server" in owner else "other")
        package[key] += count
    print(f"{held} samples hold the GIL ({args.file.name})")
    if args.all:
        everything = sum(_folded(args.all).values())
        print(f"{everything} samples of threads doing anything ({args.all.name}): the GIL is held in "
              f"{100 * held / max(1, everything):.0f}% of them")
    print("\ntop 10 functions holding the GIL:")
    for name, count in leaf.most_common(10):
        print(f"  {100 * count / max(1, held):5.1f}%  {name}")
    print("\nby package:", {k: f"{100 * v / max(1, held):.0f}%" for k, v in package.most_common(8)})


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="mode", required=True)
    for name, fn in (("ceiling", ceiling), ("threads", threads), ("procs", procs), ("engine", engine)):
        p = sub.add_parser(name)
        p.add_argument("--images", type=Path, required=True)
        p.add_argument("--pages", type=int, default=20)
        p.add_argument("--n", type=lambda s: [int(x) for x in s.split(",")], default=[1, 2, 4, 8])
        p.add_argument("--out", type=Path)
        if name in ("threads", "procs"):
            p.add_argument("--pools", choices=("one", "default"), default="one",
                           help="one: every native thread pool (OpenMP, BLAS, Accelerate) set to 1 thread before torch "
                                "loads; default: torch.set_num_threads(1) only, as the first run did")
        if name in ("ceiling", "engine"):
            p.add_argument("--model", type=Path, required=True)
        if name == "ceiling":
            p.add_argument("--kraken")
        if name == "engine":
            p.add_argument("--threads", choices=("one", "default"), default="one")
        p.set_defaults(fn=fn)
    p = sub.add_parser("spy-top")
    p.add_argument("file", type=Path)
    p.add_argument("--all", type=Path)
    p.set_defaults(fn=spy_top)
    args = ap.parse_args()
    if getattr(args, "pools", None) == "one":  # before any torch import; spawned children inherit it
        os.environ.update(ONE_THREAD)
    args.fn(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
