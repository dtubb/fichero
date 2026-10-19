"""The routes that send pages on a request's own yes also ask the app's places (#5831, review 214, `source.onboard.places-cap`).

WHY: #5828 capped every recipe use site through `places.may_leave_to`, but Read at Scale (ACENET and Hugging Face),
Training and Copy to another Mac sent pages on `pages_may_leave=yes` alone. Each now refuses in words, sending nothing,
when the app does not allow that place; with the place on, it works as before.
"""
from __future__ import annotations

import pytest

from fichero_server.models.compute_requests import ReadAtScaleRequest
from fichero_server.recipes import places
from fichero_server.remote_read import job as read_job
from fichero_server.remote_read.job import PagesMayNotLeave


@pytest.fixture
def only_this_mac(monkeypatch):
    monkeypatch.setattr(places, "get_places", lambda: ["this-mac"])


def _never_built():
    raise AssertionError("a target was built: pages would have been sent")


@pytest.mark.parametrize("target,place_words", [(read_job.TARGET, "Hugging Face"), ("a-cluster", "ACENET")])
def test_read_at_scale_is_refused_when_the_place_is_off(db, only_this_mac, target, place_words):
    request = ReadAtScaleRequest(scope_ids=["x"], card="c", pages_may_leave=True, target=target)
    with pytest.raises(PagesMayNotLeave) as refused:
        read_job.start(db, request, started_by="owner", target_factory=_never_built)
    assert place_words in str(refused.value)


def test_training_is_refused_when_the_place_is_off(db, only_this_mac):
    from fichero_server.models.compute_requests import TrainKrakenRequest
    from fichero_server.training import job as train_job

    request = TrainKrakenRequest(scope_ids=["x"], pages_may_leave=True)
    with pytest.raises(train_job.PagesMayNotLeave) as refused:
        train_job.start(db, request, started_by="owner", target_factory=_never_built)
    assert "Hugging Face" in str(refused.value)


def test_a_copy_to_another_mac_is_refused_when_the_place_is_off(only_this_mac):
    assert "another Mac of yours" in places.refusal("another-mac")
    assert places.refusal("this-mac") is None


def test_with_the_place_on_there_is_no_refusal(monkeypatch):
    monkeypatch.setattr(places, "get_places", lambda: list(places.PLACES))
    assert all(places.refusal(p) is None for p in places.PLACES)


def test_the_cloud_offer_line_says_to_allow_the_cloud_when_the_app_forbids_it(monkeypatch):
    """The offer said "letting pages leave this Mac" although the app forbids the cloud: letting them is not enough."""
    from fichero_server.recipes.assemble import Answers, assemble
    from tests.unit.recipes.test_assemble_by_rule import CARDS

    asked = Answers("search", frozenset({"es"}), frozenset({"Latn"}), "handwriting", pages=3000,
                    cloud_keys=frozenset({"google"}))
    for allowed, words in ((["this-mac"], "once you allow the cloud in Set Up Fichero"),
                           (list(places.PLACES), "letting pages leave this Mac")):
        monkeypatch.setattr(places, "get_places", lambda allowed=allowed: allowed)
        off = next(o for o in assemble(asked, CARDS)["left_off"] if o["job"] == "correct")
        assert words in off["sentence"], off
