"""#6430: a launch that opens several libraries runs at most `cap` opens together, first asked, first opened."""

import threading
import time

from fichero_server.db.manager import OpenGate


def _run(gate: OpenGate, n: int) -> list[int]:
    order: list[int] = []
    threads = []

    def one(i: int) -> None:
        with gate:
            order.append(i)
            time.sleep(0.05)

    for i in range(n):
        t = threading.Thread(target=one, args=(i,))
        threads.append(t)
        t.start()
        time.sleep(0.01)  # a deliberate order of asking
    for t in threads:
        t.join()
    return order


def test_four_opens_never_run_more_than_the_cap_together():
    gate = OpenGate(2)
    _run(gate, 4)
    assert gate.peak == 2


def test_the_library_asked_for_first_opens_first():
    assert _run(OpenGate(1), 4) == [0, 1, 2, 3]


def test_an_open_that_needs_another_library_does_not_deadlock_a_cap_of_one():
    gate = OpenGate(1)
    with gate:
        with gate:
            assert gate.peak == 1
