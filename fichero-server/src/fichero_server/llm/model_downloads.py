"""A model download survives a broken connection (#5660 item 12).

Zenodo dropped a Kraken reader part-way (IncompleteRead, 8.8 of 63 MB) and the plan showed the Python
exception. Every model download now goes through this:

* `fetch_file` writes into `<file>.part`, and when the connection breaks it tries again after a pause
  (`BACKOFF_SECONDS`), asking the server for the rest only (an HTTP Range request) where it allows it, and
  from the start where it does not; a file of the stated size is the only one that becomes `<file>`;
* `with_retries` does the same for a fetch that resumes by itself (Hugging Face's `snapshot_download`
  keeps its `.incomplete` files and continues them), so MLX, Whisper and embedding models are covered;
* only after the last try is a failure said, in one sentence a person reads, with the model's name
  (`DownloadInterrupted`); never the exception's text;
* a stop asked of the download (`should_stop`) ends it at the next chunk, keeping what it has, so starting
  it again continues from there (`DownloadStopped`).

A failure that is not the connection (a refused request, a missing file, no room) is not retried: it is
not going to get better by waiting.
"""

from __future__ import annotations

import http.client
import logging
import time
import urllib.error
import urllib.request
from pathlib import Path
from collections.abc import Callable
from typing import TypeVar

logger = logging.getLogger(__name__)

_T = TypeVar("_T")

#: The pauses between tries after a broken connection: four more tries, about a minute in all.
BACKOFF_SECONDS: tuple[float, ...] = (2.0, 5.0, 15.0, 30.0)
CHUNK_BYTES = 1 << 20
#: How long the server may stay silent (connecting, answering, or between bytes) before the try counts as a
#: broken connection. A server that took the request and sent nothing was a ~100 s stall at 60 s.
READ_TIMEOUT_SECONDS = 20.0

#: Exception class names that mean the connection broke, whichever library raised them.
_TRANSIENT_NAMES = frozenset({
    "IncompleteRead", "ConnectionError", "ChunkedEncodingError", "ReadTimeout", "ConnectTimeout", "Timeout",
    "ProtocolError", "RemoteDisconnected", "ConnectionResetError", "ConnectionAbortedError", "BrokenPipeError",
    "TimeoutError", "LocalEntryNotFoundError", "ContentTooShortError", "IncompleteDownload", "ReadError",
    "RemoteProtocolError", "socket.timeout",
})
#: The same, as a separate process (the MLX runtime's own Python) writes them on its error output.
TRANSIENT_MARKERS: tuple[str, ...] = tuple(sorted(_TRANSIENT_NAMES)) + ("Connection reset", "timed out")


class DownloadInterrupted(RuntimeError):
    """The connection broke on every try: the message is the one sentence a person reads."""

    def __init__(self, name: str, cause: BaseException | None = None, *, offline: bool = False) -> None:
        super().__init__(interrupted_sentence(name, offline=offline))
        self.name = name
        self.cause = cause


class DownloadStopped(RuntimeError):
    """A person stopped the download; what it had fetched is kept for when it is started again."""

    def __init__(self, name: str) -> None:
        super().__init__(f"Stopped by you; the download of {name} continues from where it was when started again")
        self.name = name


def looks_offline(broken: DownloadInterrupted) -> bool:
    """Whether the connection never came up at all (no DNS, no route): this Mac is offline, not the server flaky."""
    import socket

    current: BaseException | None = broken.cause
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, socket.gaierror) or "Name or service not known" in str(current) \
                or "nodename nor servname" in str(current) or "offline" in str(current).lower():
            return True
        current = current.__cause__ or current.__context__
    return False


def interrupted_sentence(name: str, *, offline: bool = False) -> str:
    if offline:
        return f"{name} can't be downloaded: this Mac looks offline. It tries again by itself when the internet is back."
    return f"The download of {name} stopped part-way; it will try again."


def is_transient(exc: BaseException) -> bool:
    """Whether a failure is the connection breaking (worth trying again), through its causes."""
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, urllib.error.HTTPError):
            return current.code >= 500 or current.code in (408, 429)
        status = getattr(getattr(current, "response", None), "status_code", None)
        if isinstance(status, int) and status >= 400:
            return status >= 500 or status in (408, 429)
        names = {cls.__name__ for cls in type(current).__mro__}
        if names & _TRANSIENT_NAMES or isinstance(current, (http.client.IncompleteRead, ConnectionError, TimeoutError)):
            return True
        if isinstance(current, urllib.error.URLError):
            return True  # not an HTTP answer: the host could not be reached
        current = current.__cause__ or current.__context__
    return False


def _pause(seconds: float, should_stop: Callable[[], bool], name: str,
           sleep: Callable[[float], None] | None) -> None:
    """Wait before the next try, a second at a time, so a stop is heard during the wait too."""
    sleep = sleep or time.sleep
    waited = 0.0
    while waited < seconds:
        if should_stop():
            raise DownloadStopped(name)
        step = min(1.0, seconds - waited)
        sleep(step)
        waited += step


def with_retries(fetch: Callable[[], _T], *, name: str, should_stop: Callable[[], bool] = lambda: False,
                 backoff: tuple[float, ...] | None = None, sleep: Callable[[float], None] | None = None,
                 on_retry: Callable[[int, BaseException], None] | None = None) -> _T:
    """Run a fetch that continues by itself where it stopped, again after each broken connection."""
    pauses = BACKOFF_SECONDS if backoff is None else backoff
    for attempt in range(len(pauses) + 1):
        if should_stop():
            raise DownloadStopped(name)
        try:
            return fetch()
        except (DownloadStopped, DownloadInterrupted):
            raise
        except Exception as exc:  # sorted below: the connection retries, anything else raises
            if not is_transient(exc):
                raise
            if attempt == len(pauses):
                logger.warning("download of %s broke on every try: %r", name, exc)
                raise DownloadInterrupted(name, exc) from exc
            logger.info("download of %s broke (%r); trying again in %.0fs", name, exc, pauses[attempt])
            if on_retry is not None:
                on_retry(attempt + 1, exc)
            _pause(pauses[attempt], should_stop, name, sleep)
    raise AssertionError("unreachable")  # pragma: no cover


def _open(url: str, start: int):
    from fichero_server.core.tls import https_context

    request = urllib.request.Request(url, headers={"User-Agent": "Fichero"})
    if start:
        request.add_header("Range", f"bytes={start}-")
    context = https_context() if url.startswith("https:") else None
    return urllib.request.urlopen(request, timeout=READ_TIMEOUT_SECONDS, context=context)


def fetch_file(url: str, dest: Path, *, name: str, size: int | None = None,
               should_stop: Callable[[], bool] = lambda: False,
               on_bytes: Callable[[int, int | None], None] | None = None,
               backoff: tuple[float, ...] | None = None, sleep: Callable[[float], None] | None = None) -> Path:
    """Download `url` to `dest`, resuming after a broken connection. `size` (the record's own) is checked:
    a shorter or longer file is never kept as `dest`. Returns `dest`."""
    dest = Path(dest)
    part = dest.with_name(dest.name + ".part")
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file() and (size is None or dest.stat().st_size == size):
        return dest

    started = time.monotonic()
    logger.info("download of %s starting: %s (size %s)", name, url, megabytes(size))

    def one_try() -> None:
        have = part.stat().st_size if part.is_file() else 0
        if size is not None and have == size:
            return
        if size is not None and have > size:
            part.unlink()
            have = 0
        if on_bytes is not None:
            on_bytes(have, size)  # each try announces itself, so a silent server still shows the clock moving
        try:
            response = _open(url, have)
        except urllib.error.HTTPError as exc:
            if exc.code == 416 and have:  # asked past the end: what is here is all of it, or wrong
                if size is None or have == size:
                    return
                part.unlink()
            raise
        with response:
            status = getattr(response, "status", 200)
            mode = "ab" if have and status == 206 else "wb"  # the server ignored the range: from the start
            if mode == "wb":
                have = 0
            total = size
            if total is None:
                length = response.headers.get("Content-Length")
                total = (have + int(length)) if length and length.isdigit() else None
            with part.open(mode) as out:
                while True:
                    if should_stop():
                        raise DownloadStopped(name)
                    chunk = response.read(CHUNK_BYTES)
                    if not chunk:
                        break
                    out.write(chunk)
                    have += len(chunk)
                    if on_bytes is not None:
                        on_bytes(have, total)
            if total is not None and have < total:
                raise http.client.IncompleteRead(b"", total - have)

    with_retries(one_try, name=name, should_stop=should_stop, backoff=backoff, sleep=sleep)
    got = part.stat().st_size if part.is_file() else 0
    if size is not None and got != size:
        raise DownloadInterrupted(name)
    part.replace(dest)
    logger.info("download of %s done: %s in %.0f s", name, megabytes(got), time.monotonic() - started)
    return dest


def megabytes(count: int | None) -> str:
    return "?" if count is None else f"{count / 1_000_000:.1f} MB"


def progress_words(name: str, have: int, total: int | None, seconds_in: float | None = None) -> str:
    """"Downloading PP-OCRv6 (medium): 8.8 MB of 63.0 MB, 12 s in"; before any byte: "Downloading X, 23 s in"."""
    when = "" if seconds_in is None else f", {seconds_in:.0f} s in"
    if not have:
        return f"Downloading {name}{when}"
    return f"Downloading {name}: {megabytes(have)}" + (f" of {megabytes(total)}" if total else "") + when
