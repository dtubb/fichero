"""The non-secret `sharing-host.json` a host engine writes into a shared project (#5898).

`sharing.synced-project-names-its-host`: exactly three keys, https only, small. A guest engine reads it so its Mac
can ask once for the host's pairing link; the app never reads the project root itself.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from urllib.parse import urlparse, urlsplit

from pydantic import BaseModel, ConfigDict, field_validator

logger = logging.getLogger(__name__)

FILE_NAME = "sharing-host.json"
MAX_BYTES = 2048


class SyncedHost(BaseModel):
    """Where a synced project's host is, and which person to ask for a pairing link. Never a secret."""

    model_config = ConfigDict(extra="forbid")

    hostURL: str  # noqa: N815 -- the file's own key
    hostName: str  # noqa: N815
    person: str

    @field_validator("hostURL")
    @classmethod
    def _https_only(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("hostURL must be an https address")
        if parsed.username or parsed.password or parsed.path not in ("", "/") or parsed.query or parsed.fragment:
            raise ValueError("hostURL must be an https origin only (no user, path, query or fragment)")
        return value

    @field_validator("hostName", "person")
    @classmethod
    def _short_text(cls, value: str) -> str:
        if not value.strip() or len(value) > 200:
            raise ValueError("must be 1-200 characters")
        if "://" in value:  # nothing link-like (a pairing link, an address) in a name
            raise ValueError("must be a name, not a link")
        return value


def read_synced_host(library_root: Path) -> SyncedHost | None:
    """The host the project names, or None: no file, too big, not JSON, extra/missing keys, or not https."""
    path = Path(library_root) / FILE_NAME
    try:
        if not path.is_file() or path.stat().st_size > MAX_BYTES:
            return None
        return SyncedHost.model_validate(json.loads(path.read_bytes()))
    except (OSError, ValueError) as exc:  # pydantic.ValidationError and JSONDecodeError are ValueErrors
        logger.info("ignoring %s in %s: %s", FILE_NAME, library_root, exc)
        return None


def _origin(url: str | None) -> str | None:
    """`https://host[:port]`, host lower-cased, the default port dropped; None for anything that is not an https address."""
    parts = urlsplit((url or "").strip())
    if parts.scheme != "https" or not parts.hostname:
        return None
    port = f":{parts.port}" if parts.port and parts.port != 443 else ""
    return f"https://{parts.hostname.lower()}{port}"


def own_origin() -> str | None:
    """This engine's own https origin (FICHERO_PUBLIC_BASE_URL), the one test for "this engine is the recorded host"
    (the host's writer, `sharing_host_file`, names itself by the same variable)."""
    return _origin(os.environ.get("FICHERO_PUBLIC_BASE_URL"))


def host_to_ask(library_root: Path) -> SyncedHost | None:
    """What a GUEST asks for: the file's host, unless it names THIS engine (the host's own copy asks nobody)."""
    host = read_synced_host(library_root)
    if host is None:
        return None
    return None if _origin(host.hostURL) == own_origin() else host
