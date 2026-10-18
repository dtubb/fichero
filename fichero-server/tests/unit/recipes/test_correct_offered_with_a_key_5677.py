"""`source.onboard.correct-off-unless-a-corrector-is-here`, ruled Q3 2026-10-17 (#5677): with no corrector on this Mac,
Correct is off; where a cloud corrector's provider has a key set, Correct is OFFERED at Ready with its cost for the
project's pages, never turned on by itself; with no key, no cloud is named.

WHY: the off line named a cloud price whether or not the person could use that cloud, and nothing offered it.
"""
from __future__ import annotations

from fichero_server.recipes.assemble import Answers, Card, _correct_left_off

MLX = Card(id="mlx:hf/x/Qwen2.5-VL-7B@1", pin={"hf": "x/Qwen2.5-VL-7B"}, jobs=frozenset({"correct"}), scripts=None,
           languages=None, material=frozenset({"handwriting"}), size_gb=5.7, memory_gb=8, installed=False)
CLOUD = Card(id="cloud:anthropic/claude@1", pin={"provider": "anthropic"}, jobs=frozenset({"correct"}), scripts=None,
             languages=frozenset({"es"}), material=frozenset({"handwriting"}), runs_on="cloud:anthropic", cost_per_page=0.02,
             note="Claude")
A = dict(purposes=("transcribe",), materials=("handwriting",), languages=frozenset({"es"}), pages=500,
         mac_memory_gb=32)


def test_correct_offered_with_a_key_5677():
    off = _correct_left_off([MLX, CLOUD], Answers(**A, cloud_keys=("anthropic",)))
    assert off is not None and off["job"] == "correct"  # never on by itself
    offer = off["offered"]
    assert offer["runs_on"] == "anthropic" and offer["pages"] == 500 and offer["cost_usd"] == 10.0
    assert "$10.00" in off["sentence"]


def test_with_no_key_no_cloud_is_offered_or_priced_5677():
    off = _correct_left_off([MLX, CLOUD], Answers(**A))
    assert off is not None and off.get("offered") is None and "$" not in off["sentence"]
