"""Provider API keys supplied by an owning app, held in memory only (#4534).

Daniel's decision: **the app owns the keychain item; the engine never reads a
keychain.** The app is code-signed and stable across reboots and engine
rebuilds. The engine is a Python process whose executable path differs between
Dev (a venv interpreter) and Release (an embedded binary) and moves whenever it
is rebuilt — and an ACL can only be as stable as the identity it names. That
mismatch, not storage, is what made an existing OpenRouter key unreadable after
a reboot.

So keys arrive over the authenticated transport and live HERE: a process-lifetime
dict, never persisted. Persisting them engine-side would re-create the problem
in a new place — a second copy, a second lifetime, a second thing to go stale,
and a second answer to "where is my key".

The consequence is deliberate and must stay VISIBLE: **an engine restart loses
these keys until an app re-supplies them.** In the ordinary embedded path the
app spawns the engine and pushes keys as part of the connect sequence, so the
window is invisible. It is observable only when there genuinely is no app — and
then it must be reported as `not_supplied`, with the remedy, never as "no key".

ponytail: a module-level dict and four functions. A class would buy nothing —
there is exactly one engine process and exactly one set of keys in it. The
`ponytail:` ceiling worth naming is that this is per-process: a future
multi-worker engine would need each worker supplied, which the connect-sequence
push already gives for free since every worker completes its own connect.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# provider -> key. Process lifetime ONLY. Never written to disk, never logged.
_SUPPLIED: dict[str, str] = {}


def supply_api_key(provider: str, key: str) -> None:
    """Accept a key from an owning app.

    Replaces any previous value for the same provider — a re-supply on
    reconnect is the normal path, not an error.
    """
    normalized = provider.strip().lower()
    if not normalized or not key:
        return
    had_key = normalized in _SUPPLIED
    _SUPPLIED[normalized] = key
    # Never log the key. The PROVIDER and the fact of supply are the useful
    # diagnostics, and they are what tells "the app pushed keys on connect"
    # apart from "nobody ever did".
    logger.info(
        "Provider key %s for %s (in memory, process lifetime)",
        "re-supplied" if had_key else "supplied",
        normalized,
    )
    _invalidate_llm_cache(normalized)


def forget_api_key(provider: str) -> bool:
    """Drop a supplied key. Returns whether one was held."""
    normalized = provider.strip().lower()
    existed = _SUPPLIED.pop(normalized, None) is not None
    if existed:
        logger.info("Provider key for %s forgotten", normalized)
        _invalidate_llm_cache(normalized)
    return existed


def supplied_api_key(provider: str) -> str | None:
    """The key an app supplied for `provider`, or None if none has been."""
    return _SUPPLIED.get(provider.strip().lower())


def has_supplied_api_key(provider: str) -> bool:
    return supplied_api_key(provider) is not None


def supplied_providers() -> frozenset[str]:
    """Which providers currently have an app-supplied key. Snapshot, so callers
    cannot mutate the store through it."""
    return frozenset(_SUPPLIED)


def _invalidate_llm_cache(provider: str) -> None:
    """Bust llm.py's resolved-key cache so a supplied or forgotten key takes
    effect immediately (#2545's seam, same reason the keychain writes use it).
    Local import avoids an import cycle.
    """
    try:
        from fichero_server.llm import clear_api_key_cache

        clear_api_key_cache(provider)
    except Exception as exc:  # never fail a supply over a cache bust
        logger.warning("Could not invalidate API key cache for %s: %s", provider, exc)


#: What a CLI, MCP or headless caller can actually DO about a missing key.
#: The state alone ("no provider key supplied") is not actionable — a CLI user
#: has no way to guess that the answer is "open the app once", so the answer
#: travels with the state (#4534, manager condition 2).
NO_APP_REMEDY = (
    "No app has supplied this provider's API key to the engine. "
    "Open Fichero once so it can supply the key, then retry. "
    "For headless or remote engines, set the provider's API key environment "
    "variable instead."
)
