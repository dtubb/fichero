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
import re
import ctypes.util
import importlib.metadata
import importlib.util
import json
import logging
import os
import sys
import threading
from pathlib import Path
from typing import Any, Callable, TypeVar

from fichero_server.db.paths import model_store_root
from fichero_server.execution.throttle import MemoryShortError
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
    return model_store_root(home) / _MODEL_DATA_DIRNAME


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


def _global_marker_path(model_id: str, home: Path | None = None) -> Path:
    return recognition_model_dir(home) / f"{model_id}.installed"


def _marker_path(model_id: str, home: Path | None = None) -> Path:
    """A reader's record: the global store's marker, else, for a reader Fichero trained, its record
    inside an open project (#5539; `training.project_models`), else the global path (not there)."""
    marker = _global_marker_path(model_id, home)
    if not marker.exists() and model_id.startswith(TRAINED_READER_PREFIX):
        from fichero_server.training.project_models import find_kraken_record

        return find_kraken_record(model_id) or marker
    return marker


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
    # A record inside a project names its file relative to itself, so a moved project still finds it.
    return str(marker.parent / path) if path else None


def recognition_model_bytes(model_id: str, home: Path | None = None) -> int:
    """The size on disk of an installed reader's model file (a folder's files summed); 0 when it is not there
    (#5617: a downloaded reader's size is its file's when its record does not state one)."""
    path = recognition_model_path(model_id, home)
    if not path:
        return 0
    p = Path(path)
    try:
        if p.is_dir():
            return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
        return p.stat().st_size if p.is_file() else 0
    except OSError:
        return 0


#: A Kraken reader named by its record in Kraken's model repository (HTRMoPo, on Zenodo), not only
#: the catalogue's short list: `kraken-zenodo-<record number>` (#5388 follow-up, 2026-10-03).
_ZENODO_READER = re.compile(r"^kraken-zenodo-(\d+)$")


def repository_listing() -> dict[str, dict[str, object]]:
    """Kraken's model repository as `kraken list` reads it: htrmopo's listing of Zenodo's `ocr_models`
    community, {doi: {"v0"|"v1": record}} (#5519, `recipes.discovery`). Network: many requests on a
    first call (htrmopo caches what it read); call only when the person asked and egress allows it."""
    from htrmopo import get_listing

    return get_listing()


def reader_id_for_doi(doi: str) -> str:
    """The model id under which a repository reader's DOI is downloaded and run."""
    return f"kraken-zenodo-{str(doi).rsplit('.', 1)[-1]}"


#: A reader Fichero trained (`compute.tune.model-comes-back-as-a-card`, #5398): `kraken-trained-<job>`.
#: It is never downloaded; it lands from its training job with a card naming where it came from.
TRAINED_READER_PREFIX = "kraken-trained-"


def trained_reader_card(model_id: str | None, home: Path | None = None) -> dict[str, object] | None:
    """The card a landed trained reader carries (its provenance), or None."""
    if not (model_id or "").startswith(TRAINED_READER_PREFIX):
        return None
    marker = _marker_path(str(model_id), home)
    try:
        card = json.loads(marker.read_text(encoding="utf-8")).get("trained")
    except (OSError, ValueError):
        return None
    return card if isinstance(card, dict) else None


def trained_readers(home: Path | None = None) -> list[tuple[str, dict[str, object]]]:
    """Every landed trained reader, (model id, card), newest first."""
    from fichero_server.training.project_models import open_project_kraken_ids

    found = []
    ids = [m.name[: -len(".installed")] for m in recognition_model_dir(home).glob(f"{TRAINED_READER_PREFIX}*.installed")]
    for model_id in dict.fromkeys(ids + open_project_kraken_ids()):  # the global copy first, then open projects'
        card = trained_reader_card(model_id, home)
        if card is not None:
            found.append((model_id, card))
    return sorted(found, key=lambda row: str(row[1].get("trained_at", "")), reverse=True)


def recognition_spec(model_id: str | None) -> dict[str, object] | None:
    """The catalogue entry for ``model_id``, a repository reader's {doi}, or a trained reader's
    {trained: card}; None for anything else."""
    if model_id in KRAKEN_RECOGNITION_MODELS:
        return KRAKEN_RECOGNITION_MODELS[model_id]
    match = _ZENODO_READER.match(model_id or "")
    if match:
        return {"doi": f"10.5281/zenodo.{match.group(1)}"}
    card = trained_reader_card(model_id)
    return {"trained": card} if card is not None else None


def resolve_recognition_model(model_ref: str) -> tuple[str, str | None]:
    """(filesystem path, catalog id) for a recognition-model reference.

    A catalog id ("kraken-mccatmus") resolves to the app's downloaded copy; a
    literal ``.mlmodel`` path is used as-is. Raises a clear, actionable error
    when a catalog model is not installed or a path is missing — never returns a
    path that is not there (the caller must say "install it", not run against
    nothing). One source of truth for both the workflow seam and any node.
    """
    if recognition_spec(model_ref):
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


class KrakenMemoryUnavailableError(MemoryShortError):
    """Raised when the machine cannot safely run Kraken right now (#4987). A `MemoryShortError`: the
    job lane waits on it and runs the page again when memory allows, it never fails a job (#5524).

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
_PRESSURE_CRITICAL = 4

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


def _available_memory_bytes(
    *,
    free_percent: Callable[[], int | None] | None = None,
    physical_bytes: Callable[[], int | None] | None = None,
    reclaimable_bytes: Callable[[], int | None] | None = None,
) -> int | None:
    """THE reading of what this Mac can hand out without crashing (#5537): what macOS itself counts
    as free, the number `memory_pressure` prints as "System-wide memory free percentage", times the
    Mac's physical memory. That percentage is the sysctl `kern.memorystatus_level`, which the kernel
    keeps from its pageable pages -- the Mach `host_statistics64` fields `free_count + active_count +
    inactive_count + speculative_count`, i.e. everything that is neither wired nor already
    compressed: file-backed pages it can drop, purgeable pages it can empty, and app pages the
    compressor can squeeze (checked live 2026-10-06, M1 Pro 16 GB: level 39%, those four fields
    37.5%). The older reading, free + inactive + speculative only (`_mach_reclaimable_bytes`),
    left the compressor out: on the 8 GB Air it said 2.2 GB free while `memory_pressure` said 64%,
    and every 3B vision load was refused. The larger of the two is used (the Mach reading stands in
    when the sysctl cannot be read). The real crash guard is pressure (`_memory_pressure_level`):
    CRITICAL refuses whatever this says. Readers are injectable for tests; ``None`` when nothing
    can be read."""
    percent = (free_percent or _memory_free_percent)()
    total = (physical_bytes or _physical_memory_bytes)()
    raw = (reclaimable_bytes or _mach_reclaimable_bytes)()
    readings = [r for r in (total * percent // 100 if percent is not None and total else None, raw)
                if r is not None]
    return max(readings) if readings else None


def _sysctl_int(name: bytes, ctype: Any = ctypes.c_int) -> int | None:
    """One integer sysctl, read in-process (no subprocess); None when it cannot be read."""
    try:
        libc = ctypes.CDLL("libc.dylib")
        value = ctype(0)
        size = ctypes.c_size_t(ctypes.sizeof(value))
        if libc.sysctlbyname(name, ctypes.byref(value), ctypes.byref(size), None, 0) != 0:
            return None
    except Exception:  # noqa: BLE001 — a missing sysctl must degrade, not crash
        return None
    return int(value.value)


def _memory_free_percent() -> int | None:
    """`kern.memorystatus_level`: macOS's own free percentage (what `memory_pressure` prints)."""
    return _sysctl_int(b"kern.memorystatus_level")


def _physical_memory_bytes() -> int | None:
    """`hw.memsize`: this Mac's physical memory."""
    return _sysctl_int(b"hw.memsize", ctypes.c_uint64)


def _mach_reclaimable_bytes() -> int | None:
    """Free + inactive + speculative pages: memory macOS can hand out without compressing anything.

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

    Checked on EVERY call, not once at startup: the moment a queued page is
    about to run is what counts, not when it was queued.

    The decision is `throttle.memory_short`, the SAME function and number the
    job lane's throttle uses before it hands out a job (#5524): the two checks
    used to differ (pressure at warn there, 2.5 GB free here), so the throttle
    released a job this guard then failed at 2.3 GB free.

    ``available_bytes``/``pressure_level`` are injectable so a test never
    depends on the real machine's memory or pressure — pass a lambda
    returning a fixed number instead of the real macOS reader.
    """
    from fichero_server.execution.throttle import memory_short

    reason = memory_short(available_bytes=available_bytes or _available_memory_bytes,
                          pressure_level=pressure_level or _memory_pressure_level)
    if reason is not None:
        raise KrakenMemoryUnavailableError(
            f"{reason}. Close other apps, or wait for other work to finish; a queued job waits on its own.")


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
            # The person's compute priority (core/compute_preferences.py): balanced, the default,
            # is UTILITY, not background, because someone is waiting for this page (measured:
            # 23 s at utility against 426 s at background for one page, #4959); fast drops the
            # throttle; background yields to everything.
            from fichero_server.core.compute_preferences import apply_to_this_thread, compute_preferences

            threads = apply_to_this_thread(compute_preferences()["priority"])
            try:
                import torch

                # Process-wide in torch: balanced never pegs the machine, fast may.
                torch.set_num_threads(threads)
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
        _release_when_idle()
    ok, value = outcome[0]  # type: ignore[misc]
    if not ok:
        raise value  # type: ignore[misc]
    return value  # type: ignore[return-value]


def _field(item: object, name: str) -> object:
    return item.get(name) if isinstance(item, dict) else getattr(item, name, None)


def _raw_lines(segmentation: object) -> list[dict[str, object]]:
    """Each line Kraken found: its baseline, its outline and the id of the region it sits in (None when
    Kraken put it in none), in Kraken's order."""
    raw = getattr(segmentation, "lines", None)
    if raw is None and isinstance(segmentation, dict):
        raw = segmentation.get("lines", [])
    out: list[dict[str, object]] = []
    for line in raw or []:
        baseline, boundary = _field(line, "baseline"), _field(line, "boundary")
        regions = _field(line, "regions") or []
        out.append(
            {
                "baseline": [[float(x), float(y)] for x, y in (baseline or [])],
                "polygon": [[float(x), float(y)] for x, y in (boundary or [])],
                "region": str(regions[0]) if regions else None,
            }
        )
    return out


def _raw_regions(segmentation: object) -> list[dict[str, object]]:
    """The regions Kraken's segmenter found (#5487: they were thrown away), each `{"id", "type",
    "polygon"}`, by type then in Kraken's order. A line names its region by this id (`_raw_lines`)."""
    raw = getattr(segmentation, "regions", None)
    if raw is None and isinstance(segmentation, dict):
        raw = segmentation.get("regions")
    out: list[dict[str, object]] = []
    for kind, regions in (raw or {}).items():
        for region in regions or []:
            boundary = _field(region, "boundary") or []
            out.append({"id": str(_field(region, "id")), "type": str(kind),
                        "polygon": [[float(x), float(y)] for x, y in boundary]})
    return out


def _segment_raw(image_path: str | Path) -> dict[str, object]:
    from PIL import Image
    from kraken import blla

    with Image.open(image_path) as image:
        if image.mode != "RGB":
            image = image.convert("RGB")
        segmentation = blla.segment(image, model=_segmenter())
        width, height = image.width, image.height
    return {"width": width, "height": height, "lines": _raw_lines(segmentation),
            "regions": _raw_regions(segmentation)}


#: One resident model per kind ("segment", "read"), kept between pages: every page used to reload
#: the line finder and the reader from disk. Loading once and reusing it is the "load a model once,
#: group work by model" rule (ai/local-runtimes.md); a different model for the same kind replaces
#: it, and `release_resident_models` frees both before another heavy model loads. Only touched
#: inside `_kraken_call`'s single lock, so no second lock is needed.
_RESIDENT: dict[str, tuple[str, object]] = {}


def _resident(kind: str, key: str, load: Callable[[], object]) -> object:
    held = _RESIDENT.get(kind)
    if held is not None and held[0] == key:
        return held[1]
    _RESIDENT.pop(kind, None)  # drop the old one before loading its replacement
    model = load()
    _RESIDENT[kind] = (key, model)
    return model


def release_resident_models() -> None:
    """Free Kraken's resident models (before another heavy model loads, and when idle). Collected at
    once: a reader's line-extraction pool (two spawned processes) is only terminated when the reader
    itself is collected (Kraken's own `weakref.finalize`)."""
    import gc

    _RESIDENT.clear()
    gc.collect()
    torch = sys.modules.get("torch")
    if torch is not None and torch.backends.mps.is_available():
        torch.mps.empty_cache()  # a reader that ran on the GPU (`device: gpu`) gives its buffers back


#: Kraken's readers are let go after this long without a page (#5529): a bake-off or a check ends and
#: nothing else asks for Kraken, so its reader, the line finder and the reader's two line-extraction
#: processes stayed in the engine until the next model switch on the lane -- which a job with no
#: model (`evaluate-models`, `check-lines`) never causes. Long enough that a run's pages, which come
#: one after another, keep the reader they share (loading one takes seconds).
IDLE_RELEASE_SECONDS = 120.0
_idle_timer: threading.Timer | None = None


def _release_when_idle() -> None:
    """(Re)arm the one idle timer; called under `_INFERENCE_LOCK` after every call."""
    global _idle_timer
    if _idle_timer is not None:
        _idle_timer.cancel()
    _idle_timer = threading.Timer(IDLE_RELEASE_SECONDS, _release_if_idle)
    _idle_timer.daemon = True
    _idle_timer.start()


def _release_if_idle() -> None:
    if not _INFERENCE_LOCK.acquire(blocking=False):
        return  # a page is running: it re-arms the timer when it ends
    try:
        release_resident_models()
    finally:
        _INFERENCE_LOCK.release()


def _reader_config(config_cls: Callable[..., object]) -> object:
    """The reader's device, as the person chose (`torch_accelerator`: auto is the CPU, #5529). Kraken's
    "auto" was slower than either per page (measured 2026-10-03 on a Sergio notebook half-page:
    auto 28 s, CPU 13 s, MPS 11 s, with the model already loaded)."""
    from fichero_server.core.compute_preferences import compute_preferences, torch_accelerator

    return config_cls(accelerator=torch_accelerator(compute_preferences()["device"]), device=1)


def _segmenter() -> object:
    """Kraken's built-in baseline line finder, loaded once."""
    from importlib import resources

    from kraken.lib import vgsl

    return _resident("segment", "blla", lambda: vgsl.TorchVGSLModel.load_model(
        resources.files("kraken").joinpath("blla.mlmodel")))


def _recognize_raw(image_path: str | Path, model_path: str) -> dict[str, object]:
    from PIL import Image
    from kraken import blla
    from kraken.configs import RecognitionInferenceConfig
    from kraken.tasks import RecognitionTaskModel

    with Image.open(image_path) as image:
        if image.mode != "RGB":
            image = image.convert("RGB")
        segmentation = blla.segment(image, model=_segmenter())
        # Kraken 7's recognition task: it loads both a .mlmodel and a .safetensors reader (the
        # format of Kraken 7 models such as PP-OCRv6), where the old load_any read only .mlmodel.
        # blla's neural baseline segmentation gives us the lines; the reader reads each one in the
        # SAME order -- so prediction i belongs to segmented line i, and every line keeps its own
        # baseline/polygon geometry.
        net = _resident("read", model_path, lambda: RecognitionTaskModel.load_model(model_path))
        predictions = list(net.predict(image, segmentation, _reader_config(RecognitionInferenceConfig)))
        width, height = image.width, image.height
    lines = _raw_lines(segmentation)
    for index, line in enumerate(lines):
        record = predictions[index] if index < len(predictions) else None
        line["text"] = "" if record is None else str(getattr(record, "prediction", record) or "")
    return {"width": width, "height": height, "lines": lines, "regions": _raw_regions(segmentation)}


def segment_lines(
    image_path: str | Path, *, run_call: Callable[[Callable[[], _T]], _T] | None = None
) -> dict[str, object]:
    """Run the segmenter and return raw pixel geometry plus its frame."""
    if not str(image_path).strip():
        # #5019: refuse BEFORE loading the model; an empty path is not a file to open.
        raise KrakenSegmentationError("No image path was supplied for this page; the engine could not resolve its source file.")
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


def _usable(lines: list[dict[str, object]]) -> list[dict[str, object]]:
    return [ln for ln in lines if len(ln.get("baseline") or []) >= 2 and len(ln.get("polygon") or []) >= 3]


def _read_given_raw(image_path: str | Path, model_path: str, lines: list[dict[str, object]]) -> list[str]:
    from PIL import Image
    from kraken.configs import RecognitionInferenceConfig
    from kraken.containers import BaselineLine, Segmentation
    from kraken.tasks import RecognitionTaskModel

    usable = _usable(lines)

    def pts(points: object) -> list[list[int]]:
        return [[int(x), int(y)] for x, y in points]  # type: ignore[union-attr]

    with Image.open(image_path) as image:
        if image.mode != "RGB":
            image = image.convert("RGB")
        segmentation = Segmentation(
            type="baselines", imagename=str(image_path), text_direction="horizontal-lr", script_detection=False,
            lines=[BaselineLine(id=str(ln["id"]), baseline=pts(ln["baseline"]), boundary=pts(ln["polygon"]))
                   for ln in usable],
            regions={}, line_orders=[])
        net = _resident("read", model_path, lambda: RecognitionTaskModel.load_model(model_path))
        predictions = list(net.predict(image, segmentation, _reader_config(RecognitionInferenceConfig)))
    read = {str(ln["id"]): str(getattr(r, "prediction", r) or "") for ln, r in zip(usable, predictions)}
    return [read.get(str(ln["id"]), "") for ln in lines]


def read_given_lines(
    image_path: str | Path,
    model_path: str,
    lines: list[dict[str, object]],
    *,
    run_call: Callable[[Callable[[], _T]], _T] | None = None,
) -> list[str]:
    """Read lines already found (each `{"id", "baseline", "polygon"}` in page pixels) with a reader,
    on their own baselines and outlines, without finding lines again: Kraken's rough read of each line,
    in the order given ("" for a line with too little geometry to read). The teacher-line check reads
    with it (`source.lines.reading-checked-against-the-page`, #5446)."""
    if not _usable(lines):
        return ["" for _ in lines]
    caller = run_call or _kraken_call
    try:
        return caller(lambda: _read_given_raw(image_path, model_path, lines))
    except (KrakenRuntimeMissingError, KrakenMemoryUnavailableError):
        raise
    except Exception as exc:
        raise KrakenSegmentationError(f"Kraken could not read the lines: {exc}") from exc


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
    spec = recognition_spec(model_id)
    if spec is None:
        raise ValueError(f"Unknown Kraken recognition model: {model_id}")
    if "trained" in spec:
        raise ValueError(f"{model_id} is a reader Fichero trained: it lands from its training job, "
                         "it is not downloaded")
    if model_id not in KRAKEN_RECOGNITION_MODELS:
        # A repository reader: fetch it only if the repository says it IS a Kraken recognition model.
        from htrmopo import get_description

        record = get_description(str(spec["doi"]))
        if "recognition" not in (getattr(record, "model_type", None) or []) or \
                getattr(record, "software_name", None) != "kraken":
            raise ValueError(f"{spec['doi']} is not a Kraken recognition model in Kraken's repository")
    # Each reader in its own folder: in one shared folder their metadata.json and README.md overwrote
    # each other, and "the newest .mlmodel anywhere" picked ANOTHER reader when this one ships as
    # .safetensors (Kraken 7's format) -- PP-OCRv6 resolved to McCATMuS (2026-10-03).
    data_home = recognition_data_home(home) / model_id
    data_home.mkdir(parents=True, exist_ok=True)

    def _fetch() -> object:
        from htrmopo import get_model

        return get_model(str(spec["doi"]), path=str(data_home))

    caller = run_call or _kraken_call
    caller(_fetch)

    found = [p for p in data_home.rglob("*") if p.suffix in (".mlmodel", ".safetensors")]
    if len(found) != 1:
        raise RuntimeError(
            f"model fetch for {model_id} (DOI {spec['doi']}) produced {len(found)} model files, "
            "expected exactly one (.mlmodel or .safetensors)"
        )
    model_path = str(found[0])
    marker_dir = recognition_model_dir(home)
    marker_dir.mkdir(parents=True, exist_ok=True)
    _marker_path(model_id, home).write_text(
        json.dumps({"doi": str(spec["doi"]), "model_path": model_path}),
        encoding="utf-8",
    )


def _region_boxes(
    payload: dict[str, object], width: float, height: float, *, model: str, source: str
) -> tuple[list[OCRGeometryBox], dict[str, int]]:
    """Kraken's regions as boxes, and each region id's box index (#5487): the lines that sit in a region
    name it as their parent (`parent_box_index`), so the page keeps region -> line, not a flat list."""
    boxes: list[OCRGeometryBox] = []
    index_of: dict[str, int] = {}
    for region in payload.get("regions") or []:  # type: ignore[union-attr]
        polygon = [(float(x), float(y)) for x, y in region.get("polygon") or []]
        if len(polygon) < 3:
            continue
        xs = [point[0] for point in polygon]
        ys = [point[1] for point in polygon]
        x0, x1 = max(0.0, min(xs)), min(width, max(xs))
        y0, y1 = max(0.0, min(ys)), min(height, max(ys))
        if x1 <= x0 or y1 <= y0:
            continue
        index_of[str(region.get("id"))] = len(boxes)
        boxes.append(
            OCRGeometryBox(
                text="",
                bbox=[x0 / width, y0 / height, (x1 - x0) / width, (y1 - y0) / height],
                level=OCRGeometryLevel.REGION,
                provider=_PROVIDER,
                model=model,
                source=source,
                metadata={
                    "kind_raw": region.get("type"),
                    "polygon_px": [[x, y] for x, y in polygon],
                    "pixel_frame": {"width": width, "height": height},
                },
            )
        )
    return boxes, index_of


def _parent(line: dict[str, object], index_of: dict[str, int]) -> dict[str, int]:
    region = line.get("region")
    return {"parent_box_index": index_of[str(region)]} if region is not None and str(region) in index_of else {}


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

    boxes, region_index = _region_boxes(payload, width, height, model=_MODEL, source="kraken-blla")
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
                    **_parent(line, region_index),
                },
            )
        )

    if not any(box.level is OCRGeometryLevel.LINE for box in boxes):
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
    boxes, region_index = _region_boxes(payload, width, height, model=stamped_model, source="kraken-htr")
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
                    **_parent(line, region_index),
                },
            )
        )

    if not texts:
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


def train_recognition(argv: list[str], out: Path, *, on_batch: Callable[[], None],
                      on_epoch_end: Callable[[int], None]) -> None:
    """Train a recognition model in this process: `ketos <argv>`, with two callbacks (after each
    batch, after each epoch: what the caller uses to hold or stop the run) and a `last.ckpt`
    written in `out` at every epoch's end, which `--resume` carries on from.

    Not under `_INFERENCE_LOCK`: training runs for hours and steps aside at a batch boundary for a
    page a person waits for, which needs that lock; it runs as a job on the local-model lane, so
    no other heavy model loads beside it."""
    import kraken.train as kraken_train
    from kraken.ketos import cli
    from kraken.ketos.recognition import train
    from lightning.pytorch.callbacks import Callback, ModelCheckpoint

    class _Callbacks(Callback):
        def on_train_batch_end(self, trainer, pl_module, outputs, batch, batch_idx):
            on_batch()

        def on_train_epoch_end(self, trainer, pl_module):
            on_epoch_end(int(trainer.current_epoch))

    plain = kraken_train.KrakenTrainer

    class _Trainer(plain):
        def __init__(self, *args, callbacks=None, **kwargs):
            # Unmonitored, top 1: the newest epoch, always `last.ckpt` (Kraken's own checkpoints keep
            # the ten best by score, so the newest epoch's file can be pruned).
            last = ModelCheckpoint(dirpath=out, filename="last", monitor=None, save_top_k=1,
                                   enable_version_counter=False)
            super().__init__(*args, callbacks=[*(callbacks or []), _Callbacks(), last], **kwargs)

    cli.add_command(train, name="train")  # the bundled app may carry no entry-point metadata
    kraken_train.KrakenTrainer = _Trainer
    try:
        cli.main(args=argv, prog_name="ketos", standalone_mode=False)
    finally:
        kraken_train.KrakenTrainer = plain


__all__ = [
    "train_recognition",
    "release_resident_models",
    "KRAKEN_RECOGNITION_MODELS",
    "TRAINED_READER_PREFIX",
    "trained_reader_card",
    "trained_readers",
    "download_recognition_model",
    "is_installed",
    "is_recognition_model_installed",
    "recognition_data_home",
    "recognition_model_dir",
    "recognition_model_bytes",
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
