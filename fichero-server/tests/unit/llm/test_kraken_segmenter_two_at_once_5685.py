"""The blla segmenter is one resident object (`_resident("segment", "blla")`); two pages segmenting through it at once
must find what each finds alone (#5685, the follow-up to the reader's `_own_copy`: Kraken keeps a page's state on the
model). Real blla (it ships inside the kraken package), pages drawn with a different number of lines each."""
from __future__ import annotations

import threading

import pytest

from fichero_server.llm import kraken_runtime as kr


def _page(path, rows: int):
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (710, 925), "white")
    draw = ImageDraw.Draw(image)
    for row in range(rows):
        draw.text((40, 40 + row * 32), f"{rows:03} line {row} of a page of text to find and read", fill="black")
    image.save(path)
    return path


def _shape(found: dict) -> tuple:
    return (len(found["regions"]), sorted(tuple(map(tuple, ln["baseline"])) for ln in found["lines"]))


def test_two_pages_segmented_at_once_find_what_each_finds_alone(tmp_path):
    pytest.importorskip("kraken")
    pages = [_page(tmp_path / "a.png", 6), _page(tmp_path / "b.png", 18)]
    alone = [_shape(kr._segment_raw(p, None)) for p in pages]
    assert alone[0] != alone[1]
    for _round in range(4):
        got: dict[int, object] = {}
        barrier = threading.Barrier(2, timeout=60)

        def segment(i):
            barrier.wait()
            try:
                got[i] = _shape(kr._segment_raw(pages[i], None))
            except Exception as exc:  # noqa: BLE001 -- the failure is the finding
                got[i] = exc

        threads = [threading.Thread(target=segment, args=(i,)) for i in range(2)]
        [t.start() for t in threads]
        [t.join(120) for t in threads]
        assert [got.get(0), got.get(1)] == alone, f"round {_round}: {got}"
