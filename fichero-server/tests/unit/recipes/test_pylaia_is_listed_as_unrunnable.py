"""A PyLaia reader on the Hub is listed as unable to run, with the real reason, never as a transformers model
(`source.onboard.model-search-pylaia-is-remote-only`). No network."""

from __future__ import annotations

from fichero_server.recipes import discovery, where_it_runs

LISTING = {"id": "acme/pylaia-latin-hand", "modelId": "acme/pylaia-latin-hand", "pipeline_tag": "image-to-text",
           "library_name": "pylaia", "tags": ["pylaia", "htr", "image-to-text", "la"]}


def test_a_pylaia_model_is_unrunnable_and_says_why_in_words():
    card = discovery._not_runnable_card(LISTING, "an HTR model", frozenset({"la"}))
    assert not card.runs_here
    assert "PyLaia" in card.offered_because and "torch 1.13" in card.cannot_run_because
    assert "transformers" not in card.offered_because


def test_every_place_says_no_for_it():
    card = discovery._not_runnable_card(LISTING, "an HTR model", frozenset({"la"}))
    options = where_it_runs.places_it_can_run(card, this_mac_gb=16, hf_ready=True, clusters=["c"])
    assert [o["can"] for o in options] == [False, False, False]
    assert all("torch 1.13" in o["why"] for o in options)
