"""`recipes-run.order.done-in-order-shown` (#6186): pages read side by side finish out of order; the run's account counts
the first N consecutive pages finished in sidebar (fan-out) order, so progress reads alphanumerically, and a page finished
ahead is counted when the gap before it closes. A failed page closes its gap too (it is settled and listed).
WHY: dogfood B12, five Kraken pages at once: Activity's rows looked random."""
from __future__ import annotations

from fichero_server.workflows.run_account import build_account

FILES = [f"p{i:02d}.png" for i in range(6)]


def _state(finished: dict[int, str | None]) -> dict:
    """Index -> None (read) or an error, in the order the pages finished."""
    items = [{"index": i, "file": FILES[i], "document_id": f"d{i}", **({"error": e} if e else {"text": "x"})}
             for i, e in finished.items()]
    return {"files": FILES, "parallel_results": {"read": items}}


def test_a_page_finished_ahead_waits_for_the_gap_before_it():
    account = build_account(status="running", reason=None, state=_state({0: None, 2: None, 3: None}))
    assert account.pages_done == 3
    assert account.pages_done_in_order == 1  # page 1 is still reading


def test_the_gap_closing_counts_the_pages_after_it():
    account = build_account(status="running", reason=None, state=_state({0: None, 2: None, 3: None, 1: None}))
    assert account.pages_done_in_order == 4


def test_a_failed_page_closes_its_gap():
    account = build_account(status="running", reason=None, state=_state({0: None, 1: "model stopped", 2: None}))
    assert account.pages_done_in_order == 3


def test_a_run_done_in_one_call_is_all_in_order():
    state = {"files": FILES, "outputs": {"names": {"summary": {"documents_processed": 6}}}}
    assert build_account(status="completed", reason=None, state=state).pages_done_in_order == 6


def test_results_keyed_by_file_count_in_order_too():
    items = [{"file": FILES[i], "text": "x"} for i in (0, 1, 3)]
    account = build_account(status="running", reason=None, state={"files": FILES, "parallel_results": {"read": items}})
    assert account.pages_done_in_order == 2
