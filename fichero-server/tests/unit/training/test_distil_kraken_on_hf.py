# ruff: noqa: F811  (a fixture imported from another test file is used by name)
"""Kraken on Hugging Face, end to end, against a fake Hub (`distillation.md` Step 2.1, #5398, #5337).

The real half (a named machine, a real token, a real cap) is a run recorded in the review; nothing here submits a Job.
"""
from __future__ import annotations

import json

import pytest
import yaml

from fichero_server.training import job as training_job
from tests.unit.training.test_training_job import (  # noqa: F401  (fixtures)
    FakeHub, _request, _start, _subject, isolated, notebook,
)

pytestmark = pytest.mark.usefixtures("project_says_yes")


def _set_cap(test_package, cap):
    path = test_package / "recipe" / "setup.yaml"
    answers = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    answers["hf_spend_cap_usd"] = cap
    path.write_text(yaml.safe_dump(answers), encoding="utf-8")


def _queued(db):
    return db.execute_fetchone("SELECT count(*) FROM jobs WHERE kind = ?", [training_job.KIND])[0]


def test_a_cap_of_zero_refuses_a_training_start_in_words_before_anything_is_sent(db, notebook, test_package):
    """WHY: a $0 cap only held the offer; a direct start paid anyway."""
    _set_cap(test_package, 0)
    hub = FakeHub()
    with pytest.raises(training_job.OverTheCap, match=r"cap is \$0"):
        _start(db, notebook, hub)
    assert _queued(db) == 0 and hub.sent == [] and hub.submitted == []


def test_a_start_whose_price_times_limit_passes_the_cap_is_refused_with_the_sum(db, notebook, test_package):
    """WHY: the most a Job can cost is its hourly price times its time limit (0.4 x 4h = $1.60)."""
    _set_cap(test_package, 1.0)
    with pytest.raises(training_job.OverTheCap, match=r"\$1\.60.*\$1\.00"):
        _start(db, notebook, FakeHub())
    assert _queued(db) == 0


def test_a_start_under_the_cap_is_queued(db, notebook, test_package):
    _set_cap(test_package, 5.0)
    assert _start(db, notebook, FakeHub())["job_id"]


def test_spend_already_this_month_counts_against_the_cap(db, notebook, test_package):
    """WHY: a cap is a monthly ceiling; the second start must see the first (1.60 + 1.60 > 3)."""
    _set_cap(test_package, 3.0)
    _start(db, notebook, FakeHub())
    job_id = db.execute_fetchone("SELECT id FROM jobs WHERE kind = ?", [training_job.KIND])[0]
    _, detail = training_job._row(db, job_id)
    detail["far_id"] = "hf-job-1"  # the first one was sent
    db.execute("UPDATE jobs SET detail = ? WHERE id = ?", [json.dumps(detail), job_id])
    with pytest.raises(training_job.OverTheCap, match="this month"):
        _start(db, notebook, FakeHub())
