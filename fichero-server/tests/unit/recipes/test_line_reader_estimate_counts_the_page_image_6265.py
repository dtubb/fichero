"""The Start estimate for a cloud line reader counts what it sends (#6265): the page picture, in two calls of about 13k and
43k input tokens, a page, not the 1,200 tokens a text call was assumed to take (it priced 874 pages at $0.66 against a
measured $0.0143 a page). Spec: `source.onboard.estimate-counts-the-image` (models-chains-and-projects.md)."""
from __future__ import annotations

import pytest

from fichero_server.recipes.start import estimate
from fichero_server.workflows.model_comparison import estimate_cost

MODEL, PROVIDER = "claude-haiku-4-5", "anthropic"


@pytest.fixture(autouse=True)
def _not_a_batch(monkeypatch):
    """874 pages is over the batch threshold (#5940); these tests are about the tokens a page read sends, priced at the
    listed rate. The batch price of the same tokens is the last test."""
    from fichero_server.recipes import start

    monkeypatch.setattr(start, "goes_as_provider_batch", lambda run, pages: False)


def _run(job):
    return {"card": "workflow", "runs_on": "cloud:anthropic", "model_override": MODEL, "provider_override": PROVIDER,
            "workflow_id": None, "job": job, "steps": [job], "workflow": "Read"}


@pytest.mark.parametrize("job", ["read-a-line", "read-a-page"])
def test_a_cloud_reader_is_priced_on_the_page_image_it_sends(job):
    cost = estimate([_run(job)], 874)["runs"][0]["cost_usd"]
    assert cost == pytest.approx(estimate_cost(MODEL, 874 * 3_600, 874 * 400, provider=PROVIDER))  # Claude: the capped image, twice


def test_a_text_step_keeps_the_text_assumption():
    cost = estimate([_run("translate-transliterate-normalise")], 874)["runs"][0]["cost_usd"]
    assert cost == pytest.approx(estimate_cost(MODEL, 874 * 1200, 874 * 300, provider=PROVIDER))


@pytest.mark.parametrize("provider,model", [("google", "gemini-2.5-flash-lite"), ("openrouter", "google/gemini-3.1-flash-lite"),
                                            ("openai", "gpt-4.1-mini")])
def test_gemini_and_other_providers_take_the_measured_figure(provider, model):
    run = {**_run("read-a-line"), "model_override": model, "provider_override": provider, "runs_on": f"cloud:{provider}"}
    cost = estimate([run], 874)["runs"][0]["cost_usd"]
    if cost is not None:  # an unlisted price stays None, never a stand-in
        assert cost == pytest.approx(estimate_cost(model, 874 * 56_000, 874 * 400, provider=provider))


def test_openrouter_claude_is_the_capped_image_too():
    run = {**_run("read-a-page"), "model_override": "anthropic/claude-haiku-4.5", "provider_override": "openrouter"}
    cost = estimate([run], 10)["runs"][0]["cost_usd"]
    if cost is not None:
        assert cost == pytest.approx(estimate_cost("anthropic/claude-haiku-4.5", 10 * 3_600, 10 * 400, provider="openrouter"))


def test_a_batched_page_read_is_priced_on_the_page_image_at_the_batch_price(monkeypatch):
    from fichero_server.llm.spend import batch_cost_usd
    from fichero_server.recipes import start

    monkeypatch.setattr(start, "goes_as_provider_batch", lambda run, pages: True)
    row = estimate([_run("read-a-page")], 874)["runs"][0]
    assert row["cost_usd"] == pytest.approx(batch_cost_usd(PROVIDER, MODEL, 874 * 3_600, 874 * 400))
    assert row["basis"] == "the batch price, answered within a day"
