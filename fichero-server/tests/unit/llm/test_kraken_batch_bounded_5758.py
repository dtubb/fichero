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
