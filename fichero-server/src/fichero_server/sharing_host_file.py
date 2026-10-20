"""The non-secret `sharing-host.json` a shared project carries in its root (#5898, `sharing.synced-project-names-its-host`).

A project that reaches another Mac by sync arrives with no way to say where its host is. When the host shares a library with a
person, the HOST engine writes `{hostURL, hostName, person}` into the library root so the guest can ask that person for a pairing
LINK. The file holds no token, code, pin or account id, and `hostURL` is only an `https` origin (scheme, host, port): the same fact
the pairing link already carries. A failure is logged and never raised: sharing works without it.
"""

from __future__ import annotations

import json
import logging
import os
import socket
from pathlib import Path
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)

FILE_NAME = "sharing-host.json"


def _host_url() -> str | None:
    """The host's `https` origin from FICHERO_PUBLIC_BASE_URL, or None (no public https address: nothing to name)."""
    parts = urlsplit((os.environ.get("FICHERO_PUBLIC_BASE_URL") or "").strip())
    if parts.scheme != "https" or not parts.hostname:
        return None
    port = f":{parts.port}" if parts.port else ""
    return f"https://{parts.hostname}{port}"


def record_for(person: str) -> dict[str, str] | None:
    """The three fields, or None when the host has no https address."""
    url = _host_url()
    if url is None:
        return None
    name = socket.gethostname().split(".")[0] or "this Mac"
    return {"hostURL": url, "hostName": name, "person": (person or "").strip() or name}


def write(library_root: str | Path, person: str) -> bool:
    """Write the file into `library_root` when a field changed (temp file, then an atomic replace). True if it wrote."""
    try:
        record = record_for(person)
        if record is None:
            return False
        target = Path(library_root) / FILE_NAME
        text = json.dumps(record, indent=2, sort_keys=True) + "\n"
        if target.exists() and target.read_text() == text:
            return False
        tmp = target.with_name(target.name + ".tmp")
        tmp.write_text(text)
        os.replace(tmp, target)
        return True
    except Exception:
        logger.warning("could not write %s", FILE_NAME, exc_info=True)
        return False
