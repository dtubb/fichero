"""A step that names a local model the server is not serving is refused by name (#5388).

WHY: the managed oMLX server loads one model, its profile's. A Sergio-notebooks run asked for
Qwen2.5-VL 3B; the engine started the server with Qwen3-VL 8B instead, which then failed for lack
of memory, and the history recorded the 3B as what ran. A comparison of readers is worthless if
the model named is not the model used. Until the server can switch models on request, the run
refuses and says how to get the model asked for.
"""
from __future__ import annotations

import pytest

from fichero_server.llm import LocalModelUnavailableError, _refuse_a_model_the_local_server_does_not_serve


def test_a_different_managed_model_is_refused_naming_both():
    with pytest.raises(LocalModelUnavailableError) as err:
        _refuse_a_model_the_local_server_does_not_serve("Qwen2.5-VL-3B", "mlx-community/Qwen3-VL-8B")
    assert "Qwen2.5-VL 3B" in str(err.value) and "mlx-community/Qwen3-VL-8B" in str(err.value)


@pytest.mark.parametrize("requested", ["mlx-community/Qwen3-VL-8B", "mlx-community/Qwen3-VL-8B-Instruct-4bit"])
def test_the_served_model_by_id_or_repo_passes(requested):
    _refuse_a_model_the_local_server_does_not_serve(requested, "mlx-community/Qwen3-VL-8B")


def test_a_name_that_is_not_a_managed_model_is_left_to_the_server():
    _refuse_a_model_the_local_server_does_not_serve("some-served-name", "mlx-community/Qwen3-VL-8B")
