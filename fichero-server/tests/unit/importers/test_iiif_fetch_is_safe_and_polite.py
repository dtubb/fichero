"""Every IIIF fetch is safe (`iiif.fetch.*`, Step 1.1, #6921)."""
from __future__ import annotations

import io
import json
import socket
import types
import urllib.request
from pathlib import Path

import pytest

from fichero_server.media import iiif_engine, iiif_fetch

FIXTURE = Path(__file__).parents[2] / "fixtures" / "iiif" / "manifest_tiny.json"


@pytest.fixture(autouse=True)
def _dns(monkeypatch):  # no network: a literal resolves to itself, gone.example to nothing, other names to a public address
    def resolve(host, port, *args, **kwargs):
        if host == "gone.example":
            raise socket.gaierror("no such host")
        return [(0, 0, 0, "", ("93.184.216.34" if host.endswith(".example") else host, port))]
    monkeypatch.setattr(socket, "getaddrinfo", resolve)


def _once(responses, log):
    def get(url, timeout):
        log.append(url)
        return responses.pop(0)
    return get


def test_the_fixture_manifest_names_a_loopback_image_service():
    service = json.loads(FIXTURE.read_text())["items"][0]["items"][0]["items"][0]["body"]["service"][0]["id"]
    assert service == "https://127.0.0.1/img/1" and iiif_engine.refusal(service).startswith("refused:")


@pytest.mark.parametrize("url", ["https://[::]/x", "https://100.64.0.9/x", "https://10.0.0.5/x", "https://127.0.0.1/x",
                                 "https://gone.example/x", "http://iiif.archive.example/m", "https://u:p@iiif.archive.example/m"])
def test_an_address_that_is_not_public_https_is_refused_before_any_request(url, monkeypatch):
    log: list[str] = []
    monkeypatch.setattr(iiif_fetch, "urllib_get_once", _once([(200, {}, b"x")], log))
    with pytest.raises(iiif_fetch.FetchFailed, match="refused"):
        iiif_engine.safe_get(url, 5)
    assert log == [] and iiif_engine.refusal("https://iiif.archive.example/x") == ""


def test_a_redirect_to_plain_http_or_loopback_is_refused(monkeypatch):
    for target in ("http://iiif.archive.example/elsewhere", "https://127.0.0.1/secret"):
        log: list[str] = []
        monkeypatch.setattr(iiif_fetch, "urllib_get_once", _once([(302, {"location": target}, b"")], log))
        with pytest.raises(iiif_fetch.FetchFailed, match="refused"):
            iiif_engine.safe_get("https://iiif.archive.example/m", 5)
        assert log == ["https://iiif.archive.example/m"]  # the first hop only


def test_a_body_over_the_cap_is_refused(monkeypatch):
    class Big(io.BytesIO):
        status, headers = 200, {}

    monkeypatch.setattr(urllib.request, "build_opener", lambda *a: types.SimpleNamespace(open=lambda r, timeout: Big(b"x" * 2048)))
    monkeypatch.setattr(iiif_fetch, "MAX_BODY", 1024)
    with pytest.raises(iiif_fetch.FetchFailed, match="larger than"):
        iiif_fetch.urllib_get_once("https://iiif.archive.example/big", 5)

