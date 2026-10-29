"""Prototype/class resolution — node-model fold P1 (#2591 / EPIC #2081).

A node's ``prototype_key`` names a prototype *definition* — a
:class:`~fichero_server.models.knowledge.ClassificationValue` row with
``dimension == document_prototype``. Prototypes form a class hierarchy via
``parent_key`` and carry inheritable ``attributes``. This module resolves a
prototype key to its **effective** attributes: the parent chain merged
root → leaf, so a child prototype overrides its ancestors (Tinderbox-style
inheritance — the P1 keystone the folds build on).

Prefer-raise: an unknown key or a cyclic ``parent_key`` chain raises rather
than silently returning partial/empty attributes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .knowledge import ClassificationDimension, ClassificationValue


class PrototypeResolutionError(Exception):
    """Raised when a prototype key cannot be resolved (unknown key or a cycle)."""


def _prototype_by_key(db, key: str) -> ClassificationValue | None:
    matches = db.query(
        ClassificationValue,
        dimension=ClassificationDimension.document_prototype,
        key=key,
    )
    return matches[0] if matches else None


def resolve_prototype_attributes(db, key: str) -> dict[str, Any]:
    """Return a prototype's effective attributes (parent chain merged root→leaf).

    A child prototype's own ``attributes`` override values inherited from its
    ``parent_key`` ancestors.

    Raises:
        PrototypeResolutionError: ``key`` (or an ancestor it points at) is
            unknown, or the ``parent_key`` chain contains a cycle.
    """
    # Walk to the root collecting the chain leaf → root, detecting cycles.
    chain: list[ClassificationValue] = []
    seen: set[str] = set()
    cursor: str | None = key
    while cursor is not None:
        if cursor in seen:
            raise PrototypeResolutionError(
                f"Cyclic prototype parent chain at {cursor!r}"
            )
        seen.add(cursor)
        proto = _prototype_by_key(db, cursor)
        if proto is None:
            raise PrototypeResolutionError(f"Unknown prototype key: {cursor!r}")
        chain.append(proto)
        cursor = proto.parent_key

    # Merge root → leaf so the leaf (the requested key) wins.
    merged: dict[str, Any] = {}
    for proto in reversed(chain):
        merged.update(proto.attributes)
    return merged


def check_level_defaults(db, key: str, attributes: dict[str, Any]) -> None:
    """Refuse, in words, a ``subfolders``/``pages``/... default naming an unknown prototype or closing a cycle.

    ``attributes`` is the prototype being saved (``key``); the rest are read from ``db``.
    """
    from .prototype_schema import level_defaults

    own = level_defaults(attributes)
    for level, target in own.items():
        if target != key and _prototype_by_key(db, target) is None:
            raise ValueError(f"{level!r} names the unknown prototype {target!r}")

    def targets(proto_key: str) -> set[str]:
        if proto_key == key:
            return set(own.values())
        proto = _prototype_by_key(db, proto_key)
        if proto is None:
            return set()
        try:
            return set(level_defaults(resolve_prototype_attributes(db, proto_key)).values())
        except PrototypeResolutionError:
            return set(level_defaults(proto.attributes).values())

    # Depth-first from this prototype's targets: reaching `key` again is a cycle.
    stack, seen = list(own.values()), set()
    while stack:
        cur = stack.pop()
        if cur == key:
            raise ValueError(f"The nodes-beneath defaults of {key!r} form a cycle")
        if cur in seen:
            continue
        seen.add(cur)
        stack.extend(targets(cur))


# --- The two walks (attributes-and-prototypes.md §1, §2) -------------------------------------------------


def nearest_ancestor(document: Any, get_document, predicate) -> Any:
    """The nearest ancestor of ``document`` for which ``predicate(ancestor)`` is true, or None.

    THE ancestor walk: the value cascade, the kind walk and the direction cascade all call it.
    ``get_document(id)`` loads a parent; a cycle or a missing parent ends the walk.
    """
    def parent_of(doc: Any) -> str | None:
        return doc.get("parent_id") if isinstance(doc, dict) else getattr(doc, "parent_id", None)

    seen: set[str] = set()
    parent_id = parent_of(document) if document is not None else None
    while parent_id and parent_id not in seen:
        seen.add(parent_id)
        parent = get_document(parent_id)
        if parent is None:
            return None
        if predicate(parent):
            return parent
        parent_id = parent_of(parent)
    return None


def node_level(document: Any) -> str:
    """Which level a node is for the "nodes beneath" defaults: a folder is a ``subfolder``, a region a
    ``region``, anything else (file, page) a ``page``."""
    kind = getattr(getattr(document, "doc_type", None), "value", getattr(document, "doc_type", None))
    if kind in ("folder", "group"):
        return "subfolders"
    if kind == "chunk":
        return "regions"
    return "pages"


@dataclass(frozen=True)
class KindResolution:
    key: str | None
    #: ``own`` (set here), ``inherited`` (from an ancestor's kind) or ``none``.
    rule: str
    from_id: str | None = None


def _declared_level_default(db, proto_key: str | None, level: str) -> str | None:
    if not proto_key:
        return None
    from .prototype_schema import level_defaults

    try:
        return level_defaults(resolve_prototype_attributes(db, proto_key)).get(level)
    except PrototypeResolutionError:
        return None


def resolve_node_prototype(db, document: Any, _visiting: frozenset = frozenset()) -> KindResolution:
    """A node's effective prototype: its own key, else the first ancestor's effective prototype that
    declares a default for this node's level, else none. Says which rule fired and from which ancestor.

    A node with its own key restarts the chain beneath it, because the ancestor walk reads each
    ancestor's EFFECTIVE prototype (its own, else the one it inherits).
    """
    own = getattr(document, "prototype_key", None)
    if own:
        return KindResolution(own, "own")
    if document.id in _visiting:  # a parent cycle in stored data ends the walk
        return KindResolution(None, "none")
    visiting = _visiting | {document.id}
    level = node_level(document)

    get = _getter(db)

    found: dict[str, str] = {}

    def declares(ancestor) -> bool:
        proto = resolve_node_prototype(db, ancestor, visiting).key
        target = _declared_level_default(db, proto, level)
        if target:
            found["key"] = target
        return bool(target)

    ancestor = nearest_ancestor(document, get, declares)
    if ancestor is None:
        return KindResolution(None, "none")
    return KindResolution(found["key"], "inherited", ancestor.id)


def _getter(db):
    """Committed reads where the database has them (they never queue behind an import's writes)."""
    read = getattr(db, "get_committed", None) or db.get
    return lambda doc_id: read(_document_cls(), doc_id)


def _document_cls():
    from . import Document

    return Document


def effective_node_attributes(db, document: Any) -> dict[str, dict[str, Any]]:
    """Every field of a node with where its value came from.

    ``{key: {value, origin: here|inherited|default|empty, from, source}}``. ``from`` is the ancestor's
    id for ``inherited`` and the prototype key for ``default``. Only a declaration marked ``inherits``
    walks up; nothing inherited or defaulted is stored on the node.
    """
    from fichero_server.workflows.attribute_sources import sources
    from .prototype_schema import attribute_declarations, ordered_field_keys

    proto_key = resolve_node_prototype(db, document).key
    attrs = resolve_prototype_attributes(db, proto_key) if proto_key else {}
    decls = attribute_declarations(attrs)
    own = document.attributes if isinstance(document.attributes, dict) else {}
    keys = ordered_field_keys(attrs) + [k for k in own if k not in decls]
    get = _getter(db)

    def has(doc, key) -> bool:
        value = (doc.attributes or {}).get(key) if isinstance(doc.attributes, dict) else None
        return value not in (None, "")

    out: dict[str, dict[str, Any]] = {}
    for key in keys:
        decl = decls.get(key)
        entry: dict[str, Any] = {"value": None, "origin": "empty", "from": None, "source": None}
        if has(document, key):
            entry.update(value=own[key], origin="here", source=sources(document).get(key))
        elif decl is not None and decl.inherits:
            ancestor = nearest_ancestor(document, get, lambda a, k=key: has(a, k))
            if ancestor is not None:
                entry.update(value=ancestor.attributes[key], origin="inherited", **{"from": ancestor.id},
                             source=sources(ancestor).get(key))
        if entry["origin"] == "empty" and decl is not None and decl.default not in (None, ""):
            entry.update(value=decl.default, origin="default", **{"from": proto_key})
        out[key] = entry
    return out
