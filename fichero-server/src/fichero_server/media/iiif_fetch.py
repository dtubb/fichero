"""Fetching from IIIF servers politely: manifests, and images at the size a reader needs (#5398 slice 2).

An archive served over IIIF (the British Library's Endangered Archives Programme: millions of images)
is read by reference: Fichero keeps each canvas's Image API service, and fetches an image only when it
is needed, at the size needed (`{service}/full/!2000,2000/0/default.jpg`). The servers belong to the
archives, so every fetch here is polite:

* at most `per_host` requests in flight to one host at a time;
* a failed request is retried with exponential backoff and jitter;
* `429 Too Many Requests` and `503` are honoured: the `Retry-After` the server gives (seconds or an
  HTTP date) is waited out before the next try to that host, and the host as a whole slows down;
* a 4xx other than 408 and 429 is not retried: the request is wrong, not the moment.

Pure standard library and an injected `get`, so the same file runs inside the engine (viewing a page)
and inside a remote reading job (`remote_read/runner.py`, whose package carries it beside the runner).
"""
from __future__ import annotations

import email.utils
import random
import threading
import time
import urllib.parse
from dataclasses import dataclass, field
from typing import Callable

#: get(url, timeout) -> (status, headers (lower-case keys), body)
Getter = Callable[[str, float], tuple[int, dict[str, str], bytes]]

RETRYABLE = {408, 425, 429, 500, 502, 503, 504}


class FetchFailed(RuntimeError):
    """The server answered with an error that retrying would not fix, or retries ran out."""

    def __init__(self, url: str, status: int | None, message: str) -> None:
        super().__init__(f"{url}: {message}")
        self.url = url
        self.status = status


def image_url(service: str, *, longest: int | None = None, fmt: str = "jpg") -> str:
    """An Image API request for the whole image, scaled to fit `longest` on its longer side (or full)."""
    size = f"!{longest},{longest}" if longest else "max"
    return f"{service.rstrip('/')}/full/{size}/0/default.{fmt}"


def retry_after_seconds(value: str | None, now: float | None = None) -> float | None:
    """Seconds to wait from a Retry-After header: a number of seconds, or an HTTP date."""
    if not value:
        return None
    value = value.strip()
    if value.isdigit():
        return float(value)
    try:
        when = email.utils.parsedate_to_datetime(value).timestamp()
    except (TypeError, ValueError):
        return None
    return max(0.0, when - (time.time() if now is None else now))


@dataclass
class PoliteFetcher:
    get: Getter
    per_host: int = 2
    retries: int = 6
    base_delay: float = 1.0
    max_delay: float = 120.0
    timeout: float = 60.0
    sleep: Callable[[float], None] = time.sleep
    #: What happened, for the job's record: requests, retries, 429s, seconds waited.
    stats: dict[str, float] = field(default_factory=lambda: {"requests": 0, "retries": 0, "throttled": 0, "waited": 0.0})
    _gates: dict[str, threading.BoundedSemaphore] = field(default_factory=dict, repr=False)
    _not_before: dict[str, float] = field(default_factory=dict, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def _gate(self, host: str) -> threading.BoundedSemaphore:
        with self._lock:
            return self._gates.setdefault(host, threading.BoundedSemaphore(self.per_host))

    def _wait_for(self, host: str) -> None:
        with self._lock:
            wait = self._not_before.get(host, 0.0) - time.monotonic()
        if wait > 0:
            self.stats["waited"] += wait
            self.sleep(wait)

    def _hold_host(self, host: str, seconds: float) -> None:
        with self._lock:
            self._not_before[host] = max(self._not_before.get(host, 0.0), time.monotonic() + seconds)

    def fetch(self, url: str) -> bytes:
        host = urllib.parse.urlsplit(url).netloc
        last: tuple[int | None, str] = (None, "no attempt")
        for attempt in range(self.retries + 1):
            self._wait_for(host)
            with self._gate(host):
                self.stats["requests"] += 1
                try:
                    status, headers, body = self.get(url, self.timeout)
                except OSError as exc:  # connection reset, timeout: retried
                    status, headers, body = None, {}, b""
                    last = (None, f"{type(exc).__name__}: {exc}")
            if status is not None and 200 <= status < 300:
                return body
            if status is not None and status not in RETRYABLE:
                raise FetchFailed(url, status, f"HTTP {status}")
            if status is not None:
                last = (status, f"HTTP {status}")
            if attempt == self.retries:
                break
            self.stats["retries"] += 1
            delay = min(self.max_delay, self.base_delay * 2 ** attempt) * (0.5 + random.random() / 2)
            if status in (429, 503):
                self.stats["throttled"] += 1
                delay = max(delay, retry_after_seconds(headers.get("retry-after")) or 0.0)
                self._hold_host(host, delay)  # the whole host slows down, not only this request
            else:
                self.stats["waited"] += delay
                self.sleep(delay)
        raise FetchFailed(url, last[0], f"gave up after {self.retries + 1} tries ({last[1]})")


def urllib_get(url: str, timeout: float) -> tuple[int, dict[str, str], bytes]:
    """A `Getter` on the standard library, with a User-Agent that says who is asking."""
    import urllib.error
    import urllib.request

    request = urllib.request.Request(url, headers={"User-Agent": "Fichero (IIIF reader; +https://tubb.ca/apps/fichero)"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 -- https IIIF servers
            return response.status, {k.lower(): v for k, v in response.headers.items()}, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, {k.lower(): v for k, v in (exc.headers or {}).items()}, b""
