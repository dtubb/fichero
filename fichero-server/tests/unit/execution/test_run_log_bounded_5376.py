"""A run's log is bounded in memory (#5376, `activity.run.log-is-bounded`): the first and latest lines are held, the middle
counted; a node boundary appends only the lines since the last flush, by absolute index."""
from fichero_server.execution.run_log import BoundedLog


def _log(n, head=3, tail=4):
    log = BoundedLog(head=head, tail=tail)
    for i in range(n):
        log.append(f"l{i}")
    return log


def test_a_short_log_is_whole():
    log = _log(5)
    assert log.text() == "l0\nl1\nl2\nl3\nl4" and log.omitted == 0 and len(log) == 5


def test_a_long_log_holds_the_head_and_the_tail_and_counts_the_rest():
    log = _log(100)
    assert len(log) == 100 and log.omitted == 93
    assert log.text() == "l0\nl1\nl2\n… 93 log lines omitted …\nl96\nl97\nl98\nl99"


def test_since_returns_new_lines_by_absolute_index():
    log = _log(10)
    flushed = len(log)
    for i in range(10, 13):
        log.append(f"l{i}")
    assert log.since(flushed) == ["l10", "l11", "l12"]


def test_memory_does_not_grow_with_the_run():
    log = _log(50_000, head=200, tail=1800)
    assert len(log.since(0)) == 2000 and len(log) == 50_000


def test_the_runner_keeps_its_log_in_one():
    import inspect

    from fichero_server.execution import runner

    src = inspect.getsource(runner)
    assert "execution_log_lines = BoundedLog()" in src and "list(execution_log_lines)" not in src


def test_the_complete_frame_omits_big_final_state_values():
    from fichero_server.execution.run_log import bounded_final_state

    got = bounded_final_state({"small": [1], "big": "x" * 5000}, limit=100)
    assert got["small"] == [1] and got["big"] == {"omitted": 5002}
    assert bounded_final_state(None) is None
