"""`source.train.adopt-only-past-the-noise-band` (#5700, #5441, R4 exit): a reader Fichero trained becomes the
project's reader only when its CER on the held-out pages beats the best downloadable reader's by more than the
project's noise band; otherwise the downloadable one is kept, and the evaluation says why.

WHY: the evaluation measured a trained reader and wrote its score on the card, and nothing used it: a trained reader
was never set on the read step, and nothing stopped one that won by a difference inside the noise.
"""
from __future__ import annotations

from pathlib import Path

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_server.recipes.project import read_project_setup, write_noise_band, write_project_setup
from fichero_server.training.evaluation import adopt_trained

RECIPE = {"steps": [{"id": "read", "job": "read-a-line", "model": {"zenodo": "10.5281/zenodo.13788177"}}]}
TRAINED = "kraken-trained-abc123def456"


def _result(trained_cer: float, base_cer: float) -> dict:
    def row(model: str, role: str, cer: float) -> dict:
        return {"model": model, "reader": "kraken", "role": role, "measured": True, "pages_read": 20,
                "pages_total": 20, "scores": {"diplomatic": {"cer": cer}}}

    return {"ranked_by": "diplomatic", "models": [row(TRAINED, "trained", trained_cer),
                                                  row("kraken-mccatmus", "out of the box", base_cer)]}


def _setup(db) -> Path:
    library = Path(db.path).parent
    write_project_setup(library, {"purposes": ["transcribe"]}, RECIPE)
    write_noise_band(library, 0.01, pages=20, model="kraken-mccatmus")
    return library


def test_a_trained_reader_beyond_the_band_becomes_the_read_steps_reader(db):
    library = _setup(db)
    verdict = adopt_trained(db, _result(0.05, 0.08))
    assert verdict["adopted"] == TRAINED, verdict
    (override,) = read_project_setup(library)["recipe"]["overrides"]
    assert override["step"] == "read" and override["scope"] == "project"
    assert override["model"] == {"trained": TRAINED} and override["cer"] == 0.05
    assert "noise band" in override["because"] and "kraken-mccatmus" in override["because"]
    from fichero_server.recipes.cards import kraken_reader_for

    assert kraken_reader_for(override["model"]) == TRAINED  # Start reads with it


def test_a_win_inside_the_band_keeps_the_downloadable_reader_and_says_why(db):
    library = _setup(db)
    verdict = adopt_trained(db, _result(0.075, 0.08))
    assert verdict["adopted"] is None and "within the project's noise band" in verdict["why"], verdict
    assert not read_project_setup(library)["recipe"].get("overrides")


def test_a_trained_reader_worse_than_the_downloadable_one_is_not_adopted(db):
    _setup(db)
    verdict = adopt_trained(db, _result(0.09, 0.08))
    assert verdict["adopted"] is None and "kraken-mccatmus" in verdict["why"]


def test_an_evaluation_with_no_trained_reader_adopts_nothing(db):
    _setup(db)
    result = _result(0.05, 0.08)
    result["models"] = result["models"][1:]
    assert adopt_trained(db, result) is None


def test_a_reader_the_person_chose_survives_a_better_trained_one(db):
    """Review 77: only a reader the rules chose is swapped; the person's choice is the one to beat, and a better
    trained reader is offered, never switched to."""
    library = _setup(db)
    recipe = read_project_setup(library)["recipe"]
    chosen = {"step": "read", "scope": "project", "folder_id": None, "model": {"zenodo": "10.5281/zenodo.13788177"},
              "card": "kraken:zenodo/10.5281/zenodo.13788177@unpinned", "because": "chosen by you"}
    write_project_setup(library, {"purposes": ["transcribe"]}, {**recipe, "overrides": [chosen]})
    from fichero_server.recipes.cards import kraken_reader_for

    result = _result(0.05, 0.08)
    result["models"][1]["model"] = kraken_reader_for(chosen["model"])  # the person's reader was measured too
    verdict = adopt_trained(db, result)
    assert verdict["adopted"] is None and verdict["offered"] == TRAINED, verdict
    assert "you chose" in verdict["why"]
    assert read_project_setup(library)["recipe"]["overrides"] == [chosen]


def test_a_reader_the_evaluation_adopted_is_replaced_by_a_better_one(db):
    library = _setup(db)
    adopt_trained(db, _result(0.05, 0.08))
    result = _result(0.02, 0.08)
    result["models"][0]["model"] = "kraken-trained-newer0000000"
    assert adopt_trained(db, result)["adopted"] == "kraken-trained-newer0000000"
    (override,) = read_project_setup(library)["recipe"]["overrides"]
    assert override["model"] == {"trained": "kraken-trained-newer0000000"}


def test_the_steps_current_reader_is_the_one_to_beat(db):
    """Review 77: a rules-chosen reader that is not the best downloadable one is still what the trained one must beat."""
    library = _setup(db)
    from fichero_server.recipes.cards import kraken_reader_for

    result = _result(0.05, 0.08)
    result["models"][1]["model"] = "kraken-other-download"
    current = dict(result["models"][1], model=kraken_reader_for(RECIPE["steps"][0]["model"]),
                   scores={"diplomatic": {"cer": 0.055}})
    result["models"].append(current)  # the step's reader, better than the other download, inside the band
    verdict = adopt_trained(db, result)
    assert verdict["adopted"] is None and current["model"] in verdict["why"], verdict
    assert not read_project_setup(library)["recipe"].get("overrides")


def test_too_few_held_out_pages_adopt_nothing(db):
    _setup(db)
    result = _result(0.01, 0.08)
    result["models"][0]["pages_read"] = 5
    verdict = adopt_trained(db, result)
    assert verdict["adopted"] is None and "5 held-out pages" in verdict["why"]
