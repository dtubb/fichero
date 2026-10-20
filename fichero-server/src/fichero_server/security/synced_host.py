"""The non-secret `sharing-host.json` a host engine writes into a shared project (#5898).

`sharing.synced-project-names-its-host`: exactly three keys, https only, small. A guest engine reads it so its Mac
can ask once for the host's pairing link; the app never reads the project root itself.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from urllib.parse import urlparse

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
