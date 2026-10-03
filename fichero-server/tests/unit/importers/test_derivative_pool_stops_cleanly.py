"""Exit never waits for queued derivative stages (#5223).

WHY: the old pool's worker threads were not daemons, so Python's exit joined them, and they ran
every queued thumbnail and embed stage first. A test file that imported a folder passed in 14 s and
then sat at exit -- at background QoS, embedding pages of libraries pytest had already deleted --
until it was killed; a gate running such a file would hang. The stages are jobs now (#5353): rows
run by the job scheduler's DAEMON threads, so exit never joins them, and a stage not yet run stays
a waiting row for the next open instead of running at exit. If this regresses, queued stages run at
exit again.
"""

from __future__ import annotations

from fichero_server.execution import jobs
from fichero_server.importers import derivatives


def test_the_threads_that_run_derivative_stages_never_hold_up_exit():
    derivatives.register_job_kinds()
    jobs._scheduler.wake(None)
    lanes = {jobs.KINDS[kind].lane for kind in (derivatives.THUMBNAIL_KIND, derivatives.EMBED_KIND,
                                                 derivatives.NLP_KIND)}
    threads = [t for lane in lanes for t in jobs._scheduler.lanes[lane].threads]
    assert threads and all(t.daemon for t in threads)


def test_the_test_session_stops_the_pool_with_its_queue_dropped():
    """The hook is what makes a test run exit; a moved or deleted call would bring the hang back."""
    from pathlib import Path

    conftest = (Path(__file__).resolve().parents[2] / "conftest.py").read_text(encoding="utf-8")
    finish = conftest.split("def pytest_sessionfinish", 1)[1].split("\ndef ", 1)[0]
    assert "derivatives.shutdown(wait=False, cancel_pending=True)" in finish
