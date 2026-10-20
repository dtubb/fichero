"""The non-secret `sharing-host.json` a host engine writes into a shared project (#5898).

`sharing.synced-project-names-its-host`: exactly four keys, https only, small. A guest engine reads it so its Mac
can ask once for the host's pairing link; the app never reads the project root itself.
"""

from __future__ import annotations

import functools
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
    hostEngineId: str  # noqa: N815 -- the engine's stable id (not a secret)

    @field_validator("hostURL")
    @classmethod
    def _https_only(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("hostURL must be an https address")
        if parsed.username or parsed.password or parsed.path not in ("", "/") or parsed.query or parsed.fragment:
            raise ValueError("hostURL must be an https origin only (no user, path, query or fragment)")
        return value

    @field_validator("hostName", "person", "hostEngineId")
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


@functools.cache  # stable for the engine's life; each read otherwise takes the app-DB lock
def this_engine_id() -> str:
    """This engine's stable id: the `engine_id` the sign-in challenge reports. The host's writer calls this."""
    from fichero_server.api.routes.auth.accounts import _engine_id
    from fichero_server.db.app import get_app_db

    return _engine_id(get_app_db())


def is_this_engine(host_engine_id: str | None) -> bool:
    """Whether the file names THIS engine: identity is the engine's id, not its address, so Sharing off or a changed
    address cannot make the host's own copy ask the owner to ask themself. False for None or empty."""
    return bool(host_engine_id) and this_engine_id() == host_engine_id


def host_to_ask(library_root: Path) -> SyncedHost | None:
    """What a GUEST asks for: the file's host, unless it names THIS engine (the host's own copy asks nobody)."""
    host = read_synced_host(library_root)
    return None if host is None or is_this_engine(host.hostEngineId) else host
