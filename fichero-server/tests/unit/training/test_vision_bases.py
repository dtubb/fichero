"""Which vision model a LoRA starts from, and its licence (#5398, `compute.tune.licence-carries`)."""
from __future__ import annotations

from pathlib import Path

from fichero_server.training import hf_vision_lora_train
from fichero_server.training.job import TrainVisionLoraRequest
from fichero_server.training.vision_bases import DEFAULT_BASE, VISION_BASES, licence_of


def test_the_default_base_is_qwen3_vl_8b_and_apache():
    """WHY (maintainer, 2026-10-03): Qwen3-VL 8B is the default; its licence allows our use."""
    assert DEFAULT_BASE == TrainVisionLoraRequest(scope_ids=["x"], teacher="t").base_repo == "Qwen/Qwen3-VL-8B-Instruct"
    assert licence_of(DEFAULT_BASE)[0] == "Apache-2.0"


def test_each_candidates_licence_is_recorded_as_its_card_states_it():
    """WHY: the bake-off may pick chandra or Nanonets. Chandra's weights are under a modified OpenRAIL-M
    and Nanonets declares none on a research-only base: a student's card must carry that, so nobody
    releases one by mistake."""
    assert licence_of("datalab-to/chandra")[0] == "OpenRAIL-M (modified)"
    licence, note = licence_of("nanonets/Nanonets-OCR-s")
    assert licence == "undeclared" and "research-only" in note
    assert licence_of("Qwen/Qwen2.5-VL-7B-Instruct")[0] == "Apache-2.0"
    assert all(base.mlx for base in VISION_BASES.values()), "each candidate can be read untrained on this Mac"


def test_a_base_fichero_does_not_list_is_allowed_and_says_its_licence_was_not_checked():
    licence, note = licence_of("someone/new-vlm")
    assert licence == "not checked" and "not checked" in note


def test_the_trainer_names_no_model_family():
    """WHY: the base is chosen after a bake-off of several families; a trainer that loads one family's
    class or writes one family's chat would silently mis-train the others."""
    source = Path(hf_vision_lora_train.__file__).read_text(encoding="utf-8")
    assert "AutoModelForImageTextToText" in source and "apply_chat_template" in source
    assert "Qwen2_5_VL" not in source and "Qwen3VL" not in source
