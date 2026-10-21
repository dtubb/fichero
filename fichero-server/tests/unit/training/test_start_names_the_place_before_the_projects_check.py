"""`training.job.start` set `where` only inside the refusal branch, so a request that said yes to leaving hit an UnboundLocalError at
the project's own check (cand 14 gate, 29 tests). The place is named before either use."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from fichero_server.recipes import places
from fichero_server.training import job as training_job


class _Stop(Exception):
    pass


@pytest.mark.parametrize("place,words", [(training_job.TARGET, "Hugging Face"), ("rorqual", "the cluster rorqual")])
def test_a_request_that_may_leave_reaches_the_projects_check_naming_the_place(monkeypatch, place, words):
    seen = []

    def check(_db, what):
        seen.append(what)
        raise _Stop

    monkeypatch.setattr(training_job, "_place_of", lambda _r: place)
    monkeypatch.setattr(places, "refusal", lambda _p: None)
    monkeypatch.setattr(training_job, "_project_must_agree", check)
    with pytest.raises(_Stop):
        training_job.start(None, SimpleNamespace(pages_may_leave=True, scope_ids=["a"]), started_by="t")
    assert seen == [f"Training on {words}"]


def test_a_request_that_may_not_leave_is_still_refused_in_words(monkeypatch):
    monkeypatch.setattr(training_job, "_place_of", lambda _r: training_job.TARGET)
    with pytest.raises(training_job.PagesMayNotLeave, match="Hugging Face"):
        training_job.start(None, SimpleNamespace(pages_may_leave=False, scope_ids=["a"]), started_by="t")
