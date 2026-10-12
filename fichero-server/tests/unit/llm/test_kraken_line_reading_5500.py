"""A line Kraken reads carries its own reading and nothing else (#5500), tested to the spec:
`source.reading.kraken-line-is-its-own` (docs/contributor_manual/specs/source/readings-and-apparatus.md).

WHY: on Sergio's ruled notebook pages every line carried a second reading shifted by one line break, 11 of 48 lines
(Kraken found the paper's rulings) read empty, and no reading carried a confidence. Kraken itself is stubbed at its
one seam (`recognize_lines`); the geometry and the slicing are the engine's own.
"""

from __future__ import annotations

from fichero_server.llm import kraken_runtime


def _line(y: int, text: str, confidence: float | None = None) -> dict:
    line = {"polygon": [[10, y], [500, y], [500, y + 30], [10, y + 30]], "baseline": [[10, y + 25], [500, y + 25]],
            "text": text}
    if confidence is not None:
        line["confidence"] = confidence
    return line


def test_each_line_is_its_own_slice_and_an_empty_line_has_no_place_in_the_text(monkeypatch):
    monkeypatch.setattr(kraken_runtime, "recognize_lines", lambda path, model: {
        "width": 600, "height": 400, "regions": [],
        "lines": [_line(10, "Primera linea", 0.9), _line(50, ""), _line(90, "Segunda linea", 0.7)]})

    result = kraken_runtime.recognize_to_geometry("page.png", "model.mlmodel", model_id="kraken-test")

    assert result.text == "Primera linea\nSegunda linea"  # the ruled line adds no blank line to the text
    read = [b for b in result.boxes if b.text]
    assert [result.text[b.char_start:b.char_end] for b in read] == ["Primera linea", "Segunda linea"]
    (ruled,) = [b for b in result.boxes if not b.text]
    assert ruled.char_start is None and ruled.char_end is None  # its shape is kept, with no reading
    assert [b.confidence for b in read] == [0.9, 0.7]


def test_the_confidence_is_the_mean_of_the_lines_characters():
    class Record:
        prediction = "dios"
        confidences = [0.9, 0.8, 1.0, 0.7]

    assert kraken_runtime._line_confidence(Record()) == 0.85
    assert kraken_runtime._line_confidence(type("R", (), {"prediction": "x", "confidences": []})()) is None
