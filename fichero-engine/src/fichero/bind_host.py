"""Bind-host resolution for the Fichero engine.

The supported remote-access model is loopback binding plus an explicit HTTPS
transport or SSH forwarding. The shared bootstrap token is not an internet-
facing auth boundary, so non-loopback binding must stay an explicit,
risk-acknowledged escape hatch rather than the default path.
"""

from __future__ import annotations

import ipaddress
import warnings
from collections.abc import Mapping
from os import environ

DEFAULT_BIND_HOST = "127.0.0.1"
PUBLIC_URL_ENV = "FICHERO_PUBLIC_BASE_URL"
LAN_BIND_HOST_ENV = "FICHERO_LAN_HOST"
NON_LOOPBACK_BIND_ACK_ENV = "FICHERO_ALLOW_NON_LOOPBACK_BIND"
NON_LOOPBACK_BIND_ACK_VALUE = "I_UNDERSTAND_SHARED_SECRET_RISK"


def _is_loopback_host(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


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
    public_base_url = (source.get(PUBLIC_URL_ENV) or "").strip()
    if host is None and public_base_url:
        return DEFAULT_BIND_HOST
    resolved = (raw_host or DEFAULT_BIND_HOST).strip()

    if resolved == "0.0.0.0":
        if source.get(NON_LOOPBACK_BIND_ACK_ENV) != NON_LOOPBACK_BIND_ACK_VALUE:
            raise ValueError(
                "FICHERO_BIND_HOST=0.0.0.0 is not allowed without the shared-"
                "secret risk acknowledgement. Set "
                f"{NON_LOOPBACK_BIND_ACK_ENV}={NON_LOOPBACK_BIND_ACK_VALUE} to "
                "bind all interfaces."
            )

    if resolved == "::":
        raise ValueError(
            "FICHERO_BIND_HOST=:: is not allowed. Keep the engine on ::1 or "
            "127.0.0.1 and use the explicit HTTPS remote-access launch path "
            "or SSH loopback forwarding."
        )

    if not _is_loopback_host(resolved):
        if source.get(NON_LOOPBACK_BIND_ACK_ENV) != NON_LOOPBACK_BIND_ACK_VALUE:
            raise ValueError(
                f"FICHERO_BIND_HOST={resolved!r} is non-loopback. "
                "The supported remote model is 127.0.0.1 plus an explicit HTTPS "
                "remote-access transport or SSH loopback forwarding. To override "
                "deliberately, set "
                f"{NON_LOOPBACK_BIND_ACK_ENV}={NON_LOOPBACK_BIND_ACK_VALUE}."
            )
        warnings.warn(
            "WARNING: binding Fichero to a non-loopback host. The shared "
            "bootstrap token is not an internet-facing auth boundary; prefer "
            "127.0.0.1 plus an explicit HTTPS remote-access transport or SSH "
            "loopback forwarding.",
            RuntimeWarning,
            stacklevel=2,
        )

    return resolved


def resolve_lan_bind_host(
    env: Mapping[str, str] | None = None,
    host: str | None = None,
) -> str | None:
    """Return one explicit LAN listener host, or ``None`` when disabled."""

    source = env if env is not None else environ
    raw_host = host if host is not None else source.get(LAN_BIND_HOST_ENV)
    if raw_host is None or not raw_host.strip():
        return None
    if raw_host.strip() == "0.0.0.0":
        raise ValueError(
            f"{LAN_BIND_HOST_ENV}=0.0.0.0 is not allowed. Use one explicit LAN address."
        )

    resolved = resolve_bind_host(source, host=raw_host)
    if _is_loopback_host(resolved):
        raise ValueError(
            f"{LAN_BIND_HOST_ENV} must be a non-loopback address when set."
        )
    return resolved
