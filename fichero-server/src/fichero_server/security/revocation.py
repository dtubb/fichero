"""Who is told when a paired device is revoked (`sharing.revoke-closes-the-stream`, #5913).

The app database cannot import the API layer, so the API registers what to do and `revoke_device` only says which devices.
"""
from __future__ import annotations

import logging
from collections.abc import Callable, Iterable

logger = logging.getLogger(__name__)

_listeners: list[Callable[[list[str]], None]] = []


def on_revoked(listener: Callable[[list[str]], None]) -> None:
    if listener not in _listeners:
        _listeners.append(listener)


def notify(device_ids: Iterable[str]) -> None:
    """Tell every listener; one failing listener never undoes a revoke or stops the others."""
    ids = list(device_ids)
    for listener in list(_listeners):
        try:
            listener(ids)
        except Exception:  # noqa: BLE001
            logger.warning("a revoke listener failed", exc_info=True)
