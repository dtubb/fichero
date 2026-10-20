"""A correcting step's answer that did not tie to the page's lines, asked again line by line
(`source.job.correct-re-asks-per-line-when-it-does-not-tie`, #5720).

The page was asked whole, by segment id (#5719). The lines it left out are cut from the page and asked in
batches of the model's `lines_per_request` (8 when its card states none), each with its current text and the page's answer beside it for context; a batch that does
not come back as one answer per line is asked line by line (as `line_reader`), never guessed. A line that still
has no answer fails the page's step, naming the model and the lines: nothing is written."""

from __future__ import annotations

import asyncio
from typing import Any

from PIL import Image

from fichero_server.llm.line_reader import (
    CONCURRENT_CALLS,
    _crop_data_uri,
    line_call_config,
    parse_answer,
)

PROMPT = (
    "Each of the {n} images is one line cut from a photographed page. Under each is the text it was "
    "given: {given}. The whole page was reviewed as: {page}. For each image, in order, write the line as "
    "it is written, correcting the given text where the writing differs; keep spelling, abbreviations and "
    "punctuation as written. Reply with only a JSON array of {n} strings, nothing else."
)


#: The same for lines asked on their own, with no page answer beside them (Kraken's text is what the model corrects).
PROMPT_LINES_ONLY = (
    "Each of the {n} images is one line cut from a photographed page{language}. Under each is the text a first "
    "reader gave it: {given}. For each image, in order, write the line as it is written, correcting the given text "
    "where the writing differs; keep spelling, abbreviations and punctuation as written; answer null for a line "
    "you cannot read. Reply with only a JSON array of {n} strings or nulls, nothing else."
)


def _prompt(texts: list[str], page_answer: str, language: str | None = None) -> str:
    given = "; ".join(f"{i + 1}. {t!r}" for i, t in enumerate(texts))
    if not page_answer:
        hint = f" (in {language})" if language and language not in ("und", "unknown", "auto") else ""
        return PROMPT_LINES_ONLY.format(n=len(texts), given=given, language=hint)
    return PROMPT.format(n=len(texts), given=given, page=" ".join((page_answer or "").split())[:1500])


async def re_ask(image_path: str, lines: list[dict[str, Any]], page_answer: str, config, batch: int = 8,
                 language: str | None = None) -> tuple[dict[str, str], list[str]]:
    """`lines`: {'id', 'text', 'polygon'} (pixels) for the lines to ask again. Returns ({id: text} for every
    line answered, [ids still unanswered])."""
    from fichero_server import llm

    page = Image.open(image_path)
    page.load()
    gate = asyncio.Semaphore(CONCURRENT_CALLS)

    async def ask(group: list[dict[str, Any]]) -> list[str | None] | None:
        async with gate:
            raw = await llm.vision(images=[_crop_data_uri(page, g["polygon"]) for g in group],
                                   prompt=_prompt([g["text"] for g in group], page_answer, language),
                                   config=line_call_config(config, len(group)))
        return parse_answer(raw, len(group))

    async def one_batch(group: list[dict[str, Any]]) -> list[str | None]:
        answer = await ask(group)
        if answer is None and len(group) > 1:
            singles = await asyncio.gather(*(ask([g]) for g in group))
            answer = [s[0] if s else None for s in singles]
        return answer or [None] * len(group)

    groups = [lines[i:i + batch] for i in range(0, len(lines), batch)]
    answers = [a for group in await asyncio.gather(*(one_batch(g) for g in groups)) for a in group]
    got = {line["id"]: text for line, text in zip(lines, answers) if text}
    return got, [line["id"] for line in lines if line["id"] not in got]
