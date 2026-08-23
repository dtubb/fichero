"""Which TIER of the node tree a caller wants — the one definition.

Daniel, 2026-08-22: "I want to be able to show spreads, or show single pages,
etc." A diary folder holds two kinds of thing at once, both correctly: OPENINGS
(spreads whose two pages moved beneath them) and WHOLE PAGES (never split, so
they have no opening). Asking for "the folder's children" is therefore an
ambiguous question, and the tree cannot answer it — only the caller knows
which tier it means.

WHY THIS IS SHARED AND NOT A VIEW HELPER
----------------------------------------
The v3 survey found the harder half of the same problem. Adopting openings
inserted a layer between a folder and its pages, so folder-scoped WORKFLOWS
began targeting openings: all 75 spreads were transcribed as single units and
all 325 diary entries were extracted from spread transcripts, anchored to
spread frames, while the pages' own sidecar transcripts sat unread. Nothing
was broken — the workflow correctly processed the documents it was handed.
They were the wrong documents.

So "the content level" is not a display preference. It is the same question a
workflow asks when it decides what to run on, and if the view and the workflow
answer it separately they will eventually disagree. One resolver, used by both.

DRIVEN BY PROTOTYPE ATTRIBUTES, NOT BY A HARD-CODED "opening"
-------------------------------------------------------------
``prefer_children_in_library`` on a prototype means "when a caller wants
content, look past me to my children". The mechanism follows the idiom already
in the tree: ``diary_entries.py`` seeds ``attributes={"date": {"role":
"date"}}`` precisely so a declaration — not a branch in a renderer — decides
how a node is treated. A future container kind (a plate, a gatefold, a
photographed object with detail shots) gets this behaviour by declaring the
attribute, with no code change here.
"""

from __future__ import annotations

from enum import Enum

from fichero_server.models import Document
from fichero_server.models.node_prototypes import (
    PrototypeResolutionError,
    resolve_prototype_attributes,
)

#: The prototype attribute that marks a node as a container the library should
#: look THROUGH when the caller asks for content.
PREFER_CHILDREN_ATTRIBUTE = "prefer_children_in_library"


class NodeLevel(str, Enum):
    """Which tier of the tree to return."""

    #: Exactly what the tree holds — openings AND whole pages, side by side.
    #: The default, and what every existing caller already gets, so adding the
    #: parameter changes nothing for anyone who does not pass it.
    stored = "stored"
    #: The content tier: containers are replaced by their children, everything
    #: else passes through untouched. A folder of 75 openings plus 4 whole
    #: pages yields 150 pages plus those same 4 — the whole pages MUST survive,
    #: or a naive implementation silently drops every page that was never
    #: split.
    content = "content"


def _prefers_children(db, doc: Document, cache: dict[str, bool]) -> bool:
    key = doc.prototype_key
    if not key:
        return False
    if key not in cache:
        try:
            attributes = resolve_prototype_attributes(db, key)
        except PrototypeResolutionError:
            # An unknown or cyclic prototype must not decide that a node is a
            # container. Falling back to "not a container" keeps the node
            # VISIBLE — the failure mode is showing a spread where a page was
            # wanted, never a page vanishing from the library.
            cache[key] = False
        else:
            cache[key] = bool(attributes.get(PREFER_CHILDREN_ATTRIBUTE, False))
    return cache[key]


def resolve_level(
    db,
    documents: list[Document],
    level: NodeLevel | str = NodeLevel.stored,
    *,
    children_of: "callable | None" = None,
) -> list[Document]:
    """Return ``documents`` at the requested tier.

    ``children_of`` fetches a node's children; injected so this stays testable
    without a live query layer and so callers that already hold a child index
    do not re-query.

    Order is preserved: a container is replaced IN PLACE by its children, so a
    folder sorted by date keeps its shape when expanded rather than
    re-sorting into a different sequence than the user was just looking at.

    A container with NO children is returned AS ITSELF rather than dropped.
    An opening whose parts failed to import is still a real page someone can
    open, and silently omitting it would be the library lying about what it
    holds.
    """
    level = NodeLevel(level)
    if level is NodeLevel.stored:
        return list(documents)

    if children_of is None:
        def children_of(doc: Document) -> list[Document]:  # pragma: no cover - trivial
            return list(db.query(Document, parent_id=doc.id))

    cache: dict[str, bool] = {}
    resolved: list[Document] = []
    for doc in documents:
        if not _prefers_children(db, doc, cache):
            resolved.append(doc)
            continue
        children = [c for c in children_of(doc) if c.deleted_at is None]
        # Ordering within a container follows `sequence` — for an opening that
        # is left page then right page, which is reading order.
        children.sort(key=lambda c: (c.sequence if c.sequence is not None else 0, c.name or ""))
        resolved.extend(children if children else [doc])
    return resolved


def resolve_workflow_targets(db, raw_documents: list) -> list[Document]:
    """The documents a workflow should actually RUN on.

    The same content-level question the library asks, answered by the same
    resolver — which is the entire point. When the view and the workflow decide
    "what is a page" separately they drift, and on 2026-08-22 they did: the
    library showed openings, the user selected what the library showed, and
    every diary entry in Marshall v3 was extracted from a SPREAD transcript and
    anchored to a spread frame while the pages' own transcripts sat unread.

    A container is never a unit of work. Transcribing a two-page opening as one
    document fuses two pages of text into a single blob and gives every region
    derived from it a rect against the wrong frame.

    Accepts the shapes a tool is handed — dicts with an ``id``, bare id
    strings, or Documents — because tools receive whatever the runtime put in
    ``inputs["documents"]``, and a resolver that only accepted one of them
    would silently pass the others through unresolved.
    """
    loaded: list[Document] = []
    for raw in raw_documents or []:
        doc_id = None
        if isinstance(raw, Document):
            loaded.append(raw)
            continue
        if isinstance(raw, dict):
            doc_id = raw.get("id")
        elif isinstance(raw, str):
            doc_id = raw
        if not doc_id:
            continue
        document = db.get(Document, doc_id)
        if document is not None:
            loaded.append(document)
    return resolve_level(db, loaded, NodeLevel.content)
