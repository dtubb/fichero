"""A stage offers to tick only the jobs that run or can be done by hand (owner 2026-10-24).

WHY: ticking Find Lines also ticked "Put in order" and "Refine shapes", which nothing in Fichero does yet; every Ready
then listed them under Will not run, with nothing the person could do about it. A job the person ticks on its own is
still said under `by_hand` (test_setup_round_two).
"""

from fichero_server.recipes import stages
from fichero_server.recipes.start import BY_HAND_FIX, start_runs


def test_find_lines_offers_no_job_nothing_does():
    find_lines = next(s for s in stages.listing(None) if s["id"] == "find-lines")
    assert "find-lines" in find_lines["jobs"]
    assert not {"put-in-order", "refine-shapes"} & set(find_lines["jobs"])


def test_every_offered_job_runs_or_has_a_by_hand_tool():
    for stage in stages.listing(None):
        for job in stage["jobs"]:
            assert start_runs(job) or job in BY_HAND_FIX, (stage["id"], job)
