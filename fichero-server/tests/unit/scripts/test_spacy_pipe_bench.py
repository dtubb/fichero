"""The spaCy `pipe` bench builds the same page-sized passages every run (scripts/spacy_pipe_bench.py); it is run on the M4, not here."""
from __future__ import annotations

import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("spacy_pipe_bench", Path(__file__).resolve().parents[4] / "scripts" / "spacy_pipe_bench.py")
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)


def test_a_passage_is_at_least_the_asked_words_and_the_same_every_time():
    text = bench.passage(150, 3)
    assert len(text.split()) >= 150
    assert text == bench.passage(150, 3) and text != bench.passage(150, 4)


def test_the_bar_is_one_and_a_half_times():
    assert bench.CLEARS == 1.5
