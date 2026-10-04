"""A trained Kraken reader comes home as a reader card (#5398, `compute.tune.model-comes-back-as-a-card`).

The best model `ketos train -q early` wrote (`<name>_best.*`) is copied into Fichero's Kraken
recognition folder under `kraken-trained-<job>`, beside the readers downloaded by DOI, and recorded
by the same kind of marker, which carries the reader's card: its base, its teacher, the training set
(pages, lines, how many a model read and a person checked: `compute.tune.bootstrapped-data-is-marked`),
the held-out pages, the job and where it ran. It is listed in the model catalogue and can be chosen
for a Transcribe run; landing never makes it a default (`compute.tune.not-default-until-chosen`).

A reader trained on material whose models may not be released says so on its card. Nothing is
released by landing; release is a person's act (`compute.publish.*`).
"""
from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_MODEL_SUFFIXES = (".safetensors", ".mlmodel")
_EPOCH = re.compile(r"_(\d+)$")


class NoTrainedModel(RuntimeError):
    """The job's output holds no model file."""


def best_model_file(out_dir: str | Path, name: str) -> Path:
    """`<name>_best.*` when early stopping wrote one (Kraken 5 and 6), `best_<score>.*` (what Kraken 7's
    `ketos train` writes into its output folder: checked 2026-10-04 against 7.1.1, which the HF image
    and this Mac both run), else the latest epoch's checkpoint."""
    files = [p for p in Path(out_dir).rglob("*") if p.suffix in _MODEL_SUFFIXES]
    best = [p for p in files if p.stem == f"{name}_best"]
    if best:
        return best[0]
    scored = [p for p in files if p.stem.startswith("best_")]
    if scored:
        return max(scored, key=lambda p: p.stat().st_mtime)
    epochs = [(int(m.group(1)), p) for p in files if (m := _EPOCH.search(p.stem))]
    if epochs:
        return max(epochs)[1]
    raise NoTrainedModel(f"the training job wrote no model file ({', '.join(_MODEL_SUFFIXES)}) under its output")


def reader_id_for_job(job_id: str) -> str:
    from fichero_server.llm.kraken_runtime import TRAINED_READER_PREFIX

    return f"{TRAINED_READER_PREFIX}{job_id.replace('-', '')[:12]}"


def land_trained_reader(out_dir: str | Path, *, job_id: str, model_name: str, card: dict[str, Any],
                        home: Path | None = None) -> str:
    """Install the trained model as a reader; returns its model id."""
    from fichero_server.llm.kraken_runtime import _marker_path, recognition_data_home, recognition_model_dir

    source = best_model_file(out_dir, model_name)
    reader_id = reader_id_for_job(job_id)
    folder = recognition_data_home(home) / reader_id
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{model_name}{source.suffix}"
    shutil.copy2(source, target)
    full_card = {**card, "job_id": job_id, "model_file": target.name, "size_bytes": target.stat().st_size,
                 "trained_at": datetime.now(timezone.utc).isoformat()}
    recognition_model_dir(home).mkdir(parents=True, exist_ok=True)
    _marker_path(reader_id, home).write_text(
        json.dumps({"model_path": str(target), "trained": full_card}, indent=1), encoding="utf-8")
    return reader_id
