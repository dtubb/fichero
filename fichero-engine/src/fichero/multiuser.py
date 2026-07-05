"""Shared feature-gate helpers for multi-user auth and pairing."""

from __future__ import annotations

from collections.abc import Mapping
import os

TRUE_VALUES = {"1", "true", "yes", "on"}
FALSE_VALUES = {"0", "false", "no", "off"}
MULTIUSER_SETTING_KEY = "multiuser.enabled"


def multiuser_enabled(env: Mapping[str, str] | None = None) -> bool:
    """Return True when per-user auth/pairing should be active.

    Multi-user auth is **opt-in**. A fresh single-user local launch has no
    account/ACL rows, so turning the per-user authorizer on by default denied
    the Mac owner read/write to its own library (401 on app-wide routes, 403
    on library routes — #2721). Single-user local therefore defaults OFF and
    keeps the loopback + bootstrap-token trust model (#742); the ACL layer
    only matters once real accounts exist.

    It turns ON only when explicitly requested (`FICHERO_MULTIUSER=1`),
    when the persisted app setting says it is enabled, or when real account
    rows already exist in the app database and the install must stay in
    multi-user mode. Transport signals are not auth signals.
    """

    source = env if env is not None else os.environ
    configured = (source.get("FICHERO_MULTIUSER") or "").strip().lower()
    if configured in FALSE_VALUES:
        return False
    if configured in TRUE_VALUES:
        return True
    persisted = _persisted_multiuser_enabled()
    if persisted is not None:
        return persisted
    return _has_account_rows()


def _persisted_multiuser_enabled() -> bool | None:
    try:
        from fichero.app_db import get_app_db

        value = get_app_db().get_setting(MULTIUSER_SETTING_KEY)
    except Exception:
        return None
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized in TRUE_VALUES:
        return True
    if normalized in FALSE_VALUES:
        return False
    return None


def _has_account_rows() -> bool:
    try:
        from fichero.app_db import get_app_db

        return bool(get_app_db().list_users())
    except Exception:
        return False
