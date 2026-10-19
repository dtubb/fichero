"""A job set aside after its interruptions says so once, short, and a job waiting on it does not repeat the reason
(#5844, `activity.set-aside-said-once`)."""
from __future__ import annotations

from fichero_server.execution import jobs


def test_a_set_aside_reason_is_one_short_sentence_with_no_clock():
    said = jobs.set_aside_reason(3)

    assert said == "Stopped 3 times by the engine stopping; set aside. Resume to carry on."
    assert "UTC" not in said


def test_the_row_still_offers_resume_and_a_row_stored_before_still_does(db):
    jobs.load_kinds()
    kind = next(k for k, v in jobs.KINDS.items() if v.run is not None and not v.no_retry)
    assert jobs.offer_for(kind, "failed", jobs.set_aside_reason(3)) == jobs.RESUME
    assert jobs.offer_for(kind, "failed", "Interrupted 3 times: the engine stopped while it ran") == jobs.RESUME
    assert jobs.offer_for(kind, "failed", "the provider refused") is None


def test_a_job_waiting_on_a_set_aside_thumbnail_does_not_repeat_its_reason(db):
    jobs._ensure(db)
    job_id = jobs._insert(db, "thumb-5844", "p1", None, "automatic")
    db.execute("UPDATE jobs SET state = 'failed', finished_at = now(), reason = ? WHERE id = ?",
               [jobs.set_aside_reason(3), job_id])

    said = jobs.first_reason(db, ["thumb-5844"], "2000-01-01")

    assert said == "Waiting for thumbnails (set aside)"
    assert "Stopped 3 times" not in said


def test_other_thumbnail_failures_are_still_named_in_the_wait(db):
    jobs._ensure(db)
    job_id = jobs._insert(db, "thumb-5844", "p1", None, "automatic")
    db.execute("UPDATE jobs SET state = 'failed', finished_at = now(), reason = 'the file is damaged' WHERE id = ?",
               [job_id])

    assert "the file is damaged" in jobs.first_reason(db, ["thumb-5844"], "2000-01-01")
