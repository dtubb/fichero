"""A vision model trained with LoRA comes home as an MLX model (#5398, `compute.tune.convert-for-mlx`).

The Job returns the adapter (always: `compute.tune.adapter-always-returns`) and the base with the
adapter merged in (bf16, ~17 GB for 8B). Both stay in standard Hugging Face form in the job's bucket:
that is the build a Linux GPU runs (transformers, vLLM; reading at scale off the Mac). On this Mac the merged model is converted and quantised to
4-bit MLX with `mlx_vlm.convert`, in the MLX runtime's own Python, on the local ML lane as one heavy
job (it never runs beside a Kraken page or another model). The MLX model lands in the model store as
`fichero-trained/<name>` with its card, the adapter beside it; this Mac's copy of the merged weights is deleted
once the conversion succeeded (it is as large as the base) unless asked to keep it. The conversion runs on the Mac only, as the
spec rules: MLX is Apple's.

The card says what the student is: its base and licence, its teacher, its training set (lines a
model read, lines a person checked), the held-out pages, the job, where it ran, that it reads ONE line
picture per call (as it was trained), and whether it may be released.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

#: Attached kind on the local ML lane: the conversion is handed in by the training job, which waits.
CONVERT_KIND = "convert-a-model"
CONVERT_MODEL = "mlx-convert"
Q_BITS = 4


class ConversionFailed(RuntimeError):
    """`mlx_vlm.convert` did not produce an MLX model."""


def convert_command(merged: Path, dest: Path, python: str) -> list[str]:
    return [python, "-m", "mlx_vlm.convert", "--hf-path", str(merged), "--mlx-path", str(dest),
            "-q", "--q-bits", str(Q_BITS)]


def convert_for_mlx(merged: Path, dest: Path, *, run: Callable[[list[str]], Any] | None = None) -> None:
    """Convert and quantise a merged Hugging Face model into `dest` (4-bit MLX)."""
    from fichero_server.llm.mlx_runtime import get_mlx_runtime

    python = str(get_mlx_runtime().require_python_path())
    if dest.exists():
        shutil.rmtree(dest)
    command = convert_command(merged, dest, python)
    if run is not None:
        run(command)
    else:
        done = subprocess.run(command, capture_output=True, text=True)
        if done.returncode != 0:
            raise ConversionFailed((done.stderr or done.stdout).strip()[-800:] or f"exit {done.returncode}")
    if not any(dest.glob("*.safetensors")):
        raise ConversionFailed(f"mlx_vlm.convert wrote no weights into {dest.name}")


def model_id_for(name: str) -> str:
    from fichero_server.llm.mlx_model_store import TRAINED_ORG

    slug = "".join(c if c.isalnum() or c in "-_." else "-" for c in name).strip("-") or "student"
    return f"{TRAINED_ORG}/{slug}"


def land_vision_student(out_dir: str | Path, *, job_id: str, name: str, card: dict[str, Any],
                        convert: Callable[[Path, Path], None] | None = None, keep_merged: bool = False,
                        hf_build: dict[str, Any] | None = None, project: str | Path | None = None) -> str:
    """Install the trained student; returns its model id.

    One card, two builds (`compute.engine.same-card-resolves-by-platform`): `hf`, the merged weights
    and the adapter in standard Hugging Face form, run by transformers or vLLM on a Linux GPU (kept in
    the job's bucket, and here too when `keep_merged`), and `mlx`, the 4-bit conversion this Mac runs.

    With `project` (the package it was trained for) it lands inside it (#5539,
    `training.project_models`): `models/fichero-trained--<name>/` holds `mlx/` (with the card),
    `adapter/` and, when kept, `hf/`; the card names them relative to that folder. Without, it lands
    in the engine's global store as before.
    """
    from fichero_server.llm.mlx_model_store import TRAINED_CARD, get_mlx_model_store

    out = Path(out_dir)
    adapter, merged = out / "adapter", out / "merged"
    if not adapter.is_dir():
        raise ConversionFailed("the Job returned no adapter")
    if not merged.is_dir():
        raise ConversionFailed("the Job returned no merged model to convert for MLX")
    store = get_mlx_model_store()
    model_id = model_id_for(name)
    if project is not None:
        from fichero_server.training import project_models as pm

        home = pm.model_folder(project, model_id)
        dest, adapters, here = home / pm.MLX_BUILD, home / pm.ADAPTER, home / pm.MERGED

        def shown(p: Path) -> str:
            return p.relative_to(home).as_posix()
    else:
        dest = store.global_trained_dir(model_id)
        adapters = store.root / "adapters" / model_id.split("/", 1)[1]
        here = store.root / "hf" / model_id.split("/", 1)[1]

        def shown(p: Path) -> str:
            return str(p)
    dest.parent.mkdir(parents=True, exist_ok=True)
    (convert or convert_for_mlx)(merged, dest)
    if adapters.exists():
        shutil.rmtree(adapters)
    shutil.copytree(adapter, adapters)
    hf = {**(hf_build or {}), "format": "huggingface (safetensors, bf16)", "adapter_here": shown(adapters)}
    if keep_merged:
        if here.exists():
            shutil.rmtree(here)
        shutil.move(str(merged), str(here))
        hf["merged_here"] = shown(here)
    else:
        shutil.rmtree(merged)
    full = {**card, "job_id": job_id, "lines_per_call": 1, "quantised_bits": Q_BITS,
            "adapter_path": shown(adapters), "trained_at": datetime.now(timezone.utc).isoformat(),
            "builds": {"mlx": {"model_id": model_id, "path": shown(dest), "bits": Q_BITS, "runs_on": "Apple silicon"},
                       "hf": {**hf, "runs_on": "Linux GPU (transformers, vLLM)"}}}
    (dest / TRAINED_CARD).write_text(json.dumps(full, indent=1), encoding="utf-8")
    return model_id
