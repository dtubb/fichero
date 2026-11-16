"""The tie reads a page's lines once per (image, reader, line shapes), and remembers only a few pages (#6127, review wide-4 M1)."""
from __future__ import annotations

from fichero_server.checking import tie_text
from fichero_server.llm import kraken_runtime


def _lines(n: int = 2, prefix: str = "a") -> list[dict]:
    return [{"id": f"{prefix}{i}", "polygon": [[0, i], [9, i], [9, i + 1]], "baseline": [[0, i], [9, i]]} for i in range(n)]


def test_same_image_model_and_shapes_are_read_once_across_copies(tmp_path, monkeypatch):
    image = tmp_path / "p.jpg"
    image.write_bytes(b"same bytes")
    copy = tmp_path / "copy.jpg"
    copy.write_bytes(b"same bytes")
    calls = []
    monkeypatch.setattr(kraken_runtime, "read_given_lines", lambda *a, **k: calls.append(a) or ["x", "y"])
    first = tie_text._read_once(image, "m", _lines(prefix="a"), None)
    second = tie_text._read_once(copy, "m", _lines(prefix="b"), None)  # another copy: its lines carry other ids
    assert first == second == ["x", "y"] and len(calls) == 1
    tie_text._read_once(copy, "other-model", _lines(), None)
    assert len(calls) == 2


def test_the_memory_is_bounded(tmp_path, monkeypatch):
    monkeypatch.setattr(kraken_runtime, "read_given_lines", lambda *a, **k: ["x"])
    for i in range(tie_text._MOST_READS_KEPT + 20):
        image = tmp_path / f"{i}.jpg"
        image.write_bytes(str(i).encode())
        tie_text._read_once(image, "m", _lines(1), None)
    assert len(tie_text._READS) == tie_text._MOST_READS_KEPT
