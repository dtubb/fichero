"""The M4 gate's load leg (#4634): a recipe run over 100+ pages on a TEMP engine finishes (#6212).

Pins `recipes-run.reliability.hundred-pages-finish` and `recipes-run.memory.flat-over-pages`; records the engine
tree's peak footprint for `recipes-run.memory.peak-ceiling-per-model-kind` (#6076's measured table) without
asserting a ceiling: no ceiling is coded until that table exists (ruling, 2026-10-26 night).

Skipped unless FICHERO_LOAD_LEG_PAGES names a folder of at least 100 page images, so it never runs on the Pro or
in the normal suite. On the M4, in a GUI session, with the models already installed (no download here):

    FICHERO_LOAD_LEG_PAGES=~/corpora/marshall-100 FICHERO_LOAD_LEG_OUT=~/load-leg \\
      PYTHONPATH=fichero-server/src .venv/bin/pytest fichero-server/tests/perf/test_recipe_run_100_pages.py -s

FICHERO_LOAD_LEG_PURPOSES (default "transcribe,search") picks the recipe. The engine is `_engine_harness.start_engine`
on a fresh FICHERO_BASE_PATH: never the owner's app database.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
PAGES = os.environ.get("FICHERO_LOAD_LEG_PAGES", "")
IMAGES = {".jpg", ".jpeg", ".png", ".tif", ".tiff"}
MIN_PAGES = 100
SAMPLE_EVERY = 2.0  # seconds (the spec's sampling interval)
HEALTH_LIMIT = 1.0  # seconds: /api/health answers within 1 s at every sample
FLAT_TOLERANCE = 0.10  # pages 80-100 within 10% of pages 20-40

pytestmark = [
    pytest.mark.slow,
    pytest.mark.timing,
    pytest.mark.load_sensitive,
    pytest.mark.timeout(4 * 3600),
]
needs_pages = pytest.mark.skipif(
    not PAGES or sum(1 for p in Path(PAGES).expanduser().rglob("*") if p.suffix.lower() in IMAGES) < MIN_PAGES,
    reason=f"the load leg needs FICHERO_LOAD_LEG_PAGES: a folder of {MIN_PAGES}+ page images (the M4 gate, #4634)")


def _tree_footprint(pid: int) -> int:
    """The engine and every process it started (model servers), by physical footprint (Activity Monitor's Memory)."""
    import psutil

    from fichero_server.execution.throttle import footprint_bytes

    try:
        pids = [pid] + [c.pid for c in psutil.Process(pid).children(recursive=True)]
    except psutil.NoSuchProcess:
        return 0
    return sum(footprint_bytes(p) or 0 for p in pids)


def _running_pages_done(run: dict) -> tuple[str | None, int | None]:
    """The running stage and its pages done, from the run status's per-stage account."""
    for step in run.get("steps") or []:
        if step.get("state") == "running" and step.get("account"):
            return step.get("card"), step["account"].get("pages_done")
    return None, None


def _mean(xs: list[int]) -> float:
    return sum(xs) / len(xs)


def flat_over_pages(samples: list[dict]) -> tuple[float, float] | None:
    """Mean footprint of the first heavy stage's pages 20-40 and 80-100, or None when either band has no sample."""
    stage = next((s["stage"] for s in samples if s["stage"]), None)
    early = [s["footprint"] for s in samples if s["stage"] == stage and 20 <= (s["done"] or 0) <= 40]
    late = [s["footprint"] for s in samples if s["stage"] == stage and 80 <= (s["done"] or 0) <= 100]
    return (_mean(early), _mean(late)) if early and late else None


def test_flat_over_pages_reads_the_first_stage_bands():
    """The band rule itself, so the load leg's arithmetic is checked wherever the suite runs (not skipped)."""
    samples = [{"stage": "read", "done": d, "footprint": f} for d, f in ((10, 1), (25, 100), (35, 104), (85, 108), (99, 106))]
    samples.append({"stage": "search", "done": 90, "footprint": 999})  # a later stage is not the band
    assert flat_over_pages(samples) == (102.0, 107.0)
    assert flat_over_pages(samples[:2]) is None


@needs_pages
def test_a_100_page_run_finishes_flat_and_answering(tmp_path):
    sys.path.insert(0, str(SCRIPTS))
    import httpx
    from _engine_harness import start_engine
    from e2e_recipe_run import _import, _wait

    out = Path(os.environ.get("FICHERO_LOAD_LEG_OUT") or tmp_path)
    out.mkdir(parents=True, exist_ok=True)
    purposes = os.environ.get("FICHERO_LOAD_LEG_PURPOSES", "transcribe,search").split(",")
    report: dict = {"pages": PAGES, "purposes": purposes, "samples": []}
    base = tempfile.mkdtemp(prefix="fich_load_")
    ep = start_engine(transport="uds", log_dir=str(out), base_path=base)
    library = str(Path(tempfile.mkdtemp(prefix="load_", dir="/tmp")) / "load.fichero")
    headers = {"Authorization": f"Bearer {ep.token}", "X-Fichero-Library-Path": library}
    stop = threading.Event()
    health: list[float] = []

    def _sample_health():  # its own client and thread: a held run poll never hides a slow health answer
        with httpx.Client(timeout=30, headers=headers, **ep.httpx_kwargs()) as c:
            while not stop.is_set():
                t0 = time.monotonic()
                c.get("/api/health").raise_for_status()
                health.append(time.monotonic() - t0)
                stop.wait(SAMPLE_EVERY)

    try:
        with httpx.Client(timeout=120, headers=headers, **ep.httpx_kwargs()) as client:
            client.post("/api/library", json={"path": library}).raise_for_status()
            _import(client, str(Path(PAGES).expanduser()), report, "pages")
            answers = {"purposes": purposes, "languages": ["la"], "scripts": ["Latn"], "materials": ["handwriting"],
                       "cloud_allowed": False, "pages": 5}
            client.put("/api/recipes/project", json={"answers": answers}).raise_for_status()
            started = client.post("/api/recipes/project/start", json={})
            assert started.status_code == 200, started.text[:2000]
            job = started.json()["started"]["job_id"]
            sampler = threading.Thread(target=_sample_health, daemon=True)
            sampler.start()

            def _sample(run: dict) -> None:
                assert ep.proc.poll() is None, f"the engine died mid-run (rc={ep.proc.returncode}); log: {ep.log_path}"
                stage, done = _running_pages_done(run)
                report["samples"].append({"t": time.monotonic(), "stage": stage, "done": done,
                                          "footprint": _tree_footprint(ep.proc.pid), "state": run.get("state")})

            run = _wait(client, f"/api/recipes/project/runs/{job}",
                        lambda b: (b.get("state") or "") not in ("", "queued", "running", "waiting", "paused", "pending"),
                        every=SAMPLE_EVERY, limit=4 * 3600, say=_sample)
            report["run"] = run
    finally:
        stop.set()
        alive = ep.proc.poll() is None
        ep.stop()
        report["health_seconds_max"] = max(health, default=None)
        report["peak_footprint_bytes"] = max((s["footprint"] for s in report["samples"]), default=None)
        (out / "load_leg_report.json").write_text(json.dumps(report, indent=1, default=str))

    assert alive, f"the engine was not alive at the end; log: {ep.log_path}"
    assert run.get("state") == "done", f"run ended {run.get('state')}: {run.get('reason')}"
    failed = [s.get("card") for s in run.get("steps") or [] if s.get("state") == "failed"]
    assert not failed, f"steps failed outright: {failed}"
    slow = [h for h in health if h > HEALTH_LIMIT]
    assert health and not slow, f"/api/health took over {HEALTH_LIMIT}s {len(slow)} of {len(health)} times (max {max(health):.1f}s)"
    bands = flat_over_pages(report["samples"])
    assert bands, "no footprint sample fell in both the 20-40 and the 80-100 page bands"
    early, late = bands
    assert late <= early * (1 + FLAT_TOLERANCE), (
        f"memory grew page over page: pages 80-100 average {late / 1024**3:.2f} GB, pages 20-40 {early / 1024**3:.2f} GB")
