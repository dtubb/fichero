"""The Catalogue stage of a started recipe (`catalogue.folder-description-fields`, #6087): last, at folder level, one
archival description per folder written from what the folder holds, describe only. A folder is redone only when what
it covers changed, so pages added later redo the new folder and the folders above it, nothing else
(`source.recipe.catalogue-follows-new-material`)."""
from __future__ import annotations

import asyncio
import hashlib
import logging
import re
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
    """The folders above these pages (all the way up), deepest first; each once. The documents are read once, not one
    read a page and a parent."""
    from fichero_server.models import Document

    nodes = {d.id: d for d in db.query(Document)}
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
    return max(rows, key=lambda a: a.created_at, default=None)


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

    system = get_prompt("catalogue", "folder_description").render(output_language=language, max_words=max_words)

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
}
_YEAR = re.compile(r"(?<!\d)(1\d{3}|20\d{2})(?!\d)")
_SHORT_END = re.compile(r"(?<!\d)(1\d{3}|20\d{2})\s*[-\u2013\u2014/]\s*(\d{2})(?!\d)")


def _years(dates: str) -> list[str]:
    """The four-digit years a Dates field names; a short end of a range ("1850-60", "1850/60") is the year it ends: 1860."""
    years = _YEAR.findall(dates)
    for start, tail in _SHORT_END.findall(dates):
        end = int(start[:2] + tail)
        years.append(str(end + 100 if end < int(start) else end))  # "1899-01" ends in 1901, not 1801
    return years


def parse_fields(text: str) -> dict[str, Any]:
    """The folder attributes in a description's labelled lines (#6141): `{attribute key: value}`, a list for creators and access
    points (split at semicolons), and the Dates field also as ISO 8601 years (`catalogue_date_start`, `catalogue_date_end`: the
    earliest and latest four-digit year it names, none when it names none). A field the text lacks is not in the result."""
    found: dict[str, Any] = {}
    for line in text.splitlines():
        label, sep, value = line.partition(":")
        entry = ATTRIBUTE_FIELDS.get(label.strip())
        value = value.strip().rstrip(".") if entry and entry[1] else value.strip()
        if not sep or entry is None or not value:
            continue
        key, is_list = entry
        found[key] = [part.strip() for part in value.split(";") if part.strip()] if is_list else value
    if years := _years(found.get("catalogue_dates", "")):
        found["catalogue_date_start"], found["catalogue_date_end"] = min(years), max(years)
    return found


def put_in_attributes(db: Any, folder_id: str, text: str, artifact_id: str, *, run_id: str | None, provider: str,
                      model: str) -> list[str]:
    """The description's fields as the folder's attributes, through the one attribute path (#6141): each value cites this run
    and its artifact; a value a person set is never overwritten, and a value an earlier run wrote that this description no
    longer has is taken away. Returns the keys written."""
    from fichero_server.models import Document
    from fichero_server.workflows import attribute_sources as sources

    doc = db.get(Document, folder_id)
    if doc is None:
        return []
    values = parse_fields(text)
    every = [key for key, _ in ATTRIBUTE_FIELDS.values()] + ["catalogue_date_start", "catalogue_date_end"]
    gone = {k: None for k in every if k not in values and sources.sources(doc).get(k, {}).get("by") == sources.BY_MACHINE}
    source = sources.machine_source(tool="catalogue", step="catalogue", run_id=run_id, artifact_id=artifact_id,
                                    provider=provider, model=model, said=text)
    return sources.write_answers_from_run(db, doc, {k: (v, source) for k, v in {**values, **gone}.items()})


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
                       provider=config.provider, model=config.model, run_id=run_id)
        db.save(art)
        _describe_container(db, folder.id, text, art.id, [old.id] if old is not None else [],
                            run_id=run_id, library_path=library_path)
        try:
            put_in_content(db, folder.id, text, art.id)
        except ReembedNotQueued as exc:  # the content stands; a failed get or save is NOT this and still fails the step
            logger.exception("could not queue the re-embed of folder %s", folder.id)
            account["flags"].append(f"{folder.name}: its description is saved, but search was not told: {exc}")
        put_in_attributes(db, folder.id, text, art.id, run_id=run_id, provider=config.provider, model=config.model)
        account["described"] += 1
        account["flags"].extend(f"{folder.name}: {f}" for f in flags)
    return account
