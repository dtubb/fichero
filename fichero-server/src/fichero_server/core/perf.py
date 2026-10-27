"""Lightweight performance logging helpers for backend hot paths."""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import Any, Iterator


def _format_value(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


@contextmanager
def perf_span(
    name: str,
    *,
    logger: logging.Logger | None = None,
    level: int = logging.INFO,
    **context: Any,
) -> Iterator[dict[str, Any]]:
    """Log a one-line timing summary for a scoped operation."""
    perf_logger = logger or logging.getLogger(__name__)
    details: dict[str, Any] = dict(context)
    started = time.perf_counter()
    try:
        yield details
    except Exception as exc:
        details.setdefault("status", "error")
        details.setdefault("error", exc.__class__.__name__)
        raise
    finally:
        elapsed_ms = (time.perf_counter() - started) * 1000
        details["duration_ms"] = round(elapsed_ms, 2)
        ordered = " ".join(
            f"{key}={_format_value(value)}"
            for key, value in sorted(details.items())
            if value is not None
        )
        message = f"PERF {name}"
        if ordered:
            message = f"{message} {ordered}"
        perf_logger.log(level, message)


#: A model loaded again this soon after its last load was let go mid-run: a run's model is loaded once (owner's north
#: star, #6236; #5846 reloaded Kraken per page). Past the window it is an idle release and a fresh load.
RELOAD_WINDOW_SECONDS = 600.0
_LOADS: dict[str, tuple[int, float, bool]] = {}  # model -> (loads, when the last ended, reload said)
_logger = logging.getLogger(__name__)


@contextmanager
def model_load(model: str) -> Iterator[None]:
    """Time one model load: one INFO line with its time and count, and one WARNING the first time it is loaded again
    within the window."""
    started = time.monotonic()
    yield
    ended = time.monotonic()
    count, last, said = _LOADS.get(model, (0, None, False))
    count += 1
    _logger.info("model-lane: loaded %s in %.1f s (load %d in this engine)", model, ended - started, count)
    if last is not None and started - last < RELOAD_WINDOW_SECONDS and not said:
        said = True
        _logger.warning("model loaded again: %s, %.0f s after its last load (load %d in this engine, %.1f s): "
                        "something let it go mid-run", model, started - last, count, ended - started)
    _LOADS[model] = (count, ended, said)
