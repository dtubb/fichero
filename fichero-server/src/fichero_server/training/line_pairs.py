"""Line pictures and their teacher's readings, as training pairs for a vision model (#5398).

The vision-model card of the train job (`compute.tune.lora`) learns from the SAME training set as the
Kraken card: the teacher's line passes written as PAGE XML beside each photograph
(`training.kraken_set`). Each TextLine becomes one pair:

* the picture: cut from the photograph by `llm.line_reader.crop_line`, the very cut the teacher
  read (`compute.tune.input-is-a-training-set`: no second way to cut line pictures);
* the instruction: the line reader's own prompt for one picture (`line_reader.prompt_for(1, …)`);
* the answer: what the teacher's reply to that prompt is, a JSON array of one string.

So the student learns the teacher's task as the line reader asks it, and can be put in the teacher's
place in the same workflow. Pairs are written to `pairs.jsonl` beside a `lines/` folder, inside the
set, so the same send carries both.
"""
from __future__ import annotations

import json
from fichero_server.security.xml_security import parse_xml_string
from pathlib import Path

from PIL import Image

from fichero_server.formats.pagexml import PAGE_NS_2019
from fichero_server.llm.line_reader import crop_line, prompt_for
from fichero_server.training.kraken_set import MANIFEST

PAIRS = "pairs.jsonl"
LINES_DIR = "lines"
_NS = f"{{{PAGE_NS_2019}}}"


def _points(coords: str) -> list[tuple[float, float]]:
    return [tuple(float(v) for v in pair.split(",")) for pair in coords.split()]


def lines_of(page_xml: str) -> list[tuple[list[tuple[float, float]], str]]:
    """(polygon in pixels, text) for each TextLine with an outline and some text, in file order."""
    root = parse_xml_string(page_xml)
    found = []
    for line in root.iter(f"{_NS}TextLine"):
        coords = line.find(f"{_NS}Coords")
        text = "".join(u.text or "" for u in line.iter(f"{_NS}Unicode")).strip()
        if coords is not None and coords.get("points") and text:
            found.append((_points(coords.get("points")), text))
    return found


def write_line_pairs(set_dir: str | Path, *, language: str | None = None) -> int:
    """Add `lines/` and `pairs.jsonl` to a training set; returns the number of pairs."""
    root = Path(set_dir)
    manifest = json.loads((root / MANIFEST).read_text(encoding="utf-8"))
    (root / LINES_DIR).mkdir(exist_ok=True)
    prompt = prompt_for(1, language)
    count = 0
    with (root / PAIRS).open("w", encoding="utf-8") as out:
        for page in manifest["pages"]:
            image = Image.open(root / page["image"])
            image.load()
            stem = Path(page["xml"]).stem
            for index, (polygon, text) in enumerate(lines_of((root / page["xml"]).read_text(encoding="utf-8")), 1):
                name = f"{LINES_DIR}/{stem}_{index:03d}.jpg"
                crop_line(image, polygon).save(root / name, format="JPEG", quality=90)
                out.write(json.dumps({"image": name, "prompt": prompt,
                                      "answer": json.dumps([text], ensure_ascii=False),
                                      "document_id": page["document_id"], "line": index},
                                     ensure_ascii=False) + "\n")
                count += 1
    manifest["line_pairs"] = count
    (root / MANIFEST).write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    return count
