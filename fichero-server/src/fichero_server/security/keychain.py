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

logger = logging.getLogger(__name__)

# Service name for all Fichero keychain items
SERVICE = "com.fichero.fichero"


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


def get_api_key(provider: str) -> str | None:
    """Get API key from Keychain.

    Args:
        provider: Provider name (e.g., "openai", "anthropic")

    Returns:
        API key string, or None if not found
    """
    if not _is_macos():
        logger.debug("Not on macOS - keychain disabled")
        return None

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
        return stdout.strip()

    # Error code 44 means item not found - not an error
    if returncode == 44:
        return None

    if returncode != 0:
        logger.debug("Keychain get failed: %s", stderr.strip())

    return None


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
    """Check if API key exists in Keychain.

    Args:
        provider: Provider name

    Returns:
        True if key exists
    """
    return get_api_key(provider) is not None


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
    "get_api_key",
    "set_api_key",
    "delete_api_key",
    "has_api_key",
    "list_providers",
    "is_available",
    "SERVICE",
]
