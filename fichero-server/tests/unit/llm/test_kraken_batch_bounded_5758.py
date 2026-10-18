"""The reader's batch is bounded by the memory the Mac has (#5758: the engine peaked at 18.2 GB on a 16 GB Mac)."""

from __future__ import annotations

from dataclasses import dataclass

from fichero_server.llm import kraken_runtime

GB = 1024**3


@dataclass
class _Config:
    accelerator: str = "cpu"
    device: int = 1
    num_line_workers: int = 0
    batch_size: int = 64


def test_the_batch_follows_the_available_memory(monkeypatch):
    sizes = {}
    for gb in (1, 4, 8, 16):
        monkeypatch.setattr(kraken_runtime, "_available_memory_bytes", lambda gb=gb: gb * GB)
        sizes[gb] = kraken_runtime.reader_batch_size()
    assert sizes[1] == 1 and 1 <= sizes[4] <= sizes[8] <= sizes[16] <= 16, sizes
    assert sizes[16] > sizes[1]


def test_the_batch_is_unknown_memory_safe(monkeypatch):
    monkeypatch.setattr(kraken_runtime, "_available_memory_bytes", lambda: None)
    assert kraken_runtime.reader_batch_size() == 1


def test_the_reader_config_carries_the_bound_when_kraken_takes_one(monkeypatch):
    monkeypatch.setattr(kraken_runtime, "_available_memory_bytes", lambda: 4 * GB)
    config = kraken_runtime._reader_config(_Config)
    assert config.batch_size == kraken_runtime.reader_batch_size() < 64
    assert config.num_line_workers == 0


def test_pages_read_at_once_follow_the_memory_and_never_exceed_the_cap(monkeypatch):
    sizes = {}
    for gb in (3, 6, 16, 64):
        monkeypatch.setattr(kraken_runtime, "_available_memory_bytes", lambda gb=gb: gb * GB)
        sizes[gb] = kraken_runtime.page_fan_out(4)
    assert sizes[3] == 1 and sizes[3] <= sizes[6] < sizes[64] == 4, sizes
    monkeypatch.setattr(kraken_runtime, "_available_memory_bytes", lambda: None)
    assert kraken_runtime.page_fan_out(4) == 1


def test_the_local_fan_out_semaphore_takes_the_memory_bound(monkeypatch):
    import asyncio

    from fichero_server.workflows import builder

    monkeypatch.setattr(kraken_runtime, "_available_memory_bytes", lambda: 3 * GB)

    async def size():
        return builder._get_vision_semaphore()._value

    monkeypatch.setattr(builder, "_vision_fan_out_sem", None)
    assert asyncio.run(size()) == 1
