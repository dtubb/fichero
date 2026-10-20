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
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Callable
from xml.sax.saxutils import escape, quoteattr

try:  # in the engine (tests, a local run)
    from fichero_server.llm.line_cut import crop_line, parse_answer
except ImportError:  # shipped alone (a Hugging Face Job): `run_shard` loads `_fichero/line_cut.py` from the package
    crop_line = parse_answer = None  # type: ignore[assignment]

PAGE_NS = "http://schema.primaresearch.org/PAGE/gts/pagecontent/2019-07-15"


# --- pure parts: the line cut and the answer parser are the engine's own (`llm/line_cut.py`), shipped beside this file ---

def _points(points: list) -> str:
    return " ".join(f"{round(x)},{round(y)}" for x, y in points)


def page_xml(source_id: str, size: tuple[int, int], lines: list[dict[str, Any]], *, creator: str,
             image_name: str | None = None) -> str:
    """PAGE XML for one source: one region holding the lines in reading order, in the image's pixels.
    `image_name` names the pixels read: for a IIIF page the exact Image API request, so the file
    landing keeps as the pass's evidence says what was seen (`iiif.run.records-pixels-seen`)."""
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
            f'  <Page imageFilename={quoteattr(image_name or source_id + ".jpg")} imageWidth="{width}" imageHeight="{height}">\n'
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
    processor = AutoProcessor.from_pretrained(step["model"], revision=step.get("model_revision"))
    model = AutoModelForImageTextToText.from_pretrained(step["model"], revision=step.get("model_revision"),
                                                        torch_dtype=torch.bfloat16, device_map=device,
                                                        use_safetensors=True)  # never unpickle a repository (#5981 sweep)
    if step.get("adapter"):  # a PEFT adapter on its base, merged so the read runs as a plain model (#5977)
        from huggingface_hub import snapshot_download
        from peft import PeftModel

        folder = snapshot_download(step["adapter"], revision=step["adapter_revision"],
                                   allow_patterns=["*.safetensors", "*.json"])  # no pickle is fetched, so none can load
        model = PeftModel.from_pretrained(model, folder).merge_and_unload()
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
            text = ask(crop_line(image, line["polygon"]))
            if text is not None:  # no writing on this line: dropped, as the line reader does
                kept.append({**line, "text": text})
        return kept

    return read


def vllm_batch_asker(step: dict[str, Any]) -> Callable[[list[Any]], list[str | None]]:
    """vLLM offline batch inference inside this process (no server): the model loads once; every line picture of a
    page is answered in one `chat` call (`compute.hpc.vllm-offline-reader`)."""
    from vllm import LLM, SamplingParams

    llm = LLM(model=step["model"], tensor_parallel_size=int(step.get("tensor_parallel") or 1), max_model_len=4096)
    sampling = SamplingParams(temperature=0, max_tokens=256)
    prompt = step["prompt"]

    def ask(pictures: list[Any]) -> list[str | None]:
        messages = [[{"role": "user", "content": [{"type": "image_pil", "image_pil": p},
                                                   {"type": "text", "text": prompt}]}] for p in pictures]
        out = []
        for result in llm.chat(messages, sampling_params=sampling):
            parsed = parse_answer(result.outputs[0].text, 1)
            out.append(parsed[0] if parsed else None)
        return out

    return ask


def vllm_reader(package: Path, step: dict[str, Any], device: str) -> Callable[[Any], list[dict[str, Any]]]:
    from importlib import resources

    from kraken import blla
    from kraken.lib import vgsl

    segmenter = vgsl.TorchVGSLModel.load_model(resources.files("kraken").joinpath("blla.mlmodel"))
    ask = vllm_batch_asker(step)

    def read(image: Any) -> list[dict[str, Any]]:
        lines = [line for line in _raw_lines(blla.segment(image, model=segmenter)) if line["polygon"]]
        texts = ask([crop_line(image, line["polygon"]) for line in lines]) if lines else []
        return [{**line, "text": text} for line, text in zip(lines, texts) if text is not None]

    return read


READERS = {"kraken": kraken_reader, "vlm": vlm_reader, "vlm-vllm": vllm_reader}


def reader_for(step: dict[str, Any]) -> Callable[..., Callable[[Any], list[dict[str, Any]]]]:
    return READERS["vlm-vllm" if step["reader"] == "vlm" and step.get("engine") == "vllm" else step["reader"]]


# --- the shard ---------------------------------------------------------------------------------------

def run_shard(package: Path, shard: int, out: Path, *, reader: Callable[[Any], list[dict[str, Any]]] | None = None,
              get: Callable | None = None, device: str = "cuda:0",
              sleep: Callable[[float], None] = time.sleep) -> dict[str, Any]:
    from PIL import Image

    sys.path.insert(0, str(package / "_fichero"))
    from iiif_fetch import PoliteFetcher, image_url, urllib_get  # shipped beside this script

    global crop_line, parse_answer
    if crop_line is None:
        from line_cut import crop_line, parse_answer  # noqa: F811  (the engine's own, shipped in the package)

    job = json.loads((package / "job.json").read_text(encoding="utf-8"))
    indices = job["shards"][shard]
    step, longest = job["step"], job["fetch"]["longest"]
    folder = out / f"shard-{shard:05d}"
    folder.mkdir(parents=True, exist_ok=True)
    outcome_path = folder / "_outcome.json"
    outcome = json.loads(outcome_path.read_text(encoding="utf-8")) if outcome_path.exists() else {"sources": {}}
    fetcher = PoliteFetcher(get=get or urllib_get, sleep=sleep)
    read = reader or reader_for(step)(package, step, device)
    started = time.time()
    images = package
    if (package / f"shards/shard-{shard:05d}.tar").exists():  # staged as a tar: unpack to the node's own disk
        import tarfile
        import tempfile

        images = Path(tempfile.mkdtemp(prefix=f"shard-{shard:05d}-", dir=os.environ.get("SLURM_TMPDIR")))
        with tarfile.open(package / f"shards/shard-{shard:05d}.tar") as tar:
            tar.extractall(images, filter="data")
    for index in indices:
        source = job["sources"][index]
        target = folder / f"{source['id']}.xml"
        if target.exists() and outcome["sources"].get(source["id"], {}).get("ok"):
            continue  # done before this task was cut short
        try:
            fetched = package / prefetched(source)
            seen = image_url(source["iiif_service"], longest=longest) if source.get("iiif_service") else source["image"]
            if source.get("iiif_service") and fetched.exists():  # fetched on a login node beforehand
                image = Image.open(fetched)
            elif source.get("iiif_service"):
                data = fetcher.fetch(seen)
                image = Image.open(io.BytesIO(data))
            else:
                image = Image.open(images / source["image"])
            image.load()
            image = image.convert("RGB")
            lines = read(image)
            target.write_text(page_xml(source["id"], image.size, lines, creator=f"Fichero remote reader ({step['card']})",
                                       image_name=seen), encoding="utf-8")
            outcome["sources"][source["id"]] = {"ok": True, "size": list(image.size), "lines": len(lines), "seen": seen}
        except Exception as exc:  # noqa: BLE001 -- one source's failure is recorded; the shard goes on
            outcome["sources"][source["id"]] = {"ok": False, "why": f"{type(exc).__name__}: {exc}"[:500]}
        tmp = outcome_path.with_suffix(".part")
        tmp.write_text(json.dumps(outcome, indent=1), encoding="utf-8")
        os.replace(tmp, outcome_path)
    outcome.update({"shard": shard, "done": True, "seconds": round(time.time() - started, 1), "fetch": fetcher.stats})
    outcome_path.write_text(json.dumps(outcome, indent=1), encoding="utf-8")
    if images != package:
        shutil.rmtree(images, ignore_errors=True)  # nothing of the pages stays on the node
    return outcome


def prefetched(source: dict[str, Any]) -> str:
    return f"images/iiif-{source['id']}.jpg"


def prefetch(package: Path, *, get: Callable | None = None) -> dict[str, Any]:
    """Fetch every IIIF image of the package into it, politely, at the reader's size: run on a
    cluster's login node, which has the internet, before the array starts (compute nodes do not)."""
    sys.path.insert(0, str(package / "_fichero"))
    from iiif_fetch import FetchFailed, PoliteFetcher, image_url, urllib_get

    job = json.loads((package / "job.json").read_text(encoding="utf-8"))
    fetcher = PoliteFetcher(get=get or urllib_get)
    failed = {}
    for source in job["sources"]:
        target = package / prefetched(source)
        if not source.get("iiif_service") or target.exists():
            continue
        try:
            data = fetcher.fetch(image_url(source["iiif_service"], longest=job["fetch"]["longest"]))
        except FetchFailed as exc:
            failed[source["id"]] = str(exc)[:300]  # the shard tries again itself, or records it
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.with_suffix(".part").write_bytes(data)
        os.replace(target.with_suffix(".part"), target)
    return {"failed": failed, "fetch": fetcher.stats}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", required=True)
    parser.add_argument("--shard", type=int)
    parser.add_argument("--out")
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--prefetch", action="store_true", help="fetch the IIIF images into the package, and stop")
    args = parser.parse_args()
    if args.prefetch:
        done = prefetch(Path(args.package))
        print(f"prefetched; {len(done['failed'])} failed", flush=True)
        return
    if args.shard is None or not args.out:
        parser.error("--shard and --out are needed to read a shard")
    outcome = run_shard(Path(args.package), args.shard, Path(args.out), device=args.device)
    failed = [k for k, v in outcome["sources"].items() if not v.get("ok")]
    print(f"shard {args.shard}: {len(outcome['sources']) - len(failed)} read, {len(failed)} failed", flush=True)


if __name__ == "__main__":
    main()
