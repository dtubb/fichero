"""A model card's memory is the number the load gate uses, not a second one (#5537, `ai.where.one-memory-number`):
`local_memory_gb(spec)` is the weights, the KV cache for the default context and the overhead; the shipped
text-model cards state exactly that."""
from __future__ import annotations

from fichero_server.llm.local_inference import fit_estimate, local_memory_gb
from fichero_server.llm.mlx_model_store import MANAGED_MLX_MODELS
from fichero_server.recipes.discovery import other_text_cards


def _text_specs():
    return [s for s in MANAGED_MLX_MODELS.values() if tuple(s.capabilities) == ("text",)]


def test_local_memory_gb_is_the_load_gates_need():
    spec = _text_specs()[0]
    assert local_memory_gb(spec) == round(fit_estimate(spec, physical_memory=64 * 1024**3).need_bytes / 1024**3, 2)


def test_a_shipped_text_card_states_the_load_gates_number():
    cards = {c.id: c for c in other_text_cards() if c.source == "shipped"}
    checked = 0
    for spec in _text_specs():
        card = cards.get(f"mlx:text/{spec.repo_id}@{spec.revision}")
        if card is not None:
            assert card.memory_gb == local_memory_gb(spec), spec.repo_id
            checked += 1
    assert checked, "at least one shipped text model is offered"
