"""A recipe run is step-major within a batch: Kraken's cards, then the MLX / reader cards, then spaCy's, then embedding,
then the next batch (the per-batch loop is test_recipe_batches_to_spec.py::test_every_step_finishes_a_batch_before_the_next_batch) (`activity.run.step-major-per-batch`, #5358; owner ruling 2026-10-21 ## 664). WHY: a 16 GB Mac holds
one heavy model at a time; each batch loads each heavy model once."""
from __future__ import annotations

from fichero_server.recipes.assemble import STEP_ORDER
from fichero_server.recipes.jobs import get_job

def test_step_order_puts_every_kraken_job_before_every_reader_before_spacy_before_embedding():
    """The order a batch runs its cards in: the page-image jobs (prepare, find regions and lines: Kraken's) precede
    every reading job (MLX / vision / cloud readers, Correct), which precede spaCy's names, then the embedder."""
    at = STEP_ORDER.index
    reading_first = at("read-a-line")
    assert all(at(job) < reading_first for job in STEP_ORDER if get_job(job) and get_job(job).layer in ("prepare", "lines"))
    assert at("read-a-line") < at("correct") < at("find-names-tag-words") < at("make-a-vector")

