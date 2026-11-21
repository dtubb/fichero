"""Every IIIF fetch is safe (`iiif.fetch.*`, Step 1.1, #6921). No network: fakes answer and record what was asked."""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path

import pytest

from fichero_server.media import iiif_engine, iiif_fetch
from fichero_server.media.iiif_fetch import FetchFailed

FIXTURE = Path(__file__).parents[2] / "fixtures" / "iiif" / "manifest_tiny.json"


def _once(responses, log):
    def get(url, timeout):
        log.append(url)
        return responses.pop(0) if isinstance(responses, list) else responses(url)
    return get


def test_the_fixture_manifest_names_a_loopback_image_service():
    service = json.loads(FIXTURE.read_text())["items"][0]["items"][0]["items"][0]["body"]["service"][0]["id"]
    assert service == "https://127.0.0.1/img/1" and iiif_engine.refusal(service).startswith("refused:")


def test_a_loopback_address_is_refused_before_any_request(monkeypatch):
    log: list[str] = []
    monkeypatch.setattr(iiif_fetch, "urllib_get_once", _once([(200, {}, b"x")], log))
    with pytest.raises(FetchFailed, match="refused"):
        iiif_engine.safe_get("https://127.0.0.1/img/1/full/max/0/default.jpg", 5)
    assert log == []


def test_plain_http_and_credentials_are_refused(monkeypatch):
    log: list[str] = []
    monkeypatch.setattr(iiif_fetch, "urllib_get_once", _once([(200, {}, b"x")], log))
    for url in ("http://iiif.archive.example/m", "https://user:pw@iiif.archive.example/m"):
        with pytest.raises(FetchFailed, match="refused"):
            iiif_engine.safe_get(url, 5)
    assert log == []


def test_a_redirect_to_plain_http_or_loopback_is_refused(monkeypatch):
    for target in ("http://iiif.archive.example/elsewhere", "https://127.0.0.1/secret"):
        log: list[str] = []
        monkeypatch.setattr(iiif_fetch, "urllib_get_once", _once([(302, {"location": target}, b"")], log))
        with pytest.raises(FetchFailed, match="refused"):
            iiif_engine.safe_get("https://iiif.archive.example/m", 5)
        assert log == ["https://iiif.archive.example/m"]  # the first hop only


def test_a_redirect_to_a_public_https_address_is_followed(monkeypatch):
    log: list[str] = []
    answers = {"https://iiif.archive.example/a": (301, {"location": "/b"}, b""),
               "https://iiif.archive.example/b": (200, {}, b"ok")}
    monkeypatch.setattr(iiif_fetch, "urllib_get_once", _once(lambda url: answers[url], log))
    assert iiif_engine.safe_get("https://iiif.archive.example/a", 5)[2] == b"ok"
    assert log == list(answers)


def test_a_body_over_the_cap_is_refused(monkeypatch):
    class Big:
        status = 200
        headers: dict = {}

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self, n):
            return b"x" * n

    class Opener:
        def open(self, request, timeout):
            return Big()

    monkeypatch.setattr(urllib.request, "build_opener", lambda *a: Opener())
    monkeypatch.setattr(iiif_fetch, "MAX_BODY", 1024)
    with pytest.raises(FetchFailed, match="larger than"):
        iiif_fetch.urllib_get_once("https://iiif.archive.example/big", 5)


def test_the_engine_fetcher_is_one_object_with_four_per_host():
    assert iiif_engine.engine_fetcher() is iiif_engine.engine_fetcher() and iiif_engine.engine_fetcher().per_host == 4

