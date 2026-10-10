"""YOLO layout models: find a page's regions (`prep.yolo.regions-card`, #5525).

Ultralytics ships inside the app (pyproject); the WEIGHTS are data, downloaded on request into the model store
and never bundled (the stock model is AGPL-3.0, like Fichero). Ultralytics is kept quiet in the sandbox
(`prep.yolo.quiet-in-the-sandbox`): its settings live under the model store, not `/tmp`, and nothing is synced or
checked online.

Measured 2026-10-10: the stock DocLayNet model runs (0.1 s a page warm on the GPU, 6 s for its first load), but on
handwritten manuscript photographs it finds little (one "Picture" at 26-28%). It is the starting point that a
project's corrected regions fine-tune (`prep.yolo.fine-tune-from-corrected-regions`).
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from pathlib import Path

#: The layout models this Mac can fetch: id -> (Hugging Face repository, file, what it was trained on).
YOLO_MODELS: dict[str, tuple[str, str, str]] = {
    "yolo-doclaynet-11n": ("hantian/yolo-doclaynet", "yolov11n-doclaynet.pt",
                           "DocLayNet (printed and born-digital pages), YOLO11 nano, AGPL-3.0"),
}
DEFAULT_MODEL = "yolo-doclaynet-11n"

_LOCK = threading.Lock()
_LOADED: dict[str, object] = {}


@dataclass(frozen=True)
class Region:
    #: The model's own label (DocLayNet: Text, Title, Section-header, Table, Picture, Page-header, ...): each is
    #: saved as a region segment with this as its `kind_raw` (`source.segment.open-kinds`).
    kind_raw: str
    #: [x, y, width, height], each 0..1 of the image.
    rect: list[float]
    confidence: float


def _models_path() -> Path:
    """The YOLO weights' folder in the one shared models folder (`check_model_download_location`)."""
    from fichero_server.db.paths import model_store_root

    return model_store_root() / "models" / "yolo"


def model_path(model_id: str) -> Path | None:
    """The weights of a known model: downloaded to the store, or trained in an open project; else None."""
    from fichero_server.training.yolo_local import TRAINED_PREFIX

    if model_id.startswith(TRAINED_PREFIX):
        from fichero_server.training.project_models import _open_projects, model_folder

        for package in _open_projects():
            trained = model_folder(package, model_id) / "model.pt"
            if trained.is_file():
                return trained
        return None
    spec = YOLO_MODELS.get(model_id)
    if spec is None:
        return None
    path = _models_path() / spec[1]
    return path if path.is_file() and path.stat().st_size > 0 else None


def is_installed(model_id: str) -> bool:
    return model_path(model_id) is not None


def download(model_id: str) -> Path:
    """Fetch a model's weights into the store (the `download-model` job runs this)."""
    spec = YOLO_MODELS.get(model_id)
    if spec is None:
        raise ValueError(f"no download for yolo:{model_id}")
    from huggingface_hub import hf_hub_download

    models_path = _models_path()
    models_path.mkdir(parents=True, exist_ok=True)
    return Path(hf_hub_download(repo_id=spec[0], filename=spec[1], local_dir=str(models_path)))


def _quiet() -> None:
    """Ultralytics' settings under the store and offline: no `/tmp` folder, no sync, no online checks."""
    home = _models_path()
    home.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("YOLO_CONFIG_DIR", str(home))
    os.environ.setdefault("YOLO_OFFLINE", "1")
    from ultralytics import settings

    # Ultralytics 8.4's own keys: no sync, no experiment loggers, and its folders under the store (never the
    # engine's working folder, which a sandboxed app cannot write).
    settings.update({"sync": False, "clearml": False, "comet": False, "dvc": False, "mlflow": False,
                     "raytune": False, "tensorboard": False, "wandb": False,
                     "datasets_dir": str(home / "datasets"), "weights_dir": str(home / "weights"),
                     "runs_dir": str(home / "runs")})


def _model(model_id: str):
    path = model_path(model_id)
    if path is None:
        raise FileNotFoundError(f"The layout model {model_id} is not downloaded")
    with _LOCK:
        if model_id not in _LOADED:
            _quiet()
            from ultralytics import YOLO

            _LOADED[model_id] = YOLO(str(path))
        return _LOADED[model_id]


def _device() -> str:
    import torch

    return "mps" if torch.backends.mps.is_available() else "cpu"


def regions_from(names: dict[int, str], boxes: list[tuple[int, float, list[float]]],
                 width: int, height: int) -> list[Region]:
    """A model's boxes ((class, confidence, [x1, y1, x2, y2] in pixels)) as Fichero regions, in reading order
    (top to bottom, then left to right)."""
    out = []
    for cls, conf, (x1, y1, x2, y2) in boxes:
        label = names.get(int(cls), str(cls))
        out.append(Region(kind_raw=label,
                          rect=[x1 / width, y1 / height, (x2 - x1) / width, (y2 - y1) / height],
                          confidence=round(float(conf), 3)))
    return sorted(out, key=lambda r: (round(r.rect[1], 2), r.rect[0]))


def detect_regions(image_path: str | Path, model_id: str = DEFAULT_MODEL, *, confidence: float = 0.25) -> list[Region]:
    """The regions a layout model finds on one page image."""
    model = _model(model_id)
    with _LOCK:  # one page at a time through a loaded model
        result = model.predict(str(image_path), imgsz=1024, conf=confidence, device=_device(), verbose=False)[0]
    height, width = result.orig_shape
    boxes = [(int(b.cls), float(b.conf), b.xyxy[0].tolist()) for b in result.boxes]
    return regions_from(result.names, boxes, width, height)
