"""Training a Kraken reader on this Mac, gently (`compute.tune.on-this-mac`, `compute.tune.measured-on-16gb`, #5397).

The same card as the Hugging Face path (`training/job.py`): the same training set
(`training/kraken_set.py`), the same `ketos train` settings, and the same landing
(`training/landing.py`), so a reader trained here is the same kind of card as one trained there.
What differs is where it runs and how it shares the Mac:

* **On the local-model lane, as one heavy model** (kind `train-on-this-mac`, model `kraken:train`):
  nothing else heavy runs beside it, and Kraken's resident reader is let go before it starts.
* **In the engine's own process.** Not as a `ketos` child: a child of the sandboxed engine re-execs
  the signed stub, which hangs in `_libsecinit_appsandbox` (proven 2026-09-20, `llm/kraken_runtime.py`'s
  docstring), and forking a process that has torch loaded is unsafe. `ketos train` runs through its
  own click command, with two Lightning callbacks added.
* **Gentle, at every batch** (`activity.throttle.power-heat-memory`). While the Mac is in use, hot or on
  battery, training HOLDS where it is (no work lost, no CPU used; the row says why). When memory is
  tight, background work is paused, someone is waiting for other work on the lane, or the person
  cancels, it STOPS: memory is let go and the job goes back to waiting.
* **Resumes without repeating an epoch.** Every epoch ends in `last.ckpt`; a stopped or interrupted
  job (pause, quit, crash) resumes from it with `ketos train --resume`. Checked on Kraken 7.1.1
  (2026-10-04, S18): resuming from epoch 0's checkpoint trains epoch 1 only. A stop mid-epoch redoes
  that epoch's batches, never a finished epoch.
* **Utility QoS, bounded threads** (`embed_threads()`, about half the cores), one data worker (no
  worker processes, for the same sandbox reason). CPU: Kraken's CTC loss has no Apple GPU kernel
  (measured 2026-10-04: `-d mps` fails with `aten::_ctc_loss` not implemented).
* **Measured** (`compute.tune.measured-on-16gb`): the engine's resident memory is sampled during
  training; the peak, what training added, the device, the threads, the epochs and the time are kept
  on the job and on the landed card, never typed by hand.
"""
from __future__ import annotations

import ctypes
import ctypes.util
import gc
import json
import shutil
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from fichero_server.execution import jobs
from fichero_server.training import job as remote_job
from fichero_server.training.job import TrainKrakenHereRequest

KIND = "train-on-this-mac"
MODEL = "kraken:train"
DEVICE = "cpu"
#: How often the gentle callback looks at the Mac and the row, at most (it runs at every batch).
CHECK_SECONDS = 2.0
#: How long training holds before it looks again.
HOLD_SECONDS = 2.0


class _Stop(Exception):
    def __init__(self, kind: str, reason: str):
        super().__init__(reason)
        self.kind = kind  # "cancel" or "defer"
        self.reason = reason


def start(db: Any, request: TrainKrakenHereRequest, *, started_by: str) -> dict[str, Any]:
    """Queue a training job on this Mac; it starts when the lane and the Mac allow. A base reader
    that is not installed is refused now, not after the set is prepared."""
    if request.base:
        from fichero_server.llm.kraken_runtime import resolve_recognition_model

        resolve_recognition_model(request.base)
    detail = {"card": "kraken-here", "request": request.model_dump(), "phase": "waiting",
              "history": [{"phase": "waiting", "at": remote_job._now()}]}
    job_id = jobs.enqueue(db, KIND, f"training:{uuid.uuid4()}", started_by=started_by, detail=json.dumps(detail))
    return {"job_id": job_id}


def request_cancel(db: Any, job_id: str) -> str:
    """One not started yet ends now; a running one stops at its next batch."""
    state, detail = remote_job._row(db, job_id)
    if state in ("waiting", "paused"):
        jobs.cancel_waiting(db, job_id)
        return "cancelled"
    if state == "running":
        detail["cancel"] = True
        remote_job._save(db, job_id, detail, reason="Stopping at the next step")
    return state


def resident_bytes() -> int | None:
    """This process's resident memory now (mach `task_info`), or None off macOS."""
    class _Info(ctypes.Structure):
        _fields_ = [("virtual_size", ctypes.c_uint64), ("resident_size", ctypes.c_uint64),
                    ("resident_size_max", ctypes.c_uint64), ("user_time", ctypes.c_int * 2),
                    ("system_time", ctypes.c_int * 2), ("policy", ctypes.c_int), ("suspend_count", ctypes.c_int)]

    try:
        libsystem = ctypes.CDLL(ctypes.util.find_library("System"))
        info, count = _Info(), ctypes.c_uint(ctypes.sizeof(_Info) // 4)
        if libsystem.task_info(ctypes.c_uint.in_dll(libsystem, "mach_task_self_"), 20,
                               ctypes.byref(info), ctypes.byref(count)) != 0:
            return None
    except (OSError, ValueError, AttributeError):
        return None
    return int(info.resident_size)


class Gentle:
    """What the trainer calls at every batch and epoch: hold, stop, or go on; and the measurements."""

    def __init__(self, db: Any, job_id: str, detail: dict[str, Any]):
        self.db, self.job_id, self.detail = db, job_id, detail
        self.measured = detail.setdefault("measured", {})
        self.baseline = resident_bytes()
        self.peak = self.baseline or 0
        self.epoch = int(self.measured.get("epochs_done", 0))
        self._checked = 0.0
        self._holding: str | None = None

    def verdict(self) -> tuple[str, str] | None:
        from fichero_server.execution.throttle import MEMORY_REASON, why_wait

        row = jobs.read_job(self.db, self.job_id)
        if row and json.loads(row["detail"] or "{}").get("cancel"):
            return "cancel", "Stopped by you"
        if jobs.is_paused():
            return "defer", "Paused by you"
        if jobs._scheduler.someone_is_waiting():
            return "defer", "Stepped aside for work someone is waiting for"
        reason = why_wait(person_waiting=False)
        if reason == MEMORY_REASON:
            return "defer", reason
        return ("hold", reason) if reason else None

    def on_batch(self) -> None:
        now = resident_bytes()
        if now:
            self.peak = max(self.peak, now)
        if time.monotonic() - self._checked < CHECK_SECONDS:
            return
        while True:
            self._checked = time.monotonic()
            verdict = self.verdict()
            if verdict is None:
                if self._holding:
                    self._say(f"Training: epoch {self.epoch + 1}")
                    self._holding = None
                return
            kind, reason = verdict
            if kind in ("cancel", "defer"):
                raise _Stop(kind, reason)
            if self._holding != reason:
                self._say(f"{reason} (training holds in epoch {self.epoch + 1})")
                self._holding = reason
            time.sleep(HOLD_SECONDS)

    def on_epoch_end(self, epoch: int) -> None:
        self.epoch = epoch + 1
        self.measured["epochs_done"] = self.epoch
        self._say(f"Training: epoch {self.epoch} done")

    def _say(self, reason: str) -> None:
        remote_job._save(self.db, self.job_id, self.detail, reason=reason)

    def record(self, seconds: float) -> None:
        mb = 1 << 20
        self.measured["peak_resident_mb"] = max(int(self.measured.get("peak_resident_mb", 0)), self.peak // mb)
        if self.baseline:
            self.measured["added_by_training_mb"] = max(int(self.measured.get("added_by_training_mb", 0)),
                                                        (self.peak - self.baseline) // mb)
        self.measured["seconds"] = round(float(self.measured.get("seconds", 0.0)) + seconds, 1)


def ketos_args(request: TrainKrakenHereRequest, data: Path, out: Path, *, base_file: str | None,
               resume: Path | None, threads: int) -> list[str]:
    """`ketos` arguments: the Hugging Face trainer's settings (`hf_kraken_train.py`), sized for a Mac."""
    args = ["-d", DEVICE, "--threads", str(threads), "--workers", "0", "train", "-f", "page", "-B",
            str(request.batch_size), "-p", "0.9", "-o", str(out)]
    if request.epochs:
        args += ["-q", "fixed", "-N", str(request.epochs)]
    else:
        args += ["-q", "early", "--min-epochs", "5", "--lag", "5"]
    if resume is not None:
        args += ["--resume", str(resume)]
    elif base_file:
        args += ["-i", str(data / "base" / base_file), "--resize", "union"]
    return [*args, *sorted(str(p) for p in data.glob("*.xml"))]


def train_in_process(argv: list[str], out: Path, gentle: Gentle) -> None:
    """Run `ketos <argv>` here, through the Kraken seam, with the gentle callbacks and an
    end-of-epoch `last.ckpt` added."""
    from fichero_server.llm.kraken_runtime import train_recognition

    train_recognition(argv, out, on_batch=gentle.on_batch, on_epoch_end=gentle.on_epoch_end)


#: The trainer the job calls (tests put a fake here).
TRAINER: Callable[[list[str], Path, Gentle], None] = train_in_process


def run(db: Any, subject: str) -> str:
    """Prepare the set (once), train until done or stopped, and land the reader."""
    from fichero_server.core.background_compute import embed_threads
    from fichero_server.llm.kraken_runtime import resolve_recognition_model
    from fichero_server.training.kraken_set import export_training_set
    from fichero_server.training.landing import land_trained_reader

    job_id = jobs.current_job_id()
    _state, detail = remote_job._row(db, job_id)
    request = TrainKrakenHereRequest(**detail["request"])
    work = remote_job._work_dir(job_id)
    data, out = work / "data", work / "out"

    if "training_set" not in detail:
        remote_job._save(db, job_id, detail, phase="preparing", reason="Preparing the training set")
        if data.exists():
            shutil.rmtree(data)
        made = export_training_set(db, scope_ids=request.scope_ids, teacher=request.teacher,
                                   held_out_ids=request.held_out_ids, out_dir=data)
        detail["training_set"] = made.summary()
        if request.base:
            base_path = Path(resolve_recognition_model(request.base)[0])
            (data / "base").mkdir()
            shutil.copy2(base_path, data / "base" / base_path.name)
            detail["base_file"] = base_path.name

    jobs._release_kraken()  # no resident Kraken reader beside the trainer
    resume = out / "last.ckpt"
    threads = max(1, embed_threads())
    argv = ketos_args(request, data, out, base_file=detail.get("base_file"),
                      resume=resume if resume.exists() else None, threads=threads)
    gentle = Gentle(db, job_id, detail)
    gentle.measured.update({"device": DEVICE, "threads": threads, "batch_size": request.batch_size})
    remote_job._save(db, job_id, detail, phase="training",
                     reason=f"Training on this Mac: epoch {gentle.epoch + 1}" + (" (resumed)" if resume.exists() else ""))
    started = time.monotonic()
    try:
        TRAINER(argv, out, gentle)
    except _Stop as stop:
        gentle.record(time.monotonic() - started)
        (out / "checkpoint_abort.ckpt").unlink(missing_ok=True)  # resume from the epoch's end, not mid-epoch
        gc.collect()
        if stop.kind == "cancel":
            remote_job._save(db, job_id, detail, phase="cancelled", reason=stop.reason)
            raise jobs.JobCancelled(stop.reason) from None
        reason = f"{stop.reason}; carries on from epoch {gentle.epoch + 1}"
        remote_job._save(db, job_id, detail, phase="waiting", reason=reason)
        raise jobs.JobDeferred(reason) from None
    gentle.record(time.monotonic() - started)
    gc.collect()

    remote_job._save(db, job_id, detail, phase="landing", reason="Adding the reader to this Mac's Kraken readers")
    ts = detail["training_set"]
    card = {
        "display_name": request.display_name or f"{request.name} (taught by {request.teacher}, on this Mac)",
        "summary": (f"Taught by {request.teacher} on {ts['pages']} pages ({ts['lines']} lines, none checked by a "
                    f"person), trained on this Mac; {len(request.held_out_ids)} pages held out as the test."),
        "teacher": request.teacher, "training_set": ts, "held_out": ts.get("held_out", []), "base": request.base,
        "target": "this-mac", "measured": dict(gentle.measured),
        "not_for_release": request.not_for_release,
        "release_note": request.release_note or (remote_job.NOT_FOR_RELEASE_NOTE if request.not_for_release else None),
    }
    reader_id = land_trained_reader(out, job_id=job_id, model_name=request.name, card=card)
    detail["reader_id"] = reader_id
    remote_job._save(db, job_id, detail, phase="done", reason=f"Done: {reader_id} is ready to read with")
    return reader_id


def register_job_kinds() -> None:
    """Called by the scheduler before its first scan (`execution.jobs._KIND_MODULES`)."""
    from fichero_server.core.background_compute import set_utility_qos

    if KIND not in jobs.KINDS:
        jobs.register_kind(KIND, lambda db, subject: run(db, subject), model=MODEL, qos=set_utility_qos,
                           name="Train a reader on this Mac", cancel=request_cancel)
