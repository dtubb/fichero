"""A trained model's id is accepted as the app shows it (#5567).

WHY: `--model fichero-trained/mosquera-qwen25vl3b` was split on its first slash into provider
`fichero-trained`, and the run died with "Unknown LLM provider fichero-trained". The execute
request keeps a trained id whole and sends it to the local MLX server, whichever way a client split
it; every other choice passes through untouched.
"""

from __future__ import annotations

import pytest

from fichero_server.api.routes.workflow_execution.schemas import ExecuteWorkflowRequest


@pytest.mark.parametrize(
    ("provider", "model"),
    [
        ("fichero-trained", "mosquera-qwen25vl3b"),  # the CLI's split on the first slash
        (None, "fichero-trained/mosquera-qwen25vl3b"),  # the whole id, no provider
        ("omlx", "fichero-trained/mosquera-qwen25vl3b"),  # the operator's workaround
    ],
)
def test_a_trained_model_id_reaches_the_run_whole(provider, model):
    request = ExecuteWorkflowRequest(workflow_id="w", provider_override=provider, model_override=model)
    assert (request.provider_override, request.model_override) == ("omlx", "fichero-trained/mosquera-qwen25vl3b")


@pytest.mark.parametrize(
    ("provider", "model"),
    [("openrouter", "google/gemini-3-flash-preview"), ("omlx", "Qwen2.5-VL-3B"), (None, None)],
)
def test_any_other_choice_is_untouched(provider, model):
    request = ExecuteWorkflowRequest(workflow_id="w", provider_override=provider, model_override=model)
    assert (request.provider_override, request.model_override) == (provider, model)
