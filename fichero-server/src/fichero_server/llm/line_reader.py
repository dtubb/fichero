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
import difflib
import logging
import re
import unicodedata
from typing import Any

from PIL import Image

from fichero_server.llm.working_lines import NO_WRITING_KEY, VISION_NOTHING_TWICE, reads_mostly_nothing
from fichero_server.llm.line_cut import _MAX_CROP_WIDTH, _says_null, crop_line, parse_answer  # noqa: F401  (one cut, one parser: shipped to the runner)
from fichero_server.llm.read_guard import READ_FLAG_KEY, ReadFlag, check_read, finish_reason_of, is_truncation
from fichero_server.media.ocr_geometry import OCRGeometryBox, OCRGeometryLevel, OCRGeometryResult
from fichero_server.media.upright import frame_of, open_in_frame

logger = logging.getLogger(__name__)

#: 16 a call: measured on a cloud reader (2026-10-24, `source.recipe.cloud-reads-lines-per-page`): as aligned as 8 and as cheap a page, in half the calls.
LINES_PER_CALL = 16
#: The most line pictures one call carries, whatever the granularity asks (`source.recipe.cloud-reads-lines-per-page`): a page
#: of 120 lines is read in calls of at most this many. It keeps a call inside the providers' image limits (the page for
#: context rides beside the crops) and its answer inside the output ceiling (`TOKENS_PER_LINE` x this + 32 is under 8,192).
MAX_LINES_PER_CALL = 40
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


def _letters(text: str | None) -> str:
    folded = unicodedata.normalize("NFD", str(text or "").casefold())
    return "".join(c for c in folded if c.isalnum())


def _alike(answers: list[str | None], references: list[str | None], shift: int) -> float | None:
    """The mean letter similarity (`difflib` ratio, 0 to 1) of each answer to the reference `shift` lines further on; None with nothing to compare."""
    pairs = [(a, references[i + shift]) for i, a in enumerate(answers) if 0 <= i + shift < len(references)]
    ratios = [difflib.SequenceMatcher(None, _letters(a), _letters(r)).ratio() for a, r in pairs if _letters(a) and _letters(r)]
    return sum(ratios) / len(ratios) if ratios else None


def answers_follow_order(answers: list[str | None], references: list[str | None]) -> bool:
    """Whether a batch's answers sit on the lines they were asked for: each answer matches the reference reading of its OWN
    line at least as well as that of ANY other shift of the batch (a relative test over every shift, so a batch moved by two
    lines, or rotated, fails as surely as one moved by one; a batch is at most `MAX_LINES_PER_CALL` lines, so it is cheap). A
    hand the reference reads badly still passes, where an absolute floor would send a correct page line by line. Pairs where
    either side says nothing are not compared; with nothing to compare the batch is believed."""
    own = _alike(answers, references, 0)
    if own is None:
        return True
    n = len(answers)
    return all(own >= other for shift in range(1 - n, n) if shift and (other := _alike(answers, references, shift)) is not None)


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
    measured asking that way. No call carries more than `MAX_LINES_PER_CALL` lines: a longer group is split in order."""
    groups = _request_groups(found, granularity, per_call)
    return [g[i:i + MAX_LINES_PER_CALL] for g in groups for i in range(0, len(g), MAX_LINES_PER_CALL)]


def _request_groups(found: list[OCRGeometryBox], granularity: str | None, per_call: int) -> list[list[int]]:
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
                     page_context: bool | None = None, page_image: Any = None) -> OCRGeometryResult:
    """Kraken's lines (`segment_to_geometry`) with each one's text read by `config`'s vision model, or, with
    `apple`, by Apple Vision on each line's own picture (one line a call: its answer IS the reading, not a JSON
    array, and it is not checked for loops, as only a generative model loops).

    `page_image` (`media/current_image.PageImage`): the lines are measured on the page's photograph and `image_path` is the page's
    current image (edits applied); each line's outline is carried onto it before it is cut, so the crop is the line as edited."""
    from fichero_server.llm import LLMConfig, vision

    if apple:
        config = LLMConfig(provider="apple", model="apple-vision")

    lines_frame = frame_of(lines.metadata, *(b.metadata for b in lines.boxes[:1]))
    carried = page_image.lines_map(lines_frame) if page_image is not None else None
    page = open_in_frame(image_path, None if carried is not None else lines_frame)
    found = [b for b in lines.boxes if b.metadata.get("polygon_px") and b.level == OCRGeometryLevel.LINE]
    # Kraken's regions are kept, first, as the lines' parents (#5487); a line names its region by position.
    kept = [(i, b) for i, b in enumerate(lines.boxes) if b.level != OCRGeometryLevel.LINE]
    regions = [b for _i, b in kept]
    moved = {i: n for n, (i, _b) in enumerate(kept)}
    crops = [_crop_data_uri(page, carried.carry_pixels(b.metadata["polygon_px"]) if carried is not None
                            else b.metadata["polygon_px"]) for b in found]
    # Variant B (`source.recipe.kraken-lines-cloud-reads`): a generative model gets the page ONCE per request, reduced,
    # beside the batch of lines; never once a line, and never for a reader trained on one picture or Apple's.
    # A reader that runs on this Mac (any local provider) reads a line as trained: the page costs its memory, not money.
    # Off unless asked (2026-10-24, measured): the page beside the lines made a batch answer out of order and cost twice as much
    # (one line a call), and the lines were read as well without it (`source.recipe.cloud-reads-lines-per-page`).
    context = False if page_context is None else (page_context and not apple)
    page_uri = _page_context_uri(page) if context and crops else None
    gate = asyncio.Semaphore(CONCURRENT_CALLS)

    async def ask(indices: list[int], with_page: bool = True) -> list[str | None] | None:
        rides = bool(page_uri) and with_page  # a retry of one line is a single picture: the page is not sent again
        async with gate:
            raw = await vision(images=([page_uri] if rides else []) + [crops[i] for i in indices],
                               prompt=prompt_for(len(indices), language, page_context=rides),
                               config=line_call_config(config, len(indices)),
                               **({"language": language, "recognition_only_ok": True} if apple else {}))
        if apple:
            text = " ".join((raw or "").split())
            if not text:
                # Vision does not read one picture the same way twice (#5901): an empty answer is not "no writing".
                vision_empty.add(indices[0])
                return None
            return [text]
        answer = parse_answer(raw, len(indices))
        if answer is None and len(indices) == 1 and is_truncation(finish_reason_of(raw)):
            return [cut_short_reading(raw)]
        if answer is None and len(indices) == 1:
            said = " ".join(str(raw or "").split())
            why_not[indices[0]] = (f"the model answered with text that is not a reading ({said[:80]!r})" if said
                                   else "the model gave no answer")
        return answer

    reasked: list[int] = []  # the size of each batch that answered out of order and was asked line by line

    async def _done(value):
        return value

    looked: set[int] = set()  # lines the reader answered for, with or without words
    vision_empty: set[int] = set()  # Apple Vision lines whose latest answer was empty
    why_not: dict[int, str] = {}  # a line asked on its own that came back unread, and what the model said (variant B)

    probed: dict[int, list[str | None] | None] = {}  # lines already asked alone as the order check's reference: not asked twice

    async def in_order(indices: list[int], answer: list[str | None]) -> bool:
        """A batch asked with the page beside it is checked against a reference reading of its lines (`answers_follow_order`):
        Kraken's own reading where the line carries one, else the first and last line asked alone (kept in `probed`)."""
        refs: list[str | None] = [found[i].text or None for i in indices]
        if not any(refs):
            probes = sorted({0, len(indices) - 1})
            singles = await asyncio.gather(*(ask([indices[k]], with_page=False) for k in probes))
            for k, single in zip(probes, singles):
                probed[indices[k]] = single
                refs[k] = single[0] if single else None
        return answers_follow_order(answer, refs)

    async def batch(indices: list[int]) -> list[str | None]:
        answer = await ask(indices)
        if answer is not None and page_uri and len(indices) > 1 and not await in_order(indices, answer):
            logger.info("line reader %s: a batch of %d lines answered out of order on %s; asked line by line",
                        config.model, len(indices), image_path)
            reasked.append(len(indices))
            answer = None
        if answer is None and len(indices) > 1:  # re-ask line by line rather than misplace a reading
            singles = list(await asyncio.gather(*(
                _done(probed[i]) if probed.get(i) is not None else ask([i], with_page=False) for i in indices)))
            answer = [s[0] if s else None for s in singles]
            looked.update(i for i, s in zip(indices, singles) if s is not None)
        elif answer is not None:
            looked.update(indices)
        return answer or [None]

    per_call = 1 if apple else lines_per_call(config)
    groups = request_groups(found, None if apple else granularity, per_call)
    readings = [r for group in await asyncio.gather(*(batch(g) for g in groups)) for r in group]
    final_empty: set[int] = set()  # Apple Vision lines empty twice, not part of a failed page: final, with a reason
    if apple and vision_empty:
        # Once more, in this run (`source.read.vision-empty-line-says-so`): one empty answer is not evidence of a blank line.
        again = sorted(vision_empty)
        vision_empty.clear()
        for n, second in zip(again, await asyncio.gather(*(ask([n]) for n in again))):
            if second is not None:
                readings[n] = second[0]
        if vision_empty:
            from fichero_server.recipes.done import MOSTLY_NOTHING_FOR_PAGE, NOTHING_FOR_PAGE

            if reads_mostly_nothing(len(vision_empty), len(found)):  # a hand it cannot read is not a blank page: stays unread
                for n in vision_empty:
                    why_not[n] = NOTHING_FOR_PAGE if len(vision_empty) == len(found) else MOSTLY_NOTHING_FOR_PAGE
            else:
                final_empty = set(vision_empty)
                for n in final_empty:
                    why_not[n] = VISION_NOTHING_TWICE

    boxes, texts, cursor = list(regions), [], 0
    flagged: list[ReadFlag] = []
    no_writing: list[str] = []  # looked at, nothing written: a ruled or blank line, read as such (#5758)
    for n, (box, text) in enumerate(zip(found, readings)):
        if text is None:
            if (n in looked or n in final_empty) and box.metadata.get("segment_id"):
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
                     "batches_reasked_by_order": len(reasked), "lines_reasked_by_order": sum(reasked),
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
