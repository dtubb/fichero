"""Kraken's neural line segmenter, as a geometry provider behind the OCR seam.

Kraken finds LINES — a polygon and a baseline per written line — and reads
nothing. That is the point. Apple Vision reads well and localises badly on
historical hands: measured 2026-09-04 on Caciques 533r (17th-century Spanish
secretary hand, ~30 lines), macOS 26's document request found 6 lines and
7 words while Kraken found 33 line polygons with baselines in 13.4s. On modern
cursive the two agree closely and Apple is faster, so this is not a better
engine; it is the engine that still works on the material an archive is made
of.

Two rules this module exists to keep:

* It is a USER-CHOSEN install (Daniel, 2026-09-04). torch alone is 596 MB
  installed and the smallest working set is 996 MB, so nothing here is
  provisioned automatically or bundled. A runtime that is not installed says
  so with a typed error; it never returns an empty result that reads as "this
  page has no lines".
* Its output speaks the existing ``OCRGeometryResult`` vocabulary — normalized
  top-left boxes, a named pixel frame, a carried ``rendition_id`` — so nothing
  downstream can tell a Kraken box from an Apple one.

The segmenter runs in its own venv via subprocess, exactly as the MLX runtime
does. It never enters the engine process: it would drag torch, lightning and
coremltools into an env that deliberately excludes them.
"""

from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
import json
import logging
import os
from pathlib import Path
import shutil
import subprocess
import uuid
import venv

from fichero_server.db.paths import server_state_dir
from fichero_server.media.ocr_geometry import (
    OCRGeometryBox,
    OCRGeometryLevel,
    OCRGeometryResult,
    OCRGeometryStatus,
    geometry_unavailable,
)

logger = logging.getLogger(__name__)

KRAKEN_VERSION = "7.1.1"

#: kraken pins ``scipy~=1.15.3``, and that build's PROPACK extension is
#: rejected by this OS's dyld ("__DATA/__thread_bss has a zero-fill section
#: type, but offset field is not zero"), so `import kraken` fails outright on
#: macOS 26/27. Overriding an upstream pin is a cost we own deliberately
#: rather than a workaround we hide: it is recorded here, in the install
#: command, and in the runtime metadata, so the next person to see a kraken
#: dependency warning knows it was a decision.
KRAKEN_SCIPY_OVERRIDE = "scipy>=1.16"

_RUNTIME_DIRNAME = "kraken-runtime"
_METADATA_FILENAME = "runtime.json"
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
#   it is "installed" exactly when the runtime venv is. This is what Fichero's
#   OCR-geometry seam uses today.
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


def recognition_model_dir(home: Path | None = None) -> Path:
    """Where completed recognition-model installs are recorded (our markers)."""
    return kraken_runtime_dir(home) / "recognition"


def recognition_data_home(home: Path | None = None) -> Path:
    """XDG_DATA_HOME we point `kraken get` at, so the .mlmodel lands in OUR tree.

    `kraken get` writes to ``$XDG_DATA_HOME/htrmopo/<uuid>/`` with an opaque
    UUID dir. Rather than reverse-map DOI→uuid, we make that base a directory we
    own, then scan it for the fetched ``.mlmodel`` — a deterministic path under
    the app's control instead of the user's global ``~/.local/share``.
    """
    return kraken_runtime_dir(home) / "htr-data"


def kraken_bin(home: Path | None = None) -> Path | None:
    """The runtime venv's `kraken` CLI, or None when the runtime is absent.

    economy_htr's kraken backend must run the app's OWN kraken (the one this
    runtime installed), not a system `kraken` that may not exist — the two
    kraken worlds that used to never meet.
    """
    candidate = kraken_runtime_dir(home) / "bin" / "kraken"
    return candidate if candidate.exists() else None


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


def _default_run_get(argv: list[str]) -> str:
    result = subprocess.run(argv, check=True, capture_output=True, text=True)
    return result.stdout or ""


def _locate_downloaded_mlmodel(data_home: Path) -> str | None:
    """Newest ``.mlmodel`` under the data-home htrmopo tree, or None."""
    if not data_home.exists():
        return None
    models = sorted(
        data_home.rglob("*.mlmodel"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return str(models[0]) if models else None


def download_recognition_model(
    model_id: str,
    home: Path | None = None,
    run_command=None,
) -> None:
    """Fetch a recognition model with `kraken get <DOI>` and record its path.

    Requires the runtime venv (kraken lives in it). Raises rather than
    half-succeeding: without the venv there is no `kraken` to run, and a fetch
    that quietly does nothing is the shape a user reads as success. The fetched
    ``.mlmodel`` path is recorded so economy_htr can run against it.

    NOTE: `kraken get`'s on-disk layout is verified LIVE — pointing XDG_DATA_HOME
    at our own tree and scanning for the newest ``.mlmodel`` is robust to the
    opaque UUID dir, but the exact CLI behaviour needs a real ~1 GB fetch to
    confirm end to end (flagged for Daniel's live check).
    """
    spec = KRAKEN_RECOGNITION_MODELS.get(model_id)
    if spec is None:
        raise ValueError(f"Unknown Kraken recognition model: {model_id}")
    if not is_installed(home):
        raise KrakenRuntimeMissingError(
            "Install the Kraken runtime before downloading recognition models."
        )
    runner = run_command or _default_run_get
    data_home = recognition_data_home(home)
    data_home.mkdir(parents=True, exist_ok=True)
    interpreter = kraken_runtime_dir(home) / "bin" / "kraken"
    # HTRMoPo reads XDG_DATA_HOME for where to place the model, so setting it in
    # the environment routes the download into our tree.
    prior = os.environ.get("XDG_DATA_HOME")
    os.environ["XDG_DATA_HOME"] = str(data_home)
    try:
        runner([str(interpreter), "get", str(spec["doi"])])
    finally:
        if prior is None:
            os.environ.pop("XDG_DATA_HOME", None)
        else:
            os.environ["XDG_DATA_HOME"] = prior
    model_path = _locate_downloaded_mlmodel(data_home)
    marker_dir = recognition_model_dir(home)
    marker_dir.mkdir(parents=True, exist_ok=True)
    _marker_path(model_id, home).write_text(
        json.dumps({"doi": str(spec["doi"]), "model_path": model_path}),
        encoding="utf-8",
    )


def remove_recognition_model(model_id: str, home: Path | None = None) -> None:
    """Forget a recognition model (drops our marker; htrmopo cache is kraken's)."""
    marker = _marker_path(model_id, home)
    if marker.exists():
        marker.unlink()


class KrakenRuntimeMissingError(RuntimeError):
    """Raised when Kraken segmentation is asked of a runtime without Kraken."""


class KrakenSegmentationError(RuntimeError):
    """Raised when the segmenter ran and did not return usable geometry."""


@dataclass(frozen=True)
class KrakenLine:
    """One segmented line, in the pixels of the image it was measured on."""

    polygon: tuple[tuple[float, float], ...]
    baseline: tuple[tuple[float, float], ...]


def kraken_runtime_dir(home: Path | None = None) -> Path:
    override = os.environ.get("FICHERO_KRAKEN_RUNTIME_DIR")
    if override:
        return Path(override).expanduser()
    return server_state_dir(home) / _RUNTIME_DIRNAME


def python_path(home: Path | None = None) -> Path:
    return kraken_runtime_dir(home) / "bin" / "python"


def _metadata(home: Path | None = None) -> dict[str, object]:
    path = kraken_runtime_dir(home) / _METADATA_FILENAME
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def is_installed(home: Path | None = None) -> bool:
    """Whether Kraken can actually segment.

    The metadata file is written LAST, after the packages land, so its presence
    is the honest signal — the same rule the MLX runtime learned when a venv
    that existed but held no mlx-lm reported itself ready (#4504).
    """
    return python_path(home).exists() and bool(_metadata(home).get("kraken_version"))


def runtime_status(home: Path | None = None) -> dict[str, object]:
    installed = is_installed(home)
    return {
        "installed": installed,
        "kraken_version": _metadata(home).get("kraken_version"),
        "scipy_override": _metadata(home).get("scipy_override"),
        "runtime_dir": str(kraken_runtime_dir(home)),
        "disk_usage_bytes": _disk_usage_bytes(kraken_runtime_dir(home)),
        "reason": None
        if installed
        else (
            "Kraken is not installed. Install it from Settings -> AI -> Local "
            "Inference to segment historical hands; it is a ~1 GB download and "
            "is never installed automatically."
        ),
    }


def require_python_path(home: Path | None = None) -> Path:
    if is_installed(home):
        return python_path(home)
    raise KrakenRuntimeMissingError(str(runtime_status(home)["reason"]))


def install(home: Path | None = None, run_command=None, create_venv=None) -> dict[str, object]:
    """Create the Kraken venv and install it. Blocking; caller owns threading.

    ``create_venv`` is injectable so a test can assert the install ORDER — which
    is load-bearing here — without spending two minutes building a real venv.
    """
    runner = run_command or _default_run_command
    builder = create_venv or _default_create_venv
    target = kraken_runtime_dir(home)
    target.parent.mkdir(parents=True, exist_ok=True)
    builder(target)
    interpreter = str(python_path(home))
    runner([interpreter, "-m", "pip", "install", f"kraken=={KRAKEN_VERSION}"])
    # AFTER kraken, deliberately: kraken pulls its own pinned scipy first and
    # this replaces it. Doing it before would let kraken's pin win.
    runner([interpreter, "-m", "pip", "install", "--upgrade", KRAKEN_SCIPY_OVERRIDE])
    (target / _METADATA_FILENAME).write_text(
        json.dumps(
            {"kraken_version": KRAKEN_VERSION, "scipy_override": KRAKEN_SCIPY_OVERRIDE},
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return runtime_status(home)


def remove(home: Path | None = None) -> dict[str, object]:
    target = kraken_runtime_dir(home).resolve()
    if target.name != _RUNTIME_DIRNAME:
        raise RuntimeError(f"Refusing to remove unexpected runtime dir: {target}")
    if target.exists():
        shutil.rmtree(target)
    return runtime_status(home)


_SEGMENT_SCRIPT = """
import json, sys
from PIL import Image
from kraken import blla
image = Image.open(sys.argv[1])
if image.mode != "RGB":
    image = image.convert("RGB")
segmentation = blla.segment(image)
lines = []
raw = getattr(segmentation, "lines", None)
if raw is None and isinstance(segmentation, dict):
    raw = segmentation.get("lines", [])
for line in raw or []:
    if isinstance(line, dict):
        baseline, boundary = line.get("baseline"), line.get("boundary")
    else:
        baseline = getattr(line, "baseline", None)
        boundary = getattr(line, "boundary", None)
    lines.append({
        "baseline": [[float(x), float(y)] for x, y in (baseline or [])],
        "polygon": [[float(x), float(y)] for x, y in (boundary or [])],
    })
sys.stdout.write("__FICHERO_KRAKEN__" + json.dumps(
    {"width": image.width, "height": image.height, "lines": lines}
))
"""


def segment_lines(image_path: str | Path, home: Path | None = None) -> dict[str, object]:
    """Run the segmenter and return raw pixel geometry plus its frame."""
    interpreter = require_python_path(home)
    try:
        completed = subprocess.run(
            [str(interpreter), "-c", _SEGMENT_SCRIPT, str(image_path)],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        tail = (exc.stderr or exc.stdout or "").strip().splitlines()
        raise KrakenSegmentationError(
            f"Kraken segmentation failed: {tail[-1] if tail else exc.returncode}"
        ) from exc
    marker = "__FICHERO_KRAKEN__"
    if marker not in completed.stdout:
        raise KrakenSegmentationError(
            "The segmenter produced no geometry payload; "
            f"stderr: {(completed.stderr or '').strip()[-400:]}"
        )
    return json.loads(completed.stdout.split(marker, 1)[1])


def segment_to_geometry(
    image_path: str | Path,
    *,
    rendition_id: str | None = None,
    home: Path | None = None,
) -> OCRGeometryResult:
    """Segment one image into the shared OCR geometry vocabulary.

    ``rendition_id`` names WHICH PICTURE these boxes were measured on. Kraken
    works in absolute pixels of the exact file it was handed, so a result whose
    frame is not named is a result nobody can place on a page that has more
    than one rendition (the bbox program's root cause). It is carried through
    unchanged, never inferred.

    A runtime that is not installed raises rather than returning an empty
    result: "no lines found" and "no segmenter installed" are different facts,
    and only one of them is about the page.
    """
    payload = segment_lines(image_path, home=home)
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


_RECOGNIZE_SCRIPT = """
import json, sys
from PIL import Image
from kraken import blla, rpred
from kraken.lib import models
image_path, model_path = sys.argv[1], sys.argv[2]
image = Image.open(image_path)
if image.mode != "RGB":
    image = image.convert("RGB")
# blla's neural baseline segmentation gives us the lines; rpred reads each one
# with the recognition model, in the SAME order — so prediction i belongs to
# segmented line i, and every line keeps its own baseline/polygon geometry.
segmentation = blla.segment(image)
net = models.load_any(model_path)
seg_lines = getattr(segmentation, "lines", None)
if seg_lines is None and isinstance(segmentation, dict):
    seg_lines = segmentation.get("lines", [])
predictions = list(rpred.rpred(net, image, segmentation))
lines = []
for index, line in enumerate(seg_lines or []):
    if isinstance(line, dict):
        baseline, boundary = line.get("baseline"), line.get("boundary")
    else:
        baseline = getattr(line, "baseline", None)
        boundary = getattr(line, "boundary", None)
    record = predictions[index] if index < len(predictions) else None
    text = "" if record is None else str(getattr(record, "prediction", record) or "")
    lines.append({
        "text": text,
        "baseline": [[float(x), float(y)] for x, y in (baseline or [])],
        "polygon": [[float(x), float(y)] for x, y in (boundary or [])],
    })
sys.stdout.write("__FICHERO_KRAKEN__" + json.dumps(
    {"width": image.width, "height": image.height, "lines": lines}
))
"""


def recognize_lines(
    image_path: str | Path,
    model_path: str,
    home: Path | None = None,
) -> dict[str, object]:
    """Segment + RECOGNISE one image; raw per-line text plus pixel geometry.

    Unlike :func:`segment_lines` (baselines only, no reading), this runs the
    recognition model over each segmented line so every line comes back with
    the text Kraken read AND the baseline/polygon it read it from. Runs in the
    Kraken venv, same subprocess/marker protocol as the segmenter.
    """
    interpreter = require_python_path(home)
    try:
        completed = subprocess.run(
            [str(interpreter), "-c", _RECOGNIZE_SCRIPT, str(image_path), str(model_path)],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        tail = (exc.stderr or exc.stdout or "").strip().splitlines()
        raise KrakenSegmentationError(
            f"Kraken recognition failed: {tail[-1] if tail else exc.returncode}"
        ) from exc
    marker = "__FICHERO_KRAKEN__"
    if marker not in completed.stdout:
        raise KrakenSegmentationError(
            "The recogniser produced no payload; "
            f"stderr: {(completed.stderr or '').strip()[-400:]}"
        )
    return json.loads(completed.stdout.split(marker, 1)[1])


def recognize_to_geometry(
    image_path: str | Path,
    model_path: str,
    *,
    model_id: str | None = None,
    rendition_id: str | None = None,
    home: Path | None = None,
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
    payload = recognize_lines(image_path, model_path, home=home)
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


@dataclass
class KrakenInstallJob:
    """One background Kraken install, with coarse but real progress.

    Kraken is a ~1 GB download, so the UI needs something to poll. The steps
    are the load-bearing ones ``install()`` already performs — create the venv,
    install kraken, override its scipy pin — counted as they happen rather than
    guessed, so a stalled pip is visible as a job stuck on that step.
    """

    job_id: str
    state: str  # queued | running | completed | failed
    current: int
    total: int
    message: str
    error: str | None = None

    @property
    def percent(self) -> float:
        if self.total <= 0:
            return 0.0
        return (self.current / self.total) * 100

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["percent"] = self.percent
        return data


class KrakenRuntimeManager:
    """Own the Kraken install as a coalesced background job with status.

    Mirrors ``MLXRuntime``: one install runs at a time, ``status()`` merges the
    on-disk runtime facts with the live job, and provisioning NEVER starts on
    its own — only an explicit ``start_install`` (the POST endpoint) begins it,
    keeping Daniel's "never automatic" rule true at the process layer too.
    """

    #: create venv, install kraken, override scipy, write metadata.
    _TOTAL_STEPS = 4

    def __init__(
        self,
        home: Path | None = None,
        *,
        create_venv=None,
        run_command=None,
    ) -> None:
        self._home = home
        # Injectable so a test can drive an install to completion without
        # spending minutes building a real venv (the same seam install() has).
        self._create_venv = create_venv or _default_create_venv
        self._run_command = run_command or _default_run_command
        self._job_lock = asyncio.Lock()
        self._install_task: asyncio.Task[None] | None = None
        self._job: KrakenInstallJob | None = None

    def runtime_dir(self) -> Path:
        return kraken_runtime_dir(self._home)

    def status(self) -> dict[str, object]:
        payload = dict(runtime_status(self._home))
        payload["job"] = self._job.to_dict() if self._job is not None else None
        return payload

    async def start_install(self) -> dict[str, object]:
        async with self._job_lock:
            if self._install_task is not None and not self._install_task.done():
                return self.status()
            if is_installed(self._home):
                # Already there — do not rebuild a 1 GB venv for a no-op.
                self._job = KrakenInstallJob(
                    job_id=str(uuid.uuid4()),
                    state="completed",
                    current=self._TOTAL_STEPS,
                    total=self._TOTAL_STEPS,
                    message="Kraken already installed",
                )
                return self.status()
            job = KrakenInstallJob(
                job_id=str(uuid.uuid4()),
                state="running",
                current=0,
                total=self._TOTAL_STEPS,
                message="Creating Kraken runtime",
            )
            self._job = job
            self._install_task = asyncio.create_task(self._install(job))
            return self.status()

    async def wait_for_current_job(self) -> None:
        task = self._install_task
        if task is not None:
            await task

    async def _install(self, job: KrakenInstallJob) -> None:
        def bump_venv(target: Path) -> None:
            job.current = 1
            job.message = "Creating Kraken virtual environment"
            self._create_venv(target)

        def bump_run(argv: list[str]) -> None:
            # The two pip calls, named as they run: kraken first, then the
            # scipy override that replaces kraken's broken pin.
            if job.current < 2:
                job.current = 2
                job.message = f"Installing kraken=={KRAKEN_VERSION}"
            else:
                job.current = 3
                job.message = f"Overriding scipy pin ({KRAKEN_SCIPY_OVERRIDE})"
            self._run_command(argv)

        try:
            await asyncio.to_thread(
                install,
                self._home,
                run_command=bump_run,
                create_venv=bump_venv,
            )
            job.current = self._TOTAL_STEPS
            job.state = "completed"
            job.message = "Kraken runtime ready"
        except Exception as exc:  # noqa: BLE001 — surfaced on the job, not raised
            job.state = "failed"
            job.error = str(exc)
            job.message = "Kraken install failed"

    def remove(self) -> dict[str, object]:
        if self._install_task is not None and not self._install_task.done():
            raise RuntimeError("Kraken install is still running")
        remove(self._home)
        self._job = None
        return self.status()


_RUNTIME_MANAGER: KrakenRuntimeManager | None = None


def get_kraken_runtime() -> KrakenRuntimeManager:
    """Process-wide Kraken install manager, rebound if the runtime dir moves."""
    global _RUNTIME_MANAGER
    target = kraken_runtime_dir()
    if _RUNTIME_MANAGER is None or _RUNTIME_MANAGER.runtime_dir() != target:
        _RUNTIME_MANAGER = KrakenRuntimeManager()
    return _RUNTIME_MANAGER


def _disk_usage_bytes(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(file.stat().st_size for file in path.rglob("*") if file.is_file())


def _default_create_venv(target: Path) -> None:
    venv.EnvBuilder(with_pip=True, clear=False, upgrade=False).create(target)


def _default_run_command(argv: list[str]) -> None:
    subprocess.run(argv, check=True, capture_output=True, text=True)


__all__ = [
    "KRAKEN_RECOGNITION_MODELS",
    "KRAKEN_SCIPY_OVERRIDE",
    "KRAKEN_VERSION",
    "download_recognition_model",
    "is_recognition_model_installed",
    "kraken_bin",
    "recognition_data_home",
    "recognition_model_dir",
    "recognition_model_path",
    "resolve_recognition_model",
    "remove_recognition_model",
    "KrakenInstallJob",
    "KrakenRuntimeManager",
    "KrakenRuntimeMissingError",
    "KrakenSegmentationError",
    "get_kraken_runtime",
    "install",
    "is_installed",
    "kraken_runtime_dir",
    "python_path",
    "recognize_lines",
    "recognize_to_geometry",
    "remove",
    "require_python_path",
    "runtime_status",
    "segment_lines",
    "segment_to_geometry",
]
