"""The Start estimate for a cloud line reader counts what it sends (#6265): the page picture, in two calls of about 13k and
43k input tokens, a page, not the 1,200 tokens a text call was assumed to take (it priced 874 pages at $0.66 against a
measured $0.0143 a page). Spec: `source.onboard.estimate-counts-the-image` (models-chains-and-projects.md)."""
from __future__ import annotations

import pytest

from fichero_server.recipes.start import estimate
from fichero_server.workflows.model_comparison import estimate_cost

MODEL, PROVIDER = "claude-haiku-4-5", "anthropic"


def _run(job):
    return {"card": "workflow", "runs_on": "cloud:anthropic", "model_override": MODEL, "provider_override": PROVIDER,
            "workflow_id": None, "job": job, "steps": [job], "workflow": "Read"}


@pytest.mark.parametrize("job", ["read-a-line", "read-a-page"])
def test_a_cloud_reader_is_priced_on_the_page_image_it_sends(job):
    cost = estimate([_run(job)], 874)["runs"][0]["cost_usd"]
    assert cost == pytest.approx(estimate_cost(MODEL, 874 * 56_000, 874 * 400, provider=PROVIDER))


def test_a_text_step_keeps_the_text_assumption():
    cost = estimate([_run("translate-transliterate-normalise")], 874)["runs"][0]["cost_usd"]
    assert cost == pytest.approx(estimate_cost(MODEL, 874 * 1200, 874 * 300, provider=PROVIDER))
