"""A TrOCR model from Hugging Face as a line reader (`source.onboard.model-search-trocr-runs-here`, #5981). It reads the lines
Kraken found, one strip each: the page is cut by each line's outline, and the strips go to the TrOCR line reader the economy
HTR tool already has (`economy_htr.trocr_transcribe_lines`, the bundled torch and transformers, on the CPU unless the person
chose the GPU). Its reader id is `trocr-hf-<owner>--<repo>`; the weights download into Fichero's store on first use."""
from __future__ import annotations

import re
import tempfile
from pathlib import Path
from typing import Any

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


def read_lines(image_path: str | Path, repo: str, lines: list[dict[str, Any]]) -> list[str]:
    """The text of each line (`{"id", "polygon"}` in page pixels), in the order given; "" for a line with no outline.
    Blocking and heavy: call it on the model lane."""
    from PIL import Image

    from fichero_server.media.image_flatten import flatten_for_opaque_format
    from fichero_server.workflows.tools import economy_htr

    out = [""] * len(lines)
    with tempfile.TemporaryDirectory(prefix="trocr-lines-") as folder, Image.open(image_path) as page:
        page.load()
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
