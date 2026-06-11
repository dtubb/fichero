"""Bind-host resolution for the Fichero engine.

The engine may bind to a specific tailnet interface address via
``FICHERO_BIND_HOST``. A blanket ``0.0.0.0`` bind is refused because it would
expose the engine on all interfaces instead of only the intended private one.
"""

from __future__ import annotations

from collections.abc import Mapping
from os import environ

DEFAULT_BIND_HOST = "127.0.0.1"


def resolve_bind_host(
    env: Mapping[str, str] | None = None,
    host: str | None = None,
) -> str:
    """Return the configured bind host, enforcing the private-bind guard.

    ``host`` overrides the environment when passed explicitly. When neither is
    set, the engine stays on loopback.
    """

    source = env if env is not None else environ
    raw_host = host if host is not None else source.get("FICHERO_BIND_HOST")
    resolved = (raw_host or DEFAULT_BIND_HOST).strip()

    if resolved == "0.0.0.0":
        raise ValueError(
            "FICHERO_BIND_HOST=0.0.0.0 is not allowed. "
            "Bind the engine to a specific tailnet address or leave "
            "FICHERO_BIND_HOST unset to stay on 127.0.0.1."
        )

    return resolved
