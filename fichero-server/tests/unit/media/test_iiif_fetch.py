"""Fetching from IIIF servers politely (#5398 slice 2): the archives' servers are not ours."""
from __future__ import annotations

import threading
import time

import pytest

from fichero_server.media.iiif_fetch import FetchFailed, PoliteFetcher, image_url, retry_after_seconds


def test_an_image_is_asked_for_at_the_size_the_reader_needs():
    """WHY: a full-size archive image can be 50 MB; a reader needs about 2,000 px, and the Image API
    scales it on the server, so only that crosses the network."""
    assert image_url("https://iiif.example/img/1/", longest=2000) == "https://iiif.example/img/1/full/!2000,2000/0/default.jpg"
    assert image_url("https://iiif.example/img/1") == "https://iiif.example/img/1/full/max/0/default.jpg"


def test_a_429_storm_is_waited_out_as_the_server_asks():
    """WHY: a server that says 429 with Retry-After is asking us to wait that long. Ignoring it is how a
    harvester gets an archive's server blocked for everyone; the fetch must wait and then succeed."""
    answers = [(429, {"retry-after": "7"}, b"")] * 4 + [(200, {}, b"image")]
    slept: list[float] = []
    fetcher = PoliteFetcher(get=lambda url, timeout: answers.pop(0), sleep=slept.append, base_delay=0.01)
    t0 = time.monotonic()
    assert fetcher.fetch("https://bl.example/iiif/p1/full/!2000,2000/0/default.jpg") == b"image"
    assert fetcher.stats["throttled"] == 4 and fetcher.stats["requests"] == 5
    assert sum(slept) >= 4 * 7 - 1 and time.monotonic() - t0 < 5  # waited (in the fake clock) as asked


def test_a_request_that_is_wrong_is_not_repeated():
    """WHY: a 404 or 403 is not a busy server; retrying it six times is six wasted requests to an
    archive. It fails at once, naming the status."""
    calls = []
    fetcher = PoliteFetcher(get=lambda url, timeout: calls.append(url) or (404, {}, b""), sleep=lambda s: None)
    with pytest.raises(FetchFailed) as failed:
        fetcher.fetch("https://bl.example/missing")
    assert failed.value.status == 404 and len(calls) == 1


def test_it_gives_up_after_its_retries_and_says_how():
    fetcher = PoliteFetcher(get=lambda url, timeout: (503, {}, b""), retries=3, sleep=lambda s: None, base_delay=0.0)
    with pytest.raises(FetchFailed, match="gave up after 4 tries"):
        fetcher.fetch("https://bl.example/busy")


def test_no_more_than_the_cap_are_in_flight_to_one_host():
    """WHY: a reading job runs many threads; the per-host cap is what keeps them from becoming a flood
    on one archive's server."""
    in_flight, peak, lock = [0], [0], threading.Lock()

    def get(url, timeout):
        with lock:
            in_flight[0] += 1
            peak[0] = max(peak[0], in_flight[0])
        time.sleep(0.01)
        with lock:
            in_flight[0] -= 1
        return 200, {}, b"x"

    fetcher = PoliteFetcher(get=get, per_host=2)
    threads = [threading.Thread(target=fetcher.fetch, args=(f"https://bl.example/{i}",)) for i in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert peak[0] == 2


def test_retry_after_may_be_a_date():
    assert retry_after_seconds("Wed, 21 Oct 2015 07:28:00 GMT", now=1445412470.0) == pytest.approx(10.0)
    assert retry_after_seconds("not a date") is None
