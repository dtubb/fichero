"""`prep.setup.three-questions-suggested-from-a-sample` (#6733 item 9): `GET /api/recipes/prepare-images/facts`
answers 200 with the engine's sentence naming the operations; it was a 500 (a call to a function that is not where
the route looked)."""
from __future__ import annotations


def test_the_prepare_images_facts_answer(client, with_material):
    r = client.get("/api/recipes/prepare-images/facts")
    assert r.status_code == 200, r.text
    assert r.json()["how_it_works"]
