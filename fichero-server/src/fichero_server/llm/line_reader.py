"""Read the lines Kraken found with a vision model (`compute.distill`: the teacher labels lines).

Kraken's segmenter finds each written line (a polygon and a baseline) and reads nothing. This
cuts each line out of the page and asks a vision model what it says, a few lines per call, so
the result is Kraken's own geometry carrying the model's text. That pairing is what Kraken trains
on: exported as PAGE XML, it is the training set for distilling a large model's reading into a
small local Kraken reader. A line the model says holds no writing (a ruler, graph paper, blank
paper) is dropped, and the count is recorded; a batch whose answer cannot be matched line for
line is re-asked one line at a time, never guessed into place.
"""
from __future__ import annotations

import asyncio
import base64
import dataclasses
import io
import json
import logging
import re

from PIL import Image

from fichero_server.llm.read_guard import READ_FLAG_KEY, ReadFlag, check_read, finish_reason_of, is_truncation
from fichero_server.media.ocr_geometry import OCRGeometryBox, OCRGeometryLevel, OCRGeometryResult

logger = logging.getLogger(__name__)

LINES_PER_CALL = 8
CONCURRENT_CALLS = 4
_MAX_CROP_WIDTH = 1600
#: What one line's reading may spend (#5534). A line of handwriting is a few dozen words; the
#: step's own ceiling (8,192) let a student that loops on a line ("1000000000…") generate for
#: ~100 s per line at 20 tokens/s, past the 60 s request timeout, and every retry ran it again.
TOKENS_PER_LINE = 192

PROMPT = (
    "Each of the {n} images is one line cut from a photographed handwritten page{language}. "
    "For each image, in order, write exactly what is written on it: keep the spelling, "
    "abbreviations, punctuation and capitals as written; do not correct or modernise; leave out "
    "fragments of the lines above and below that show at the edges. If an image holds no "
    "writing (a ruler, graph paper, blank paper, a smudge), answer null for it. Reply with only "
    "a JSON array of {n} strings or nulls, nothing else."
)


def crop_line(page: Image.Image, polygon_px: list) -> Image.Image:
    """The line's polygon bounds, padded by a third of its height, at most 1,600 px wide: the
    picture the teacher reads. A student is trained on exactly this cut (`training.line_pairs`),
    so it learns the teacher's task and is asked it the same way."""
    xs = [p[0] for p in polygon_px]
    ys = [p[1] for p in polygon_px]
    pad = (max(ys) - min(ys)) / 3
    crop = page.crop((max(0, min(xs) - pad), max(0, min(ys) - pad),
                      min(page.width, max(xs) + pad), min(page.height, max(ys) + pad)))
    if crop.width > _MAX_CROP_WIDTH:
        crop = crop.resize((_MAX_CROP_WIDTH, round(crop.height * _MAX_CROP_WIDTH / crop.width)))
    return crop.convert("RGB")


def prompt_for(n: int, language: str | None = None) -> str:
    """The instruction for n line pictures, with the language when it is known."""
    hint = f" (in {language})" if language and language not in ("und", "unknown") else ""
    return PROMPT.format(n=n, language=hint)


def _crop_data_uri(page: Image.Image, polygon_px: list) -> str:
    """`crop_line` as a JPEG data URI."""
    buf = io.BytesIO()
    crop_line(page, polygon_px).save(buf, format="JPEG", quality=90)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def _crop(page: Image.Image, box: OCRGeometryBox) -> str:
    return _crop_data_uri(page, box.metadata["polygon_px"])


def lines_per_call(config) -> int:
    """How many line pictures one call carries: `LINES_PER_CALL`, or what a model Fichero trained says
    on its card (a student trained on one picture at a time is asked one at a time)."""
    if getattr(config, "provider", None) == "omlx":
        from fichero_server.llm.mlx_model_store import get_mlx_model_store

        card = get_mlx_model_store().trained_card(str(getattr(config, "model", "") or "").removeprefix("omlx/"))
        if card and int(card.get("lines_per_call") or 0) > 0:
            return int(card["lines_per_call"])
    return LINES_PER_CALL


def line_call_config(config, n: int):
    """`config` with its output ceiling cut to what n lines can need (`TOKENS_PER_LINE`)."""
    cap = TOKENS_PER_LINE * n + 32
    current = getattr(config, "max_tokens", None)
    if not dataclasses.is_dataclass(config) or (isinstance(current, int) and 0 < current <= cap):
        return config
    return dataclasses.replace(config, max_tokens=cap)


def cut_short_reading(raw: str) -> str | None:
    """A one-line answer that ran out of room, as the text it got to (the read checker then marks
    it), rather than dropped as a line with no writing."""
    text = re.sub(r'^\s*(?:```(?:json)?\s*)?\[?\s*"?', "", raw or "").strip()
    return text or None


def parse_answer(raw: str, n: int) -> list[str | None] | None:
    """The model's JSON array of n readings, or None when it is not exactly that."""
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", (raw or "").strip())
    try:
        answer = json.loads(text)
    except ValueError:
        return None
    if not isinstance(answer, list) or len(answer) != n:
        return None
    if not all(a is None or isinstance(a, str) for a in answer):
        return None
    return [a.strip() if isinstance(a, str) and a.strip() else None for a in answer]


async def read_lines(image_path: str, lines: OCRGeometryResult, config, *, language: str | None = None) -> OCRGeometryResult:
    """Kraken's lines (`segment_to_geometry`) with each one's text read by `config`'s vision model."""
    from fichero_server.llm import vision

    page = Image.open(image_path)
    page.load()
    found = [b for b in lines.boxes if b.metadata.get("polygon_px")]
    crops = [_crop(page, b) for b in found]
    gate = asyncio.Semaphore(CONCURRENT_CALLS)

    async def ask(indices: list[int]) -> list[str | None] | None:
        async with gate:
            raw = await vision(images=[crops[i] for i in indices],
                               prompt=prompt_for(len(indices), language),
                               config=line_call_config(config, len(indices)))
        answer = parse_answer(raw, len(indices))
        if answer is None and len(indices) == 1 and is_truncation(finish_reason_of(raw)):
            return [cut_short_reading(raw)]
        return answer

    async def batch(indices: list[int]) -> list[str | None]:
        answer = await ask(indices)
        if answer is None and len(indices) > 1:  # re-ask line by line rather than misplace a reading
            singles = await asyncio.gather(*(ask([i]) for i in indices))
            answer = [s[0] if s else None for s in singles]
        return answer or [None]

    per_call = lines_per_call(config)
    groups = [list(range(i, min(i + per_call, len(found)))) for i in range(0, len(found), per_call)]
    readings = [r for group in await asyncio.gather(*(batch(g) for g in groups)) for r in group]

    boxes, texts, cursor = [], [], 0
    flagged: list[ReadFlag] = []
    for box, text in zip(found, readings):
        if text is None:
            continue
        texts.append(text)
        # Each line's reading is checked as it lands (#5522): one picture is one line, so a reading
        # that loops or runs far past a line's length is marked on its box.
        flag = check_read(text, line_count=1, model=config.model)
        metadata = box.metadata
        if flag is not None:
            flagged.append(flag)
            metadata = {**box.metadata, READ_FLAG_KEY: flag.as_data()}
        boxes.append(box.model_copy(update={
            "text": text, "char_start": cursor, "char_end": cursor + len(text),
            "level": OCRGeometryLevel.LINE, "provider": config.provider, "model": config.model,
            "source": "kraken-lines+vision", "metadata": metadata,
        }))
        cursor += len(text) + 1
    logger.info("line reader %s: %d lines found, %d read, %d without writing, %d flagged",
                config.model, len(found), len(boxes), len(found) - len(boxes), len(flagged))
    page_metadata = {**lines.metadata, "lines_found_by": "kraken", "lines_found": len(found),
                     "lines_without_writing": len(found) - len(boxes), "lines_flagged": len(flagged)}
    if flagged:
        # The page's reading is as trusted as its worst line: it lands marked, not as the page's text.
        page_metadata[READ_FLAG_KEY] = {
            "kind": flagged[0].kind,
            "reason": f"{flagged[0].reason} on {len(flagged)} of its {len(boxes)} lines",
            "measure": {"lines_flagged": len(flagged), "lines_read": len(boxes), **flagged[0].measure},
        }
    return lines.model_copy(update={
        "text": "\n".join(texts), "boxes": boxes, "provider": config.provider, "model": config.model,
        "source": "kraken-lines+vision", "metadata": page_metadata,
    })
