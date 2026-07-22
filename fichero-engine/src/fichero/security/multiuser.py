"""Shared feature-gate helpers for multi-user auth and pairing."""

from __future__ import annotations

from collections.abc import Mapping
import logging
import os

logger = logging.getLogger(__name__)
TRUE_VALUES = {"1", "true", "yes", "on"}
FALSE_VALUES = {"0", "false", "no", "off"}
MULTIUSER_SETTING_KEY = "multiuser.enabled"


def multiuser_enabled(env: Mapping[str, str] | None = None) -> bool:
    """Return True when per-user auth/pairing should be active.

    Multi-user auth is **explicit opt-in only**. A fresh single-user local
    launch must never silently enable multi-user because account rows happen
    to exist (the ``__paired_device_owner__`` phantom, #3331).

    It turns ON only when explicitly requested (``FICHERO_MULTIUSER=1``) or
    when the persisted app setting says it is enabled. Account rows alone are
    NEVER sufficient — an account row existing is a side effect of pairing,
    not a user's intent to enable multi-user auth.
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
    # ponytail: no _has_account_rows() fallback — account rows are a side
    # effect, not intent. Multi-user stays OFF until explicitly turned on.
    return False


def _persisted_multiuser_enabled() -> bool | None:
    try:
        from fichero.db.app import get_app_db

        value = get_app_db().get_setting(MULTIUSER_SETTING_KEY)
    except Exception as exc:
        logger.warning("Could not read persisted multi-user setting: %s", exc)
        return None
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized in TRUE_VALUES:
        return True
    if normalized in FALSE_VALUES:
        return False
    return None
