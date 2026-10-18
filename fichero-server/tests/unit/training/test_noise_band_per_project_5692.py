"""`source.train.noise-band-per-project` (#5692, ruled Q6 2026-10-17): a project's noise band is the CER spread over
three held-out splits of its corrected pages, 0.5 CER points until measured; stored with the project and served on
every train offer, so a comparison says when a difference is noise.

WHY: nothing measured, stored or served one, so a trained model could be adopted on a difference within the noise.
"""
from __future__ import annotations

from fichero_server.recipes.project import read_noise_band, write_noise_band
from fichero_server.recipes.train_offers import train_offers
from fichero_server.training.evaluation import noise_band
from fichero_server.training.reasons_ab import NOISE_BAND


def _page(distance: int, chars: int = 100) -> dict:
    return {"read": True, "scores": {"default": {"cer": distance / chars, "distance": distance, "reference_chars": chars}}}


def test_the_band_is_the_cer_spread_over_three_splits(monkeypatch):
    import fichero_server.workflows.transcription_accuracy as ta

    monkeypatch.setattr(ta, "DEFAULT_POLICY_NAME", "default")
    # pages go to splits 0,1,2,0,1,2: split CERs 0.02, 0.05, 0.08 -> spread 0.06
    pages = [_page(2), _page(5), _page(8), _page(2), _page(5), _page(8)]
    assert round(noise_band(pages), 6) == 0.06
    assert noise_band(pages[:2]) is None  # fewer pages than splits: not measured


def test_until_measured_the_ruled_band_is_served_and_said_so(tmp_path):
    band = read_noise_band(tmp_path)
    assert band["value"] == NOISE_BAND == 0.005 and band["measured"] is False and "until" in band["basis"]
    write_noise_band(tmp_path, 0.012, pages=30, model="kraken-mccatmus")
    band = read_noise_band(tmp_path)
    assert band["value"] == 0.012 and band["measured"] is True and "30 pages" in band["basis"]


def test_every_train_offer_carries_the_projects_band():
    recipe = {"steps": [{"id": "read", "job": "read-a-line", "settings": {}}]}
    counts = {"pages": [], "unmarked": 0, "region_pages": 0, "scope_ids": [], "teacher": None}
    band = {"value": 0.012, "measured": True, "basis": "measured"}
    (offer,) = train_offers(recipe, counts, stays_local=True, noise_band=band)
    assert offer["noise_band"] == band
