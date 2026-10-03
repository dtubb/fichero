"""The vision models a LoRA can start from, with what is known of their licences (#5398).

`compute.tune.licence-carries`: a fine-tuned model's card carries its base's licence. The facts below
were read from each model's own card on the Hugging Face Hub on 2026-10-03 (its `license` field and
`base_model`), never guessed; a model whose card declares no licence says so. A base not listed may
still be chosen; its card then records that Fichero did not check its licence.

`mlx` names the 4-bit MLX build the store already knows, where one exists, so the untrained base can be
read on this Mac in the bake-off that chooses which base to fine-tune.
"""
from __future__ import annotations

from dataclasses import dataclass

DEFAULT_BASE = "Qwen/Qwen3-VL-8B-Instruct"


@dataclass(frozen=True)
class VisionBase:
    repo: str
    licence: str
    note: str
    mlx: str | None = None


VISION_BASES: dict[str, VisionBase] = {b.repo: b for b in (
    VisionBase("Qwen/Qwen3-VL-8B-Instruct", "Apache-2.0", "Hub card: apache-2.0.",
               "mlx-community/Qwen3-VL-8B-Instruct-4bit"),
    VisionBase("Qwen/Qwen3-VL-8B-Thinking", "Apache-2.0", "Hub card: apache-2.0. A reasoning model.",
               "mlx-community/Qwen3-VL-8B-Thinking-4bit"),
    VisionBase("Qwen/Qwen2.5-VL-7B-Instruct", "Apache-2.0", "Hub card: apache-2.0.",
               "mlx-community/Qwen2.5-VL-7B-Instruct-4bit"),
    VisionBase("datalab-to/chandra", "OpenRAIL-M (modified)",
               "Hub card: openrail; Datalab's modified OpenRAIL-M, which restricts some commercial use. "
               "Fine for unreleased research; a release needs its terms read.", "mlx-community/chandra-4bit"),
    VisionBase("nanonets/Nanonets-OCR-s", "undeclared",
               "Hub card declares no licence; its base is Qwen/Qwen2.5-VL-3B-Instruct, whose licence is "
               "research-only. Not for release in any case.", "mlx-community/Nanonets-OCR-s-4bit"),
)}


def licence_of(repo: str) -> tuple[str, str]:
    """(licence, note) for a base: from the list, or 'not checked' for one Fichero does not list."""
    base = VISION_BASES.get(repo)
    if base is None:
        return "not checked", f"{repo} is not in Fichero's list of vision bases; its licence was not checked."
    return base.licence, base.note
