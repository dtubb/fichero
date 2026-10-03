"""A line's stored reading is not offered a second time as its run's own echo.

WHY: a run that writes its pass also keeps its artifact, so every line came back twice -- the
stored reading and a provisional copy of the same words -- and Fichero's PAGE export wrote two
identical TextEquivs per line into a distillation training set (found 2026-10-03 on the Sergio
notebooks). A CORRECTION is different: the machine's original then still stands beside it as
history, so only a word-for-word echo is dropped.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fichero_server.api.routes.document.segment_readings import ReadingRead, _not_already_stored


def _r(text, *, provisional, kind="transcription", rid=None):
    return ReadingRead(id=rid or f"{'p' if provisional else 's'}-{text}", provisional=provisional,
                       document_id="d", segment_id="s", kind=kind, content=text,
                       provenance_kind="workflow", created_at=datetime(2026, 10, 3, tzinfo=timezone.utc))


def test_an_echo_of_the_stored_reading_is_dropped():
    stored = [_r("por la mitad mas o menos", provisional=False)]
    assert _not_already_stored(stored, [_r("por la mitad mas o menos", provisional=True)]) == []


def test_a_corrected_line_keeps_the_machines_original_beside_it():
    stored = [_r("por la mitad más o menos", provisional=False)]
    original = [_r("por la mitad mas o menos", provisional=True)]
    assert _not_already_stored(stored, original) == original


def test_the_same_words_under_another_kind_are_not_an_echo():
    stored = [_r("vende", provisional=False, kind="translation")]
    original = [_r("vende", provisional=True)]
    assert _not_already_stored(stored, original) == original
