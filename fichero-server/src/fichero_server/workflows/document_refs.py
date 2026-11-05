"""Source nodes carry document ids, not page text; a tool gets the text when it runs (#4390).

WHY: a source put every selected page's full dump into run state, held for the whole run and capped at 8 MB
(`docs/contributor_manual/design/workflow-source-node-memory.md`: 500 pages x 40 KB = 20 MB). The source's output is now
references; `hydrate_documents` loads the full documents for the one call that reads them and the result is dropped
after it. A tool that loads pages itself is listed in `REF_AWARE_TOOLS` and gets the references untouched.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

#: What a reference carries: who the document is and where it sits, never its text (matches sources.document_ref).
REF_FIELDS = ("id", "name", "doc_type", "parent_id", "sequence", "path")

#: Tools that read each page from the library themselves.
REF_AWARE_TOOLS = frozenset({"date_extract"})


def is_ref(doc: Any) -> bool:
    """A reference is a dict with an id and none of the content fields."""
    return isinstance(doc, dict) and bool(doc.get("id")) and "page_content" not in doc and "metadata" not in doc


def slim_documents(documents: list[Any]) -> list[Any]:
    """The documents as references; anything that is not a full document dict passes through. A SEGMENT's work unit (it carries
    `segment_target`) stays whole: a reference would hydrate back into the whole page and lose the segment, so its read landed
    nowhere (`source.extract.run-on-any-level`, 3 tests went red); its text is the segment's, small."""
    from fichero_server.workflows.selection import SEGMENT_TARGET_KEY  # noqa: PLC0415

    return [{k: d.get(k) for k in REF_FIELDS} if isinstance(d, dict) and "page_content" in d and SEGMENT_TARGET_KEY not in d else d
            for d in documents]


def _hydrate_one(db: Any, doc: Any) -> Any:
    if not is_ref(doc):
        return doc
    from fichero_server.models import Document  # noqa: PLC0415

    full = db.get(Document, doc["id"])
    return full.model_dump(mode="json") if full is not None else doc


def hydrate_documents(documents: list[Any], library_path: str | None) -> list[Any]:
    """References become full documents from the library; with no library or no match the reference stays as it was."""
    if not library_path or not any(is_ref(d) for d in documents or []):
        return documents
    from fichero_server.db import db_manager  # noqa: PLC0415
    from fichero_server.db.manager import LibraryNotFoundError  # noqa: PLC0415

    try:
        db = db_manager.get_database(library_path)
    except LibraryNotFoundError:  # no library at that path: the references stay, as the docstring says (17 workflow tests went red)
        return documents
    return [_hydrate_one(db, d) for d in documents]
