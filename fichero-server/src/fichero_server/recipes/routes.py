"""What can we do with this many pages? Routes side by side (`source.onboard.routes-for-the-volume`).

Three routes for one volume: the cloud teacher reads it all; a reader on this Mac reads it all; or
distil (the teacher labels a sample, a small model trains, then reads the whole volume). Every
figure says where it came from, so nothing is a guess dressed as a fact:

* ``measured``: from this project's own finished job rows (the median seconds per page a model took
  here) or a local run's zero cost;
* ``estimate``: the vendored price list times the per-page token assumption the Start plan prices
  with (`recipes/start.py`);
* ``unknown``: no basis yet (a cloud model's wall-clock time, a training run's hours, accuracy
  before a bake-off). Shown as unknown, never filled in.
"""
from __future__ import annotations

import statistics
from typing import Any

from fichero_server.recipes.start import _TOKENS_IN, _TOKENS_OUT

#: The most recent finished pages a speed is measured over.
SPEED_SAMPLE = 200


def _figure(value: float | None, basis: str, source: str) -> dict[str, Any]:
    return {"value": value, "basis": basis if value is not None else "unknown", "from": source}


def measured_seconds_per_page(db, model: str) -> float | None:
    """The median seconds a page took for `model` on this Mac, from its finished job rows."""
    from fichero_server.execution.jobs import finished_seconds

    seconds = finished_seconds(db, model, limit=SPEED_SAMPLE)
    return statistics.median(seconds) if seconds else None


def _cloud_cost(teacher: str, pages: int) -> float | None:
    from fichero_server.workflows.model_comparison import estimate_cost

    provider, _, model = teacher.partition("/")
    return estimate_cost(model, pages * _TOKENS_IN, pages * _TOKENS_OUT, provider=provider)


def _local_time(db, reader: str, pages: int) -> dict[str, Any]:
    per_page = measured_seconds_per_page(db, reader)
    return _figure(None if per_page is None else per_page * pages, "measured",
                   f"median of this Mac's finished '{reader}' pages")


def routes_for_volume(db, pages: int, *, teacher: str, local_reader: str,
                      sample_pages: int) -> list[dict[str, Any]]:
    """The routes for `pages`, each with cost, time and accuracy figures that name their basis.

    `teacher` is a cloud model as provider/model; `local_reader` a model id as job rows record it
    (for example ``kraken:kraken-zenodo-21788410``); `sample_pages` how many pages the teacher labels
    on the distil route (capped at the volume)."""
    sample = min(sample_pages, pages)
    unmeasured_accuracy = _figure(None, "measured", "this project's checked pages (run the bake-off)")
    teacher_cost = _figure(_cloud_cost(teacher, pages), "estimate", "price list x per-page tokens")
    return [
        {"id": "cloud", "title": f"Read it all with {teacher}", "pages": pages,
         "cost_usd": teacher_cost,
         "time_seconds": _figure(None, "measured", "a cloud model's speed is not measured yet"),
         "accuracy_cer": unmeasured_accuracy, "leaves_this_mac": True},
        {"id": "this-mac", "title": f"Read it all on this Mac with {local_reader}", "pages": pages,
         "cost_usd": _figure(0.0, "measured", "runs on this Mac"),
         "time_seconds": _local_time(db, local_reader, pages),
         "accuracy_cer": unmeasured_accuracy, "leaves_this_mac": False},
        {"id": "distil", "title": f"Distil {teacher} into a small model, then read it all", "pages": pages,
         "steps": [
             {"step": "label a sample", "pages": sample,
              "cost_usd": _figure(_cloud_cost(teacher, sample), "estimate", "price list x per-page tokens")},
             {"step": "train the small model",
              "cost_usd": _figure(None, "estimate", "the target's price per hour x training hours"),
              "time_seconds": _figure(None, "measured", "no training run measured yet")},
             {"step": "read it all with the small model", "pages": pages,
              "cost_usd": _figure(0.0, "measured", "runs on this Mac"),
              # A fine-tuned reader keeps its base's network, so its base's measured speed is its own.
              "time_seconds": _local_time(db, local_reader, pages)},
         ],
         "accuracy_cer": unmeasured_accuracy, "leaves_this_mac": True},
    ]
