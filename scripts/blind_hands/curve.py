"""The blind-hands learning curve (#6967, `hands.bench.learning-curve-at-five-points`).

`nested_subsets` shuffles a hand's adaptation-pool lines with one seed and takes prefixes, so the 50 lines are among the
100, and so on, and two configurations given the same pool and seed learn from the same lines. `curve` calls a
caller-supplied `measure(lines)` once per point and keeps what it returns; `measure` is where the whole-page error from
the one scorer and the error on given lines come from. A point larger than the pool is the string
"not measured: N lines in the pool", never a number.
"""

from __future__ import annotations

import random
from collections.abc import Callable

POINTS = (0, 50, 100, 200, 400)


def nested_subsets(pool_lines: list[str], seed: int, points: tuple[int, ...] = POINTS) -> dict[int, list[str]]:
    """Per point that the pool can fill, the first `point` lines of one seeded shuffle; larger points are absent."""
    order = list(pool_lines)
    random.Random(seed).shuffle(order)
    return {p: order[:p] for p in points if p <= len(order)}


def curve(pool_lines: list[str], seed: int, measure: Callable[[list[str]], dict],
          points: tuple[int, ...] = POINTS) -> dict:
    """`{"seed": seed, "points": {point: measure(lines) | "not measured: N lines in the pool"}}`."""
    subsets = nested_subsets(pool_lines, seed, points)
    return {"seed": seed,
            "points": {p: measure(subsets[p]) if p in subsets else f"not measured: {len(pool_lines)} lines in the pool"
                       for p in points}}
