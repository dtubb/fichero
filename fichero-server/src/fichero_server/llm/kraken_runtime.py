"""Kraken's neural line segmenter, as a geometry provider behind the OCR seam.

Kraken finds LINES — a polygon and a baseline per written line — and reads
nothing. That is the point. Apple Vision reads well and localises badly on
historical hands: measured 2026-09-04 on Caciques 533r (17th-century Spanish
secretary hand, ~30 lines), macOS 26's document request found 6 lines and
7 words while Kraken found 33 line polygons with baselines in 13.4s. On modern
cursive the two agree closely and Apple is faster, so this is not a better
engine; it is the engine that still works on the material an archive is made
of.

## #4959 (2026-09-20): Kraken ships INSIDE the engine bundle, not a runtime
## install, and runs IN-PROCESS, not a child process

There used to be a separate venv, built and pip-installed the first time
someone asked for it. Two things killed that design:

* Building it with `venv.EnvBuilder` copied or symlinked `sys.executable` —
  inside the sandboxed app that IS the signed `Fichero Server` stub, and the
  sandbox refuses the copy outright (`[Errno 1] Operation not permitted`).
* Even a venv that avoided that would fail one step later: a sandboxed app's
  own write is quarantined, and macOS refuses to `dlopen` a quarantined
  native library. Kraken's missing dependencies (scikit-image, shapely,
  coremltools, lxml) are native code. `fichero-server/pyproject.toml`
  already records this exact lesson for `libpdfium.dylib`.
* It is also forbidden outright on the Mac App Store tier (Guideline 2.5.2:
  no downloading/installing/executing code that changes the app's
  functionality — model WEIGHTS are data and are fine; Kraken's own code is
  not).

So Kraken is installed at BUILD time — `scripts/install_kraken_into_engine_
bundle.py`, called from `scripts/release-all.sh` after the engine bundle
stages and before signing, reading its pinned version and missing-package
list from `pyproject.toml`'s `[tool.fichero.kraken_bundle]` table (ONE place)
— and ships signed and notarized with the app, same as torch (already in the
bundle via pykeen). `is_installed()` now means exactly "is `kraken`
importable" — there is nothing left to provision.

A SECOND design also fell, one ruling later: routing every call through a
`kraken_worker.py` child process, spawned by re-executing the app's own
signed stub via `FICHERO_RUN_MODULE`. Proven broken (2026-09-20, live test)
before it shipped: that re-exec is a subprocess of the ALREADY
sandboxed-inherit-child engine process — the exact shape `_libsecinit_
appsandbox` hangs on (#4555, `kreuzberg_cache.py::_fork_worker`'s docstring:
a second-level `com.apple.security.inherit` grandchild can never establish
its own sandbox). `fork()` was considered and rejected too: this engine
process already has torch loaded (via pykeen), and forking that and then
importing lightning/torch again in the child is the textbook unsafe case.

So Kraken runs IN-PROCESS, through the ONE seam below (`_kraken_call`) — the
old isolation bought nothing once torch was already loaded in this same
process anyway. Two rules this module still keeps:

* Its output speaks the existing ``OCRGeometryResult`` vocabulary — normalized
  top-left boxes, a named pixel frame, a carried ``rendition_id`` — so nothing
  downstream can tell a Kraken box from an Apple one.
* `import kraken` (and `htrmopo`) happens LAZILY, only inside `_kraken_call`'s
  own callees — never at module import — so importing this module never pays
  the cost and never requires Kraken to be installed (engine start-up time,
  and the packaging import test, are unaffected).
"""

from __future__ import annotations

import ctypes
import ctypes.util
import importlib.metadata
import importlib.util
import json
import logging
import os
import threading
from pathlib import Path
from typing import Callable, TypeVar

from fichero_server.core.background_compute import embed_threads, set_utility_qos
from fichero_server.db.paths import server_state_dir
from fichero_server.media.ocr_geometry import (
    OCRGeometryBox,
    OCRGeometryLevel,
    OCRGeometryResult,
    OCRGeometryStatus,
    geometry_unavailable,
)

logger = logging.getLogger(__name__)

_T = TypeVar("_T")

#: Kraken's pinned version and its missing-package list live in
#: `pyproject.toml`'s `[tool.fichero.kraken_bundle]` table -- the build step
#: and the packaging test read that table directly. This module deliberately
#: does NOT duplicate it: `runtime_status()` below reports whatever is
#: ACTUALLY importable (`importlib.metadata`), so a status report can never
#: drift from what really shipped in a given build.

_PROVIDER = "kraken"
_MODEL = "blla"

# =============================================================================
# Kraken model catalog (#4671 follow-up — Daniel's "No models found")
# =============================================================================
#
# Two kinds of Kraken model:
#
# * SEGMENTATION — finding the lines. `blla` is Kraken's built-in neural
#   segmenter and ships INSIDE the package, so it needs no separate download;
#   it is "installed" exactly when Kraken itself is importable. This is what
#   Fichero's OCR-geometry seam uses today.
#
# * RECOGNITION (HTR/OCR) — reading the lines. These are separate `.mlmodel`
#   files retrieved by DOI with `kraken get <DOI>` (stored under
#   ~/.local/share/htrmopo). A short HARDCODED shortlist of known-good general
#   Latin-script models, measured from Zenodo. Fichero does not yet run a
#   Kraken recognition pass — this makes the models installable so the picker
#   is populated and the pieces are in place.
#
# CURATION IS PROVISIONAL: these are sensible general Latin-script options, NOT
# a considered pick for Daniel's Spanish 1870-1930 court hand. He knows the
# paleography; the shortlist is flagged for his call and this table is the one
# place to edit it.
KRAKEN_RECOGNITION_MODELS: dict[str, dict[str, object]] = {
    "kraken-mccatmus": {
        "doi": "10.5281/zenodo.13788177",
        "display_name": "McCATMuS (multi-script HTR)",
        "size_bytes": 16_173_802,
        "note": "General transcription of handwritten, printed and typewritten "
                "documents, 16th-21st century, multi-script. A broad Latin-script "
                "starting point; not tuned for any one hand.",
    },
    "kraken-catmus-medieval": {
        "doi": "10.5281/zenodo.12743230",
        "display_name": "CATMuS Medieval",
        "size_bytes": 16_332_989,
        "note": "Medieval manuscripts (Old/Middle French, Latin, Spanish). "
                "Older hands than a 19th-20th century court record — offered as "
                "a general Latin-script option, not a court-hand pick.",
    },
}

_MODEL_DATA_DIRNAME = "kraken-models"


def _kraken_data_dir(home: Path | None = None) -> Path:
    """Where HTR model downloads and their markers live -- DATA, unlike the
    old `kraken-runtime`: this directory holds nothing that needs to be
    signed or notarized, so it stays an ordinary app-state directory."""
    override = os.environ.get("FICHERO_KRAKEN_DATA_DIR")
    if override:
        return Path(override).expanduser()
    return server_state_dir(home) / _MODEL_DATA_DIRNAME


def recognition_model_dir(home: Path | None = None) -> Path:
    """Where completed recognition-model installs are recorded (our markers)."""
    return _kraken_data_dir(home) / "recognition"


def recognition_data_home(home: Path | None = None) -> Path:
    """XDG_DATA_HOME we point `kraken get` at, so the .mlmodel lands in OUR tree.

    `kraken get` writes to ``$XDG_DATA_HOME/htrmopo/<uuid>/`` with an opaque
    UUID dir. Rather than reverse-map DOI→uuid, we make that base a directory we
    own, then scan it for the fetched ``.mlmodel`` — a deterministic path under
    the app's control instead of the user's global ``~/.local/share``.
    """
    return _kraken_data_dir(home) / "htr-data"


def _marker_path(model_id: str, home: Path | None = None) -> Path:
    return recognition_model_dir(home) / f"{model_id}.installed"


def is_recognition_model_installed(model_id: str, home: Path | None = None) -> bool:
    """Whether a recognition model has been fetched (our marker is the signal)."""
    return _marker_path(model_id, home).exists()


def recognition_model_path(model_id: str, home: Path | None = None) -> str | None:
    """Filesystem path to a downloaded recognition ``.mlmodel``, or None.

    Reads the path recorded at download time. None means "not downloaded (or the
    fetch could not be located)" — the caller must say so rather than run
    kraken against a path that is not there.
    """
    marker = _marker_path(model_id, home)
    if not marker.exists():
        return None
    try:
        data = json.loads(marker.read_text(encoding="utf-8"))
    except Exception:
        return None
    path = data.get("model_path")
    return str(path) if path else None


def resolve_recognition_model(model_ref: str) -> tuple[str, str | None]:
    """(filesystem path, catalog id) for a recognition-model reference.

    A catalog id ("kraken-mccatmus") resolves to the app's downloaded copy; a
    literal ``.mlmodel`` path is used as-is. Raises a clear, actionable error
    when a catalog model is not installed or a path is missing — never returns a
    path that is not there (the caller must say "install it", not run against
    nothing). One source of truth for both the workflow seam and any node.
    """
    if model_ref in KRAKEN_RECOGNITION_MODELS:
        resolved = recognition_model_path(model_ref)
        if not resolved:
            raise RuntimeError(
                f"Kraken recognition model '{model_ref}' is not downloaded — "
                "install it from Settings -> AI -> Local Inference (the on-device "
                "model catalog)."
            )
        return resolved, model_ref
    if not model_ref:
        raise RuntimeError(
            "Kraken recognition needs a model — a catalog id (e.g. "
            "'kraken-mccatmus') or a path to a .mlmodel."
        )
    if not Path(model_ref).exists():
        raise RuntimeError(f"Kraken recognition model not found: {model_ref}")
    return model_ref, None


def remove_recognition_model(model_id: str, home: Path | None = None) -> None:
    """Forget a recognition model (drops our marker; htrmopo cache is kraken's)."""
    marker = _marker_path(model_id, home)
    if marker.exists():
        marker.unlink()


class KrakenRuntimeMissingError(RuntimeError):
    """Raised when Kraken segmentation is asked of a build without Kraken.

    Should be unreachable in a real release (Kraken is bundled, always
    importable) — this is a genuine "something is wrong with this build"
    signal, not a "go install it" prompt any more.
    """


class KrakenSegmentationError(RuntimeError):
    """Raised when the segmenter ran and did not return usable geometry."""


class KrakenMemoryUnavailableError(RuntimeError):
    """Raised when the machine cannot safely run Kraken right now (#4987).

    "Know before running": Kraken shares this process with the rest of the
    engine (#4959), so its peak memory IS the engine's peak memory, and it
    is measured (`agent-work/reviews/kraken-memory-4987.md`, 2026-09-20, M1
    16 GB) to settle into a 2.3-3.6 GB peak band per page and NOT give that
    memory back afterward. A message a non-programmer can act on: what
    Kraken needs, what is free right now, and that closing other apps or
    waiting will help.
    """


# #4987: the declared need: ONE named constant, measured, not guessed.
# Measured 2026-09-20 on an M1 MacBook Pro (16 GB): a page peaks at 2.3 to
# 3.6 GB resident once warm (agent-work/reviews/kraken-memory-4987.md). The
# floor is what the machine must have AVAILABLE, which is not the same number:
# in that same measurement every run SUCCEEDED with 3.3 to 5.5 GB available
# (rows C, E and I ran at 3.3 to 3.9 GB), because macOS compresses and pages
# other work while memory pressure is normal. A 4 GB floor would have refused
# runs the measurement itself completed, and on a 16 GB laptop in ordinary use
# would refuse most of the time. So: pressure must be NORMAL (the real safety
# signal) and at least 2.5 GB must be available (the report's own minimum).
# Override with the environment variable for a machine where this is wrong.
_DEFAULT_KRAKEN_MEMORY_NEED_BYTES = int(2.5 * 1024**3)
_MEMORY_NEED_ENV_VAR = "FICHERO_KRAKEN_MEMORY_NEED_MB"

# kern.memorystatus_vm_pressure_level values (Apple's dispatch_source
# memorypressure levels; verified live via `sysctl kern.memorystatus_vm_
# pressure_level` and the matching ctypes read, 2026-09-20).
_PRESSURE_NORMAL = 1
_PRESSURE_LABELS = {2: "warn", 4: "critical"}

# Mach `host_statistics64` — the public struct layout from Apple's
# <mach/vm_statistics.h>, reproduced here only because ctypes needs a field
# layout to read into; no subprocess, no new dependency.
_HOST_VM_INFO64 = 4


class _VMStatistics64(ctypes.Structure):
    _fields_ = [
        ("free_count", ctypes.c_uint32),
        ("active_count", ctypes.c_uint32),
        ("inactive_count", ctypes.c_uint32),
        ("wire_count", ctypes.c_uint32),
        ("zero_fill_count", ctypes.c_uint64),
        ("reactivations", ctypes.c_uint64),
        ("pageins", ctypes.c_uint64),
        ("pageouts", ctypes.c_uint64),
        ("faults", ctypes.c_uint64),
        ("cow_faults", ctypes.c_uint64),
        ("lookups", ctypes.c_uint64),
        ("hits", ctypes.c_uint64),
        ("purges", ctypes.c_uint64),
        ("purgeable_count", ctypes.c_uint32),
        ("speculative_count", ctypes.c_uint32),
        ("decompressions", ctypes.c_uint64),
        ("compressions", ctypes.c_uint64),
        ("swapins", ctypes.c_uint64),
        ("swapouts", ctypes.c_uint64),
        ("compressor_page_count", ctypes.c_uint32),
        ("throttled_count", ctypes.c_uint32),
        ("external_page_count", ctypes.c_uint32),
        ("internal_page_count", ctypes.c_uint32),
        ("total_uncompressed_pages_in_compressor", ctypes.c_uint64),
    ]


_HOST_VM_INFO64_COUNT = ctypes.sizeof(_VMStatistics64) // ctypes.sizeof(ctypes.c_int)


def _kraken_memory_need_bytes() -> int:
    """The declared need, overridable per-machine via env var (MB)."""
    override = os.environ.get(_MEMORY_NEED_ENV_VAR)
    if override:
        try:
            return int(float(override) * 1024 * 1024)
        except ValueError:
            logger.warning(
                "%s=%r is not a number; using the default", _MEMORY_NEED_ENV_VAR, override
            )
    return _DEFAULT_KRAKEN_MEMORY_NEED_BYTES


def _available_memory_bytes() -> int | None:
    """Best-effort free memory on macOS — no new dependency.

    #4987 follow-up: `psutil` is NOT in the shipped bundle's dependency
    closure. Checked directly (`pip show psutil` against the dev venv,
    2026-09-20): its only `Required-by` are `briefcase` (the BUILD tool,
    never bundled) and `flufl.lock` (itself unused anywhere in this
    project's own source) — no runtime package this engine ships pulls it
    in. Using it here would make this exact guard raise
    `ModuleNotFoundError` in the one build it exists to protect.

    In-process only — NO subprocess (`vm_stat` was tried and rejected: this
    module has its own hard, tested rule against ever shelling out or
    provisioning a runtime, `test_kraken_runtime_never_shells_out_or_
    provisions_a_runtime`, for the same sandboxing reasons #4555 already
    forced this module in-process in the first place). Calls the public
    Mach host API directly via ctypes — `host_statistics64`, the same
    mechanism `psutil` itself uses on macOS, and the same
    `ctypes.CDLL(ctypes.util.find_library("System"))` technique this
    project's own `kraken_timing.py` measurement script already uses for
    QoS. Cross-checked live against `psutil.virtual_memory().available`,
    2026-09-20: within ~1.3% (`(free + inactive + speculative) pages`,
    reading slightly LOW — the safer direction for a refuse-below-threshold
    guard).

    Sysctl names alone (`vm.page_free_count` etc., no `host_statistics64`)
    were tried first and rejected: macOS keeps almost nothing in `free` and
    parks most reclaimable memory in `inactive`, which has no equivalent
    sysctl — a free+speculative-only reading came in at ~117 MB against
    psutil's ~3.7 GB on the same machine at the same moment, ~97% low —
    unusably conservative, not just "safer".

    Returns ``None`` on any failure (non-macOS, the Mach call itself
    failing) — callers must decide what "unknown" means; this never
    guesses a number.
    """
    try:
        libsystem = ctypes.CDLL(ctypes.util.find_library("System"))
    except OSError:
        return None
    try:
        host_port = libsystem.mach_host_self()
        page_size = ctypes.c_uint64(0)
        if libsystem.host_page_size(host_port, ctypes.byref(page_size)) != 0:
            return None
        vm_stat = _VMStatistics64()
        count = ctypes.c_uint32(_HOST_VM_INFO64_COUNT)
        kr = libsystem.host_statistics64(
            host_port, _HOST_VM_INFO64, ctypes.byref(vm_stat), ctypes.byref(count)
        )
        if kr != 0:
            return None
    except Exception:  # noqa: BLE001 — a platform surprise here must degrade, not crash
        return None
    free_pages = vm_stat.free_count + vm_stat.inactive_count + vm_stat.speculative_count
    return free_pages * page_size.value


def _memory_pressure_level() -> int | None:
    """macOS ``kern.memorystatus_vm_pressure_level`` via one sysctl read
    (no subprocess — a single syscall through ctypes, not "shelling out on
    every call", per #4987). 1=normal, 2=warn, 4=critical. ``None`` if
    unavailable (non-macOS, or the sysctl name doesn't resolve)."""
    try:
        libc = ctypes.CDLL("libc.dylib")
    except OSError:
        return None
    value = ctypes.c_int(0)
    size = ctypes.c_size_t(ctypes.sizeof(value))
    try:
        ret = libc.sysctlbyname(
            b"kern.memorystatus_vm_pressure_level",
            ctypes.byref(value),
            ctypes.byref(size),
            None,
            0,
        )
    except Exception:  # noqa: BLE001 — a missing/renamed sysctl must degrade, not crash
        return None
    return value.value if ret == 0 else None


def assert_memory_available_for_kraken(
    *,
    available_bytes: Callable[[], int | None] | None = None,
    pressure_level: Callable[[], int | None] | None = None,
) -> None:
    """Refuse BEFORE any kraken/torch import if this machine cannot safely
    run one Kraken call right now (#4987).

    Checked on EVERY call, not once at startup: the measurement showed
    Kraken's elevated memory floor is NOT released between calls within a
    session, so a machine that had room for the first page may not have
    room for the fifth.

    ``available_bytes``/``pressure_level`` are injectable so a test never
    depends on the real machine's memory or pressure — pass a lambda
    returning a fixed number instead of the real macOS reader.
    """
    get_available = available_bytes or _available_memory_bytes
    get_pressure = pressure_level or _memory_pressure_level

    need = _kraken_memory_need_bytes()
    free = get_available()
    if free is not None and free < need:
        raise KrakenMemoryUnavailableError(
            f"Kraken needs about {need / 1024**3:.1f} GB of free memory to run "
            f"safely, and this Mac has about {free / 1024**3:.1f} GB free right "
            "now. Close other apps, or wait for other work to finish, then try "
            "again."
        )

    level = get_pressure()
    if level is not None and level != _PRESSURE_NORMAL:
        label = _PRESSURE_LABELS.get(level, f"level {level}")
        raise KrakenMemoryUnavailableError(
            f"This Mac's memory pressure is {label}, not normal, so starting "
            f"Kraken now (it needs about {need / 1024**3:.1f} GB) risks the "
            "whole app crashing. Close other apps, or wait, then try again."
        )


def is_installed() -> bool:
    """Whether Kraken can actually segment: is it importable at all.

    #4959: there is nothing left to "install" at runtime -- Kraken ships in
    the bundle or it does not. `find_spec` (not a real import) so checking
    status never pays torch/lightning's import cost.
    """
    return importlib.util.find_spec("kraken") is not None


def runtime_status() -> dict[str, object]:
    installed = is_installed()
    version: str | None = None
    if installed:
        try:
            version = importlib.metadata.version("kraken")
        except importlib.metadata.PackageNotFoundError:
            version = None
    return {
        "installed": installed,
        "kraken_version": version,
        "reason": None
        if installed
        else (
            "Kraken is not bundled in this build — this is a packaging problem, "
            "not something to install from Settings."
        ),
    }


def require_installed() -> None:
    if not is_installed():
        raise KrakenRuntimeMissingError(str(runtime_status()["reason"]))


# =============================================================================
# THE SEAM (#4959) — every actual Kraken call passes through here, and only
# here. See the module docstring for why in-process, not a subprocess.
# =============================================================================

_INFERENCE_LOCK = threading.Lock()


def _kraken_call(op: Callable[[], _T]) -> _T:
    """Run one Kraken operation in-process, one at a time, off the main
    thread (callers already dispatch through `asyncio.to_thread`, same as
    every other CPU-bound provider in this engine — see `vision_base.py`).

    ponytail: this exists — kraken (with the torch/lightning/coremltools it
    drags in) shares this process with the rest of the engine now, guarded
    by ONE lock so two pages can never double the memory. If a crash or a
    memory blow-up ever shows up here, move `op()` into a worker process;
    this is the one place to change it.
    """
    require_installed()
    outcome: list[object] = []

    def _throttled() -> None:
        try:
            # #4987 "know before running": checked INSIDE the lock, before
            # ANY kraken/torch import — a queued second call must see the
            # machine's state at the moment IT is about to run, not the
            # (possibly much rosier) state when it was first queued, since
            # measured Kraken memory is not released between calls within
            # a session. A refusal here costs nothing: no import has
            # happened yet.
            assert_memory_available_for_kraken()

            # The throttle is set on a thread this seam OWNS and that ends with
            # the call. Callers arrive on `asyncio.to_thread`'s POOLED workers;
            # a QoS class set on one of those would outlive this call and slow
            # whatever unrelated request that worker serves next.
            # UTILITY, not background: someone is waiting for this page.
            # Measured: 23 s at utility against 426 s at background for one
            # page (#4959).
            set_utility_qos()
            try:
                import torch

                # Same balanced-throttle knob the embedder uses
                # (`embed_threads`, `FICHERO_EMBED_THREADS`-overridable); no
                # second preference. Process-wide in torch, which is the
                # point: never peg the machine.
                torch.set_num_threads(max(1, embed_threads()))
            except (ImportError, RuntimeError):
                # Narrow on purpose: a throttle that crashes the work is
                # worse than an unthrottled page, but nothing else may be
                # hidden here.
                logger.warning("could not cap torch threads for kraken", exc_info=True)
            outcome.append((True, op()))
        except BaseException as exc:  # noqa: BLE001 — re-raised on the caller's thread
            outcome.append((False, exc))

    with _INFERENCE_LOCK:
        worker = threading.Thread(target=_throttled, name="kraken-inference", daemon=True)
        worker.start()
        worker.join()
    ok, value = outcome[0]  # type: ignore[misc]
    if not ok:
        raise value  # type: ignore[misc]
    return value  # type: ignore[return-value]


def _raw_lines(segmentation: object) -> list[dict[str, object]]:
    raw = getattr(segmentation, "lines", None)
    if raw is None and isinstance(segmentation, dict):
        raw = segmentation.get("lines", [])
    out: list[dict[str, object]] = []
    for line in raw or []:
        if isinstance(line, dict):
            baseline, boundary = line.get("baseline"), line.get("boundary")
        else:
            baseline = getattr(line, "baseline", None)
            boundary = getattr(line, "boundary", None)
        out.append(
            {
                "baseline": [[float(x), float(y)] for x, y in (baseline or [])],
                "polygon": [[float(x), float(y)] for x, y in (boundary or [])],
            }
        )
    return out


def _segment_raw(image_path: str | Path) -> dict[str, object]:
    from PIL import Image
    from kraken import blla

    with Image.open(image_path) as image:
        if image.mode != "RGB":
            image = image.convert("RGB")
        segmentation = blla.segment(image)
        width, height = image.width, image.height
    return {"width": width, "height": height, "lines": _raw_lines(segmentation)}


def _recognize_raw(image_path: str | Path, model_path: str) -> dict[str, object]:
    from PIL import Image
    from kraken import blla, rpred
    from kraken.lib import models

    with Image.open(image_path) as image:
        if image.mode != "RGB":
            image = image.convert("RGB")
        segmentation = blla.segment(image)
        net = models.load_any(model_path)
        # blla's neural baseline segmentation gives us the lines; rpred reads
        # each one with the recognition model, in the SAME order -- so
        # prediction i belongs to segmented line i, and every line keeps its
        # own baseline/polygon geometry.
        predictions = list(rpred.rpred(net, image, segmentation))
        width, height = image.width, image.height
    lines = _raw_lines(segmentation)
    for index, line in enumerate(lines):
        record = predictions[index] if index < len(predictions) else None
        line["text"] = "" if record is None else str(getattr(record, "prediction", record) or "")
    return {"width": width, "height": height, "lines": lines}


def segment_lines(
    image_path: str | Path, *, run_call: Callable[[Callable[[], _T]], _T] | None = None
) -> dict[str, object]:
    """Run the segmenter and return raw pixel geometry plus its frame."""
    caller = run_call or _kraken_call
    try:
        return caller(lambda: _segment_raw(image_path))
    except (KrakenRuntimeMissingError, KrakenMemoryUnavailableError):
        # Both are already the plain-language, non-programmer-actionable
        # message #4987/#4959 want on screen — wrapping either as "Kraken
        # segmentation failed: ..." would bury that message inside a less
        # useful one, so both pass through the SAME way.
        raise
    except Exception as exc:
        raise KrakenSegmentationError(f"Kraken segmentation failed: {exc}") from exc


def recognize_lines(
    image_path: str | Path,
    model_path: str,
    *,
    run_call: Callable[[Callable[[], _T]], _T] | None = None,
) -> dict[str, object]:
    """Segment + RECOGNISE one image; raw per-line text plus pixel geometry."""
    caller = run_call or _kraken_call
    try:
        return caller(lambda: _recognize_raw(image_path, model_path))
    except (KrakenRuntimeMissingError, KrakenMemoryUnavailableError):
        raise
    except Exception as exc:
        raise KrakenSegmentationError(f"Kraken recognition failed: {exc}") from exc


def download_recognition_model(
    model_id: str,
    home: Path | None = None,
    *,
    run_call: Callable[[Callable[[], object]], object] | None = None,
) -> None:
    """Fetch a recognition model and record its path. Raises rather than
    half-succeeding: a fetch that quietly does nothing is the shape a user
    reads as success.

    In-process, via htrmopo's own library API (`get_model`) — NOT the
    `kraken get` CLI (there is no CLI process to shell out to; see the
    module docstring). `get_model(doi, path=...)` writes into the given
    directory itself (no XDG_DATA_HOME juggling needed) and returns that
    same directory; we then find the newest `.mlmodel` under it exactly as
    the old CLI-driven path did, since the exact filename is htrmopo's own
    choice, not documented as stable.
    """
    spec = KRAKEN_RECOGNITION_MODELS.get(model_id)
    if spec is None:
        raise ValueError(f"Unknown Kraken recognition model: {model_id}")
    data_home = recognition_data_home(home)
    data_home.mkdir(parents=True, exist_ok=True)

    def _fetch() -> object:
        from htrmopo import get_model

        return get_model(str(spec["doi"]), path=str(data_home))

    caller = run_call or _kraken_call
    caller(_fetch)

    models = sorted(
        data_home.rglob("*.mlmodel"), key=lambda p: p.stat().st_mtime, reverse=True,
    )
    model_path = str(models[0]) if models else None
    if not model_path:
        raise RuntimeError(f"model fetch produced no .mlmodel for {model_id} (DOI {spec['doi']})")
    marker_dir = recognition_model_dir(home)
    marker_dir.mkdir(parents=True, exist_ok=True)
    _marker_path(model_id, home).write_text(
        json.dumps({"doi": str(spec["doi"]), "model_path": model_path}),
        encoding="utf-8",
    )


def segment_to_geometry(
    image_path: str | Path,
    *,
    rendition_id: str | None = None,
) -> OCRGeometryResult:
    """Segment one image into the shared OCR geometry vocabulary.

    ``rendition_id`` names WHICH PICTURE these boxes were measured on. Kraken
    works in absolute pixels of the exact file it was handed, so a result whose
    frame is not named is a result nobody can place on a page that has more
    than one rendition (the bbox program's root cause). It is carried through
    unchanged, never inferred.

    A build without Kraken raises rather than returning an empty result:
    "no lines found" and "not bundled" are different facts, and only one
    of them is about the page.
    """
    payload = segment_lines(image_path)
    width = float(payload.get("width") or 0)
    height = float(payload.get("height") or 0)
    if width <= 0 or height <= 0:
        raise KrakenSegmentationError(
            f"Kraken reported an unusable pixel frame for {image_path}"
        )

    boxes: list[OCRGeometryBox] = []
    for index, line in enumerate(payload.get("lines") or []):
        polygon = [(float(x), float(y)) for x, y in line.get("polygon") or []]
        if len(polygon) < 3:
            continue
        xs = [point[0] for point in polygon]
        ys = [point[1] for point in polygon]
        x0, x1 = max(0.0, min(xs)), min(width, max(xs))
        y0, y1 = max(0.0, min(ys)), min(height, max(ys))
        if x1 <= x0 or y1 <= y0:
            continue
        boxes.append(
            OCRGeometryBox(
                # Kraken reads nothing, so there is no text to attach. An empty
                # string is the truthful value; inventing a placeholder would
                # put words on the page that nobody wrote.
                text="",
                bbox=[x0 / width, y0 / height, (x1 - x0) / width, (y1 - y0) / height],
                level=OCRGeometryLevel.LINE,
                provider=_PROVIDER,
                model=_MODEL,
                source="kraken-blla",
                metadata={
                    "line_index": index,
                    # The polygon and baseline are what Kraken uniquely offers —
                    # neither Apple arm produces a baseline at any setting — so
                    # they are kept in the page's own pixels alongside the
                    # normalized box the shared contract requires.
                    "polygon_px": [[x, y] for x, y in polygon],
                    "baseline_px": [
                        [float(x), float(y)] for x, y in line.get("baseline") or []
                    ],
                    "pixel_frame": {"width": width, "height": height},
                },
            )
        )

    if not boxes:
        return geometry_unavailable(
            status=OCRGeometryStatus.PRODUCED_NOTHING,
            provider=_PROVIDER,
            model=_MODEL,
            reason="Kraken segmented this image and found no text lines.",
            source="kraken-blla",
        )

    return OCRGeometryResult(
        text="",
        provider=_PROVIDER,
        model=_MODEL,
        boxes=boxes,
        source="kraken-blla",
        rendition_id=rendition_id,
        metadata={"pixel_frame": {"width": width, "height": height}},
    )


def recognize_to_geometry(
    image_path: str | Path,
    model_path: str,
    *,
    model_id: str | None = None,
    rendition_id: str | None = None,
) -> OCRGeometryResult:
    """Segment + recognise one image into the shared OCR geometry vocabulary.

    The result is a full transcript (``result.text`` = the lines joined by
    newlines) whose every line is TIED to the baseline it was read from: each
    box carries the recognised ``text`` plus its ``polygon_px``/``baseline_px``
    in page pixels, and ``char_start``/``char_end`` index that line's slice of
    ``result.text`` — so the reader can anchor text to the page and the pairs
    are ground-truth for HTR training. Pure on-device Kraken, no LLM.

    ``model_id`` is the catalog id to stamp on the boxes (e.g. "kraken-mccatmus")
    when ``model_path`` is a resolved filesystem path; falls back to the path.
    """
    payload = recognize_lines(image_path, model_path)
    width = float(payload.get("width") or 0)
    height = float(payload.get("height") or 0)
    if width <= 0 or height <= 0:
        raise KrakenSegmentationError(
            f"Kraken reported an unusable pixel frame for {image_path}"
        )

    stamped_model = model_id or str(model_path)
    boxes: list[OCRGeometryBox] = []
    texts: list[str] = []
    cursor = 0
    for index, line in enumerate(payload.get("lines") or []):
        polygon = [(float(x), float(y)) for x, y in line.get("polygon") or []]
        if len(polygon) < 3:
            continue
        xs = [point[0] for point in polygon]
        ys = [point[1] for point in polygon]
        x0, x1 = max(0.0, min(xs)), min(width, max(xs))
        y0, y1 = max(0.0, min(ys)), min(height, max(ys))
        if x1 <= x0 or y1 <= y0:
            continue
        text = str(line.get("text") or "")
        # char_start/char_end index the line's slice of the joined transcript.
        # Assigned as we build (a running cursor + 1 per newline) so the mapping
        # is EXACT even when two lines read identically — a search would tie
        # both to the first occurrence.
        char_start = cursor
        char_end = cursor + len(text)
        cursor = char_end + 1  # + the "\n" that will join this line to the next
        texts.append(text)
        boxes.append(
            OCRGeometryBox(
                text=text,
                bbox=[x0 / width, y0 / height, (x1 - x0) / width, (y1 - y0) / height],
                level=OCRGeometryLevel.LINE,
                provider=_PROVIDER,
                model=stamped_model,
                source="kraken-htr",
                char_start=char_start,
                char_end=char_end,
                metadata={
                    "line_index": index,
                    "polygon_px": [[x, y] for x, y in polygon],
                    "baseline_px": [
                        [float(x), float(y)] for x, y in line.get("baseline") or []
                    ],
                    "pixel_frame": {"width": width, "height": height},
                },
            )
        )

    if not boxes:
        return geometry_unavailable(
            status=OCRGeometryStatus.PRODUCED_NOTHING,
            provider=_PROVIDER,
            model=stamped_model,
            reason="Kraken recognised this image and found no text lines.",
            source="kraken-htr",
        )

    return OCRGeometryResult(
        text="\n".join(texts),
        provider=_PROVIDER,
        model=stamped_model,
        boxes=boxes,
        source="kraken-htr",
        rendition_id=rendition_id,
        metadata={"pixel_frame": {"width": width, "height": height}},
    )


__all__ = [
    "KRAKEN_RECOGNITION_MODELS",
    "download_recognition_model",
    "is_installed",
    "is_recognition_model_installed",
    "recognition_data_home",
    "recognition_model_dir",
    "recognition_model_path",
    "resolve_recognition_model",
    "remove_recognition_model",
    "require_installed",
    "KrakenRuntimeMissingError",
    "KrakenSegmentationError",
    "KrakenMemoryUnavailableError",
    "assert_memory_available_for_kraken",
    "recognize_lines",
    "recognize_to_geometry",
    "runtime_status",
    "segment_lines",
    "segment_to_geometry",
]
