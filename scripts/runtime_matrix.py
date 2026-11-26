#!/usr/bin/env python3
"""Measure every runtime the engine has, on this Mac, with real models (`runner.measured.runtime-matrix`).

    PYTHONPATH=fichero-server/src python3 scripts/runtime_matrix.py [--out matrix.json] [--only NAME ...]
                                                                    [--python PATH | --engine-app APP] [--remote hf-jobs|cluster]

`--python PATH` runs every runtime under that interpreter, for a Mac whose dev venv lacks mlx_vlm, mlx_whisper or
ultralytics: pass the shipped engine's Python (inside the app bundle, its Resources python), with PYTHONPATH as above.
`--engine-app <the built engine .app>` does the same from the app bundle: its bundled Python and its
Contents/Resources/app_packages on PYTHONPATH (where ultralytics, mlx_vlm and mlx_whisper ship). YOLO also needs its
weights downloaded to the model store (the app's download-model job), else its row says so.
The sample is the 5 fixtures plus one A4 page at 300 dpi built at run time; the embedder runs offline.

Each runtime runs a fixed sample of public test-fixture page images through the engine's own entry point, twice in a
row. Per runtime: ran ok or failed (the failure kind and words from the engine's kinds table), seconds per page (the
first page, which pays the cold load, apart), the peak RSS of the process that ran it, and how many times its model was
LOADED across the two passes (1 is right; 2 or more means it unloads between pages). Each runtime runs in a fresh
child process so its peak RSS is its own. State and library are scratch dirs under a temp dir, never the app's; the
installed models are read from this Mac's model store (`FICHERO_MODEL_STORE_ROOT`, default the app's), never written.
`--remote` only dry-runs (no job is submitted, nothing is paid). Prints a Markdown table, writes one JSON file, exits 0
even when runtimes fail: the table is the result.
"""
from __future__ import annotations

import argparse
import functools
import json
import os
import platform
import resource
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FIXTURES = REPO / "test-fixtures" / "files"
#: The sample: 5 page images from the repo's public fixtures (no archive material).
SAMPLE = ("sample.png", "sample.jpg", "sample_text_page1.png", "sample_text_page2.png", "sample.webp")
AUDIO = "sample.wav"
TEXT = "Mr. Davidson wrote to Mrs. Hale in Boston on 4 May 1861 about the ship."
REAL_PAGE = "page_a4_300dpi.png"
PASSES = 2
WORKER_TIMEOUT_SECONDS = 1800

#: Loads counted in this process, by the model's name (kraken, spaCy and the embedder report through the engine's own
#: `model_load`; YOLO and MLX through their libraries' constructors).
LOADS: dict[str, int] = {}
#: The interpreter each isolated worker runs under (`--python`); None: this one.
WORKER_PYTHON: str | None = None


@dataclass
class Runtime:
    name: str
    #: Why this runtime cannot run on this Mac, or None. Called before anything loads.
    unavailable: Callable[[], str | None]
    #: Runs one page (an image path; the audio path for Whisper) through the engine's entry point.
    call: Callable[[Path], object]
    #: Prefix of the `LOADS` keys that are this runtime's model; None: loads are not counted for it.
    load_key: str | None = None
    note: str = ""
    inputs: Callable[[list[Path]], list[Path]] = field(default=lambda pages: pages)


def loads_of(prefix: str | None) -> int | None:
    return None if prefix is None else sum(n for key, n in LOADS.items() if key.startswith(prefix))


def failure_of(exc: BaseException) -> dict[str, str]:
    """The engine's own kind and words for an exception (`llm.failure.classify`)."""
    from fichero_server.llm.failure import classify

    failure = classify(exc, str(exc))
    return {"kind": failure.kind, "words": failure.words, "exception": type(exc).__name__}


def measure(runtime: Runtime, pages: list[Path], *, passes: int = PASSES,
            clock: Callable[[], float] = time.perf_counter) -> dict[str, object]:
    """Run `pages` through `runtime` `passes` times; one result row. A failure is a row, never an exception."""
    row: dict[str, object] = {"runtime": runtime.name, "note": runtime.note}
    why = runtime.unavailable()
    if why:
        return {**row, "status": "unavailable", "words": why}
    work = runtime.inputs(pages)
    before = loads_of(runtime.load_key)
    times: list[float] = []
    try:
        for _ in range(passes):
            for page in work:
                started = clock()
                runtime.call(page)
                times.append(clock() - started)
    except Exception as exc:  # noqa: BLE001 -- the failure is the measurement
        return {**row, "status": "failed", **failure_of(exc), "pages_done": len(times),
                "loads": None if before is None else (loads_of(runtime.load_key) or 0) - before}
    after = loads_of(runtime.load_key)
    rest = times[1:]
    return {**row, "status": "ok", "pages": len(work), "passes": passes, "first_page_s": round(times[0], 3),
            "per_page_s": round(sum(rest) / len(rest), 3) if rest else None,
            "loads": None if before is None or after is None else after - before}


def footprint_mb() -> float | None:
    """This process's physical footprint now (what Activity Monitor calls Memory), beside the peak RSS, which on macOS
    leaves out compressed and GPU-held pages; None when it cannot be read."""
    sys.path.insert(0, str(REPO / "fichero-server" / "src"))
    try:
        from fichero_server.execution.throttle import footprint_bytes

        value = footprint_bytes(os.getpid())
    except ImportError:
        return None
    return None if value is None else round(value / 1048576, 1)


def real_size_page(folder: Path) -> Path:
    """An A4 page at 300 dpi (2480 x 3508) of rendered print, 40 lines: Kraken scales every page to 1800 rows, so the
    fixtures (100 to 900 px wide) measured upscaled thumbnails. Built on the first call, reused after."""
    from PIL import Image, ImageDraw, ImageFont

    path = folder / REAL_PAGE
    if path.exists():
        return path
    image = Image.new("L", (2480, 3508), 255)
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=48)
    for line in range(40):
        draw.text((220, 250 + line * 78), f"{line + 1:02d}  {TEXT}  {TEXT[:30]}", fill=0, font=font)
    folder.mkdir(parents=True, exist_ok=True)
    image.save(path)
    return path


def sample_pages(folder: Path) -> list[Path]:
    return [FIXTURES / name for name in SAMPLE] + [real_size_page(folder)]


def engine_app_python(app: Path) -> tuple[Path, Path]:
    """The shipped engine's interpreter and its `app_packages` folder (where `ultralytics`, `mlx_vlm` and `mlx_whisper` are
    installed), found from the engine app bundle. Exits naming what is missing."""
    contents = app / "Contents"
    pythons = sorted(contents.glob("Frameworks/Python.framework/Versions/3.*/bin/python3.*"))
    packages = contents / "Resources" / "app_packages"
    if not pythons or not packages.is_dir():
        raise SystemExit(f"--engine-app {app}: no bundled Python (Contents/Frameworks/Python.framework/Versions/3.x/bin) "
                         "or no Contents/Resources/app_packages in it")
    return pythons[-1], packages


def peak_rss_mb() -> float:
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return round(peak / (1024 * 1024 if sys.platform == "darwin" else 1024), 1)  # bytes on macOS, KB on Linux


def machine() -> dict[str, object]:
    """Chip, RAM, macOS and free memory at the start."""
    def sysctl(name: str) -> str | None:
        try:
            return subprocess.run(["/usr/sbin/sysctl", "-n", name], capture_output=True, text=True, timeout=10).stdout.strip() or None
        except (OSError, subprocess.SubprocessError):
            return None

    ram = sysctl("hw.memsize")
    free_mb = None
    try:
        out = subprocess.run(["vm_stat"], capture_output=True, text=True, timeout=10).stdout
        page = int(out.split("page size of")[1].split("bytes")[0])
        counts = {line.split(":")[0]: int(line.split(":")[1].strip(" .")) for line in out.splitlines()[1:] if ":" in line}
        free_mb = round((counts.get("Pages free", 0) + counts.get("Pages inactive", 0)) * page / 1048576)
    except (OSError, subprocess.SubprocessError, IndexError, ValueError):
        pass
    return {"chip": sysctl("machdep.cpu.brand_string") or platform.machine(),
            "ram_gb": round(int(ram) / 2**30) if ram else None,
            "macos": platform.mac_ver()[0] or platform.platform(), "free_memory_mb": free_mb}


# --- the real runtimes ---------------------------------------------------------------------------------------------

def _missing(module: str) -> str | None:
    import importlib.util

    return None if importlib.util.find_spec(module) else f"the {module} package is not in this Python"


@functools.cache
def _kraken_model() -> str | None:
    from fichero_server.llm import kraken_runtime as kr

    folder = kr.recognition_model_dir()
    for marker in sorted(folder.glob("*.installed")) if folder.is_dir() else []:
        if kr.recognition_model_path(marker.stem):
            return marker.stem
    return None


def _kraken_read_why() -> str | None:
    return _missing("kraken") or (None if _kraken_model() else "no Kraken reader is installed in the model store")


def _kraken_read(page: Path) -> object:
    from fichero_server.llm import kraken_runtime as kr

    return kr.recognize_lines(page, kr.recognition_model_path(_kraken_model() or ""))


def _kraken_segment(page: Path) -> object:
    from fichero_server.llm import kraken_runtime as kr

    return kr.segment_lines(page)


@functools.cache
def _mlx_model():
    from fichero_server.llm.mlx_model_store import MLXModelStore

    store = MLXModelStore()
    found = [e for e in store.list_catalog_entries() if e.installed and "vision" in list(e.capabilities)]
    return min(found, key=lambda e: e.download_size_bytes or 0) if found else None


def _mlx_why() -> str | None:
    return _missing("mlx_vlm") or (None if _mlx_model() else "no MLX vision model is installed in the model store")


@functools.cache
def _mlx_loaded() -> tuple[object, object]:
    """The vision model and its processor, loaded once per process, so the timed pages measure reads, not loads."""
    import mlx_vlm
    from fichero_server.llm.mlx_model_store import MLXModelStore

    return mlx_vlm.load(MLXModelStore().resolve_model_path(_mlx_model().model_id))


def _mlx_read(page: Path) -> object:
    """ponytail: calls mlx_vlm directly (the engine's read goes through its model server), so `loads` is not counted
    for this row."""
    import mlx_vlm

    model, processor = _mlx_loaded()
    return mlx_vlm.generate(model, processor, "Transcribe the text on this page.", image=[str(page)], max_tokens=200)


def _embed(_page: Path) -> object:
    from fichero_server.db import embeddings as emb
    from fichero_server.llm.local_models import MODELS_BASE

    space = emb._configured_embedding_space()
    emb._register_fastembed_model_for_space(space)
    with emb.leased_embedder(space.fastembed_model_name, str(MODELS_BASE / "embeddings")) as embedder:
        return embedder.embed([TEXT])


def _spacy(_page: Path) -> object:
    from fichero_server.knowledge import spacy_ner

    return spacy_ner.extract_entities(TEXT, "en")


def _yolo_why() -> str | None:
    from fichero_server.llm import yolo_runtime

    return _missing("ultralytics") or (None if yolo_runtime.is_installed(yolo_runtime.DEFAULT_MODEL)
                                       else "the layout model is not installed in the model store")


def _yolo(page: Path) -> object:
    from fichero_server.llm import yolo_runtime

    return yolo_runtime.detect_regions(page)


def _opencv(page: Path) -> object:
    from PIL import Image

    from fichero_server.media.enhance import denoise

    with Image.open(page) as image:
        return denoise.run(image, denoise.Params())


def _whisper_why() -> str | None:
    from fichero_server.llm import whisper_runtime

    return _missing("mlx_whisper") or (None if whisper_runtime.is_installed("base") and (FIXTURES / AUDIO).is_file()
                                       else "no Whisper model is installed in the model store")


def _whisper(audio: Path) -> object:
    from fichero_server.llm import whisper_runtime

    return whisper_runtime.transcribe_sync(str(audio))


def _apple_why() -> str | None:
    version = platform.mac_ver()[0]
    if not version or int(version.split(".")[0]) < 27:
        return "Apple Vision / Foundation Models need macOS 27 or later"
    return "the engine has no Python entry for Apple Vision or Foundation Models (the app's Swift bridge calls them)"


def real_runtimes() -> list[Runtime]:
    return [
        Runtime("kraken-segment", lambda: _missing("kraken"), _kraken_segment, "kraken segment"),
        Runtime("kraken-read", _kraken_read_why, _kraken_read, "kraken read"),
        Runtime("mlx-vision-read", _mlx_why, _mlx_read, None, "mlx_vlm direct, not the engine's server; loads not counted"),
        Runtime("embedder", lambda: _missing("fastembed"), _embed, "embedder"),
        Runtime("spacy-names", lambda: _missing("spacy"), _spacy, "spacy"),
        Runtime("yolo", _yolo_why, _yolo, "yolo"),
        Runtime("opencv-preprocess", lambda: _missing("cv2"), _opencv, None),
        Runtime("whisper", _whisper_why, _whisper, None, "one audio fixture per pass; loads not counted",
                inputs=lambda _pages: [FIXTURES / AUDIO]),
        Runtime("apple", _apple_why, lambda _p: None, None),
    ]


def install_load_counters() -> None:
    """Count model loads: the engine's `model_load` (kraken, spaCy, the embedder) and the YOLO constructor."""
    from contextlib import contextmanager

    from fichero_server.core import perf

    real = perf.model_load

    @contextmanager
    def counted(model: str):
        with real(model):
            yield
        LOADS[model] = LOADS.get(model, 0) + 1

    perf.model_load = counted
    try:
        import ultralytics

        constructor = ultralytics.YOLO

        def counting_yolo(*args, **kwargs):
            LOADS["yolo"] = LOADS.get("yolo", 0) + 1
            return constructor(*args, **kwargs)

        ultralytics.YOLO = counting_yolo
    except ImportError:
        pass


# --- remote: dry-run only ------------------------------------------------------------------------------------------

def remote_dry_run(where: str) -> dict[str, object]:
    """What the engine says about a remote place without submitting anything or paying."""
    row: dict[str, object] = {"runtime": f"remote:{where}", "note": "dry run only, nothing submitted"}
    try:
        if where == "hf-jobs":
            from fichero_server.recipes.discovery import remote_compute

            said = remote_compute(price=False)  # no network, no job
            return {**row, "status": "ok" if said["available"] else "unavailable",
                    "words": said["why"] or f"set up; flavor {said['flavor']}"}
        from fichero_server.workflows.remote_jobs import HpcClusterConfig, build_bundle_manifest, build_remote_run_spec

        cluster = HpcClusterConfig(cluster_id="matrix", name="matrix", host_alias="matrix-host", username="matrix",
                                   remote_base_dir="/scratch/matrix")
        manifest = build_bundle_manifest(workflow_id="matrix", workflow_name="matrix", input_files=list(SAMPLE),
                                         library_path="library", run_id="matrix")
        spec = build_remote_run_spec(cluster=cluster, manifest=manifest, input_indices=list(range(len(SAMPLE))))
        return {**row, "status": "ok", "words": f"job script built, not submitted ({spec.array_directive})"}
    except Exception as exc:  # noqa: BLE001
        return {**row, "status": "failed", **failure_of(exc)}


# --- running and printing ------------------------------------------------------------------------------------------

def run_matrix(runtimes: list[Runtime], pages: list[Path], *, isolate: bool, scratch: Path | None = None) -> list[dict]:
    rows = []
    for runtime in runtimes:
        if not isolate:
            row = measure(runtime, pages)
            row["peak_rss_mb"] = peak_rss_mb() if row["status"] != "unavailable" else None
            row["footprint_mb"] = footprint_mb() if row["status"] != "unavailable" else None
            rows.append(row)
            continue
        command = [WORKER_PYTHON or sys.executable, str(Path(__file__).resolve()), "--worker", runtime.name]
        try:
            done = subprocess.run(command, capture_output=True, text=True, timeout=WORKER_TIMEOUT_SECONDS, check=False)
            rows.append(json.loads(done.stdout.strip().splitlines()[-1]))
        except (subprocess.TimeoutExpired, IndexError, ValueError) as exc:
            rows.append({"runtime": runtime.name, "note": "", "status": "failed", "kind": "unexpected",
                         "words": f"the measuring process did not finish ({type(exc).__name__})", "peak_rss_mb": None})
    return rows


def table(report: dict) -> str:
    m = report["machine"]
    lines = [f"Mac: {m['chip']}, {m['ram_gb']} GB, macOS {m['macos']}, {m['free_memory_mb']} MB free at start", "",
             "| runtime | result | first page s | s/page | peak RSS MB | footprint MB | loads | words |",
             "|---|---|---|---|---|---|---|---|"]

    def cell(value: object) -> str:
        return "-" if value is None else str(value)

    for r in report["runtimes"]:
        loads = r.get("loads")
        flag = f"{loads} (unloads between pages)" if isinstance(loads, int) and loads > 1 else cell(loads)
        words = " ".join(str(w) for w in (r.get("kind"), r.get("words"), r.get("note")) if w)
        lines.append(f"| {r['runtime']} | {r['status']} | {cell(r.get('first_page_s'))} | {cell(r.get('per_page_s'))} "
                     f"| {cell(r.get('peak_rss_mb'))} | {cell(r.get('footprint_mb'))} | {flag} | {words.replace('|', '/')} |")
    return "\n".join(lines)


def build_report(runtimes: list[Runtime], pages: list[Path], *, isolate: bool, remote: str | None = None) -> dict:
    rows = run_matrix(runtimes, pages, isolate=isolate)
    if remote:
        rows.append(remote_dry_run(remote))
    return {"machine": machine(), "sample": [p.name for p in pages], "passes": PASSES, "runtimes": rows}


def scratch_environment(root: Path) -> None:
    """Point the engine at scratch state and a scratch library; keep reading the models this Mac already has."""
    sys.path.insert(0, str(REPO / "fichero-server" / "src"))
    from fichero_server.db.paths import default_server_state_dir

    os.environ.setdefault("FICHERO_MODEL_STORE_ROOT", str(default_server_state_dir()))
    os.environ["FICHERO_BASE_PATH"] = str(root / "state")
    # The embedder's model runs in a child process by default, which this process's peak RSS does not see.
    os.environ["FICHERO_EMBED_IN_PROCESS"] = "1"
    # fastembed downloads a model it lacks; that download was timed as the embedder's load (116 s, 2026-11-19). Offline,
    # a missing model is a failed row with the library's words, never a number.
    os.environ["HF_HUB_OFFLINE"] = "1"
    (root / "state").mkdir(parents=True, exist_ok=True)
    (root / "library").mkdir(parents=True, exist_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=Path("runtime-matrix.json"))
    parser.add_argument("--only", nargs="*", default=[], help="runtime names to measure (default: all)")
    parser.add_argument("--remote", choices=["hf-jobs", "cluster"], help="dry-run a remote place, never a job")
    parser.add_argument("--python", type=Path, help="run every runtime under this interpreter (the shipped engine's Python, "
                        "which has mlx_vlm, mlx_whisper and ultralytics); default: this one")
    parser.add_argument("--engine-app", type=Path, help="the built engine app: run every runtime under its "
                        "bundled Python with its app_packages, so YOLO, MLX VLM and Whisper run as shipped")
    parser.add_argument("--worker", help="internal: measure this one runtime and print its row as JSON")
    args = parser.parse_args(argv)
    global WORKER_PYTHON
    if args.engine_app:
        if args.python:
            parser.error("--engine-app and --python are two ways to name the interpreter: give one")
        python, packages = engine_app_python(args.engine_app)
        WORKER_PYTHON = str(python)
        os.environ["PYTHONPATH"] = os.pathsep.join(p for p in (str(packages), os.environ.get("PYTHONPATH")) if p)
    elif args.python:
        if not args.python.is_file():
            parser.error(f"--python {args.python}: no such interpreter")
        WORKER_PYTHON = str(args.python)
    with tempfile.TemporaryDirectory(prefix="runtime-matrix-") as tmp:
        scratch_environment(Path(tmp))
        install_load_counters()
        pages = sample_pages(Path(tmp) / "pages")
        runtimes = [r for r in real_runtimes() if not args.only or r.name in args.only]
        if args.worker:
            row = measure(next(r for r in runtimes if r.name == args.worker), pages)
            row["peak_rss_mb"] = peak_rss_mb() if row["status"] != "unavailable" else None
            row["footprint_mb"] = footprint_mb() if row["status"] != "unavailable" else None
            print(json.dumps(row))
            return 0
        report = build_report(runtimes, pages, isolate=True, remote=args.remote)
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(table(report))
    print(f"\nJSON: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
