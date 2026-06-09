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
