"""The Catalogue stage of a started recipe (`catalogue.folder-description-fields`, #6087): last, at folder level, one
archival description per folder written from what the folder holds, describe only. A folder is redone only when what
it covers changed, so pages added later redo the new folder and the folders above it, nothing else
(`source.recipe.catalogue-follows-new-material`)."""
from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path
from typing import Any

from fichero_server.llm.catalogue_lint import FOLDER_DESCRIPTION_MAX_WORDS

ARTIFACT_TYPE = "catalogue.narrative"
PAGE_CHARS = 1500  # of one page's reading given to the model
TOTAL_CHARS = 24000  # of all the pages' readings for one folder


def _is_folder(doc: Any) -> bool:
    return getattr(doc.doc_type, "value", doc.doc_type) == "folder"


def folders_covering(db: Any, page_ids: list[str]) -> list[Any]:
    """The folders above these pages (all the way up), deepest first; each once."""
    from fichero_server.models import Document

    seen: dict[str, Any] = {}
    for page_id in page_ids:
        node = db.get(Document, page_id)
        while node is not None and node.parent_id:
            node = db.get(Document, node.parent_id)
            if node is not None and _is_folder(node) and not node.deleted_at:
                seen.setdefault(node.id, node)
    depth: dict[str, int] = {}

    def level(doc: Any) -> int:
        if doc.id not in depth:
            parent = db.get(Document, doc.parent_id) if doc.parent_id else None
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
    return text


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
        account["described"] += 1
        account["flags"].extend(f"{folder.name}: {f}" for f in flags)
    return account
