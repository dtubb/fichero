"""Shared feature-gate helpers for multi-user auth and pairing.

Remote pairing should not depend on one fragile env variable when the engine is
already explicitly configured for remote presence or transport. This module
centralizes the "is multi-user mode on?" decision so auth middleware, ACLs, and
pairing routes all agree.
"""

from __future__ import annotations

from collections.abc import Mapping
import os

from fichero.bind_host import _is_loopback_host

TRUE_VALUES = {"1", "true", "yes", "on"}
FALSE_VALUES = {"0", "false", "no", "off"}


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in TRUE_VALUES


def multiuser_enabled(env: Mapping[str, str] | None = None) -> bool:
    """Return True when per-user auth/pairing should be active.

    Multi-user auth is **opt-in**. A fresh single-user local launch has no
    account/ACL rows, so turning the per-user authorizer on by default denied
    the Mac owner read/write to its own library (401 on app-wide routes, 403
    on library routes — #2721). Single-user local therefore defaults OFF and
    keeps the loopback + bootstrap-token trust model (#742); the ACL layer
    only matters once real accounts exist.

    It turns ON when explicitly requested (`FICHERO_MULTIUSER=1`) or when a
    genuinely network-facing deployment signal is present:
    - Bonjour advertisement
    - a configured public/private reachable URL for clients
    - a deliberate non-loopback bind host

    Explicit `FICHERO_MULTIUSER=0` forces it off even under those signals
    (development/tests).
    """

    source = env if env is not None else os.environ
    configured = (source.get("FICHERO_MULTIUSER") or "").strip().lower()
    if configured in FALSE_VALUES:
        return False
    if configured in TRUE_VALUES:
        return True
    if _truthy(source.get("FICHERO_ENABLE_BONJOUR")):
        return True
    if (source.get("FICHERO_PUBLIC_BASE_URL") or "").strip():
        return True

    for name in ("FICHERO_BIND_HOST", "FICHERO_REMOTE_BACKEND_BIND_HOST"):
        host = (source.get(name) or "").strip()
        if host and not _is_loopback_host(host):
            return True

    return False
