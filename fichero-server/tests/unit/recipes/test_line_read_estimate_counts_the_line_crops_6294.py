"""The Start estimate for a Claude line reader counts what it sends (#6294): one crop a line (about 280 tokens each, the
cut is at most 1,600 px wide) plus a short prompt, and about 28 tokens of answer a line, for the lines a page is assumed
to hold, not the page picture twice (3,600 in / 400 out) which priced it 2.5x low. Spec:
`source.onboard.estimate-counts-the-image` (models-chains-and-projects.md)."""
from __future__ import annotations

import pytest

from fichero_server.recipes.start import ASSUMED_LINES_PER_PAGE, estimate
from fichero_server.workflows.model_comparison import estimate_cost

MODEL, PROVIDER = "claude-sonnet-4-5", "anthropic"


@pytest.fixture(autouse=True)
def _not_a_batch(monkeypatch):
    from fichero_server.recipes import start

    monkeypatch.setattr(start, "goes_as_provider_batch", lambda run, pages: False)


def _run(job, model=MODEL, provider=PROVIDER):
    return {"card": "workflow", "runs_on": f"cloud:{provider}", "model_override": model, "provider_override": provider,
            "workflow_id": None, "job": job, "steps": [job], "workflow": "Read"}


def test_a_claude_line_read_is_priced_on_a_crop_a_line():
    assert ASSUMED_LINES_PER_PAGE == 33
    # Hand-worked, 16 pages: one call a page (33 lines is under the 40 a call), 150 prompt + 33 x 280 crop = 9,390 in;
    # 33 x 28 = 924 out. Sonnet $3 / $15 a million: 16 x (9,390 x 3e-6 + 924 x 15e-6) = 16 x 0.04203 = $0.6725.
    cost = estimate([_run("read-a-line")], 16)["runs"][0]["cost_usd"]
    assert cost == pytest.approx(estimate_cost(MODEL, 16 * 9_390, 16 * 924, provider=PROVIDER))
    assert cost == pytest.approx(0.6725, abs=0.001)


def test_a_claude_page_read_keeps_the_page_image_price():
    cost = estimate([_run("read-a-page")], 16)["runs"][0]["cost_usd"]
    assert cost == pytest.approx(estimate_cost(MODEL, 16 * 3_600, 16 * 400, provider=PROVIDER))


def test_gemini_line_read_keeps_the_measured_figure():
    run = _run("read-a-line", "gemini-2.5-flash-lite", "google")
    cost = estimate([run], 16)["runs"][0]["cost_usd"]
    assert cost == pytest.approx(estimate_cost("gemini-2.5-flash-lite", 16 * 56_000, 16 * 400, provider="google"))
