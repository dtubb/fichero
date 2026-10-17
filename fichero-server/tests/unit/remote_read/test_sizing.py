"""Batches sized from a measured rate (`compute.hpc.batches-fit-the-walltime`, the plan's GPU-hours)."""
from __future__ import annotations

import pytest

from fichero_server.remote_read.sizing import size_run


def test_a_batch_finishes_inside_the_shorter_walltime_class_with_margin():
    plan = size_run(100_000, pages_per_second=2.0, gpus_per_task=1)
    # 3 h class, 20% margin: 2.0 pages/s * 3600 * 3 * 0.8 = 17,280 pages a batch
    assert plan["walltime_class_hours"] == 3 and plan["shard_size"] == 17_280
    assert plan["shards"] == 6  # ceil(100000 / 17280)
    assert plan["gpu_hours"] == pytest.approx(100_000 / 2.0 / 3600, rel=0.01)


def test_a_slow_reader_means_more_shards_never_a_longer_class():
    slow = size_run(1_000, pages_per_second=0.05, gpus_per_task=2)  # the 3 h class fits 432 pages
    assert slow["walltime_class_hours"] == 3 and slow["shard_size"] == 432 and slow["shards"] == 3
    assert slow["gpu_hours"] == pytest.approx(1_000 / 0.05 / 3600 * 2, rel=0.01)
    one_shard = size_run(500, pages_per_second=0.05)
    assert one_shard["shards"] == 2  # 500 > 432


def test_no_measured_rate_means_no_plan():
    with pytest.raises(ValueError, match="pilot"):
        size_run(1_000, pages_per_second=0)
