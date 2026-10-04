# /// script
# requires-python = ">=3.11,<3.14"
# dependencies = ["kraken==7.1.1", "pillow>=11"]
# ///
"""Fichero's reading runner: one shard of a read package, where the job runs (#5398 slice 2).

    python runner.py --package <dir> --shard <n> --out <dir>

Runs on Hugging Face Jobs (a uv script) or as one task of a Slurm array on a cluster
(`compute.job.array-by-shard`). For each source of the shard it gets the image (from the package, or
from the source's IIIF Image API service, politely, at `fetch.longest` pixels), finds the lines with
Kraken's line finder, reads each line with the package's reader, and writes one PAGE XML file per
source, its coordinates in the pixels of the image it read. `_outcome.json` records each source's
outcome; a source that fails is recorded and the shard goes on. A shard re-run skips the sources it
already wrote (a preempted task resumes). The Mac lands the results; nothing here writes to a library
(`compute.land.only-the-mac-writes`).

A vision-model reader (`reader: vlm`) needs torch and transformers, which the submitter adds as the
job's dependencies; the line picture and the instruction are the line reader's own
(`llm/line_reader.py`, whose crop and answer parsing are mirrored here and pinned by tests).
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Callable
from xml.sax.saxutils import escape, quoteattr

PAGE_NS = "http://schema.primaresearch.org/PAGE/gts/pagecontent/2019-07-15"
_MAX_CROP_WIDTH = 1600


# --- pure parts (pinned by tests against Fichero's own reader and line reader) -----------------------

def crop_box(polygon: list, width: int, height: int) -> tuple[float, float, float, float]:
    """The line's polygon bounds padded by a third of its height: `line_reader.crop_line`'s box."""
    xs = [p[0] for p in polygon]
    ys = [p[1] for p in polygon]
    pad = (max(ys) - min(ys)) / 3
    return (max(0, min(xs) - pad), max(0, min(ys) - pad), min(width, max(xs) + pad), min(height, max(ys) + pad))


def parse_answer(raw: str, n: int) -> list[str | None] | None:
    """The model's JSON array of n readings, or None: `line_reader.parse_answer`."""
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", (raw or "").strip())
    try:
        answer = json.loads(text)
    except ValueError:
        return None
    if not isinstance(answer, list) or len(answer) != n or not all(a is None or isinstance(a, str) for a in answer):
        return None
    return [a.strip() if isinstance(a, str) and a.strip() else None for a in answer]


def _points(points: list) -> str:
    return " ".join(f"{round(x)},{round(y)}" for x, y in points)


def page_xml(source_id: str, size: tuple[int, int], lines: list[dict[str, Any]], *, creator: str) -> str:
    """PAGE XML for one source: one region holding the lines in reading order, in the image's pixels."""
    width, height = size
    rows = []
    for index, line in enumerate(lines, 1):
        polygon, baseline = line.get("polygon") or [], line.get("baseline") or []
        if len(polygon) < 3 or len(baseline) < 2:
            continue
        rows.append(
            f'      <TextLine id="l{index}"><Coords points="{_points(polygon)}"/><Baseline points="{_points(baseline)}"/>'
            f'<TextEquiv><Unicode>{escape(line.get("text") or "")}</Unicode></TextEquiv></TextLine>')
    region = (f'    <TextRegion id="r1"><Coords points="0,0 {width},0 {width},{height} 0,{height}"/>\n'
              + "\n".join(rows) + "\n    </TextRegion>\n") if rows else ""
    return (f'<?xml version="1.0" encoding="UTF-8"?>\n<PcGts xmlns="{PAGE_NS}">\n'
            f'  <Metadata><Creator>{escape(creator)}</Creator><Created>1970-01-01T00:00:00</Created>'
            f'<LastChange>1970-01-01T00:00:00</LastChange></Metadata>\n'
            f'  <Page imageFilename={quoteattr(source_id + ".jpg")} imageWidth="{width}" imageHeight="{height}">\n'
            f'{region}  </Page>\n</PcGts>\n')


# --- readers (heavy imports inside) -----------------------------------------------------------------

def _raw_lines(segmentation: Any) -> list[dict[str, Any]]:
    out = []
    for line in getattr(segmentation, "lines", None) or []:
        out.append({"baseline": [[float(x), float(y)] for x, y in (getattr(line, "baseline", None) or [])],
                    "polygon": [[float(x), float(y)] for x, y in (getattr(line, "boundary", None) or [])]})
    return out


def kraken_reader(package: Path, step: dict[str, Any], device: str) -> Callable[[Any], list[dict[str, Any]]]:
    from importlib import resources

    from kraken import blla
    from kraken.configs import RecognitionInferenceConfig
    from kraken.lib import vgsl
    from kraken.tasks import RecognitionTaskModel

    segmenter = vgsl.TorchVGSLModel.load_model(resources.files("kraken").joinpath("blla.mlmodel"))
    net = RecognitionTaskModel.load_model(str(package / step["model_file"]))
    config = RecognitionInferenceConfig(accelerator="gpu" if device.startswith("cuda") else "cpu", device=1)

    def read(image: Any) -> list[dict[str, Any]]:
        segmentation = blla.segment(image, model=segmenter)
        lines = _raw_lines(segmentation)
        for line, record in zip(lines, net.predict(image, segmentation, config)):
            line["text"] = str(getattr(record, "prediction", record) or "")
        return lines

    return read


def vlm_reader(package: Path, step: dict[str, Any], device: str) -> Callable[[Any], list[dict[str, Any]]]:
    from importlib import resources

    import torch
    from kraken import blla
    from kraken.lib import vgsl
    from transformers import AutoModelForImageTextToText, AutoProcessor

    segmenter = vgsl.TorchVGSLModel.load_model(resources.files("kraken").joinpath("blla.mlmodel"))
    processor = AutoProcessor.from_pretrained(step["model"])
    model = AutoModelForImageTextToText.from_pretrained(step["model"], torch_dtype=torch.bfloat16, device_map=device)
    prompt = step["prompt"]

    def ask(picture: Any) -> str | None:
        chat = [{"role": "user", "content": [{"type": "image"}, {"type": "text", "text": prompt}]}]
        text = processor.apply_chat_template(chat, tokenize=False, add_generation_prompt=True)
        inputs = processor(text=[text], images=[picture], return_tensors="pt").to(model.device)
        with torch.no_grad():
            generated = model.generate(**inputs, max_new_tokens=256, do_sample=False)
        answer = processor.batch_decode(generated[:, inputs["input_ids"].shape[1]:], skip_special_tokens=True)[0]
        parsed = parse_answer(answer, 1)
        return parsed[0] if parsed else None

    def read(image: Any) -> list[dict[str, Any]]:
        lines = [line for line in _raw_lines(blla.segment(image, model=segmenter)) if line["polygon"]]
        kept = []
        for line in lines:
            picture = image.crop(crop_box(line["polygon"], image.width, image.height))
            if picture.width > _MAX_CROP_WIDTH:
                picture = picture.resize((_MAX_CROP_WIDTH, round(picture.height * _MAX_CROP_WIDTH / picture.width)))
            text = ask(picture.convert("RGB"))
            if text is not None:  # no writing on this line: dropped, as the line reader does
                kept.append({**line, "text": text})
        return kept

    return read


READERS = {"kraken": kraken_reader, "vlm": vlm_reader}


# --- the shard ---------------------------------------------------------------------------------------

def run_shard(package: Path, shard: int, out: Path, *, reader: Callable[[Any], list[dict[str, Any]]] | None = None,
              get: Callable | None = None, device: str = "cuda:0") -> dict[str, Any]:
    from PIL import Image

    sys.path.insert(0, str(package / "_fichero"))
    from iiif_fetch import PoliteFetcher, image_url, urllib_get  # shipped beside this script

    job = json.loads((package / "job.json").read_text(encoding="utf-8"))
    indices = job["shards"][shard]
    step, longest = job["step"], job["fetch"]["longest"]
    folder = out / f"shard-{shard:05d}"
    folder.mkdir(parents=True, exist_ok=True)
    outcome_path = folder / "_outcome.json"
    outcome = json.loads(outcome_path.read_text(encoding="utf-8")) if outcome_path.exists() else {"sources": {}}
    fetcher = PoliteFetcher(get=get or urllib_get)
    read = reader or READERS[step["reader"]](package, step, device)
    started = time.time()
    for index in indices:
        source = job["sources"][index]
        target = folder / f"{source['id']}.xml"
        if target.exists() and outcome["sources"].get(source["id"], {}).get("ok"):
            continue  # done before this task was cut short
        try:
            if source.get("iiif_service"):
                data = fetcher.fetch(image_url(source["iiif_service"], longest=longest))
                image = Image.open(io.BytesIO(data))
            else:
                image = Image.open(package / source["image"])
            image.load()
            image = image.convert("RGB")
            lines = read(image)
            target.write_text(page_xml(source["id"], image.size, lines, creator=f"Fichero remote reader ({step['card']})"),
                              encoding="utf-8")
            outcome["sources"][source["id"]] = {"ok": True, "size": list(image.size), "lines": len(lines)}
        except Exception as exc:  # noqa: BLE001 -- one source's failure is recorded; the shard goes on
            outcome["sources"][source["id"]] = {"ok": False, "why": f"{type(exc).__name__}: {exc}"[:500]}
        tmp = outcome_path.with_suffix(".part")
        tmp.write_text(json.dumps(outcome, indent=1), encoding="utf-8")
        os.replace(tmp, outcome_path)
    outcome.update({"shard": shard, "done": True, "seconds": round(time.time() - started, 1), "fetch": fetcher.stats})
    outcome_path.write_text(json.dumps(outcome, indent=1), encoding="utf-8")
    return outcome


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", required=True)
    parser.add_argument("--shard", type=int, required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--device", default="cuda:0")
    args = parser.parse_args()
    outcome = run_shard(Path(args.package), args.shard, Path(args.out), device=args.device)
    failed = [k for k, v in outcome["sources"].items() if not v.get("ok")]
    print(f"shard {args.shard}: {len(outcome['sources']) - len(failed)} read, {len(failed)} failed", flush=True)


if __name__ == "__main__":
    main()
