"""A palaeographer's reasons for each line, kept in the episode ledger (#4642, `distill.reasoning.*`).

The thinking palaeographer, a teacher's task a student can later be trained to do: for each line
picture, the letterforms that decided a hard reading, each abbreviation as written and expanded, the
readings it is unsure of with their alternatives, then the transcription. (The palaeographer REVIEWER is
the check job's readings card, `checking/cards.py`, `source.check.readings-card`: its episodes are kept
under `REVIEW` and read back here for the vision card's `review` arm.)

It runs over the lines of the project's CHECKED pass (its own outlines, cut by the line reader's
`crop_line`), so every reason is about a line whose right answer is known, and is found again by that
line's PAGE id (`formats.harness.xml_id` of the segment). Each call is ONE episode in the ledger
(`observability.episodes`): the prompt, the raw answer, the model's thinking when it gives one (a
`<think>` block; a hosted model's hidden reasoning is not returned and is recorded as absent), the
model, the prompt file and the time; its `lines` hold the parsed reasons by line id. No second store
holds traces (`distill.reasoning.traces-in-the-ledger`). The training set reads them back with
`traces_by_line`.

One line per call: a thinking trace can only be tied to one line when the call read one.
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable

READ = "read"
REVIEW = "review"
USE_CASE = {READ: "palaeography-reasons", REVIEW: "palaeography-review"}
CONCURRENT_CALLS = 4

READ_PROMPT = (
    "Each of the {n} images is one line cut from a photographed handwritten page{language}. Read each "
    "as a palaeographer. For each image, in order, give: the letterforms that decided any hard reading; "
    "each abbreviation as written and as expanded; any reading you are unsure of, with its alternatives; "
    "then the transcription exactly as written (spelling, abbreviations, punctuation and capitals kept; "
    "nothing corrected or modernised; fragments of neighbouring lines at the edges left out). If an image "
    "holds no writing, give null for it. Reply with only a JSON array of {n} items, each null or "
    '{{"letterforms": "...", "abbreviations": [{{"as_written": "...", "expanded": "..."}}], '
    '"uncertain": [{{"reading": "...", "alternatives": ["..."]}}], "text": "..."}}.'
)


def prompt_for(mode: str, n: int, language: str | None = None, template: str | None = None) -> str:
    """The instruction for n line pictures: the recipe's prompt file when it gives one, else the default."""
    hint = f" (in {language})" if language and language not in ("und", "unknown") else ""
    return (template or READ_PROMPT).format(n=n, language=hint)


def split_thinking(raw: str) -> tuple[str, str | None]:
    """(answer, thinking): a `<think>` block, or the text before a lone `</think>` (Qwen3's thinking
    template opens the block in the prompt), is the thinking; the rest is the answer."""
    text = raw or ""
    whole = re.search(r"<think>(.*?)</think>", text, re.DOTALL)
    if whole:
        return (text[:whole.start()] + text[whole.end():]).strip(), whole.group(1).strip() or None
    if "</think>" in text:
        before, after = text.split("</think>", 1)
        return after.strip(), before.strip() or None
    return text.strip(), None


def parse_reasons(answer: str, n: int) -> list[dict[str, Any] | None] | None:
    """The JSON array of n items, each checked for its shape; None when it is not exactly that."""
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", (answer or "").strip())
    try:
        items = json.loads(text)
    except ValueError:
        return None
    if not isinstance(items, list) or len(items) != n:
        return None
    out: list[dict[str, Any] | None] = []
    for item in items:
        if item is None:
            out.append(None)
            continue
        if not isinstance(item, dict) or not isinstance(item.get("text"), str) or not item["text"].strip():
            return None
        out.append({**item, "text": item["text"].strip()})
    return out


@dataclass
class Line:
    line_id: str
    document_id: str
    polygon: list[tuple[float, float]]
    checked: str


@dataclass
class Collected:
    calls: int = 0
    lines: int = 0
    reasoned: int = 0
    with_thinking: int = 0
    unparsed: int = 0
    stopped: bool = False
    missing: list[dict[str, str]] = field(default_factory=list)


def checked_lines(db: Any, *, scope_ids: list[str], checked: str, held_out_ids: list[str] = (),
                  library_root: Path | None = None) -> tuple[list[Line], dict[str, Path], list[dict[str, str]]]:
    """The checked pass's lines on every page in scope (held-out pages left out), the photographs, and
    the pages without one, with why."""
    from fichero_server.page_export import ExportRefused, export_page
    from fichero_server.training.kraken_set import pages_in_scope, teacher_pass
    from fichero_server.training.line_pairs import lines_with_ids

    lines: list[Line] = []
    photos: dict[str, Path] = {}
    missing: list[dict[str, str]] = []
    held = set(held_out_ids)

    def page_lines(page_id: str, model: str) -> list[tuple[str, list, str]] | None:
        chosen = teacher_pass(db, page_id, model)
        if chosen is None:
            return None
        try:
            return lines_with_ids(export_page(db, page_id, "pagexml", pass_id=chosen.id).data.decode("utf-8"))
        except ExportRefused:
            return None

    for page in pages_in_scope(db, scope_ids):
        if page.id in held:
            continue
        mine = page_lines(page.id, checked)
        if not mine:
            missing.append({"document_id": page.id, "why": f"no pass by {checked} with read lines"})
            continue
        source = Path(page.path) if not library_root or Path(page.path).is_absolute() else library_root / page.path
        if not source.is_file():
            missing.append({"document_id": page.id, "why": "its photograph is not on this Mac"})
            continue
        photos[page.id] = source
        for line_id, polygon, text in mine:
            lines.append(Line(line_id, page.id, polygon, text))
    return lines, photos, missing


Ask = Callable[[list[str], str], Awaitable[str]]


async def collect(lines: list[Line], photos: dict[str, Path], *, ask: Ask, model: dict[str, Any],
                  library_path: str, language: str | None = None, template: str | None = None,
                  prompt_file: str | None = None, should_stop: Callable[[], bool] | None = None) -> Collected:
    """Ask the teacher for every line's reasons, recording one episode per call."""
    from PIL import Image

    from fichero_server.llm.line_reader import _crop_data_uri
    from fichero_server.observability import episodes

    token = episodes.set_library(library_path)
    out = Collected(lines=len(lines))
    pages: dict[str, Any] = {}
    gate = asyncio.Semaphore(CONCURRENT_CALLS)

    def page(doc_id: str) -> Any:
        if doc_id not in pages:
            image = Image.open(photos[doc_id])
            image.load()
            pages[doc_id] = image
        return pages[doc_id]

    async def call(group: list[Line]) -> None:
        if should_stop is not None and should_stop():
            out.stopped = True
            return
        prompt = prompt_for(READ, len(group), language, template)
        images = [_crop_data_uri(page(g.document_id), g.polygon) for g in group]
        started = time.monotonic()
        async with gate:
            raw = await ask(images, prompt)
        answer, thinking = split_thinking(raw)
        parsed = parse_reasons(answer, len(group))
        out.calls += 1
        if parsed is None:
            out.unparsed += len(group)
        per_line = [{"line_id": g.line_id, "document_id": g.document_id, **(item or {"text": None})} for g, item in zip(group, parsed or [None] * len(group))]
        if len(group) == 1 and thinking:
            per_line[0]["thinking"] = thinking
            out.with_thinking += 1
        out.reasoned += sum(1 for item in (parsed or []) if item)
        episodes.record(
            subject={"document_ids": sorted({g.document_id for g in group}), "line_ids": [g.line_id for g in group]},
            model={**model, "use_case": USE_CASE[READ], "prompt_file": prompt_file},
            exchange={"prompt": prompt, "output": raw, "thinking": thinking, "images": len(images)},
            timing={"seconds": round(time.monotonic() - started, 2)},
            extra={"lines": per_line},
        )

    try:
        await asyncio.gather(*(call([line]) for line in lines))  # one line a call: its thinking is that line's
    finally:
        episodes._episode_library_path.reset(token)
    return out


def traces_by_line(library_path: str, mode: str = READ) -> dict[str, dict[str, Any]]:
    """Every line's newest reasons of this kind from the ledger, by line id, with its episode and model."""
    folder = Path(library_path) / "episodes"
    found: dict[str, dict[str, Any]] = {}
    for path in sorted(folder.glob("*.jsonl")) if folder.is_dir() else []:
        for raw in path.read_text(encoding="utf-8").splitlines():
            try:
                record = json.loads(raw)
            except ValueError:
                continue
            if (record.get("model") or {}).get("use_case") != USE_CASE[mode]:
                continue
            for item in record.get("lines") or []:
                if item.get("text") is not None:
                    found[item["line_id"]] = {**item, "episode_id": record["episode_id"],
                                              "teacher": (record.get("model") or {}).get("model")}
    return found


async def gather_reasons(db: Any, *, scope_ids: list[str], checked: str, config: Any,
                         held_out_ids: list[str] = (), language: str | None = None,
                         prompt_file: str | None = None, should_stop: Callable[[], bool] | None = None) -> Collected:
    """The teacher (`config`'s vision model) gives its reasons for every checked line in scope.
    `prompt_file` is the recipe's prompt (`source.recipe.is-a-file`), read here and named on each episode."""
    from fichero_server.llm import vision

    template = Path(prompt_file).read_text(encoding="utf-8") if prompt_file else None
    lines, photos, missing = checked_lines(db, scope_ids=scope_ids, checked=checked, held_out_ids=held_out_ids)

    async def ask(images: list[str], prompt: str) -> str:
        return await vision(images=images, prompt=prompt, config=config)

    done = await collect(lines, photos, ask=ask, library_path=str(Path(db.path).parent),
                         model={"provider": config.provider, "model": config.model}, language=language,
                         template=template, prompt_file=Path(prompt_file).name if prompt_file else None,
                         should_stop=should_stop)
    done.missing = missing
    return done
