"""source.recipe.reader-tiers.frontier-on-the-try-pages (#5922): the recommendation weighs frontier models as well as
local ones: the candidate that reads best by more than the project's noise band; a local or cheaper one within the band
of the best is recommended instead, and the reason is said in words, with the cost per page and for the whole set."""
from fichero_server.recipes import bakeoff


def row(card, name, cer, cost_set, *, local, measured=True):
    return {"card": card, "name": name, "cer": cer, "measured": measured and cer is not None, "local": local,
            "runs_on": "this Mac" if local else "OpenRouter",
            "cost_usd": {"value": cost_set, "basis": "estimate", "source": "price list"}}


FRONTIER = row("openrouter:anthropic/claude-fable", "Claude", 0.020, 80.0, local=False)
LOCAL = row("kraken:model", "Kraken", 0.045, 0.0, local=True)
VISION = row("apple:vision", "Apple Vision", 0.060, 0.0, local=True)
BAND = 0.01


def test_a_frontier_model_that_reads_better_by_more_than_the_band_is_recommended_with_its_cost():
    pick = bakeoff.recommend([FRONTIER, LOCAL, VISION], volume=400, noise_band=BAND)

    assert pick["card"] == FRONTIER["card"]
    assert pick["cost_per_page_usd"] == 0.2 and pick["cost_set_usd"] == 80.0
    assert "reads best" in pick["sentence"] and "$0.20 per page" in pick["sentence"] and "$80.00 for the 400 pages" in pick["sentence"]


def test_a_local_reader_within_the_band_of_the_best_is_recommended_and_the_reason_is_said():
    near = row("kraken:model", "Kraken", 0.027, 0.0, local=True)
    pick = bakeoff.recommend([FRONTIER, near, VISION], volume=400, noise_band=BAND)

    assert pick["card"] == "kraken:model"
    assert "within the noise band of Claude" in pick["sentence"]
    assert "$0.00 per page" in pick["sentence"] and "on this Mac" in pick["sentence"]


def test_the_band_is_the_projects_not_a_fixed_one_point():
    near = row("kraken:model", "Kraken", 0.045, 0.0, local=True)
    assert bakeoff.recommend([FRONTIER, near], volume=400, noise_band=0.01)["card"] == FRONTIER["card"]
    assert bakeoff.recommend([FRONTIER, near], volume=400, noise_band=0.03)["card"] == "kraken:model"


def test_a_cheaper_cloud_reader_within_the_band_beats_a_dearer_one():
    cheap = row("openrouter:google/gemini", "Gemini", 0.024, 5.0, local=False)
    pick = bakeoff.recommend([FRONTIER, cheap], volume=400, noise_band=BAND)
    assert pick["card"] == "openrouter:google/gemini"
    assert "within the noise band of Claude" in pick["sentence"]


def test_only_measured_readers_are_weighed_and_none_measured_is_no_recommendation():
    unmeasured = row("kraken:model", "Kraken", None, 0.0, local=True)
    assert bakeoff.recommend([unmeasured], volume=400, noise_band=BAND) is None
    assert bakeoff.recommend([unmeasured, FRONTIER], volume=400, noise_band=BAND)["card"] == FRONTIER["card"]


def test_an_unpriced_cloud_reader_is_recommended_without_inventing_a_price():
    unpriced = row("openrouter:new/model", "New", 0.010, None, local=False)
    pick = bakeoff.recommend([unpriced, LOCAL], volume=400, noise_band=BAND)
    assert pick["card"] == "openrouter:new/model"
    assert pick["cost_per_page_usd"] is None and "price not known" in pick["sentence"]
