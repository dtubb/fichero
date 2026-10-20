"""The non-secret `sharing-host.json` a shared project carries in its root (#5898, `sharing.synced-project-names-its-host`).

A project that reaches another Mac by sync arrives with no way to say where its host is. When the host shares a library with a
person, the HOST engine writes `{hostURL, hostName, person, hostEngineId}` into the library root so the guest can ask that person
for a pairing LINK. The file holds no token, code, pin or account id; `hostURL` is only an `https` origin; `hostEngineId` is the
engine's stable id (the one the sign-in challenge reports), which is how an engine knows the library is its own.

Only the engine that OWNS the project writes it: the first engine to share records itself, and from then on only that engine
rewrites the file (`synced_host.is_this_engine`). A guest's own engine, which has the synced copy and may have Sharing on, never
writes its own address over the host's, and a file it cannot read as ours is left alone. A failure is logged and never raised:
sharing works without the file.
"""

from __future__ import annotations

import json
import logging
import os
import socket
import subprocess
import tempfile
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


MAX_NAME = 200  # what the guest's reader accepts for hostName and person (`synced_host.SyncedHost`): 1-200 characters, no "://"


def _clip(text: str) -> str:
    """A name the reader will accept: control characters dropped, nothing link-like, at most 200 characters; '' if nothing is left."""
    cleaned = "".join(ch for ch in (text or "") if ch.isprintable()).replace("://", "")
    return cleaned.strip()[:MAX_NAME].strip()


def _host_name() -> str:
    """The name the person sees for this Mac (System Settings > General > About: `scutil --get ComputerName`), else the host name."""
    try:
        name = subprocess.run(["scutil", "--get", "ComputerName"], capture_output=True, text=True, timeout=2).stdout.strip()
    except Exception:  # noqa: BLE001 -- not macOS, or scutil is not there
        name = ""
    return _clip(name) or _clip(socket.gethostname().split(".")[0]) or "this Mac"


def record_for(person: str) -> dict[str, str] | None:
    """The four fields, or None when the host has no https address."""
    url = _host_url()
    if url is None:
        return None
    from fichero_server.security import synced_host

    name = _host_name()
    return {"hostURL": url, "hostName": name, "person": _clip(person) or name, "hostEngineId": synced_host.this_engine_id()}


def _may_write(target: Path) -> bool:
    """No file yet, or a valid file that names THIS engine. Anything else (another engine's, or one we cannot read as ours:
    corrupt, three keys from before engine ids, extra keys) is left as it is; deleting it is the owner's call."""
    if not target.exists():
        return True
    from fichero_server.security import synced_host

    host = synced_host.read_synced_host(target.parent)
    if host is None:
        logger.info("not overwriting an unreadable %s in %s", FILE_NAME, target.parent)
        return False
    if not synced_host.is_this_engine(host.hostEngineId):
        logger.info("not overwriting %s in %s: it names another engine", FILE_NAME, target.parent)
        return False
    return True


def write(library_root: str | Path, person: str) -> bool:
    """Write the file into `library_root` when this engine owns the project and a field changed (a uniquely named temp file in the
    same directory, then an atomic replace, so two Macs syncing can never collide on one temp name). True if it wrote."""
    tmp_name = None
    try:
        target = Path(library_root) / FILE_NAME
        record = record_for(person)
        if record is None or not _may_write(target):
            return False
        text = json.dumps(record, indent=2, sort_keys=True) + "\n"
        if target.exists() and target.read_text() == text:
            return False
        with tempfile.NamedTemporaryFile("w", dir=target.parent, prefix=".sharing-host.", suffix=".tmp", delete=False) as tmp:
            tmp_name = tmp.name
            tmp.write(text)
        os.replace(tmp_name, target)
        return True
    except Exception:
        logger.warning("could not write %s", FILE_NAME, exc_info=True)
        if tmp_name:
            Path(tmp_name).unlink(missing_ok=True)
        return False
