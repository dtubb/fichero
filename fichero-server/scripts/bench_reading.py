#!/usr/bin/env python3
"""Speed benchmark for Find Lines + Read with Kraken (the speed review, 2026-10-19).

Target: a median page of 10 s or less (M1 Pro 5-10 s, M4 4-8 s). Over ~20 s a page is overhead, and the per-stage
numbers say which.

Two ways to run it (a script for the tester on the M4; no pytest):

  python fichero-server/scripts/bench_reading.py --model /path/to/reader.safetensors [--pages 20] [--images DIR]
      Reads N pages in this process as a PERSON would start them (the same `_kraken_call` seam a Transcribe
      page goes through: priority, threads, memory guard, resident models), collects the engine's own per-page log
      lines, and prints the statistics. Without --images it draws N synthetic pages of text lines (a proxy: real
      handwriting is slower). Needs the engine's venv (kraken, torch).

  python fichero-server/scripts/bench_reading.py --log engine.log
      Reads the same lines out of an engine log (a run done in the app) and prints the same statistics.

The lines read (written by `llm/kraken_runtime.py` and `workflows/tools/llm_base.py`):
  kraken page <name>: load Xs segment Xs recognise Xs total Xs | priority=.. qos=.. threads=.. person=.. throttle=..
  kraken write <name>: Xs
  model-lane: load|unload <model> ...        (counted per run: every one is a model swap)

Prints min / p50 / p95 / max per stage and for the total, the model loads and unloads, and the priority each page
ran at. Exit 0 if the median page is <= 10 s, else 1.
"""

from __future__ import annotations

import argparse
import logging
import re
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

#: The per-page line (stages in seconds) and the priority fields after the bar.
PAGE = re.compile(
    r"kraken page (?P<name>.+?): load (?P<load>[\d.]+)s segment (?P<segment>[\d.]+)s "
    r"recognise (?P<recognise>[\d.]+)s total (?P<total>[\d.]+)s"
    r"(?: \| priority=(?P<priority>\S+) qos=(?P<qos>\S+) threads=(?P<threads>\S+) person=(?P<person>\S+)"
    r" throttle=(?P<throttle>\S+))?")
STAMP = re.compile(r"^(?P<at>\d{4}-\d\d-\d\d \d\d:\d\d:\d\d),(?P<ms>\d{3})")
WRITE = re.compile(r"kraken write (?P<name>.+?): (?P<write>[\d.]+)s")
LANE = re.compile(r"model-lane: (?P<what>load|unload) (?P<model>.+)")
STAGES = ("load", "segment", "recognise", "write", "total")
TARGET_MEDIAN_SECONDS = 10.0


def parse(lines) -> tuple[list[dict], Counter]:
    """(one record per page with its stages, the model-lane loads and unloads counted by 'load kraken' etc.)."""
    pages: list[dict] = []
    writes: dict[str, float] = {}
    lane: Counter = Counter()
    for line in lines:
        if m := PAGE.search(line):
            record = {k: v for k, v in m.groupdict().items() if v is not None}
            if (when := STAMP.match(line)) is not None:  # an engine log's own clock: the wall time of two pages at once
                from datetime import datetime

                record["ended"] = datetime.strptime(when["at"], "%Y-%m-%d %H:%M:%S").timestamp() + int(when["ms"]) / 1000
            for stage in ("load", "segment", "recognise", "total"):
                record[stage] = float(record[stage])
            pages.append(record)
        elif m := WRITE.search(line):
            writes[m["name"]] = float(m["write"])
        elif m := LANE.search(line):
            lane[f"{m['what']} {m['model'].split(' ')[0]}"] += 1
    for record in pages:
        if record["name"] in writes:
            record["write"] = writes[record["name"]]
    return pages, lane


def percentile(values: list[float], p: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(round(p * (len(ordered) - 1))))]


def report(pages: list[dict], lane: Counter) -> int:
    if not pages:
        print("No 'kraken page' lines found: nothing was read, or the engine is older than the instrument.")
        return 1
    print(f"{len(pages)} pages\n")
    print(f"{'stage':<10}{'min':>8}{'p50':>8}{'p95':>8}{'max':>8}")
    for stage in STAGES:
        values = [p[stage] for p in pages if stage in p]
        if values:
            print(f"{stage:<10}{min(values):>8.1f}{statistics.median(values):>8.1f}"
                  f"{percentile(values, 0.95):>8.1f}{max(values):>8.1f}")
    print("\npriority  ", dict(Counter(f"{p.get('priority', '?')}/{p.get('qos', '?')}/threads={p.get('threads', '?')}"
                                     f"/person={p.get('person', '?')}/{p.get('throttle', '?')}" for p in pages)))
    print("model-lane", dict(lane) or "no model load or unload lines")
    median = statistics.median(p["total"] for p in pages)
    if all("ended" in p for p in pages):
        # Two pages at once make each page's own time longer; what the person waits for is the wall time of the run.
        began = min(p["ended"] - p["total"] for p in pages)
        wall = max(p["ended"] for p in pages) - began
        median = wall / len(pages)
        print(f"\nwall: {wall:.1f}s for {len(pages)} pages = {median:.1f} s a page")
    ok = median <= TARGET_MEDIAN_SECONDS
    print(f"\nmedian page {median:.1f}s: {'OK' if ok else 'OVER'} (target <= {TARGET_MEDIAN_SECONDS:.0f}s)")
    return 0 if ok else 1


class _Collect(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.INFO)
        self.lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(record.getMessage())


def _synthetic_pages(folder: Path, count: int) -> list[Path]:
    from PIL import Image, ImageDraw

    folder.mkdir(parents=True, exist_ok=True)
    out = []
    for i in range(count):
        image = Image.new("RGB", (710, 925), "white")
        draw = ImageDraw.Draw(image)
        for row in range(26):
            draw.text((40, 40 + row * 32), f"{i:03} line {row} of a page of text to find and read", fill="black")
        path = folder / f"IMG_{i + 1:03}.png"
        image.save(path)
        out.append(path)
    return out


def run(model: str, pages: int, images: Path | None, concurrency: int = 1, automatic: bool = False) -> tuple[list[dict], Counter]:
    """Read the pages through Kraken's own seam, as a person's Start would: flat out, the engine's per-page lines
    collected."""
    import tempfile

    from fichero_server.execution import jobs
    from fichero_server.llm import kraken_runtime

    if automatic:  # an import's own run while the Mac is used: the throttle's lowest class, which Kraken lifts
        from fichero_server.execution import throttle

        throttle.mac_is_in_use = lambda: "the Mac is in use"
    collect = _Collect()
    logging.getLogger().addHandler(collect)
    logging.getLogger().setLevel(logging.INFO)
    files = sorted(images.glob("*.*"))[:pages] if images else _synthetic_pages(Path(tempfile.mkdtemp()), pages)
    def read(path: Path) -> None:
        jobs._current.person = not automatic  # a job a person started or watches (`current_job_is_a_persons`); per thread; --automatic: an import's own run
        kraken_runtime.recognize_lines(str(path), model)

    began = time.perf_counter()
    if concurrency > 1:  # the engine's own fan-out: pages arrive on pooled threads, the seam lets two read at once
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            list(pool.map(read, files))
    else:
        for path in files:
            read(path)
    wall = time.perf_counter() - began
    import resource

    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss  # bytes on macOS (kilobytes on Linux)
    peak_gb = peak / 1024**3 if sys.platform == "darwin" else peak / 1024**2
    print(f"read {len(files)} pages in {wall:.1f}s with {concurrency} at once: {wall / max(1, len(files)):.1f} s a page "
          f"(wall), peak memory {peak_gb:.1f} GB\n")
    return parse(collect.lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--log", help="read the lines from this engine log instead of running")
    ap.add_argument("--model", help="a Kraken reader (.mlmodel / .safetensors) to read with")
    ap.add_argument("--pages", type=int, default=20)
    ap.add_argument("--images", type=Path, help="a folder of page images (default: drawn pages)")
    ap.add_argument("--concurrency", type=int, default=1,
                    help="pages sent at once, as the engine's fan-out does (the seam reads two together when memory allows)")
    ap.add_argument("--automatic", action="store_true", help="read as an import's own (automatic) run, not a person's")
    args = ap.parse_args()
    if args.log:
        pages, lane = parse(Path(args.log).read_text(errors="replace").splitlines())
    elif args.model:
        pages, lane = run(args.model, args.pages, args.images, args.concurrency, args.automatic)
    else:
        ap.error("give --model (to run) or --log (to read an engine log)")
    return report(pages, lane)


if __name__ == "__main__":
    sys.exit(main())
