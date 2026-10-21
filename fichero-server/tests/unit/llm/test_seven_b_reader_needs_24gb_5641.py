"""The 7B MLX reader is not chosen to read pages under 24 GB until it is measured (`runtime.mlx.seven-b-reader-needs-24gb`, #5641).

On the 16 GB Pro it read at 0.1 tok/s with swap full: its load floor (16 GB) equalled the Mac's whole memory, and the seed card
said 7 GB (weights only), so the catalogue choice and the recipe default both took it."""
from __future__ import annotations

from fichero_server.llm import local_model_choice as choice
from fichero_server.llm.local_model_facts import LocalInferenceCapabilities
from fichero_server.llm.mlx_model_store import MANAGED_MLX_MODELS
from fichero_server.recipes.assemble import Answers, _refusal
from fichero_server.recipes.cards import seed_cards

GIB = 1024**3
SEVEN = "mlx:hf/mlx-community/Qwen2.5-VL-7B-Instruct-4bit@unpinned"


def _mac(gb: int) -> LocalInferenceCapabilities:
    return LocalInferenceCapabilities(system="Darwin", machine="arm64", is_apple_silicon=True, physical_memory_bytes=gb * GIB)


def test_the_catalogue_entry_has_a_24_gb_page_floor_and_a_16_gb_mac_is_refused_in_words():
    spec = MANAGED_MLX_MODELS["Qwen2.5-VL-7B"]
    assert spec.page_memory_bytes == 24 * GIB
    ok, why = choice.runs_here(spec, "vision", capabilities=_mac(16))
    assert not ok and "24" in why
    assert choice.runs_here(spec, "vision", capabilities=_mac(24))[0]


def test_a_16_gb_mac_is_not_given_the_7b_as_its_vision_model():
    pick = choice.choose_local_model("vision", capabilities=_mac(16))
    assert pick.model_id != "Qwen2.5-VL-7B"


def test_the_seed_card_asks_for_24_gb_so_a_16_gb_mac_is_refused_and_a_32_gb_one_is_not():
    card = next(c for c in seed_cards() if c.id == SEVEN)
    assert card.memory_gb >= 24
    small = Answers(purposes=("transcribe",), languages=frozenset({"es"}), scripts=frozenset({"Latn"}),
                    materials=("handwriting",), mac_memory_gb=16)
    refusal = _refusal("read-a-page", card, small, "handwriting")
    assert refusal is not None and refusal[0] == "not-enough-memory"
    big = Answers(purposes=("transcribe",), languages=frozenset({"es"}), scripts=frozenset({"Latn"}),
                  materials=("handwriting",), mac_memory_gb=32)
    refused = _refusal("read-a-page", card, big, "handwriting")
    assert refused is None or refused[0] != "not-enough-memory"
