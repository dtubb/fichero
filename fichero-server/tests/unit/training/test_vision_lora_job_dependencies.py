"""The vision-LoRA trainer's own dependency header (#5398).

WHY: the script runs inside a Hugging Face Job from its inline `# /// script` header alone. On
2026-10-06 the first real run (Qwen2.5-VL-3B) failed a minute in: transformers' Qwen-VL processor
needs torchvision ("AutoVideoProcessor requires the Torchvision library"), and the header didn't list
it, so the path had never trained. Every image-text-to-text base the trainer names needs it.
"""

from __future__ import annotations

import re
from pathlib import Path

import fichero_server.training.hf_vision_lora_train as trainer_module

_SCRIPT = Path(trainer_module.__file__)


def _header_dependencies() -> list[str]:
    text = _SCRIPT.read_text(encoding="utf-8")
    block = re.search(r"# /// script\n(.*?)# ///", text, re.S)
    assert block, "the trainer must carry an inline script header (the Job reads only that)"
    deps = re.search(r"# dependencies = \[(.*?)\]", block.group(1))
    assert deps, "the header must list the Job's dependencies"
    return [d.strip().strip('"') for d in deps.group(1).split(",")]


def test_the_job_installs_torchvision_for_vision_processors():
    names = {re.split(r"[<>=!~ ]", d, maxsplit=1)[0] for d in _header_dependencies()}
    assert {"torch", "torchvision", "transformers", "peft"} <= names
