"""Assembling a recipe by rule (`source.onboard.deterministic-recipe`, `source.recipe.cheapest-local-first`,
`source.onboard.purpose-sets-layers`, `source.recipe.volume-rule`, `source.recipe.embedder-by-language`).

Why it matters: setup proposes this recipe to a researcher, and its whole promise is that the same
answers give the same recipe, for reasons it can name. If the rules drift (a print-only reader
offered for handwriting, a model that does not know the language allowed to "correct" it, the
cloud chosen while the project keeps pages local, a 2.3 GB embedder where a small one serves), the
first run on someone's archive does the wrong thing silently. The cards here mirror real models
from the 2026-10-01 search (Kraken blla, PP-OCRv6, Tesseract, Qwen2.5-VL, spaCy, E5, BGE-M3).
"""
from __future__ import annotations

import random

from fichero_server.recipes.assemble import CORRECT_QUESTION, Answers, Card, assemble
from fichero_server.recipes.recipe import check_recipe

ANY = None
CARDS = [
    Card("kraken-blla", {"kraken": "blla", "kraken_version": "5.2"}, frozenset({"find-lines"}), ANY, ANY,
         frozenset({"handwriting", "print", "typescript"}), pages_per_hour=200, size_gb=0.01, memory_gb=2.5),
    Card("ppocrv6-medium", {"hf": "small-models-for-glam/kraken-ppocrv6-medium", "revision": "main"},
         frozenset({"read-a-line"}), frozenset({"Latn", "Arab", "Hebr", "Syrc", "Grek", "Cyrl", "Armn", "Geor", "Ethi", "Mlym"}),
         None, frozenset({"handwriting", "print"}), cer_published=0.039, trainable=True, size_gb=0.06, memory_gb=1.0,
         pages_per_hour=300),
    Card("tesseract-spa", {"tesseract": "5", "traineddata": "spa"}, frozenset({"read-a-line"}), frozenset({"Latn"}),
         frozenset({"es"}), frozenset({"print"}), cer_published=0.02, pages_per_hour=900, size_gb=0.02, trainable=True),
    Card("qwen25vl-7b-mlx", {"hf": "mlx-community/Qwen2.5-VL-7B-Instruct-4bit", "revision": "main"},
         frozenset({"correct", "read-a-page"}), frozenset({"Latn", "Cyrl", "Hani"}), frozenset({"es", "en", "fr", "pt"}),
         frozenset({"handwriting", "print"}), size_gb=5.6, memory_gb=7.0, pages_per_hour=20),
    Card("gemini-flash", {"cloud": "google", "model": "gemini-2.5-flash"}, frozenset({"correct", "read-a-page"}),
         frozenset({"Latn", "Cher"}), frozenset({"es", "en", "chr"}), frozenset({"handwriting", "print"}),
         runs_on="cloud:google", cost_per_page=0.002, pages_per_hour=600),
    Card("spacy-es-md", {"spacy": "es_core_news_md", "version": "3.8.0"}, frozenset({"find-names-tag-words"}),
         frozenset({"Latn"}), frozenset({"es"}), frozenset({"handwriting", "print", "typescript"}), size_gb=0.04),
    Card("e5-small", {"hf": "intfloat/multilingual-e5-small", "revision": "main"}, frozenset({"make-a-vector"}),
         ANY, frozenset({"es", "en", "chr", "fr"}), frozenset({"handwriting", "print", "typescript"}), size_gb=0.47),
    Card("bge-m3", {"hf": "BAAI/bge-m3", "revision": "main"}, frozenset({"make-a-vector"}), ANY,
         frozenset({"es", "en", "chr", "fr"}), frozenset({"handwriting", "print", "typescript"}), size_gb=2.3),
]
SPANISH_LETTERS = Answers("search", frozenset({"es"}), frozenset({"Latn"}), "handwriting", pages=3000)
#: Correct is optional: it joins the plan only when the person says yes (owner ruling 2026-10-19, #5812).
YES_CORRECT = {CORRECT_QUESTION: True}


def _models(recipe):
    return {s["job"]: s.get("model") for s in recipe["steps"]}


def test_the_same_answers_and_cards_give_the_same_recipe_whatever_their_order():
    first = assemble(SPANISH_LETTERS, CARDS)
    shuffled = CARDS[:]
    random.Random(7).shuffle(shuffled)
    assert assemble(SPANISH_LETTERS, shuffled) == first


def test_handwriting_gets_a_local_line_reader_never_a_print_only_one():
    m = _models(assemble(Answers("search", frozenset({"es"}), frozenset({"Latn"}), "handwriting", pages=3000,
                                 job_answers=YES_CORRECT), CARDS))
    assert m["find-lines"]["kraken"] == "blla"
    assert m["read-a-line"]["hf"].endswith("kraken-ppocrv6-medium")   # not Tesseract (print only)
    assert m["correct"]["hf"].startswith("mlx-community/Qwen2.5-VL")  # local first, not the cloud


def test_print_gets_tesseract_as_the_cheap_fast_local_baseline():
    m = _models(assemble(Answers("transcribe", frozenset({"es"}), frozenset({"Latn"}), "print"), CARDS))
    assert m["read-a-line"] == {"tesseract": "5", "traineddata": "spa"}


def test_the_embedder_is_the_smallest_that_covers_the_languages():
    assert _models(assemble(SPANISH_LETTERS, CARDS))["make-a-vector"]["hf"] == "intfloat/multilingual-e5-small"


def test_a_language_the_model_does_not_know_is_never_corrected_into_another():
    cherokee = Answers("transcribe", frozenset({"chr"}), frozenset({"Cher"}), "handwriting")
    recipe = assemble(cherokee, CARDS)
    steps = {s["job"]: s for s in recipe["steps"]}
    assert "gap" in steps["read-a-line"]                     # nothing reads the syllabary locally
    # Qwen lacks chr and the cloud is not allowed: Correct is off, saying so (#5677).
    assert "correct" not in steps
    (off,) = [o["sentence"] for o in recipe["left_off"] if o["job"] == "correct"]
    assert "cloud" in off


def test_the_cloud_is_used_only_when_allowed_and_nothing_local_fits():
    cherokee = Answers("transcribe", frozenset({"chr"}), frozenset({"Cher"}), "handwriting", cloud_allowed=True,
                       job_answers=YES_CORRECT)
    assert _models(assemble(cherokee, CARDS))["correct"] == {"cloud": "google", "model": "gemini-2.5-flash"}


def test_a_large_volume_offers_training_from_the_start():
    small = [s["job"] for s in assemble(SPANISH_LETTERS, CARDS)["steps"]]
    big = [s["job"] for s in assemble(Answers("search", frozenset({"es"}), frozenset({"Latn"}), pages=20_000), CARDS)["steps"]]
    assert "train-a-model" not in small and big[-1] == "train-a-model"


def test_the_purpose_decides_the_steps():
    jobs = [s["job"] for s in assemble(Answers("transcribe", frozenset({"es"}), frozenset({"Latn"})), CARDS)["steps"]]
    assert jobs == ["find-lines", "read-a-line"]  # Correct waits to be asked for
    asked = Answers("transcribe", frozenset({"es"}), frozenset({"Latn"}), job_answers=YES_CORRECT)
    assert [s["job"] for s in assemble(asked, CARDS)["steps"]] == ["find-lines", "read-a-line", "correct"]
    assert assemble(Answers("not-sure", frozenset({"es"}), frozenset({"Latn"})), CARDS)["steps"] == []


def test_a_gap_free_generated_recipe_passes_the_check():
    recipe = assemble(SPANISH_LETTERS, CARDS)
    assert recipe["gaps"] == []
    assert check_recipe(recipe) == []


def test_each_choice_names_its_reasons():
    read = next(s for s in assemble(SPANISH_LETTERS, CARDS)["steps"] if s["job"] == "read-a-line")
    assert "made for handwriting" in read["reasons"] and "runs on this Mac, free" in read["reasons"]


def test_the_egress_question_is_needed_only_where_a_cloud_model_would_fit():
    """Setup asks once whether pages may leave this Mac, and only when it matters
    (`source.onboard.cloud-asked-once`): a cloud model that fits a step is named, while every step
    still chooses locally. Without this, setup either asks everyone or never asks."""
    # Correct is optional (#5812, 0d2ddeeff): a cloud model fits a step only once the person asks for that step.
    recipe = assemble(Answers("search", frozenset({"es"}), frozenset({"Latn"}), "handwriting", pages=3000,
                              job_answers=YES_CORRECT), CARDS)
    assert recipe["cloud_options"] == ["correct"]
    assert not any(s["uses_cloud"] for s in recipe["steps"])
    for_print = Answers("transcribe", frozenset({"es"}), frozenset({"Latn"}), "print")
    assert assemble(for_print, [c for c in CARDS if c.id != "gemini-flash"])["cloud_options"] == []


def test_the_egress_question_says_what_is_sent_to_whom_how_many_pages_and_the_estimate():
    """`source.onboard.egress-asked-once`: the toggle is not a bare yes. Per step a cloud model would fit, it names what
    would be sent, to whom, for how many pages and at what cost, so the answer is an informed one."""
    recipe = assemble(Answers("search", frozenset({"es"}), frozenset({"Latn"}), "handwriting", pages=3000,
                              job_answers=YES_CORRECT), CARDS)
    offer = {o["job"]: o for o in recipe["cloud_offer"]}
    assert list(offer) == recipe["cloud_options"] == ["correct"]
    correct = offer["correct"]
    assert correct["sends"] == "the text of the pages" and correct["pages"] == 3000
    assert correct["to"] and correct["cost_usd"] is not None and correct["cost_usd"] > 0
    assert str(correct["pages"]) in correct["sentence"].replace(",", "") and correct["to"] in correct["sentence"]
    assert f"${correct['cost_usd']:.2f}" in correct["sentence"]
    # Nothing a cloud model fits: nothing is offered, so nothing is asked.
    for_print = Answers("transcribe", frozenset({"es"}), frozenset({"Latn"}), "print")
    assert assemble(for_print, [c for c in CARDS if c.id != "gemini-flash"])["cloud_offer"] == []


def test_the_estimate_comes_from_the_price_list_not_from_a_price_set_on_the_card():
    """Review 379: the shipped cards never set `cost_per_page` (it is 0.0), so an offer priced from it said "cannot work out"
    for everyone, and `min()` picked an unpriced card. The price is the vendored list's, through the pin's provider/model."""
    from dataclasses import replace

    from fichero_server.recipes.assemble import cloud_offer

    real = next(c for c in CARDS if c.id == "gemini-flash")
    priced = replace(real, cost_per_page=0.0)  # as shipped: no price on the card
    assert priced.pin["cloud"] and priced.pin["model"]
    unpriced = replace(real, id="unlisted", cost_per_page=0.0, pin={"cloud": "google", "model": "no-such-model-xyz"})
    a = Answers("search", frozenset({"es"}), frozenset({"Latn"}), "handwriting", pages=1000, cloud_allowed=True,
                job_answers=YES_CORRECT)
    offer = cloud_offer(["correct"], [unpriced, priced], a)[0]
    assert offer["cost_usd"] is not None and offer["cost_usd"] > 0, offer["sentence"]
    assert f"${offer['cost_usd']:.2f}" in offer["sentence"]
    only_unpriced = cloud_offer(["correct"], [unpriced], a)[0]
    assert only_unpriced["cost_usd"] is None and "cannot work out" in only_unpriced["sentence"]


def test_a_picture_step_says_the_page_pictures_are_sent():
    from fichero_server.recipes.assemble import cloud_offer

    card = next(c for c in CARDS if c.id == "gemini-flash")
    one = cloud_offer(["read-a-line"], [type(card)(**{**card.__dict__, "jobs": frozenset({"read-a-line"})})],
                      Answers("transcribe", frozenset({"es"}), frozenset({"Latn"}), "handwriting", pages=1,
                              cloud_allowed=True))
    assert one and one[0]["sends"] == "the page pictures" and "1 page " in one[0]["sentence"] + " "


def test_a_chosen_step_carries_its_cards_facts():
    """Setup shows what it proposes, not just a pin (`source.onboard.proposes-chain`)."""
    steps = {s["job"]: s for s in assemble(SPANISH_LETTERS, CARDS)["steps"]}
    card = steps["read-a-line"]["card"]
    assert card["id"] == "ppocrv6-medium" and card["cer_published"] == 0.039 and card["trainable"]
