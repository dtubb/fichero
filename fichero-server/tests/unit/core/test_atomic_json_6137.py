"""#6137 (`distill.card.every-writer-is-atomic`): a card write is whole or not at all, and the Reasons A/B entry shares the
lock an evaluation holds, so neither is lost."""
from __future__ import annotations

import json
import threading
from pathlib import Path

from fichero_server.core.atomic_json import write_json_atomic
from fichero_server.training import evaluation, reasons_ab


def test_write_json_atomic_leaves_the_file_whole_and_no_temp_file(tmp_path):
    path = tmp_path / "deep" / "card.json"
    write_json_atomic(path, {"a": 1})
    write_json_atomic(path, {"a": 2}, indent=None)
    assert json.loads(path.read_text(encoding="utf-8")) == {"a": 2}
    assert [p.name for p in path.parent.iterdir()] == ["card.json"]


def test_a_failed_write_keeps_the_old_card(tmp_path):
    path = tmp_path / "card.json"
    write_json_atomic(path, {"a": 1})
    try:
        write_json_atomic(path, {"a": object()})
    except TypeError:
        pass
    assert json.loads(path.read_text(encoding="utf-8")) == {"a": 1}
    assert [p.name for p in tmp_path.iterdir()] == ["card.json"]


def test_reasons_ab_and_evaluations_finishing_together_both_land(tmp_path, monkeypatch):
    from fichero_server.llm import mlx_model_store as store_module

    model = f"{store_module.TRAINED_ORG}/m"
    card = tmp_path / store_module.TRAINED_CARD
    card.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(evaluation, "card_path", lambda m, r: card)
    store = type("S", (), {"trained_dir": staticmethod(lambda m: Path(tmp_path))})()
    monkeypatch.setattr(store_module, "get_mlx_model_store", lambda: store)
    contender = type("C", (), {"model": model})()
    n = 20
    start = threading.Barrier(2 * n)

    def ab() -> None:
        start.wait()
        reasons_ab.record_on_cards({"r": 1}, [contender], held_out=[])

    def ev(i: int) -> None:
        start.wait()
        evaluation.record_on_card("m", "kraken", {"run": i})

    threads = [threading.Thread(target=ab) for _ in range(n)] + [threading.Thread(target=ev, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    saved = json.loads(card.read_text(encoding="utf-8"))
    assert len(saved["reasons_ab"]) == n and len(saved["evaluations"]) == n
