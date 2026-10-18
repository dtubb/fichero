"""`source.distil.each-step-has-a-method` (#5770, ruled: any recipe step with a model distils into a local model, each
by its own method; order read-a-line, review, regions, names).

WHY: the train offers were a per-job table with two jobs in it; review, statements and the rest had no word on how
(or whether) they distil.
"""
from __future__ import annotations

from fichero_server.recipes.jobs import all_jobs
from fichero_server.recipes.train_offers import WAYS, _ways, method_for


def _model_jobs():
    return [job for job in all_jobs() if "model" in job.settings]


def test_source_distil_each_step_has_a_method():
    """Every job whose step takes a model declares its distil method, or `none` with why."""
    for job in _model_jobs():
        method = method_for(job.id)
        assert method is not None, f"{job.id} declares no distil method"
        if method.student:
            assert method.teacher and method.trainer and method.measure, job.id
        else:
            assert method.why, f"{job.id}: a step with no method says why"


def test_the_train_offers_agree_with_the_declarations():
    """A job declaring a method has an available way to train it; one declaring none has none."""
    for job in _model_jobs():
        available = job.id in WAYS and any(w["available"] for w in _ways(job.id, stays_local=False))
        assert available == bool(method_for(job.id).student), job.id
    assert {j for j in WAYS if any(w["available"] for w in _ways(j, stays_local=False))} == {"read-a-line", "find-regions"}
    assert "spaCy" in method_for("find-names-tag-words").why and "#4642" in method_for("correct").why
