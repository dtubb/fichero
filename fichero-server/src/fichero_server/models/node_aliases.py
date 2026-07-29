"""Alias (reference) nodes — node-model fold P2 (#2591 / EPIC #2081).

A Tinderbox-style *alias* is a node that references another node. It lives inside
a container (via ``parent_id``) and resolves to its target, but never duplicates
the target's content. This is the keystone relation #2591 calls out
("Aliases = reference relation"); bookmarks (Fold-D) and Mind-Palace connections
(Fold-E) both build on it.

Convention: an alias is a :class:`~fichero_server.models.Document` with
``node_kind == "alias"`` and ``alias_target_id`` pointing at the referenced node.

Design rules honoured here:
- **No copy.** The alias carries no ``page_content``; reads go through the target.
- **Prefer raise over silent fallback.** Resolving a dangling alias (missing
  ``alias_target_id`` or a target that no longer exists) raises
  :class:`DanglingAliasError` rather than returning ``None`` or a stand-in node.
"""

from __future__ import annotations

from . import Document

ALIAS_NODE_KIND = "alias"


class DanglingAliasError(Exception):
    """Raised when an alias cannot be resolved to a live target node."""


def is_alias(doc: Document) -> bool:
    """True when ``doc`` is an alias (reference) node."""
    return doc.node_kind == ALIAS_NODE_KIND and bool(doc.alias_target_id)


def make_alias(target: Document, parent_id: str | None, name: str | None = None) -> Document:
    """Build an alias node that references ``target`` inside ``parent_id``.

    The alias mirrors the target's structural ``doc_type`` (so a folder alias
    still reads as a container) but carries no content of its own.
    """
    return Document(
        parent_id=parent_id,
        node_kind=ALIAS_NODE_KIND,
        doc_type=target.doc_type,
        alias_target_id=target.id,
        name=name if name is not None else target.name,
    )


def resolve_alias(db, alias: Document) -> Document:
    """Return the live target node an alias references.

    Raises:
        ValueError: ``alias`` is not an alias node.
        DanglingAliasError: the alias has no target, or the target is gone.
    """
    if alias.node_kind != ALIAS_NODE_KIND:
        raise ValueError(f"Not an alias node: {alias.id} (node_kind={alias.node_kind!r})")
    if not alias.alias_target_id:
        raise DanglingAliasError(f"Alias {alias.id} has no target")
    target = db.get(Document, alias.alias_target_id)
    if target is None:
        raise DanglingAliasError(
            f"Alias {alias.id} references missing node {alias.alias_target_id}"
        )
    return target
