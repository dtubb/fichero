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


def test_lines_found_but_all_read_empty_are_kept_not_thrown_away(monkeypatch):
    """M4 run 2026-10-17: page 1 had 30 lines, Kraken read every one as '' and the page was saved with no
    geometry at all: the lines were stored nowhere."""
    line = {"polygon": [[0, 0], [90, 0], [90, 20], [0, 20]], "baseline": [[0, 15], [90, 15]], "text": ""}
    monkeypatch.setattr(kraken_runtime, "recognize_lines",
                        lambda path, model: {"width": 100, "height": 100, "lines": [line, line], "regions": []})
    result = kraken_runtime.recognize_to_geometry("p.png", "m")
    lines = [b for b in result.boxes if str(b.level) == "line"]
    assert result.text == "" and len(lines) == 2 and all(b.metadata.get("page_read_nothing") for b in lines)
    some = dict(line, text="texto")
    monkeypatch.setattr(kraken_runtime, "recognize_lines",
                        lambda path, model: {"width": 100, "height": 100, "lines": [line, some], "regions": []})
    mixed = [b for b in kraken_runtime.recognize_to_geometry("p.png", "m").boxes if str(b.level) == "line"]
    assert all(b.metadata.get("page_has_readings") for b in mixed)
    monkeypatch.setattr(kraken_runtime, "recognize_lines",
                        lambda path, model: {"width": 100, "height": 100, "lines": [], "regions": []})
    assert not kraken_runtime.recognize_to_geometry("p.png", "m").boxes


def test_the_local_slot_reads_the_memory_each_time_not_once(monkeypatch):
    import asyncio

    from fichero_server.workflows import builder

    memory = {"gb": 64}
    monkeypatch.setattr(kraken_runtime, "_available_memory_bytes", lambda: memory["gb"] * GB)
    monkeypatch.setattr(builder, "_vision_fan_out_sem", None)
    monkeypatch.setattr(builder, "_GATE_POLL_SECONDS", 0.01)

    async def run():
        peak = 0
        async def one():
            nonlocal peak
            async with builder.vision_slot():
                peak = max(peak, builder._local_in_flight)
                await asyncio.sleep(0.05)
        memory["gb"] = 3  # the Mac is under pressure when the pages arrive: one at a time
        await asyncio.gather(*(one() for _ in range(4)))
        return peak

    assert asyncio.run(run()) == 1
