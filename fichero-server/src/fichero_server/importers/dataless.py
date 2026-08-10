"""Download files whose bytes are not on this machine before import (#4233, #45).

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

Policy (revised, Daniel 2026-08-09: "when file is online it should be
downloaded, no?"): MATERIALIZE the file at ingest time — reading a dataless
file is the download trigger — and refuse loudly, per file, only when the
download cannot complete (offline, timeout, or a bare `.icloud` stub, which
is a different inode from the real file). A failure still leaves an
`ingest_error` on the failed stub, which the folder ingest surfaces in the
task status.

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
    """Materialize ``path`` if it is a cloud placeholder, or raise.

    Daniel's ruling (2026-08-09): "when file is online it should be
    downloaded, no?" — a dataless file is DOWNLOADED at ingest time, not
    refused. Reading a dataless file is itself the download trigger: the
    kernel faults the bytes in through fileproviderd for any process whose
    VFS iopolicy materializes dataless files (the default). Only when the
    download cannot complete does this raise ``DatalessSourceError``, at
    INGEST time, so the failure is attributable to one file and lands in
    that file's ingest error.

    A bare ``.<name>.icloud`` stub is still refused outright: the stub is a
    different inode from the real file — reading it downloads nothing, and
    importing the stub was never what the user meant.
    """
    reason = dataless_reason(path)
    if reason is None:
        return
    if path.name.startswith(".") and path.name.endswith(".icloud"):
        logger.warning("Refusing to import an iCloud stub: %s", path)
        raise DatalessSourceError(
            f"{path.name} has no local bytes: {reason}. Download the real file "
            f"(keep it downloaded in Finder) and import that instead."
        )
    _materialize(path, reason)


# ponytail: sequential read at an assumed ≥1 MB/s floor; a per-library
# bandwidth estimate can replace the constant if slow links time out a lot.
_MIN_TIMEOUT_SECONDS = 120.0
_ASSUMED_BYTES_PER_SECOND = 1_000_000
_READ_CHUNK = 8 * 1024 * 1024


def _materialize(path: Path, reason: str) -> None:
    """Fault the file's bytes in by reading it, bounded by a size-scaled
    deadline, then verify the placeholder is actually gone."""
    import time

    size = getattr(path.stat(), "st_size", 0) or 0
    deadline = time.monotonic() + max(
        _MIN_TIMEOUT_SECONDS, size / _ASSUMED_BYTES_PER_SECOND
    )
    logger.info(
        "Downloading cloud placeholder before import: %s (%d bytes; %s)",
        path, size, reason,
    )
    try:
        with path.open("rb") as fh:
            while fh.read(_READ_CHUNK):
                if time.monotonic() > deadline:
                    raise DatalessSourceError(
                        f"{path.name} has no local bytes and the download did "
                        f"not finish in time ({size} bytes). Download it in "
                        f"Finder (keep it downloaded) and import again."
                    )
    except OSError as exc:
        raise DatalessSourceError(
            f"{path.name} has no local bytes and downloading it failed "
            f"({exc}). Download it in Finder (keep it downloaded) and "
            f"import again."
        ) from exc

    still = dataless_reason(path)
    if still is not None:
        logger.warning("Still dataless after a full read: %s (%s)", path, still)
        raise DatalessSourceError(
            f"{path.name} has no local bytes: {still}. Fichero tried to "
            f"download it, but the bytes still are not local. Download it in "
            f"Finder (keep it downloaded) and import again."
        )
    logger.info("Downloaded and importing: %s", path)
