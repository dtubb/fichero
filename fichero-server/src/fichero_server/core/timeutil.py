"""Canonical clock for the server: timezone-aware UTC, always.

Why this module exists (#4347): the server used to stamp rows with
``datetime.now()`` — a NAIVE *local* datetime. Serialized without an offset,
every ISO-8601 decoder (the Swift client included) reads that value as UTC, so
a run that just finished rendered as "3 hours ago" in ADT (UTC-3).

The rules, in one place:

* **Write** ``utc_now()`` — never ``datetime.now()`` / ``datetime.utcnow()``.
  ``scripts/check_naive_datetimes.py`` fails the gate on the naive forms. An
  explicit ``datetime.now(timezone.utc)`` is equivalent and also passes the gate
  (a lot of already-correct code predates this module); ``utc_now()`` is simply
  the shorter, single-definition spelling.
* **Persist** aware UTC. DuckDB ``TIMESTAMP`` columns are naive, and binding an
  aware value makes DuckDB shift it into the *session* timezone before dropping
  the offset. ``fichero_server.db.connect`` therefore pins every connection to
  ``TimeZone='UTC'`` so that shift is a no-op and the stored wall clock is UTC.
* **Read** naive values back through ``ensure_utc()`` before comparing them with
  ``utc_now()`` or serializing them — a naive value from storage *is* UTC by
  this contract, so ``ensure_utc`` attaches ``+00:00`` rather than guessing.

``ensure_utc`` is deliberately total on datetimes and rejects nothing silently:
naive means UTC, aware means convert. It never substitutes a different instant.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, overload

__all__ = ["ensure_utc", "naive_utc", "utc_now", "utc_now_iso"]


def utc_now() -> datetime:
    """Current instant as a timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


def utc_now_iso(timespec: str = "auto") -> str:
    """Current instant as an ISO-8601 string carrying the ``+00:00`` offset."""
    return utc_now().isoformat(timespec=timespec)


@overload
def ensure_utc(value: datetime) -> datetime: ...


@overload
def ensure_utc(value: None) -> None: ...


def ensure_utc(value: Optional[datetime]) -> Optional[datetime]:
    """Return ``value`` as aware UTC; a naive value is *interpreted* as UTC.

    ``None`` passes through so callers can normalize optional columns without a
    branch. No other type is accepted — a wrong type raises rather than
    silently yielding a plausible-looking instant.
    """
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise TypeError(f"ensure_utc expects datetime or None, got {type(value)!r}")
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def naive_utc(value: Optional[datetime] = None) -> Optional[datetime]:
    """UTC wall clock with the offset stripped, for naive storage columns.

    Prefer binding the aware value directly (connections are pinned to
    ``TimeZone='UTC'``); use this only where a naive datetime is required by an
    external contract that cannot carry an offset.
    """
    normalized = ensure_utc(utc_now() if value is None else value)
    return None if normalized is None else normalized.replace(tzinfo=None)
