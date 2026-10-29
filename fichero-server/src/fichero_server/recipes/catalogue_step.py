"""The Catalogue stage of a started recipe (`catalogue.folder-description-fields`, #6087): last, at folder level, one
archival description per folder written from what the folder holds, describe only. A folder is redone only when what
it covers changed, so pages added later redo the new folder and the folders above it, nothing else
(`source.recipe.catalogue-follows-new-material`)."""
from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import unicodedata
from pathlib import Path
from typing import Any

from fichero_server.llm.catalogue_lint import FOLDER_DESCRIPTION_MAX_WORDS, MAX_WORDS, cut_to_cap

logger = logging.getLogger(__name__)

ARTIFACT_TYPE = "catalogue.narrative"
PAGE_CHARS = 1500  # of one page's reading given to the model
TOTAL_CHARS = 24000  # of all the pages' readings for one folder


def _is_folder(doc: Any) -> bool:
    return getattr(doc.doc_type, "value", doc.doc_type) == "folder"


def folders_covering(db: Any, page_ids: list[str]) -> list[Any]:
    """The folders above these pages (all the way up), deepest first; each once. Reads the pages and then each level of
    their parents, a read a level, not the library (#6268)."""
    from fichero_server.models import Document

    nodes: dict[str, Any] = {}
    todo = set(page_ids)
    while todo:
        for doc in db.query_in(Document, "id", todo):
            nodes[doc.id] = doc
        todo = {d.parent_id for d in nodes.values() if d.parent_id and d.parent_id not in nodes} - todo
    seen: dict[str, Any] = {}
    for page_id in page_ids:
        node = nodes.get(page_id)
        while node is not None and node.parent_id:
            node = nodes.get(node.parent_id)
            if node is not None and _is_folder(node) and not node.deleted_at:
                seen.setdefault(node.id, node)
    depth: dict[str, int] = {}

    def level(doc: Any) -> int:
        if doc.id not in depth:
            parent = nodes.get(doc.parent_id) if doc.parent_id else None
            depth[doc.id] = 0 if parent is None else 1 + level(parent)
        return depth[doc.id]

    return sorted(seen.values(), key=lambda d: (-level(d), d.name))


def _below(db: Any, folder_id: str) -> tuple[list[Any], list[Any]]:
    """(direct child folders, every non-folder node under the folder at any depth), live ones only."""
    from fichero_server.models import Document

    children = [c for c in db.query(Document, parent_id=folder_id) or [] if not c.deleted_at]
    folders = [c for c in children if _is_folder(c)]
    leaves = [c for c in children if not _is_folder(c)]
    for sub in folders:
        leaves.extend(_below(db, sub.id)[1])
    return folders, leaves


def coverage(leaves: list[Any]) -> str:
    """A digest of what a folder covers: each node under it and its reading, so any added or changed page changes it."""
    h = hashlib.sha1()
    for doc in sorted(leaves, key=lambda d: d.id):
        h.update(doc.id.encode())
        h.update(hashlib.sha1((doc.page_content or "").encode()).digest())
    return h.hexdigest()


def _latest(db: Any, folder_id: str) -> Any | None:
    from fichero_server.models import Artifact

    rows = [a for a in db.query(Artifact, document_id=folder_id) or []
            if a.artifact_type == ARTIFACT_TYPE and not getattr(a, "deleted_at", None)]
    return max(rows, key=lambda a: (a.version, a.created_at), default=None)


def _material(db: Any, folder: Any, child_folders: list[Any], leaves: list[Any]) -> str:
    """What the model is given: the facts, the subfolders' own descriptions, then the pages' readings (cut)."""
    texts = [(d.name, (d.page_content or "").strip()) for d in sorted(leaves, key=lambda d: (d.sequence or 0, d.name))]
    with_text = [(n, t) for n, t in texts if t]
    parts = [f"Folder name: {folder.name}", f"Pages and files under it: {len(leaves)}; with a reading: {len(with_text)}"]
    if child_folders:
        parts.append("Subfolders: " + "; ".join(c.name for c in child_folders))
        for sub in child_folders:
            art = _latest(db, sub.id)
            if art is not None and art.content:
                parts.append(f"Description of subfolder {sub.name}:\n{art.content}")
    used = 0
    for name, text in with_text:
        piece = text[:PAGE_CHARS]
        if used + len(piece) > TOTAL_CHARS:
            parts.append(f"(readings of {len(with_text)} pages; the rest are not shown)")
            break
        used += len(piece)
        parts.append(f"Page {name}:\n{piece}")
    return "\n\n".join(parts)


async def _write(material: str, config: Any, language: str, max_words: int, flags: list[str]) -> str:
    from fichero_server.llm import chat_with_fallback
    from fichero_server.llm.catalogue_lint import enforce
    from fichero_server.llm.prompts import get_prompt

    system = get_prompt("catalogue", "folder_description", version=3).render(output_language=language, max_words=max_words)

    async def call(note: str = "") -> str:
        return (await chat_with_fallback(material, config=config, system=system + ("\n\n" + note if note else ""),
                                         permissive_guardrails=True)).strip()

    text, found = await enforce(await call(), call, long_item=False, source=material, max_words=max_words, aim_min=0)
    flags.extend(found)
    return _cap_description(text)


def _cap_description(text: str) -> str:
    """The `Description:` field (the last) is never over MAX_WORDS (#6123), cut at a sentence end like any entry."""
    head, sep, tail = text.rpartition("Description:")
    if not sep or (head and not head.endswith("\n")):
        return text
    return head + sep + " " + cut_to_cap(tail.strip(), MAX_WORDS)


def folders_to_describe(db: Any, page_ids: list[str]) -> tuple[list[Any], int]:
    """(the folders above these pages a run would describe, how many are already described): `describe_folders`'s own rule,
    read without running it. A folder with no reading under it is neither."""
    todo, current = [], 0
    for folder in folders_covering(db, page_ids):
        leaves = _below(db, folder.id)[1]
        old = _latest(db, folder.id)
        if old is not None and (old.data or {}).get("covers") == coverage(leaves):
            current += 1
        elif any((d.page_content or "").strip() for d in leaves):
            todo.append(folder)
    return todo, current


#: `Document.metadata` key marking a folder's content as the Catalogue stage's description (the artifact it came from),
#: so a re-run may replace its own text and never a person's (#6131).
CONTENT_FROM = "catalogue_content_from"


class ReembedNotQueued(RuntimeError):
    """The folder's content is saved but queueing its re-embed failed (#6131): search has not been told."""


def put_in_content(db: Any, folder_id: str, text: str, artifact_id: str) -> bool:
    """The description as the folder's content (#6131): what selecting the folder shows and search and export read. Only
    where the folder has no content, or has the Catalogue stage's own earlier description: text a person wrote, or
    edited, stays the content (the description is still its `description` reading). True when written."""
    from fichero_server.models import Document
    from fichero_server.workflows.curation_guard import page_content_is_user_edited, page_text_is_derived

    doc = db.get(Document, folder_id)
    if doc is None or page_content_is_user_edited(doc) or page_text_is_derived(db, folder_id):
        return False
    metadata = dict(doc.metadata or {})
    if (doc.page_content or "").strip() and CONTENT_FROM not in metadata:
        return False
    doc.page_content = text
    doc.metadata = {**metadata, CONTENT_FROM: artifact_id}
    db.save(doc)
    from fichero_server.actions.page_text_cache import queue_reembed

    try:
        queue_reembed(db, [folder_id])  # search reads it
    except Exception as exc:  # noqa: BLE001 -- typed, so the caller tells it from a failed save
        raise ReembedNotQueued(str(exc)) from exc  # raised AFTER the content is saved
    return True


#: The description's labelled fields that also become the folder's attributes (#6141): label -> (attribute key, a list?).
ATTRIBUTE_FIELDS = {
    "Title": ("catalogue_title", False), "Dates": ("catalogue_dates", False), "Extent": ("catalogue_extent", False),
    "Creator and hands": ("catalogue_creators", True), "Language and script": ("catalogue_language_script", False),
    "Condition": ("catalogue_condition", False), "Access points": ("catalogue_access_points", True),
    "Scope and content": ("catalogue_scope_content", False), "Arrangement": ("catalogue_arrangement", False),
}
_YEAR = re.compile(r"(?<!\d)(1\d{3}|20\d{2})(?!\d)")
# "1913 - 19 de febrero": a number followed by "de <month>" is a day, not a short end year
_SHORT_END = re.compile(r"(?<!\d)(1\d{3}|20\d{2})\s*[-\u2013\u2014/]\s*(\d{2})(?!\d)(?!\s+de\s)")
_THOUSANDS = re.compile(r"(?<!\d)([12])\.(\d{3})(?!\d)")  # Spanish "1.918" = 1918
_DROPPED_ONE = re.compile(r"(?<!\d)([89]\d{2})(?!\d)")  # "914" = 1914, "814" = 1814


_ONES = {w: n for n, w in enumerate("uno dos tres cuatro cinco seis siete ocho nueve diez once doce trece catorce quince".split(), 1)}
_ONES.update(dieciseis=16, diecisiete=17, dieciocho=18, diecinueve=19, veinte=20, treinta=30, cuarenta=40, cincuenta=50,
             sesenta=60, setenta=70, ochenta=80, noventa=90, cien=100, ciento=100, doscientos=200, trescientos=300,
             cuatrocientos=400, quinientos=500, seiscientos=600, setecientos=700, ochocientos=800, novecientos=900)
_ONES.update({f"veinti{w}": 20 + n for w, n in list(_ONES.items())[:9]})
_RANGE = re.compile(r"\s*[\u2013\u2014]\s*|\s+-\s+|\s+(?:to|hasta)\s+")


def _spoken_years(dates: str) -> list[str]:
    """Years written as Spanish words ("mil novecientos seis" = 1906, "dos mil veinticuatro" = 2024)."""
    years = []
    for side in _RANGE.split(dates):  # a range's second date must not run on into the first one's number words
        words = re.sub(r"[^a-z ]", " ", unicodedata.normalize("NFD", side.lower()).encode("ascii", "ignore").decode()).split()
        for i, word in enumerate(words):
            if word != "mil":
                continue
            year, used = (2000 if words[i - 1:i] == ["dos"] else 1000), 0
            for part in words[i + 1:]:
                if part != "y" and part not in _ONES:
                    break
                year, used = year + _ONES.get(part, 0), used + 1
            if used and 1000 <= year <= 2099:  # "mil pesos" is money, not the year 1000
                years.append(str(year))
    return years


def _years(dates: str) -> list[str]:
    """The years a Dates field names, digits or Spanish words; a short end of a range ("1850-60", "1850/60") is the year it
    ends: 1860."""
    dates = _THOUSANDS.sub(r"\1\2", dates)
    years = _YEAR.findall(dates) + _spoken_years(dates)
    for start, tail in _SHORT_END.findall(dates):
        end = int(start[:2] + tail)
        years.append(str(end + 100 if end < int(start) else end))  # "1899-01" ends in 1901, not 1801
    for short in _DROPPED_ONE.findall(dates):  # only next to a full year within 30 years: "914" beside 1906
        year = 1000 + int(short)
        if any(abs(year - int(y)) <= 30 for y in years):
            years.append(str(year))
    return years


def _date_range(dates: str) -> tuple[str, str] | None:
    """(start, end) years of a Dates field, or None when a range's first side names no year: the end then stands alone, and
    to put it down as the start too (1918 for "... seis - ... 1918") says something the text does not (#6270)."""
    sides = _RANGE.split(dates, maxsplit=1)
    if len(sides) == 2 and not _years(sides[0]):
        return None
    years = _years(dates)
    return (min(years), max(years)) if years else None


def _edtf_side(side: str, fallback: str) -> str:
    """One side of a Dates field as EDTF at the precision the text supports, read by histdate (#1470's parser; Spanish months
    included); a side it cannot read is the year the span found. `?` marks an uncertain date, `~` an approximate one."""
    from fichero_server.histdate import parse_historical_date

    text = _THOUSANDS.sub(r"\1\2", side).strip(" .,;")
    read = parse_historical_date(text)
    if read is None:
        return fallback + ("?" if re.search(r"\?|incierto|uncertain", side, re.I) else "")
    precision, iso = read.meta.get("precision"), str(read.meta.get("converted_gregorian_iso"))
    if precision == "circa":
        return iso[:4] + "~"
    return iso[:{"year": 4, "month": 7}.get(str(precision), 10)] + ("?" if re.search(r"\?|incierto|uncertain", side, re.I) else "")


def _date_normalised(dates: str, span: tuple[str, str]) -> str:
    """The Dates field as an EDTF interval ("1906-03/1918-02-19"), one date when both ends are the same."""
    sides = _RANGE.split(dates, maxsplit=1)
    first, last = (sides[0], sides[1]) if len(sides) == 2 else (dates, dates)
    start, end = (_edtf_side(first, span[0]), _edtf_side(last, span[1]))
    if len(sides) == 1 and (start[:4] != span[0] or end[:4] != span[1]):
        start, end = span  # several years in one side ("1906, 1918", "1850-60"): the span, at year precision
    return start if start == end else f"{start}/{end}"


_MULTI_WORD = [label for label in (*ATTRIBUTE_FIELDS, "Description") if " " in label]
# A label starts a field on its own line or after a sentence's end or closing mark ("... [uncertain] Condition:" too); a
# label of several words ("Access points") is specific enough to start one after any space.
_LABEL = re.compile(
    r"(?:(?:^|(?<=[.;!?\]\)\"\u201d]\s)|(?<=\n))\s*(?P<a>" + "|".join(map(re.escape, [*ATTRIBUTE_FIELDS, "Description"]))
    + r")|(?<=\s)(?P<b>" + "|".join(map(re.escape, _MULTI_WORD)) + r"))\s*:", re.M)
#: The markers the readings carry in English, in the language of a description written in Spanish.
_SPANISH_MARKERS = {"[uncertain]": "[incierto]", "[illegible]": "[ilegible]"}


def _one_field(chunk: str) -> str:
    """A field's own text: it ends at a blank line, or at the end of its line unless the line breaks mid-list (ends in ; or ,)
    or the next line carries on in lower case; the unlabelled text after it is not part of it."""
    lines = chunk.split("\n")
    kept = [lines[0]]
    for line in lines[1:]:
        if not line.strip() or not (kept[-1].rstrip().endswith((";", ",")) or line.lstrip()[:1].islower()):
            break
        kept.append(line)
    return "\n".join(kept)


def parse_fields(text: str, language: str | None = None) -> dict[str, Any]:
    """The folder attributes in a description's labelled fields (#6141): `{attribute key: value}`, a list for creators and access
    points (split at semicolons), and the Dates field also as ISO 8601 years (`catalogue_date_start`, `catalogue_date_end`: the
    earliest and latest year it names; none when it names none, or when a range's first year cannot be read). A label starts a
    field on its own line or inline after a sentence ("... 1918. Access points: ..."): the field before it ends there (#6270).
    A field the text lacks is not in the result. In a Spanish description the English `[uncertain]` marker the prompt asks
    the model to keep is put in Spanish in the attribute (the prompt itself needs a new version to stop it: held)."""
    found: dict[str, Any] = {}
    marks = list(_LABEL.finditer(text))
    for mark, after in zip(marks, [*marks[1:], None]):
        label = mark.group("a") or mark.group("b")
        if label not in ATTRIBUTE_FIELDS:
            continue  # Description is prose: it stays in the content, but ends the field before it
        key, is_list = ATTRIBUTE_FIELDS[label]
        value = " ".join(_one_field(text[mark.end():after.start() if after else len(text)]).split())
        value = value.rstrip(".") if is_list else value
        if str(language or "").lower().startswith(("es", "span")):  # ponytail: Spanish only; other languages when asked
            for english, spanish in _SPANISH_MARKERS.items():
                value = value.replace(english, spanish)
        if value:
            found[key] = [part.strip() for part in value.split(";") if part.strip()] if is_list else value
    if dates := found.get("catalogue_dates"):
        if span := _date_range(dates):
            found["catalogue_date_start"], found["catalogue_date_end"] = span
            found["catalogue_date_normalised"] = _date_normalised(dates, span)
    return found


def put_in_attributes(db: Any, folder_id: str, text: str, artifact_id: str, *, run_id: str | None, provider: str,
                      model: str, language: str | None = None) -> list[str]:
    """The description's fields as the folder's attributes, through the one attribute path (#6141): each value cites this run
    and its artifact; a value a person set is never overwritten, and a value an earlier run wrote that this description no
    longer has is taken away. Returns the keys written."""
    from fichero_server.models import Document
    from fichero_server.workflows import attribute_sources as sources

    doc = db.get(Document, folder_id)
    if doc is None:
        return []
    values = parse_fields(text, language)
    every = [key for key, _ in ATTRIBUTE_FIELDS.values()] + ["catalogue_date_start", "catalogue_date_end", "catalogue_date_normalised"]
    gone = {k: None for k in every if k not in values and sources.sources(doc).get(k, {}).get("by") == sources.BY_MACHINE}
    source = sources.machine_source(tool="catalogue", step="catalogue", run_id=run_id, artifact_id=artifact_id,
                                    provider=provider, model=model, said=text)
    return sources.write_answers_from_run(db, doc, {k: (v, source) for k, v in {**values, **gone}.items()})


def promote_folder(db: Any, folder: Any) -> dict[str, Any] | None:
    """Put the folder's latest saved description in its content and attributes again, with no model call (the same
    `put_in_content` and `put_in_attributes` a run uses): for a folder described before a field existed.
    Returns what the folder held before (content, metadata, attributes) when this changed it, for an undo; else None."""
    art = _latest(db, folder.id)
    if art is None or not (art.content or "").strip():
        return None
    from fichero_server.models import Document

    def state() -> tuple:
        doc = db.get(Document, folder.id)
        return doc.page_content, dict(doc.metadata or {}), dict(doc.attributes or {})

    was = state()
    try:
        put_in_content(db, folder.id, art.content, art.id)
    except ReembedNotQueued:  # the content stands; search catches up on the next re-embed
        logger.exception("could not queue the re-embed of folder %s", folder.id)
    put_in_attributes(db, folder.id, art.content, art.id, run_id=art.run_id, provider=art.provider, model=art.model,
                      language=(art.data or {}).get("language"))
    return dict(zip(("page_content", "metadata", "attributes"), was)) if state() != was else None


def describe_folders(db: Any, page_ids: list[str], config: Any, *, run_id: str | None,
                     stop: Any = lambda: False, language: str | None = None,
                     max_words: int = FOLDER_DESCRIPTION_MAX_WORDS) -> dict[str, Any]:
    """Describe the folders above `page_ids`, deepest first (a folder's subfolders are described before it). A folder
    whose coverage matches its saved description is left. The account: described / unchanged / no_text / failed."""
    from fichero_server.llm.lang_detect import configured_primary_language, resolve_output_language
    from fichero_server.models import Artifact
    from fichero_server.workflows.tools.catalogue import _describe_container

    library_path = str(Path(db.path).parent)
    account: dict[str, Any] = {"described": 0, "unchanged": 0, "no_text": 0, "failed": [], "flags": []}
    for folder in folders_covering(db, page_ids):
        if stop():
            break
        child_folders, leaves = _below(db, folder.id)
        covers = coverage(leaves)
        old = _latest(db, folder.id)
        if old is not None and (old.data or {}).get("covers") == covers:
            account["unchanged"] += 1
            continue
        if not any((d.page_content or "").strip() for d in leaves):
            account["no_text"] += 1
            continue
        flags: list[str] = []
        material = _material(db, folder, child_folders, leaves)
        try:
            # The records' own language, as the Catalogue workflow resolves it ("auto"), unless one is given.
            written_in = resolve_output_language(language or "auto", material, primary_language=configured_primary_language())
            text = asyncio.run(_write(material, config, written_in, max_words, flags))
        except Exception as exc:  # noqa: BLE001 -- the model's failure, in its words, on the step
            account["failed"].append(f"{folder.name}: {exc}")
            continue
        art = Artifact(document_id=folder.id, artifact_type=ARTIFACT_TYPE, content=text,
                       data={"covers": covers, "pages": len(leaves), "flags": flags, "max_words": max_words,
                             "language": written_in},
                       provider=config.provider, model=config.model, run_id=run_id,
                       version=old.version + 1 if old is not None else 1,
                       source_artifact_id=old.id if old is not None else None)  # a rerun is the next version
        db.save(art)
        _describe_container(db, folder.id, text, art.id, [old.id] if old is not None else [],
                            run_id=run_id, library_path=library_path)
        try:
            put_in_content(db, folder.id, text, art.id)
        except ReembedNotQueued as exc:  # the content stands; a failed get or save is NOT this and still fails the step
            logger.exception("could not queue the re-embed of folder %s", folder.id)
            account["flags"].append(f"{folder.name}: its description is saved, but search was not told: {exc}")
        put_in_attributes(db, folder.id, text, art.id, run_id=run_id, provider=config.provider, model=config.model,
                          language=written_in)
        account["described"] += 1
        account["flags"].extend(f"{folder.name}: {f}" for f in flags)
    return account
