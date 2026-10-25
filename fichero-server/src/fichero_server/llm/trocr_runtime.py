"""A TrOCR model from Hugging Face as a line reader (`source.onboard.model-search-trocr-runs-here`, #5981). It reads the lines
Kraken found, one strip each: the page is cut by each line's outline, and the strips go to the TrOCR line reader the economy
HTR tool already has (`economy_htr.trocr_transcribe_lines`, the bundled torch and transformers, on the CPU unless the person
chose the GPU). Its reader id is `trocr-hf-<owner>--<repo>`.

Only safetensors weights are ever loaded: a `.bin`, `.pt` or `.ckpt` is a pickle, and unpickling a repository a recipe pin names
would run its code in the engine. The download pins the Hub's commit, takes no pickled file, and is refused in words when the
repository has no safetensors; the load names that commit and `use_safetensors=True`, from the files on this Mac only
(`source.onboard.model-search-trocr-runs-here`, review 765)."""
from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path
from typing import Any, Callable

from fichero_server.core.atomic_json import write_json_atomic

_READER = re.compile(r"^trocr-hf-([A-Za-z0-9_.-]+?)--([A-Za-z0-9_.-]+)$")
#: A strip is cut a little wider than the outline, as the economy tool does, so a stroke at the edge is not lost.
PAD = 6


def reader_id_for_trocr(repo: str) -> str:
    """The reader id of a Hub TrOCR repository; a name holding `--` could not be read back, so it has none."""
    owner, _, name = repo.partition("/")
    if not owner or not name or "--" in owner or "--" in name or "/" in name:
        raise ValueError(f"{repo!r} has no reader id (owner/name without '--')")
    return f"trocr-hf-{owner}--{name}"


def repo_of(reader_id: str | None) -> str | None:
    """The repository a TrOCR reader id names, or None for any other reader."""
    match = _READER.match(reader_id or "")
    return f"{match.group(1)}/{match.group(2)}" if match else None


def read_lines(image_path: str | Path, repo: str, lines: list[dict[str, Any]], *, frame: str | None = None) -> list[str]:
    """The text of each line (`{"id", "polygon"}` in page pixels), in the order given; "" for a line with no outline.
    Blocking and heavy: call it on the model lane."""
    from fichero_server.media.image_flatten import flatten_for_opaque_format
    from fichero_server.media.upright import open_in_frame
    from fichero_server.workflows.tools import economy_htr

    out = [""] * len(lines)
    with tempfile.TemporaryDirectory(prefix="trocr-lines-") as folder:
        page = open_in_frame(image_path, frame)  # the frame the lines were measured on
        paths: list[str] = []
        slots: list[int] = []
        for slot, line in enumerate(lines):
            points = line.get("polygon") or []
            if len(points) < 3:
                continue
            xs, ys = [p[0] for p in points], [p[1] for p in points]
            box = (max(0, int(min(xs)) - PAD), max(0, int(min(ys)) - PAD),
                   min(page.width, int(max(xs)) + PAD), min(page.height, int(max(ys)) + PAD))
            if box[2] <= box[0] or box[3] <= box[1]:
                continue
            path = Path(folder) / f"line-{slot:04d}.png"
            flatten_for_opaque_format(page.crop(box)).save(path, format="PNG")
            paths.append(str(path))
            slots.append(slot)
        if paths:
            for slot, text in zip(slots, economy_htr.trocr_transcribe_lines(paths, repo)):
                out[slot] = (text or "").strip()
    return out


#: Files that are pickles or a runtime this reader never loads: not downloaded.
PICKLED = ("*.bin", "*.pt", "*.pth", "*.ckpt", "*.pkl", "*.pickle", "*.h5", "*.msgpack", "*.onnx")


class NoSafetensors(ValueError):
    """The repository has no safetensors weights: Fichero will not load a pickled model."""


def _store() -> Path:
    from fichero_server.db.paths import hf_hub_dir

    return Path(hf_hub_dir())


def _record_path(repo: str) -> Path:
    return _store() / f"{reader_id_for_trocr(repo)}.installed.json"


def hub_info(repo: str) -> dict[str, Any]:
    """The Hub's answer for a repository: its commit (`sha`) and files (`siblings`). Network."""
    import requests

    found = requests.get(f"https://huggingface.co/api/models/{repo}", params={"blobs": "true"}, timeout=60)
    found.raise_for_status()
    return found.json()


def _snapshot(repo: str, revision: str) -> None:
    from huggingface_hub import snapshot_download

    from fichero_server.db.paths import hf_hub_dir

    snapshot_download(repo_id=repo, revision=revision, cache_dir=str(hf_hub_dir()), ignore_patterns=list(PICKLED))


def is_installed(repo: str) -> bool:
    """Whether the repository's safetensors were downloaded whole at a pinned commit (its record is written last)."""
    try:
        return bool(json.loads(_record_path(repo).read_text(encoding="utf-8")).get("revision"))
    except (OSError, ValueError):
        return False


def revision_of(repo: str) -> str | None:
    """The commit this Mac holds, or None when the repository is not downloaded."""
    try:
        return str(json.loads(_record_path(repo).read_text(encoding="utf-8")).get("revision") or "") or None
    except (OSError, ValueError):
        return None


def download(repo: str, *, should_stop: Callable[[], bool] = lambda: False, on_bytes: Callable[..., None] | None = None) -> str:
    """Download the repository's safetensors at the commit the Hub answers with, and return that commit. Refused, before
    anything downloads, when it has no `.safetensors` file; a pickled file beside them is never fetched."""
    info = hub_info(repo)
    names = [str(s.get("rfilename", "")) for s in info.get("siblings") or []]
    if not any(n.endswith(".safetensors") for n in names):
        raise NoSafetensors(f"{repo} has no safetensors weights (only a pickled file, if any): Fichero loads no pickled "
                            "model, so it will not download or run this one")
    revision = str(info.get("sha") or "")
    if not revision:
        raise NoSafetensors(f"{repo}: the Hub did not name a commit to pin")
    _snapshot(repo, revision)
    size = sum(int(s.get("size") or 0) for s in info.get("siblings") or [] if str(s.get("rfilename", "")).endswith(".safetensors"))
    write_json_atomic(_record_path(repo), {"repo": repo, "revision": revision, "bytes": size}, indent=None)
    return revision


def ensure(repo: str) -> str:
    """The pinned commit to load: the one downloaded, else download now (the TRIDIS default of the economy tool, which no
    plan listed first). Raises `NoSafetensors` in words for a repository with no safetensors."""
    return revision_of(repo) or download(repo)
