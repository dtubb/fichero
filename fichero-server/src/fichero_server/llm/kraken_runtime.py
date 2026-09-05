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

from dataclasses import dataclass
import json
import logging
import os
from pathlib import Path
import shutil
import subprocess
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


def _disk_usage_bytes(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(file.stat().st_size for file in path.rglob("*") if file.is_file())


def _default_create_venv(target: Path) -> None:
    venv.EnvBuilder(with_pip=True, clear=False, upgrade=False).create(target)


def _default_run_command(argv: list[str]) -> None:
    subprocess.run(argv, check=True, capture_output=True, text=True)


__all__ = [
    "KRAKEN_SCIPY_OVERRIDE",
    "KRAKEN_VERSION",
    "KrakenRuntimeMissingError",
    "KrakenSegmentationError",
    "install",
    "is_installed",
    "kraken_runtime_dir",
    "python_path",
    "remove",
    "require_python_path",
    "runtime_status",
    "segment_lines",
    "segment_to_geometry",
]
