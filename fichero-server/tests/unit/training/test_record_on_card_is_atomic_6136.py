"""#6136 (`distill.eval.card-writes-are-atomic`): evaluations finishing together all land on the card, which always parses.

record_on_card was read, append, write_text: two evaluations read the same card and wrote back one entry each, or one read a
half-written file ('JSONDecodeError: Extra data', four flaky reds in the gate)."""
from __future__ import annotations

import json
import threading

from fichero_server.training import evaluation


def test_n_threads_recording_on_one_card_leave_a_card_that_parses_with_all_of_them(tmp_path, monkeypatch):
    card = tmp_path / "card.json"
    monkeypatch.setattr(evaluation, "card_path", lambda model, reader: card)
    n = 40
    start = threading.Barrier(n)
    errors: list[BaseException] = []

    def record(i: int) -> None:
        try:
            start.wait()
            evaluation.record_on_card("m", "kraken", {"run": i, "padding": "x" * 5000})
        except BaseException as exc:  # noqa: BLE001 -- a worker's failure is the test's to report
            errors.append(exc)

    threads = [threading.Thread(target=record, args=(i,)) for i in range(n)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert not errors, errors[0]
    saved = json.loads(card.read_text(encoding="utf-8"))
    assert sorted(e["run"] for e in saved["evaluations"]) == list(range(n))
    assert [p.name for p in tmp_path.iterdir()] == ["card.json"], "no temp file is left behind"


def test_a_card_that_does_not_parse_is_still_never_overwritten(tmp_path, monkeypatch):
    card = tmp_path / "card.json"
    card.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(evaluation, "card_path", lambda model, reader: card)
    try:
        evaluation.record_on_card("m", "kraken", {"run": 1})
    except ValueError:
        pass
    assert card.read_text(encoding="utf-8") == "{not json"
    assert [p.name for p in tmp_path.iterdir()] == ["card.json"]
