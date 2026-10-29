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

