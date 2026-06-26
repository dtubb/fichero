"""Pure geometric layout strategies for the spatial library canvas (#2297).

Given a list of ``item_ids`` and a strategy, compute a deterministic position
(``x``, ``y``, ``z``, ``z_index``) for each item. These functions are PURE — no
``datetime.now``, no randomness, no DB access — so they are trivially testable
and produce the same canvas every time for the same inputs. The caller persists
the result into the folder-scoped ``canvas_layout`` table (see #2293).

Geometric strategies only (this slice):
    grid   — items packed left-to-right, top-to-bottom into rows × cols
    row    — single horizontal line (increasing x)
    column — single vertical line (increasing y)
    circle — evenly spaced on a ring centred at the origin
    stack  — all at the same x/y, increasing z / z_index (a pile)

# ponytail: ``umap`` (embedding projection, #2290) and ``cluster_by_type``
# (needs the ontology) are FUTURE strategies — deliberately not in this enum and
# not implemented here. They are ML/ontology work, out of scope for this slice.
"""

from __future__ import annotations

import math
from enum import Enum

__all__ = ["ArrangeStrategy", "DEFAULT_SPACING", "compute_arrangement"]


DEFAULT_SPACING = 160.0


class ArrangeStrategy(str, Enum):
    """The geometric arrangement strategies supported by ``compute_arrangement``."""

    grid = "grid"
    row = "row"
    column = "column"
    circle = "circle"
    stack = "stack"


def compute_arrangement(
    item_ids: list[str],
    strategy: ArrangeStrategy | str,
    *,
    spacing: float = DEFAULT_SPACING,
    columns: int | None = None,
    radius: float | None = None,
) -> list[dict]:
    """Compute canvas transforms for ``item_ids`` under ``strategy``.

    Returns a list of ``{"item_id", "x", "y", "z", "z_index"}`` dicts, one per
    input id, in input order. Pure + deterministic. ``spacing`` is the gap (in
    canvas units) between adjacent items; ``columns`` overrides the grid width;
    ``radius`` overrides the circle radius.

    Raises ``ValueError`` for an unknown strategy so the caller can map it to a
    4xx. An empty ``item_ids`` returns ``[]`` (the caller decides if that's an
    error).
    """
    strategy = ArrangeStrategy(strategy)  # ValueError on unknown
    if not item_ids:
        return []

    if strategy is ArrangeStrategy.grid:
        return _grid(item_ids, spacing, columns)
    if strategy is ArrangeStrategy.row:
        return _row(item_ids, spacing)
    if strategy is ArrangeStrategy.column:
        return _column(item_ids, spacing)
    if strategy is ArrangeStrategy.circle:
        return _circle(item_ids, spacing, radius)
    if strategy is ArrangeStrategy.stack:
        return _stack(item_ids, spacing)
    # Unreachable: ArrangeStrategy() above rejects anything else.
    raise ValueError(f"Unsupported arrangement strategy: {strategy}")


def _pos(item_id: str, x: float, y: float, z: float, z_index: int) -> dict:
    return {"item_id": item_id, "x": x, "y": y, "z": z, "z_index": z_index}


def _grid(item_ids: list[str], spacing: float, columns: int | None) -> list[dict]:
    n = len(item_ids)
    cols = columns if columns and columns > 0 else max(1, math.ceil(math.sqrt(n)))
    return [
        _pos(item_id, (i % cols) * spacing, (i // cols) * spacing, 0.0, i)
        for i, item_id in enumerate(item_ids)
    ]


def _row(item_ids: list[str], spacing: float) -> list[dict]:
    return [
        _pos(item_id, i * spacing, 0.0, 0.0, i)
        for i, item_id in enumerate(item_ids)
    ]


def _column(item_ids: list[str], spacing: float) -> list[dict]:
    return [
        _pos(item_id, 0.0, i * spacing, 0.0, i)
        for i, item_id in enumerate(item_ids)
    ]


def _circle(item_ids: list[str], spacing: float, radius: float | None) -> list[dict]:
    n = len(item_ids)
    if n == 1:
        return [_pos(item_ids[0], 0.0, 0.0, 0.0, 0)]
    # Default radius spaces items ~``spacing`` apart along the circumference.
    r = radius if radius and radius > 0 else (n * spacing) / (2 * math.pi)
    return [
        _pos(item_id, r * math.cos(2 * math.pi * i / n), r * math.sin(2 * math.pi * i / n), 0.0, i)
        for i, item_id in enumerate(item_ids)
    ]


def _stack(item_ids: list[str], spacing: float) -> list[dict]:
    # A pile: same x/y, climbing z + z_index so later items sit on top.
    z_step = spacing / 10.0
    return [
        _pos(item_id, 0.0, 0.0, i * z_step, i)
        for i, item_id in enumerate(item_ids)
    ]
