#!/usr/bin/env python3
"""One Kraken page at a time against two at once, through the engine's REAL model lane and page gate (#5846,
`activity.lane.same-model-pages-together`, `source.read.two-pages-at-once`). Not faked work: each page is a job on the lane
(`jobs.run_on_lane_blocking`, a handed-in page a person waits on), reading with `kraken_runtime.recognize_lines`.

  python fichero-server/scripts/bench_same_model_pages.py --model /path/to/reader.safetensors [--pages 8] [--images DIR]

Runs in a scratch state dir (`FICHERO_BASE_PATH`), so nothing of the person's is touched. Without --images it draws pages
of text lines (a proxy; real handwriting is slower, so use a few public dev-corpus pages or the reader seed's pages for the
figure that counts). Run it on the M4 on AC with nothing else busy; needs the engine's venv (kraken, torch).

Prints, for 1 and then 2 pages at once: s a page (wall), the most pages that were reading at the same moment, and the
effective `pages_at_once` (2 only on the fast priority, >= 4 cores and memory for both; else the lane runs one and the two
runs will match, which the report says). Exit 0 when two at once read faster than one by >= 10 %, else 1.
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

SCRATCH = tempfile.mkdtemp(prefix="bench-same-model-")
os.environ["FICHERO_BASE_PATH"] = SCRATCH  # before any fichero_server import
sys.path.insert(0, str(Path(__file__).resolve().parent))


def _library() -> str:
    """A scratch library (the lane's jobs are rows in a library's database)."""
    from fichero_server.db.manager import db_manager

    package = Path(SCRATCH) / "bench.fichero"
    for sub in ("lance", "storage", "files"):
        (package / sub).mkdir(parents=True, exist_ok=True)
    db_manager.get_database(package)
    return str(package)


def read_pages(library: str, files: list[Path], model_path: str, model_id: str | None, wanted: int) -> dict:
    from fichero_server.execution import jobs
    from fichero_server.llm import kraken_runtime

    kraken_runtime.pages_at_once = lambda person: wanted  # the bench sets the cap itself (the real one is the cores, gated at two)
    effective = kraken_runtime.pages_at_once(True)
    lock, now, peak = threading.Lock(), [0], [0]

    def work(path: Path):
        def read():
            with lock:
                now[0] += 1
                peak[0] = max(peak[0], now[0])
            try:
                return kraken_runtime.recognize_lines(str(path), model_path)
            finally:
                with lock:
                    now[0] -= 1
        return jobs.run_on_lane_blocking(library, "read-a-line", path.name,
                                         model=f"kraken:{model_id or model_path}", fn=read)

    began = time.perf_counter()
    with ThreadPoolExecutor(max_workers=len(files)) as pool:  # every page is handed in at once; the lane admits as many as it may
        list(pool.map(work, files))
    wall = time.perf_counter() - began
    return {"wanted": wanted, "effective": effective, "peak": peak[0], "wall": wall, "per_page": wall / len(files)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", required=True, help="a Kraken reader (.mlmodel / .safetensors)")
    ap.add_argument("--pages", type=int, default=8)
    ap.add_argument("--images", type=Path, help="a folder of page images (default: drawn pages)")
    args = ap.parse_args()

    from bench_reading import _synthetic_pages
    from fichero_server.llm import kraken_runtime

    files = sorted(args.images.glob("*.*"))[: args.pages] if args.images else _synthetic_pages(Path(SCRATCH) / "pages", args.pages)
    library = _library()
    model_path, model_id = kraken_runtime.resolve_recognition_model(args.model)
    read_pages(library, files[:1], model_path, model_id, 1)  # warm: the models load once, outside the timing
    one = read_pages(library, files, model_path, model_id, 1)
    two = read_pages(library, files, model_path, model_id, 2)
    print(f"{len(files)} pages, scratch state {SCRATCH}")
    for r in (one, two):
        print(f"  {r['wanted']} at once: {r['per_page']:.1f} s a page (wall {r['wall']:.1f} s), "
              f"most reading together {r['peak']}, pages_at_once={r['effective']}")
    if two["peak"] < 2:
        print("two never read together: pages_at_once was 1 here (priority, cores or memory), so the runs match")
        return 1
    gain = 1 - two["per_page"] / one["per_page"]
    print(f"two at once is {gain * 100:.0f}% faster a page (r1's M4 figure: 6.3 s against 9.7-10.2 s, about 35-38%)")
    return 0 if gain >= 0.10 else 1


if __name__ == "__main__":
    try:
        code = main()
    finally:  # only what this run made: its own mkdtemp state dir
        from fichero_server.db.manager import db_manager

        db_manager.close_all()
        shutil.rmtree(SCRATCH, ignore_errors=True)
    from fichero_server.core.fast_exit import leave  # torch loaded: leave past its exit-time destructor (#5929)

    leave(code or 0)
    sys.exit(code)
