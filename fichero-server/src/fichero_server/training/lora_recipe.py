"""A LoRA recipe file and what a LoRA job returns (`compute.tune.lora`, `compute.tune.adapter-always-returns`, #5240).

A recipe is a shareable JSON file naming rank, learning rate, epochs and the prompt form (the trainer's `--arm`:
what the student writes). QLoRA is not built: the trainer loads the base in bf16 (`compute.tune.lora` stays PARTIAL).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROMPT_FORMS = ("answer", "why", "thinking", "review")


@dataclass(frozen=True)
class LoraRecipe:
    rank: int
    learning_rate: float
    epochs: int
    prompt_form: str

    def job_options(self) -> dict[str, Any]:
        """The keyword arguments of `hf_jobs.lora_args`."""
        return {"rank": self.rank, "lr": self.learning_rate, "epochs": self.epochs, "arm": self.prompt_form}


def resolve(project: str | Path, name: str) -> Path:
    """A recipe is a file NAME in the project's `lora-recipes` folder. A path, `..` or a link out of the folder is
    refused, and the refusal never says what the path pointed at."""
    root = (Path(project) / "lora-recipes").resolve()
    found = (root / name).resolve()
    if Path(name).name != name or not found.is_relative_to(root) or not found.is_file():
        raise ValueError("the LoRA recipe must be the name of a file in this project's lora-recipes folder")
    return found


def load(path: str | Path) -> LoraRecipe:
    body = json.loads(Path(path).read_text(encoding="utf-8"))
    for key in ("rank", "learning_rate", "epochs", "prompt_form"):
        if key not in body:
            raise ValueError(f"the LoRA recipe {Path(path).name} does not name {key}")
    if not (isinstance(body["rank"], int) and body["rank"] >= 2):
        raise ValueError("rank in the LoRA recipe must be a whole number of at least 2")
    if not (isinstance(body["learning_rate"], (int, float)) and 0 < body["learning_rate"] < 1):
        raise ValueError("learning_rate in the LoRA recipe must be above 0 and below 1")
    if not (isinstance(body["epochs"], int) and body["epochs"] >= 1):
        raise ValueError("epochs in the LoRA recipe must be a whole number of at least 1")
    if body["prompt_form"] not in PROMPT_FORMS:
        raise ValueError(f"prompt_form in the LoRA recipe must be one of {', '.join(PROMPT_FORMS)}")
    return LoraRecipe(body["rank"], float(body["learning_rate"]), body["epochs"], body["prompt_form"])


def result_package(out: Path, *, merged: bool) -> list[str]:
    """The files of a LoRA job's result that come home, sorted: the adapter and the log always, the merged model
    (as large as the base) only when asked. A result without an adapter is refused."""
    out = Path(out)
    if not (out / "adapter").is_dir():
        raise FileNotFoundError(f"the job returned no adapter under {out}")
    keep = ("adapter", "merged") if merged else ("adapter",)
    files = [p for p in out.rglob("*") if p.is_file()
             and (p.relative_to(out).parts[0] in keep or p.parent == out)]
    return sorted(p.relative_to(out).as_posix() for p in files)
