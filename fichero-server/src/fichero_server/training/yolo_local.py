"""Fine-tune a YOLO layout model on a project's corrected regions, on this Mac
(`prep.yolo.fine-tune-from-corrected-regions`, #5525).

Kraken's training on this Mac (`training/local.py`) is the shape, and its `Gentle` is reused as is: one heavy job
on the local model lane, in the engine's own process (a sandboxed engine cannot start a child), holding while the
Mac is in use and stopping (to resume later) when memory is tight, someone waits, or the person cancels. YOLO
trains on the Mac's GPU (measured 2026-10-10: two epochs on two pages in 24 s, 855 MB peak). Each epoch ends in
`last.pt`; a stopped job resumes from it. The landed model sits inside the project (`<project>/models/<id>/`), its
card naming the pages it learned from and its region-overlap score (mAP50) on the held-out pages.
"""

from __future__ import annotations

import gc
import json
import shutil
import time
import uuid
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from fichero_server.execution import jobs
from fichero_server.training import job as remote_job

KIND = "train-regions-on-this-mac"
MODEL = "yolo:train"
TRAINED_PREFIX = "trained-yolo-"


class TrainRegionsHereRequest(BaseModel):
    """Fine-tune a layout model on the regions a person corrected in these folders or pages."""

    name: str = Field(description="what to call the trained model")
    scope_ids: list[str] = Field(description="folders or pages whose corrected regions are the training set")
    held_out_ids: list[str] = Field(default_factory=list, description=(
        "pages kept out of training and used to score the model (region overlap)"))
    base: str = Field(default="yolo-doclaynet-11n", description="the layout model to start from")
    epochs: int = Field(default=30, ge=1, le=300)
    image_size: int = Field(default=1024, ge=320, le=2048)
    batch_size: int = Field(default=4, ge=1, le=32)


def start(db: Any, request: TrainRegionsHereRequest, *, started_by: str) -> dict[str, Any]:
    """Queue the training; a base model that is not downloaded is refused now."""
    from fichero_server.llm.yolo_runtime import model_path

    if model_path(request.base) is None:
        raise ValueError(f"the layout model {request.base} is not on this Mac: download it first")
    detail = {"card": "yolo-here", "request": request.model_dump(), "phase": "waiting",
              "history": [{"phase": "waiting", "at": remote_job._now()}]}
    job_id = jobs.enqueue(db, KIND, f"training:{uuid.uuid4()}", started_by=started_by, detail=json.dumps(detail))
    return {"job_id": job_id}


def _callbacks(gentle: Any) -> dict[str, Any]:
    return {"on_train_batch_end": lambda trainer: gentle.on_batch(),
            "on_train_epoch_end": lambda trainer: gentle.on_epoch_end(int(trainer.epoch))}


def train(model_file: str, data_yaml: Path, out: Path, request: TrainRegionsHereRequest, gentle: Any,
          *, resume: Path | None) -> tuple[Path, dict[str, float]]:
    """Ultralytics' training, in this process on the GPU, with the gentle checks at every batch."""
    from fichero_server.llm.yolo_runtime import _device, _quiet

    _quiet()
    from ultralytics import YOLO

    model = YOLO(str(resume) if resume else model_file)
    for event, callback in _callbacks(gentle).items():
        model.add_callback(event, callback)
    result = model.train(data=str(data_yaml), epochs=request.epochs, imgsz=request.image_size,
                         batch=request.batch_size, device=_device(), workers=0, project=str(out), name="run",
                         exist_ok=True, plots=False, verbose=False, amp=False, resume=bool(resume))
    scores = {k: round(float(v), 4) for k, v in (getattr(result, "results_dict", None) or {}).items()}
    return Path(model.trainer.best), scores


def run(db: Any, subject: str) -> str:
    """Prepare the set (once), train until done or stopped, and land the model in the project."""
    from fichero_server.llm.yolo_runtime import model_path
    from fichero_server.training.local import Gentle, _Stop
    from fichero_server.training.model_nodes import project_of
    from fichero_server.training.project_models import CARD, model_folder
    from fichero_server.training.yolo_set import export_region_set

    job_id = jobs.current_job_id()
    _state, detail = remote_job._row(db, job_id)
    request = TrainRegionsHereRequest(**detail["request"])
    work = remote_job._work_dir(job_id)
    data, out = work / "data", work / "out"
    if "training_set" not in detail:
        remote_job._save(db, job_id, detail, phase="preparing", reason="Preparing the corrected regions")
        if data.exists():
            shutil.rmtree(data)
        detail["training_set"] = export_region_set(db, scope_ids=request.scope_ids,
                                                   held_out_ids=request.held_out_ids, out_dir=data).summary()
    base = model_path(request.base)
    if base is None:
        raise RuntimeError(f"the layout model {request.base} is no longer on this Mac")
    resume = out / "run" / "weights" / "last.pt"
    gentle = Gentle(db, job_id, detail)
    gentle.measured.update({"device": "gpu", "batch_size": request.batch_size, "image_size": request.image_size})
    remote_job._save(db, job_id, detail, phase="training",
                     reason=f"Training on this Mac: epoch {gentle.epoch + 1}" + (" (resumed)" if resume.exists() else ""))
    started = time.monotonic()
    try:
        best, scores = TRAINER(str(base), data / "data.yaml", out, request, gentle,
                               resume=resume if resume.exists() else None)
    except _Stop as stop:
        gentle.record(time.monotonic() - started)
        gc.collect()
        if stop.kind == "cancel":
            remote_job._save(db, job_id, detail, phase="cancelled", reason=stop.reason)
            raise jobs.JobCancelled(stop.reason) from None
        reason = f"{stop.reason}; carries on from epoch {gentle.epoch + 1}"
        remote_job._save(db, job_id, detail, phase="waiting", reason=reason)
        raise jobs.JobDeferred(reason) from None
    gentle.record(time.monotonic() - started)
    gc.collect()

    remote_job._save(db, job_id, detail, phase="landing", reason="Adding the layout model to this project's models")
    model_id = f"{TRAINED_PREFIX}{job_id[:8]}"
    folder = model_folder(Path(db.path).parent, model_id)
    folder.mkdir(parents=True, exist_ok=True)
    shutil.copy2(best, folder / "model.pt")
    ts = detail["training_set"]
    card = {"id": model_id, "kind": "yolo", "display_name": request.name, "base": request.base,
            "training_set": ts, "held_out": ts["held_out"], "classes": ts["classes"],
            "scores": scores, "region_overlap_map50": scores.get("metrics/mAP50(B)"),
            "scored_on": "the training pages (none held out)" if ts["validated_on_training_pages"]
            else remote_job.counted(len(ts["held_out"]), "held-out page"),
            "target": "this-mac", "measured": dict(gentle.measured), "project": project_of(db)}
    (folder / CARD).write_text(json.dumps(card, indent=2), encoding="utf-8")
    detail["model_id"] = model_id
    remote_job._save(db, job_id, detail, phase="done", reason=f"Done: {model_id} finds regions in this project")
    return model_id


#: The trainer, a seam a test replaces (the real one trains for minutes).
TRAINER = train


def register_job_kinds() -> None:
    """Called by the scheduler before its first scan (`execution.jobs._KIND_MODULES`)."""
    from fichero_server.core.background_compute import set_utility_qos
    from fichero_server.training.local import request_cancel

    if KIND not in jobs.KINDS:
        jobs.register_kind(KIND, lambda db, subject: run(db, subject), model=MODEL, qos=set_utility_qos,
                           name="Train a layout model on this Mac", cancel=request_cancel)
