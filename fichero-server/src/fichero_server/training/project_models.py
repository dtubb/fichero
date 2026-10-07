"""A trained model lives inside its project (#5539, ruled 2026-10-06).

A model trained for a project lands in the project's package, under `models/`, as its card and its
weights, so a project copied or moved to another Mac carries its models:

    <project>.fichero/models/kraken-trained-<job>/<name>.mlmodel     the reader
    <project>.fichero/models/kraken-trained-<job>/fichero-card.json  its record: {model_path, trained, evaluations}
    <project>.fichero/models/fichero-trained--<name>/mlx/            the 4-bit MLX build + fichero-card.json
    <project>.fichero/models/fichero-trained--<name>/adapter/        the LoRA adapter (Hugging Face form)
    <project>.fichero/models/fichero-trained--<name>/hf/             the merged weights, when kept here

Paths on a card inside a project are relative to the model's folder, never absolute, so a moved project
still finds its weights. A model's id is the same wherever it lives (`kraken-trained-<job>`,
`fichero-trained/<name>`); the resolvers look in the engine's global store first, then in every project
this engine has open, so a reader or a recipe step naming the model finds it in its project with no
other change, and a model already in the global store (every model landed before this ruling) keeps
working.

**Make Global** (`make_global`) copies a project's model into the engine's global store so every
project can use it; the project keeps its own copy. The card goes with it unchanged, `not_for_release`
included: a model that may not be released stays so wherever it is copied. Publishing is not built.
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MODELS_DIRNAME = "models"
CARD = "fichero-card.json"
MLX_BUILD = "mlx"
ADAPTER = "adapter"
MERGED = "hf"


class NotInProject(LookupError):
    """The project holds no model by that id."""


def models_dir(package: str | Path) -> Path:
    return Path(package) / MODELS_DIRNAME


def folder_name(model_id: str) -> str:
    return model_id.replace("/", "--")


def model_folder(package: str | Path, model_id: str) -> Path:
    return models_dir(package) / folder_name(model_id)


def _open_projects() -> list[Path]:
    """The packages this engine has open, the projects whose models resolve by id."""
    try:
        from fichero_server.db.manager import db_manager

        return [Path(p) for p in db_manager.open_library_paths()]
    except Exception:  # an engine with no manager (a bare unit) has no project open
        return []


def kraken_record(package: str | Path, model_id: str) -> Path:
    return model_folder(package, model_id) / CARD


def mlx_dir(package: str | Path, model_id: str) -> Path:
    return model_folder(package, model_id) / MLX_BUILD


def find_kraken_record(model_id: str) -> Path | None:
    """A trained reader's record in an open project, or None."""
    for package in _open_projects():
        record = kraken_record(package, model_id)
        if record.is_file():
            return record
    return None


def find_mlx_dir(model_id: str) -> Path | None:
    """A trained vision model's MLX build in an open project, or None."""
    for package in _open_projects():
        build = mlx_dir(package, model_id)
        if (build / CARD).is_file():
            return build
    return None


def kraken_ids(package: str | Path) -> list[str]:
    from fichero_server.llm.kraken_runtime import TRAINED_READER_PREFIX

    root = models_dir(package)
    if not root.is_dir():
        return []
    return sorted(p.name for p in root.glob(f"{TRAINED_READER_PREFIX}*") if (p / CARD).is_file())


def mlx_ids(package: str | Path) -> list[str]:
    from fichero_server.llm.mlx_model_store import TRAINED_ORG

    root = models_dir(package)
    if not root.is_dir():
        return []
    prefix = folder_name(f"{TRAINED_ORG}/")
    return sorted(f"{TRAINED_ORG}/{p.name[len(prefix):]}" for p in root.glob(f"{prefix}*")
                  if (p / MLX_BUILD / CARD).is_file())


def open_project_kraken_ids() -> list[str]:
    return sorted({m for package in _open_projects() for m in kraken_ids(package)})


def open_project_mlx_ids() -> list[str]:
    return sorted({m for package in _open_projects() for m in mlx_ids(package)})


def make_global(package: str | Path, model_id: str) -> dict[str, Any]:
    """Copy one of this project's trained models into the engine's global store, card and weights.

    The project keeps its copy. The card is copied as it is (`not_for_release` included) with where it
    came from added. Raises `NotInProject` when the project holds no model by that id, `FileExistsError`
    when the global store already has one by that id (it is never overwritten)."""
    from fichero_server.llm.kraken_runtime import TRAINED_READER_PREFIX
    from fichero_server.llm.mlx_model_store import TRAINED_ORG

    stamp = {"project_path": str(Path(package)), "at": datetime.now(timezone.utc).isoformat()}
    if model_id.startswith(TRAINED_READER_PREFIX):
        return _kraken_global(package, model_id, stamp)
    if model_id.startswith(f"{TRAINED_ORG}/"):
        return _mlx_global(package, model_id, stamp)
    raise NotInProject(f"{model_id} is not a model Fichero trained")


def _kraken_global(package: str | Path, model_id: str, stamp: dict[str, Any]) -> dict[str, Any]:
    from fichero_server.llm.kraken_runtime import _global_marker_path, recognition_data_home, recognition_model_dir

    record_path = kraken_record(package, model_id)
    if not record_path.is_file():
        raise NotInProject(f"{model_id} is not a model in this project")
    marker = _global_marker_path(model_id)
    if marker.exists():
        raise FileExistsError(f"{model_id} is already in the global store")
    record = json.loads(record_path.read_text(encoding="utf-8"))
    source = record_path.parent / str(record["model_path"])
    folder = recognition_data_home() / model_id
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / source.name
    shutil.copy2(source, target)
    record = {**record, "model_path": str(target),
              "trained": {**record.get("trained", {}), "made_global_from": stamp}}
    recognition_model_dir().mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps(record, indent=1), encoding="utf-8")
    return {"model_id": model_id, "global_path": str(target), "may_publish": _may_publish(record["trained"])}


def _mlx_global(package: str | Path, model_id: str, stamp: dict[str, Any]) -> dict[str, Any]:
    from fichero_server.llm.mlx_model_store import TRAINED_CARD, get_mlx_model_store

    build = mlx_dir(package, model_id)
    if not (build / CARD).is_file():
        raise NotInProject(f"{model_id} is not a model in this project")
    store = get_mlx_model_store()
    dest = store.global_trained_dir(model_id)
    if (dest / TRAINED_CARD).exists():
        raise FileExistsError(f"{model_id} is already in the global store")
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(build, dest, dirs_exist_ok=True)
    card = json.loads((dest / TRAINED_CARD).read_text(encoding="utf-8"))
    adapter = model_folder(package, model_id) / ADAPTER
    if adapter.is_dir():
        adapters = store.root / "adapters" / model_id.split("/", 1)[1]
        if adapters.exists():
            shutil.rmtree(adapters)
        shutil.copytree(adapter, adapters)
        card["adapter_path"] = str(adapters)
    card["made_global_from"] = stamp
    builds = card.get("builds") if isinstance(card.get("builds"), dict) else {}
    if isinstance(builds.get("mlx"), dict):
        builds["mlx"]["path"] = str(dest)
    if isinstance(builds.get("hf"), dict):  # the merged weights stay in the project (or the bucket), never copied
        builds["hf"].pop("merged_here", None)
        builds["hf"]["adapter_here"] = card.get("adapter_path")
    (dest / TRAINED_CARD).write_text(json.dumps(card, indent=1), encoding="utf-8")
    return {"model_id": model_id, "global_path": str(dest), "may_publish": _may_publish(card)}


def _may_publish(card: dict[str, Any]) -> bool:
    """The one test of whether a model may be released: its card says `not_for_release: false`."""
    return card.get("not_for_release") is False
