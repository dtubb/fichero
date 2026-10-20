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
import logging
import re

from PIL import Image

from fichero_server.llm.working_lines import NO_WRITING_KEY
from fichero_server.llm.line_cut import _MAX_CROP_WIDTH, _says_null, crop_line, parse_answer  # noqa: F401  (one cut, one parser: shipped to the runner)
from fichero_server.llm.read_guard import READ_FLAG_KEY, ReadFlag, check_read, finish_reason_of, is_truncation
from fichero_server.media.ocr_geometry import OCRGeometryBox, OCRGeometryLevel, OCRGeometryResult

logger = logging.getLogger(__name__)

LINES_PER_CALL = 8
#: Calls one page asks at once. A model this engine serves is bounded again, across every page and
#: run, by what its memory allows (`llm.model_call_slot`, `local_inference.local_reads_at_once`:
#: one at a time for a 3B on an 8 GB Mac, #5537); a cloud model keeps these four.
CONCURRENT_CALLS = 4
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


#: Said before the line instruction when the page itself rides once, first, beside the batch of lines.
PAGE_CONTEXT = ("Before the {n} line images comes one more, first: the whole page, reduced, so you can see the hand and "
                "what the page is. It is for context only: do not read it, and do not count it in your answer. ")
#: The page beside a batch is cut to this long side: enough to see the hand and the layout, cheap to send.
PAGE_CONTEXT_SIDE = 768
#: Providers that read one line picture at a time as trained, or are not generative: no page beside the lines.
NO_PAGE_CONTEXT = ("omlx", "apple", "kraken")


def prompt_for(n: int, language: str | None = None, page_context: bool = False) -> str:
    """The instruction for n line pictures, with the language when it is known, and the page's place when it rides."""
    hint = f" (in {language})" if language and language not in ("und", "unknown") else ""
    return (PAGE_CONTEXT.format(n=n) if page_context else "") + PROMPT.format(n=n, language=hint)


def _page_context_uri(page: Image.Image) -> str:
    """The whole page, cut to `PAGE_CONTEXT_SIDE` on its long side, as a JPEG data URI."""
    small = page.convert("RGB")
    small.thumbnail((PAGE_CONTEXT_SIDE, PAGE_CONTEXT_SIDE))
    buf = io.BytesIO()
    small.save(buf, format="JPEG", quality=70)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


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
    return None if _says_null(text) else text or None


def request_groups(found: list[OCRGeometryBox], granularity: str | None, per_call: int) -> list[list[int]]:
    """The lines (indices into `found`) each call carries. `granularity` is how the bake-off measured the reader
    (#5722): "lines" one a call, "region" one region a call (a line names its region by `parent_box_index`), "page"
    all in one. None: `per_call` lines a call, as before; the other three are not cut to it, because the reader was
    measured asking that way."""
    n = len(found)
    if granularity == "lines":
        return [[i] for i in range(n)]
    if granularity == "page":
        return [list(range(n))] if n else []
    if granularity == "region":
        groups: list[list[int]] = []
        for i, box in enumerate(found):
            if groups and found[groups[-1][0]].metadata.get("parent_box_index") == box.metadata.get("parent_box_index"):
                groups[-1].append(i)
            else:
                groups.append([i])
        return groups
    return [list(range(i, min(i + per_call, n))) for i in range(0, n, per_call)]


async def read_lines(image_path: str, lines: OCRGeometryResult, config, *, language: str | None = None,
                     apple: bool = False, granularity: str | None = None,
                     page_context: bool | None = None) -> OCRGeometryResult:
    """Kraken's lines (`segment_to_geometry`) with each one's text read by `config`'s vision model, or, with
    `apple`, by Apple Vision on each line's own picture (one line a call: its answer IS the reading, not a JSON
    array, and it is not checked for loops, as only a generative model loops)."""
    from fichero_server.llm import LLMConfig, vision

    if apple:
        config = LLMConfig(provider="apple", model="apple-vision")

    page = Image.open(image_path)
    page.load()
    found = [b for b in lines.boxes if b.metadata.get("polygon_px") and b.level == OCRGeometryLevel.LINE]
    # Kraken's regions are kept, first, as the lines' parents (#5487); a line names its region by position.
    kept = [(i, b) for i, b in enumerate(lines.boxes) if b.level != OCRGeometryLevel.LINE]
    regions = [b for _i, b in kept]
    moved = {i: n for n, (i, _b) in enumerate(kept)}
    crops = [_crop(page, b) for b in found]
    # Variant B (`source.recipe.kraken-lines-cloud-reads`): a generative model gets the page ONCE per request, reduced,
    # beside the batch of lines; never once a line, and never for a reader trained on one picture or Apple's.
    context = (not apple and getattr(config, "provider", "") not in NO_PAGE_CONTEXT) if page_context is None else page_context
    page_uri = _page_context_uri(page) if context and crops else None
    gate = asyncio.Semaphore(CONCURRENT_CALLS)

    async def ask(indices: list[int]) -> list[str | None] | None:
        async with gate:
            raw = await vision(images=([page_uri] if page_uri else []) + [crops[i] for i in indices],
                               prompt=prompt_for(len(indices), language, page_context=page_uri is not None),
                               config=line_call_config(config, len(indices)),
                               **({"language": language, "recognition_only_ok": True} if apple else {}))
        if apple:
            return [" ".join((raw or "").split()) or None]
        answer = parse_answer(raw, len(indices))
        if answer is None and len(indices) == 1 and is_truncation(finish_reason_of(raw)):
            return [cut_short_reading(raw)]
        if answer is None and len(indices) == 1:
            said = " ".join(str(raw or "").split())
            why_not[indices[0]] = (f"the model answered with text that is not a reading ({said[:80]!r})" if said
                                   else "the model gave no answer")
        return answer

    looked: set[int] = set()  # lines the reader answered for, with or without words
    why_not: dict[int, str] = {}  # a line asked on its own that came back unread, and what the model said (variant B)

    async def batch(indices: list[int]) -> list[str | None]:
        answer = await ask(indices)
        if answer is None and len(indices) > 1:  # re-ask line by line rather than misplace a reading
            singles = await asyncio.gather(*(ask([i]) for i in indices))
            answer = [s[0] if s else None for s in singles]
            looked.update(i for i, s in zip(indices, singles) if s is not None)
        elif answer is not None:
            looked.update(indices)
        return answer or [None]

    per_call = 1 if apple else lines_per_call(config)
    groups = request_groups(found, None if apple else granularity, per_call)
    readings = [r for group in await asyncio.gather(*(batch(g) for g in groups)) for r in group]

    boxes, texts, cursor = list(regions), [], 0
    flagged: list[ReadFlag] = []
    no_writing: list[str] = []  # looked at, nothing written: a ruled or blank line, read as such (#5758)
    for n, (box, text) in enumerate(zip(found, readings)):
        if text is None:
            if n in looked and box.metadata.get("segment_id"):
                no_writing.append(box.metadata["segment_id"])
            # Every line left without a reading, and why (#5758): the reader said no writing, or never answered.
            logger.debug("line left without a reading: %s on %s — %s", box.metadata.get("segment_id"), image_path,
                        "the reader found no writing" if n in looked else why_not.get(n, "the reader gave no answer for it"))
            continue
        texts.append(text)
        # Each line's reading is checked as it lands (#5522): one picture is one line, so a reading
        # that loops or runs far past a line's length is marked on its box.
        flag = None if apple else check_read(text, line_count=1, model=config.model)
        metadata = box.metadata
        if "parent_box_index" in metadata:
            parent = moved.get(metadata["parent_box_index"])
            metadata = {k: v for k, v in metadata.items() if k != "parent_box_index"}
            if parent is not None:
                metadata["parent_box_index"] = parent
        if flag is not None:
            flagged.append(flag)
            metadata = {**box.metadata, READ_FLAG_KEY: flag.as_data()}
        boxes.append(box.model_copy(update={
            "text": text, "char_start": cursor, "char_end": cursor + len(text),
            "level": OCRGeometryLevel.LINE, "provider": config.provider, "model": config.model,
            "source": "apple-lines" if apple else "kraken-lines+vision", "metadata": metadata,
        }))
        cursor += len(text) + 1
    if no_writing and not texts:
        no_writing = []  # every line came back empty: a failed read, not 'no writing' (review 64); read again
    read = len(boxes) - len(regions)
    logger.info("line reader %s: %d lines found, %d read, %d without writing, %d flagged",
                config.model, len(found), read, len(found) - read, len(flagged))
    unanswered = {box.metadata.get("segment_id") or str(n): why_not[n] for n, box in enumerate(found)
                  if n in why_not and n not in looked}
    page_metadata = {**lines.metadata, "lines_unanswered": unanswered, "lines_found_by": "kraken", "lines_found": len(found),
                     "lines_without_writing": len(found) - read, "lines_flagged": len(flagged),
                     NO_WRITING_KEY: no_writing}
    if flagged:
        # The page's reading is as trusted as its worst line: it lands marked, not as the page's text.
        page_metadata[READ_FLAG_KEY] = {
            "kind": flagged[0].kind,
            "reason": f"{flagged[0].reason} on {len(flagged)} of its {read} lines",
            "measure": {"lines_flagged": len(flagged), "lines_read": read, **flagged[0].measure},
        }
    return lines.model_copy(update={
        "text": "\n".join(texts), "boxes": boxes, "provider": config.provider, "model": config.model,
        "source": "apple-lines" if apple else "kraken-lines+vision", "metadata": page_metadata,
    })
