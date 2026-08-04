"""
macOS Keychain for API key storage using the security command-line tool.

This approach is reliable and works in both sandboxed and non-sandboxed apps.

Usage:
    from fichero_server.security.keychain import get_api_key, set_api_key, delete_api_key

    # Store key
    set_api_key("openai", "sk-...")

    # Retrieve key
    key = get_api_key("openai")

    # Delete key
    delete_api_key("openai")

    # List all stored providers
    providers = list_providers()
"""

from __future__ import annotations

import logging
import subprocess
import sys
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

# Service name for all Fichero keychain items
SERVICE = "com.fichero.fichero"

# `security` exit codes we interpret. 44 is errSecItemNotFound: the item is
# genuinely not there. Everything else non-zero means the lookup FAILED, which
# is a different fact and must stay one (#4534).
_RC_ITEM_NOT_FOUND = 44


class ProviderKeyState(str, Enum):
    """Every answer the engine can give about a provider key.

    Named for the QUESTION ("what is the state of this provider's key?"), not
    for one mechanism that answers it. It began as ProviderKeyState with three
    members, and the app-owned-keys move (#4534) added a fourth reality that has
    nothing to do with a keychain -- at which point a keychain-shaped name would
    have been a lie of exactly the kind this whole program is removing. Renamed
    outright rather than aliased: no shim, no second name (rule zero).

    There have only ever been three, but the code modelled two — and collapsing
    the third into "absent" is what told the whole app that Daniel's OpenRouter
    key did not exist when it was sitting in his login keychain, written
    2026-07-27, merely unreadable by this process.
    """

    FOUND = "found"
    ABSENT = "absent"
    #: No app has supplied this key to the engine, and nothing else provided
    #: it. NOT `absent`: a user with a perfectly good key in the app must
    #: never be told there is no key -- that is the same collapse this enum
    #: exists to prevent, one layer up (#4534).
    NOT_SUPPLIED = "not_supplied"
    #: The item EXISTS and we were refused. `security` exits 36 when the item's
    #: ACL does not trust the calling binary and it cannot prompt (no UI
    #: session) — the state Daniel hit after a reboot. Also covers a locked
    #: keychain and every other non-zero, non-44 outcome: the honest common
    #: factor is "we could not read it", never "it is not there".
    UNREADABLE = "unreadable"


@dataclass(frozen=True)
class KeychainLookup:
    """A read result that cannot be mistaken for the wrong state.

    `key` is only ever populated for FOUND, so a caller that ignores `state`
    still cannot silently use an empty key as though it were a real one.
    """

    state: ProviderKeyState
    key: str | None = None
    #: Why, for UNREADABLE: the exit code and whatever the tool said. This is
    #: what reaches the user, so it must never be invented.
    detail: str | None = None

    @property
    def is_found(self) -> bool:
        return self.state is ProviderKeyState.FOUND


class KeychainUnreadableError(RuntimeError):
    """Raised when a key EXISTS but this process cannot read it.

    Deliberately not a subclass of anything a caller catches by accident. The
    rule it enforces: a failed read must never be returned as an absent value
    (#4534).
    """

    def __init__(self, provider: str, detail: str | None) -> None:
        self.provider = provider
        self.detail = detail
        super().__init__(
            f"Keychain holds an API key for {provider!r} but it could not be read"
            f"{f': {detail}' if detail else ''}"
        )


def _is_macos() -> bool:
    """Check if running on macOS."""
    return sys.platform == "darwin"


def _run_security(*args: str, input_data: str | None = None) -> tuple[int, str, str]:
    """Run a security command.

    Returns:
        Tuple of (return_code, stdout, stderr)
    """
    cmd = ["security"] + list(args)
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            input=input_data,
            timeout=10,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "Command timed out"
    except Exception as e:
        return -1, "", str(e)


# =============================================================================
# Public API
# =============================================================================


def lookup_api_key(provider: str) -> KeychainLookup:
    """Read a provider's API key and say which of the three things happened.

    This is the truthful primitive; `get_api_key` and `has_api_key` are views
    onto it. Nothing here converts a failure into an absence (#4534).
    """
    if not _is_macos():
        # Not a failure and not a lie: off macOS there is no Keychain, so there
        # is genuinely no key IN ONE. `is_available()` reports that separately.
        return KeychainLookup(
            state=ProviderKeyState.ABSENT, detail="keychain is macOS-only"
        )

    # Use security find-generic-password to get the key
    # -s: service name
    # -a: account name
    # -w: print password only
    returncode, stdout, stderr = _run_security(
        "find-generic-password",
        "-s",
        SERVICE,
        "-a",
        provider,
        "-w",  # Output password only
    )

    if returncode == 0 and stdout:
        return KeychainLookup(state=ProviderKeyState.FOUND, key=stdout.strip())

    if returncode == _RC_ITEM_NOT_FOUND:
        return KeychainLookup(state=ProviderKeyState.ABSENT)

    # Everything else: the item may well be there and we were refused. Say so,
    # loudly. This was `logger.debug`, which at the default level is the same
    # as not logging at all -- which is how a vanishing credential went
    # unnoticed until a user reported it.
    detail = stderr.strip() or f"security exited {returncode}"
    if returncode == 0:
        # rc 0 with empty stdout: the tool succeeded and gave us nothing. That
        # is not an absence we can vouch for, so it is not reported as one.
        detail = "security returned success with an empty password"
    logger.warning(
        "Keychain read FAILED for %s (rc=%s): %s -- reporting as unreadable, NOT as absent",
        provider,
        returncode,
        detail,
    )
    return KeychainLookup(state=ProviderKeyState.UNREADABLE, detail=detail)


def get_api_key(provider: str) -> str | None:
    """Get API key from Keychain.

    Args:
        provider: Provider name (e.g., "openai", "anthropic")

    Returns:
        The API key, or None when the item is genuinely ABSENT.

    Raises:
        KeychainUnreadableError: the item could not be read (ACL refusal,
            locked keychain, ...). Deliberately NOT `None`: returning the
            absent answer for a failed read is the defect this fixes (#4534).
            Callers with a legitimate fallback should catch it and log the
            reason they fell back, at the point they fall back.
    """
    result = lookup_api_key(provider)
    if result.state is ProviderKeyState.UNREADABLE:
        raise KeychainUnreadableError(provider, result.detail)
    return result.key


def _invalidate_llm_api_key_cache(provider: str) -> None:
    """Bust llm.py's resolved-api-key cache after a Keychain write so a rotated
    or deleted key takes effect immediately, without a process restart (#2545,
    M1 follow-up). Local import avoids the keychain <- llm import cycle.
    """
    try:
        from fichero_server.llm import clear_api_key_cache

        clear_api_key_cache(provider)
    except Exception as exc:  # don't fail the write; but never swallow silently
        logger.warning(
            "Could not invalidate API key cache for %s: %s", provider, exc
        )


def set_api_key(provider: str, key: str) -> bool:
    """Store API key in Keychain.

    Args:
        provider: Provider name (e.g., "openai", "anthropic")
        key: API key string

    Returns:
        True if stored successfully
    """
    if not _is_macos():
        logger.debug("Not on macOS - keychain disabled")
        return False

    if not key:
        return False

    # First try to delete existing item (ignore errors)
    delete_api_key(provider)

    # Use security add-generic-password
    # -s: service name
    # -a: account name
    # -l: label (human-readable)
    # -w: password
    # -U: update if exists (but we deleted first, so shouldn't matter)
    returncode, stdout, stderr = _run_security(
        "add-generic-password",
        "-s",
        SERVICE,
        "-a",
        provider,
        "-l",
        f"Fichero API key for {provider}",
        "-w",
        key,
        "-U",  # Update if exists
    )

    if returncode == 0:
        logger.debug("Stored API key for %s", provider)
        _invalidate_llm_api_key_cache(provider)
        return True
    else:
        logger.warning("Failed to store API key: %s", stderr.strip())
        return False


def delete_api_key(provider: str) -> bool:
    """Remove API key from Keychain.

    Args:
        provider: Provider name

    Returns:
        True if deleted (or didn't exist)
    """
    if not _is_macos():
        return False

    # Use security delete-generic-password
    returncode, stdout, stderr = _run_security(
        "delete-generic-password",
        "-s",
        SERVICE,
        "-a",
        provider,
    )

    # Success or item not found both count as successful delete
    success = returncode in (0, 44)
    if success:
        _invalidate_llm_api_key_cache(provider)
    return success


def has_api_key(provider: str) -> bool:
    """Whether a READABLE key exists.

    Still a bool, because most callers legitimately want one -- but it is now
    False for ABSENT *and* for UNREADABLE, and those must not be reported to a
    user as the same thing. Anything that renders this to a human must call
    `api_key_state` instead: `has_api_key: false` was a true value and a false
    statement, and that is what told Daniel his key was gone (#4534).
    """
    return lookup_api_key(provider).is_found


def api_key_state(provider: str) -> KeychainLookup:
    """The full three-state answer, for callers that must not flatten it.

    Returns the lookup WITHOUT its secret -- a status caller has no business
    holding the key, and this way the result can be logged or serialized
    without leaking it.
    """
    result = lookup_api_key(provider)
    return KeychainLookup(state=result.state, key=None, detail=result.detail)


def list_providers() -> list[str]:
    """List all providers with stored API keys.

    Returns:
        List of provider names
    """
    if not _is_macos():
        return []

    # Use security dump-keychain and parse for our service
    # This is a bit hacky but security doesn't have a nice list command
    returncode, stdout, stderr = _run_security(
        "dump-keychain",
    )

    if returncode != 0:
        # #4534, same defect class as the read path: an empty list here means
        # "no providers have keys", and a failed dump is not that. A locked
        # keychain would have reported every provider as unconfigured.
        logger.warning(
            "Keychain dump FAILED (rc=%s): %s -- provider list is UNKNOWN, not empty",
            returncode,
            stderr.strip() or "no stderr",
        )
        return []

    providers = []
    in_our_service = False

    for line in stdout.split("\n"):
        line = line.strip()

        # Look for our service
        if f'"svce"<blob>="{SERVICE}"' in line:
            in_our_service = True
        elif '"svce"<blob>=' in line and SERVICE not in line:
            in_our_service = False

        # If we're in our service block, look for account
        if in_our_service and '"acct"<blob>="' in line:
            # Extract account name
            start = line.find('"acct"<blob>="') + len('"acct"<blob>="')
            end = line.find('"', start)
            if end > start:
                account = line[start:end]
                if account and account not in providers:
                    providers.append(account)
            in_our_service = False

    return providers


def is_available() -> bool:
    """Check if keychain functionality is available.

    Returns:
        True if running on macOS
    """
    return _is_macos()


__all__ = [
    "KeychainLookup",
    "ProviderKeyState",
    "KeychainUnreadableError",
    "api_key_state",
    "lookup_api_key",
    "get_api_key",
    "set_api_key",
    "delete_api_key",
    "has_api_key",
    "list_providers",
    "is_available",
    "SERVICE",
]
