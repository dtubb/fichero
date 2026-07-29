"""Refuse to import files whose bytes are not on this machine (#4233).

Measured on Daniel's live library, 2026-07-28: 152 of 157 imported source
files had ZERO allocated blocks. `~/Desktop/NCM_Diary_1925` reported 380 MB
logical and 12 MB on disk. They are iCloud placeholders — "Desktop & Documents
in iCloud" is a default-adjacent macOS feature and `~/Desktop` is a completely
normal place to keep an archive, so this is not an edge case.

Why a placeholder must not be imported silently:

* `stat` reports the FULL logical size, so nothing downstream can tell the
  difference. LINK mode copies nothing, so there is no read to verify — the
  document points at a file whose bytes may never be local, and the user sees
  "no thumbnail", indistinguishable from a broken file.
* A checksum computed over a partially materialised read would have been
  internally consistent and WRONG. The write-verification work (`7022aea08`)
  catches the short read for COPY mode; nothing caught LINK at all.

Policy, tonight: REFUSE the file, loudly, per file. Materialising (forcing a
download) is deliberately out of scope — forcing a 380 MB download because
someone dragged a folder is hostile, and it is a decision to make deliberately.
Refusing gives the user an actionable message and leaves an `ingest_error` on
the failed stub, which the folder ingest already surfaces in the task status.

Detection, in confidence order:

1. ``SF_DATALESS`` in ``st_flags`` — the kernel's own "no local data" flag,
   authoritative when present (macOS).
2. Non-zero logical size with ZERO allocated blocks, and NOT ``UF_COMPRESSED``.
   An APFS-compressed file keeps its bytes in the ``com.apple.decmpfs`` xattr
   and can also report zero allocated blocks while being entirely local;
   without that second condition this would refuse legitimate compressed
   files. (``UF_COMPRESSED`` in ``st_flags`` rather than reading the xattr:
   ``os.listxattr`` is Linux-only, so on the one platform that matters it does
   not exist.)
3. A bare ``.<name>.icloud`` stub — the visible placeholder file itself.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# <sys/stat.h>: SF_DATALESS — "file is dataless object". Not exposed by the
# stdlib `stat` module, so the literal lives here with its source named.
SF_DATALESS = 0x40000000

# <sys/stat.h>: UF_COMPRESSED — "file is hfs-compressed". Set on APFS/HFS+
# decmpfs files, whose bytes live in an xattr and which can report zero
# allocated blocks while being entirely local.
UF_COMPRESSED = 0x00000020


class DatalessSourceError(ValueError):
    """The file has no local bytes. Subclasses ValueError so the ingest route
    already turns it into a 400 with this message rather than a 500."""


def dataless_reason_from_stat(name: str, st: Any) -> str | None:
    """Why this file has no local bytes, or None. Pure — no syscalls.

    Split out from ``dataless_reason`` so the detection can be tested without
    an iCloud account, entitlements, or a real placeholder on disk.
    """
    if name.startswith(".") and name.endswith(".icloud"):
        return (
            "this is an iCloud placeholder stub (.icloud), not the file itself — "
            "the bytes are not on this machine"
        )

    flags = getattr(st, "st_flags", 0) or 0
    if flags & SF_DATALESS:
        return (
            "macOS reports this file as dataless (SF_DATALESS) — a cloud "
            "placeholder whose bytes are not on this machine"
        )

    size = getattr(st, "st_size", 0) or 0
    blocks = getattr(st, "st_blocks", None)
    if size > 0 and blocks == 0 and not flags & UF_COMPRESSED:
        return (
            f"the file reports {size} bytes but has ZERO allocated blocks — a "
            "cloud placeholder whose bytes are not on this machine"
        )
    return None


def dataless_reason(path: Path) -> str | None:
    """Why ``path`` has no local bytes, or None when it is fully local."""
    try:
        st = path.stat()
    except OSError as exc:  # pragma: no cover - the caller's exists() covers this
        logger.debug("Could not stat %s for dataless check: %s", path, exc)
        return None

    return dataless_reason_from_stat(path.name, st)


def require_local_bytes(path: Path) -> None:
    """Raise ``DatalessSourceError`` when ``path`` is a cloud placeholder.

    Called at INGEST time so the failure is attributable to one file and
    lands in that file's ingest error, rather than surfacing much later as a
    missing thumbnail on a document nobody can connect back to a download.
    """
    reason = dataless_reason(path)
    if reason is None:
        return
    logger.warning("Refusing to import a file with no local bytes: %s (%s)", path, reason)
    raise DatalessSourceError(
        f"{path.name} has no local bytes: {reason}. Download it (keep it "
        f"downloaded in Finder, or open it once) and import again."
    )
