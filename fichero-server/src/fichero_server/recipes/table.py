"""Extract to a table: a prototype's questions asked of each of its documents and entries (#5636).

`docs/contributor_manual/specs/source/structured-data.md`, section 2 (`structured.extract.*`,
`structured.cite.*`). The recipe step `extract-to-a-table` names a prototype (`settings.prototype`); for each
unit of the step's pages whose kind is that prototype (or one under it), a page or an entry the splitter made
under it:

1. The input is the unit's text through the one derived-text path (`page_content`, the cache of the text
   worked out from the lines, `actions/page_text_cache.py`; an entry's text read from its lines). A unit with no
   text is not asked and is counted; the image route for a vision model is not built (#5636).
2. One call asks every question (`AttributeDecl.question`), the answer constrained to a Pydantic model made
   from the prototype: per field `{value, words, status, confidence}`. The model is the step's own, through the
   one structured call (`llm.chat_structured_with_fallback`: the same model re-asked once on a decode miss, then
   loud), never another.
3. Each answer is checked against its field's type, field by field: an answer of the wrong type is refused and
   counted with why, and the unit's other answers still land.
4. `words` is found in the text (exactly, else the closest real span, labelled fuzzy, as quotations are) and,
   where the text is tied to its lines (`checking.tie_text.line_spans`), on its line (`extractors.line_anchor`):
   the segment, the reading and the span in it. Words not on the page keep the value, `anchor: none`, and why.
5. The answers land as the node's attributes through `attribute_sources.write_answers_from_run`, each citing
   the run, the model, its answer and the words; a person's value is never overwritten. Not found, illegible and
   ambiguous are statuses with no value, never a guess.

Provisional defaults while the maintainer is away (#5636): an `entity_ref` answer stays unlinked text (no entity
is made); nothing is accepted by itself; the model's self-reported confidence is kept but never acted on; the
page's reading is used without a measured error rate (no project bar exists yet) and the source says so.
"""
from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Callable
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, create_model

from fichero_server.llm import LLMConfig, chat_structured_with_fallback

TOOL = "extract-to-a-table"
FOUND = "found"
STATUSES = (FOUND, "not_found", "illegible", "ambiguous")
#: Types whose answer is not words on the page (a place on a map, a picture, another record): not asked (#5636).
NOT_ASKED_TYPES = frozenset({"geo", "media", "document_ref", "claim_ref"})
#: Refusals kept on the step's account, so a run over thousands of units does not carry thousands.
REFUSALS_KEPT = 50

_SYSTEM = (
    "You fill in a record from the text of one historical document. Answer each question only from the text. "
    "For every question give the value, the exact words of the text it was read from (copied character for "
    "character), a status and your confidence from 0 to 1. The status is found when the text answers it, "
    "not_found when the text does not say, illegible when the words cannot be made out, ambiguous when the text "
    "allows more than one answer. Never guess: a value not in the text is not_found."
)


class FieldAnswer(BaseModel):
    """One question's answer, as the model gives it."""

    value: str | None = Field(None, description="The answer, as the question's type asks; null unless found.")
    words: str | None = Field(None, description="The exact words of the text the value was read from.")
    status: Literal["found", "not_found", "illegible", "ambiguous"] = "not_found"
    confidence: float | None = Field(None, description="How sure you are, 0 to 1.")


def _type_words(decl: Any) -> str:
    kind = decl.type
    if kind == "number":
        return "a number (digits only)"
    if kind == "date":
        return "a date as YYYY-MM-DD, YYYY-MM or YYYY"
    if kind in ("select", "multi_select"):
        many = "one or more of, comma-separated" if kind == "multi_select" else "one of"
        return f"{many}: {', '.join(decl.options)}"
    if kind == "checkbox":
        return "yes or no"
    if kind == "rating":
        return "a whole number"
    if kind == "url":
        return "a web address"
    if kind == "entity_ref":
        return "the name as written"
    return "text"


def asked_fields(declarations: dict[str, Any]) -> dict[str, Any]:
    """The declarations a run asks: every typed field whose answer is words on the page."""
    return {k: d for k, d in declarations.items() if d.type not in NOT_ASKED_TYPES}


def answer_schema(fields: dict[str, Any]) -> type[BaseModel]:
    """The output a unit's one call is held to: one `FieldAnswer` per field, under the field's key, described by
    its question and type (`structured.extract.schema-constrained`)."""
    spec = {f"f{i}": (FieldAnswer, Field(..., alias=key, description=f"{decl.question(key)} ({_type_words(decl)})"))
            for i, (key, decl) in enumerate(fields.items())}
    return create_model("TableRow", __config__=ConfigDict(populate_by_name=True), **spec)


def prompt(fields: dict[str, Any], text: str) -> str:
    """The questions, their types and examples, then the text: built from the fields and nothing else."""
    lines = ["Questions:"]
    for key, decl in fields.items():
        lines.append(f"- {key}: {decl.question(key)} Answer as {_type_words(decl)}.")
        lines += [f"  Example answer: {example}" for example in decl.examples]
    lines += ["", "Text:", text]
    return "\n".join(lines)


_NUMBER = re.compile(r"[+-]?\d+(?:\.\d+)?")


def checked(decl: Any, value: Any) -> tuple[bool, Any]:
    """(True, the value as the field's type holds it) or (False, why it is refused)."""
    text = str(value).strip() if value is not None else ""
    if not text:
        return False, "the answer is found but gives no value"
    kind = decl.type
    if kind in ("text", "long_text", "entity_ref"):
        return True, text
    if kind == "number":
        bare = re.sub(r"(?<=\d)[,\s](?=\d{3}\b)", "", text)
        if not _NUMBER.fullmatch(bare):
            return False, f"{text!r} is not a number"
        number = float(bare)
        return True, int(number) if number.is_integer() and "." not in bare else number
    if kind == "rating":
        return (True, int(text)) if text.isdigit() else (False, f"{text!r} is not a whole number")
    if kind == "date":
        parts = text.split("-")
        try:
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
                date.fromisoformat(text)
            elif re.fullmatch(r"\d{4}-\d{2}", text):
                date(int(parts[0]), int(parts[1]), 1)
            elif not re.fullmatch(r"\d{4}", text):
                raise ValueError
        except ValueError:
            return False, f"{text!r} is not a date (YYYY-MM-DD, YYYY-MM or YYYY)"
        return True, text
    if kind in ("select", "multi_select"):
        by_fold = {o.casefold(): o for o in decl.options}
        given = [t.strip() for t in re.split(r"[,;]", text)] if kind == "multi_select" else [text]
        outside = [g for g in given if g and g.casefold() not in by_fold]
        if outside:
            return False, f"{', '.join(map(repr, outside))} is not one of the options ({', '.join(decl.options)})"
        chosen = [by_fold[g.casefold()] for g in given if g]
        return True, chosen if kind == "multi_select" else chosen[0]
    if kind == "checkbox":
        folded = text.casefold()
        if folded in ("yes", "true", "y", "1"):
            return True, True
        if folded in ("no", "false", "n", "0"):
            return True, False
        return False, f"{text!r} is not yes or no"
    if kind == "url":
        return (True, text) if re.match(r"https?://\S+$", text) else (False, f"{text!r} is not a web address")
    return False, f"a {kind} field is not asked"


# ── Units and their text ─────────────────────────────────────────────────────────────────────────────


def _kinds_under(db: Any, prototype: str) -> Callable[[str | None], bool]:
    """Whether a node's prototype key is `prototype` or one under it (its parent chain reaches it)."""
    from fichero_server.models.node_prototypes import _prototype_by_key

    memo: dict[str, bool] = {}

    def under(key: str | None) -> bool:
        if not key:
            return False
        if key not in memo:
            seen, cursor, found = set(), key, False
            while cursor and cursor not in seen:
                if cursor == prototype:
                    found = True
                    break
                seen.add(cursor)
                row = _prototype_by_key(db, cursor)
                cursor = row.parent_key if row is not None else None
            memo[key] = found
        return memo[key]

    return under


def units(db: Any, documents: list[str], prototype: str) -> list[Any]:
    """The step's units among these pages: each page, and each live entry under it, whose kind is `prototype`
    (or one under it), in the pages' order."""
    from fichero_server.models import Document

    under = _kinds_under(db, prototype)
    out = []
    for doc_id in documents:
        page = db.get(Document, doc_id)
        if page is None or page.deleted_at is not None:
            continue
        if under(page.prototype_key):
            out.append(page)
        entries = sorted((d for d in db.query(Document, parent_id=page.id)
                          if d.deleted_at is None and d.node_kind == "entry" and under(d.prototype_key)),
                         key=lambda d: d.sequence or 0)
        out += entries
    return out


def _text(db: Any, unit: Any) -> str:
    """The unit's text: a page's derived text (re-derived once if its cache is stale); an entry's read from its
    lines now (`diary_entries.with_texts_read_from_lines`)."""
    from fichero_server.actions.page_text_cache import ensure_current
    from fichero_server.models import Document

    if unit.node_kind == "entry":
        from fichero_server.workflows.tools.diary_entries import with_texts_read_from_lines

        unit = with_texts_read_from_lines(db, [unit])[0]
    elif ensure_current(db, [unit.id]):
        unit = db.get(Document, unit.id) or unit
    return (unit.page_content or "").strip()


def _anchor_text(db: Any, unit: Any) -> tuple[str, str, set[str]]:
    """(the document whose text the words are looked for in, that text, the lines the unit covers). An entry's
    words are looked for in its page's text, on the entry's own lines first, so its citation is a line of the
    page; a page's in its own text."""
    from fichero_server.models import Document

    if unit.node_kind == "entry" and unit.parent_id:
        page = db.get(Document, unit.parent_id)
        if page is not None and (page.page_content or "").strip():
            return page.id, page.page_content, set((unit.metadata or {}).get("lines") or [])
    return unit.id, unit.page_content or "", set()


def cite(db: Any, unit: Any, words: str | None, *, spans_for: Callable[[str, str], list]) -> dict[str, Any]:
    """Where `words` are (`structured.cite.value-names-its-words`): exactly, else the closest real span
    (fuzzy); on the line they start on where the text is tied to its lines; else `anchor: none` and why."""
    from fichero_server.checking.tie_text import lines_under
    from fichero_server.workflows.tools.extractors import _fuzzy_anchor, line_anchor

    said = (words or "").strip()
    out: dict[str, Any] = {"kind": "span", "document_id": unit.id, "segment_id": None, "representation_id": None,
                           "char_start": None, "char_end": None, "words": said or None, "anchor": "none"}
    if not said:
        return {**out, "reason": "the model gave no words for its answer"}
    doc_id, text, own_lines = _anchor_text(db, unit)
    lines = spans_for(doc_id, text) if text else []
    found = [(m.start(), m.end()) for m in re.finditer(re.escape(said), text)]
    how = "exact"
    if not found:
        span = _fuzzy_anchor(text, said) if text else None
        found, how = ([span], "fuzzy") if span else ([], "none")
    if not found:
        return {**out, "reason": "the words are not in the text"}
    # an entry's words on its own lines first: the same words elsewhere on the page are another entry's
    start, end = next((s for s in found if own_lines and any(
        line.segment_id in own_lines for line in lines_under(lines, *s))), found[0])
    out.update(document_id=doc_id, char_start=start, char_end=end, anchor=how, words=text[start:end])
    if how == "fuzzy":
        out["model_words"] = said
    on_line = line_anchor(lines, doc_id, start, end)
    if on_line is None:
        out["reason"] = "the text is not tied to its lines"
        return out
    out.update(segment_id=on_line.segment_id, representation_id=on_line.representation_id,
               line_char_start=on_line.char_start, line_char_end=on_line.char_end)
    return out


# ── The step ─────────────────────────────────────────────────────────────────────────────────────────


def _fields_of(db: Any, prototype: str) -> dict[str, Any]:
    from fichero_server.models.node_prototypes import resolve_prototype_attributes
    from fichero_server.models.prototype_schema import attribute_declarations, is_declaration

    effective = resolve_prototype_attributes(db, prototype)
    typed = {k: v for k, v in effective.items() if is_declaration(v)}
    return asked_fields(attribute_declarations(typed))


def extract(db: Any, documents: list[str], *, prototype: str, provider: str, model: str, run_id: str | None,
            step: str | None, stop: Callable[[], bool] | None = None) -> dict[str, Any]:
    """Ask the prototype's questions of each of its units among `documents`, and land the answers. The account:
    `{"units", "asked", "without_text", "values", "not_found", "refused", "kept", "unanchored", "failed",
    "refusals": [...], "errors": [...]}`. Raises when the prototype is unknown or asks nothing."""
    from fichero_server.checking.tie_text import line_spans
    from fichero_server.workflows import attribute_sources as sources

    fields = _fields_of(db, prototype)
    if not fields:
        raise ValueError(f"the kind of document {prototype!r} has no fields to ask")
    schema = answer_schema(fields)
    config = LLMConfig(provider=provider, model=model)
    todo = units(db, documents, prototype)
    account: dict[str, Any] = {"units": len(todo), "asked": 0, "without_text": 0, "values": 0, "not_found": 0,
                               "refused": 0, "kept": 0, "unanchored": 0, "failed": 0,
                               "refusals": [], "errors": []}
    spans: dict[str, list] = {}

    def spans_for(doc_id: str, text: str) -> list:
        if doc_id not in spans:
            spans[doc_id] = line_spans(db, doc_id, text)
        return spans[doc_id]

    from fichero_server.workflows.tools._together import extract_width

    width = extract_width(config)  # the step's cloud width for a hosted model, 3 for one served here
    # Units in waves of `width`: one event loop for the wave, its questions asked together (a new loop for each unit and one
    # call after another before: `runtime.cloud-extractors.pages-together`, #5955); the answers are landed one by one, in
    # unit order, as before. A stop is looked for between waves.
    waves = [todo[at:at + width] for at in range(0, len(todo), width)]
    for wave in waves:
        if stop is not None and stop():
            break
        texts = [_text(db, unit) for unit in wave]
        answers = iter(asyncio.run(_ask_together(fields, schema, config, [t for t in texts if t])))
        for unit, text in zip(wave, texts):
            if not text:
                account["without_text"] += 1
                continue
            account["asked"] += 1
            answer = next(answers)
            if isinstance(answer, BaseException):
                if not isinstance(answer, Exception):
                    raise answer
                account["failed"] += 1  # the model's failure, in its words, on the account
                account["errors"].append(f"{unit.name}: {answer}")
                continue
            _land(db, unit, answer, fields=fields, account=account, spans_for=spans_for, step=step, run_id=run_id,
                  provider=provider, model=model)
    return account


async def _ask_together(fields: dict[str, Any], schema: Any, config: Any, texts: list[str]) -> list[Any]:
    """The answers (or the exceptions) to these texts' questions, asked together, in order."""
    return list(await asyncio.gather(
        *(chat_structured_with_fallback(prompt(fields, text), schema, config, system=_SYSTEM,
                                        use_case="extract_to_a_table") for text in texts),
        return_exceptions=True))


def _land(db: Any, unit: Any, answer: Any, *, fields: dict[str, Any], account: dict[str, Any], spans_for: Callable[..., list],
          step: str | None, run_id: str | None, provider: str, model: str) -> None:
    """Check one unit's answer against its fields and land what holds, on the account."""
    from fichero_server.workflows import attribute_sources as sources

    landing: dict[str, tuple[Any, dict]] = {}
    for i, (key, decl) in enumerate(fields.items()):
        given: FieldAnswer = getattr(answer, f"f{i}")
        base = sources.machine_source(tool=TOOL, step=step, run_id=run_id, artifact_id=None, provider=provider,
                                      model=model, said=json.dumps(given.model_dump(), ensure_ascii=False))
        base.update(status=given.status, confidence_said=given.confidence, method="text, one call per unit",
                    input={"text": "derived page text" if unit.node_kind != "entry" else "entry text from its lines",
                           "cer": None, "cer_why": "no project error-rate bar is measured yet"})
        if given.status != FOUND:
            landing[key] = (None, {**base, "cites": None})
            continue
        ok, value = checked(decl, given.value)
        if not ok:
            account["refused"] += 1
            if len(account["refusals"]) < REFUSALS_KEPT:
                account["refusals"].append({"document_id": unit.id, "field": key, "said": given.value,
                                            "why": value})
            continue
        where = cite(db, unit, given.words, spans_for=spans_for)
        if decl.type == "entity_ref":
            base["unlinked"] = True  # a name as written; an entity only when a person links it (#5636)
        landing[key] = (value, {**base, "cites": where})
    written = set(sources.write_answers_from_run(db, unit, landing)) if landing else set()
    account["kept"] += len(set(landing) - written)
    for key in written:
        value, source = landing[key]
        if value is None:
            account["not_found"] += 1
        else:
            account["values"] += 1
            account["unanchored"] += (source["cites"] or {}).get("anchor") == "none"
