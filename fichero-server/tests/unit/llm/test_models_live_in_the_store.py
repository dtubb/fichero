"""`runtime.models-in-the-store`: every model the engine fetches or finds lives in Fichero's own store.

WHY (2026-10-11): Daniel found 4.2 GB of the TrOCR reader tridis in ~/.cache/huggingface, put there by economy_htr's
`from_pretrained(model_id)` with no cache_dir. Two guards:

* every load in the engine that can download (`from_pretrained`, `SentenceTransformer`, `hf_hub_download`,
  `snapshot_download`, fastembed's `TextEmbedding`) names where (`cache_dir`, `cache_folder` or `local_dir`), except
  in scripts that run on a remote machine (a Hugging Face Job, a cluster), which are named here with why;
* at engine start the Hugging Face cache variables point inside `model_store_root()`, so a library that resolves a
  model by itself (runtime resolution, not only a download) finds the store, never ~/.cache.
"""
from __future__ import annotations

import ast
import importlib
import os
from pathlib import Path

from _scan_files import scan_rglob

SRC =Path(__file__).resolve().parents[3] / "src" / "fichero_server"
LOADS = {"from_pretrained", "SentenceTransformer", "hf_hub_download", "snapshot_download", "TextEmbedding"}
WHERE = {"cache_dir", "cache_folder", "local_dir"}
#: Scripts that run where the job runs, never on this Mac: their cache is that machine's.
REMOTE = {
    "remote_read/runner.py": "a uv script run on Hugging Face Jobs or a cluster's Slurm array",
    "training/hf_vision_lora_train.py": "a uv script run inside a Hugging Face Job",
}


def _loads_without_a_place() -> list[str]:
    found = []
    for path in sorted(scan_rglob(SRC, "*.py")):
        rel = path.relative_to(SRC).as_posix()
        if rel in REMOTE:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Call):
                continue
            name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
            if name in LOADS and not WHERE & {k.arg for k in node.keywords if k.arg}:
                if name == "TextEmbedding" and not node.keywords and not node.args:
                    continue  # TextEmbedding.list_supported_models() and the like are not loads
                found.append(f"{rel}:{node.lineno} {name}(...)")
    return found


def test_every_load_names_the_store():
    assert _loads_without_a_place() == [], (
        "a model load without cache_dir/local_dir downloads into ~/.cache: pass the store (db.paths.hf_hub_dir())")


def test_the_remote_exceptions_still_exist():
    for rel in REMOTE:
        assert (SRC / rel).is_file(), f"{rel} is gone: remove it from REMOTE"


def test_at_engine_start_every_hugging_face_cache_points_into_the_store(monkeypatch, tmp_path):
    import fichero_server
    from fichero_server.db.paths import model_store_root
    from fichero_server.db.paths import HF_CACHE_ENV as _ENV

    monkeypatch.setenv("FICHERO_MODEL_STORE_ROOT", str(tmp_path / "store"))
    for name in _ENV:
        monkeypatch.delenv(name, raising=False)
    importlib.reload(fichero_server)  # the engine's first import, as uvicorn and the embedded main both make it

    root = model_store_root().resolve()
    for name in _ENV:
        value = os.environ.get(name)
        assert value and root in Path(value).resolve().parents, (name, value)


def test_a_variable_already_set_is_left_alone(monkeypatch, tmp_path):
    from fichero_server.db.paths import pin_hf_caches

    monkeypatch.setenv("HF_HOME", str(tmp_path / "mine"))
    assert pin_hf_caches()["HF_HOME"] == str(tmp_path / "mine")
