"""Batches and GPU-hours from a measured rate (`compute.hpc.batches-fit-the-walltime`, A2's plan).

A cluster schedules short jobs sooner, so a batch is sized to finish inside the shortest walltime class with a margin,
from the rate a pilot MEASURED; a slow reader means more shards, never a longer class. No measured rate, no plan.
"""
from __future__ import annotations

import math
from typing import Any

#: The site profile's walltime classes in hours (TO CONFIRM with the site; `compute.hpc.site-profiles`).
WALLTIME_CLASSES_HOURS = (3, 12)
#: Share of the class a batch may use: the rest absorbs a slow node, model load and the final write.
MARGIN = 0.8


def size_run(pages: int, *, pages_per_second: float, gpus_per_task: int = 1,
             classes_hours: tuple[int, ...] = WALLTIME_CLASSES_HOURS, margin: float = MARGIN) -> dict[str, Any]:
    if pages_per_second <= 0:
        raise ValueError("no measured rate: run the pilot first")
    hours = min(classes_hours)
    shard_size = max(1, int(pages_per_second * 3600 * hours * margin))
    return {"walltime_class_hours": hours, "shard_size": shard_size, "shards": math.ceil(pages / shard_size),
            "gpu_hours": pages / pages_per_second / 3600 * gpus_per_task}
