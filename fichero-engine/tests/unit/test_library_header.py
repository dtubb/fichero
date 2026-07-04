"""Tests for the library-path transport header dependencies (#117 contract audit).

`require_library_path` / `optional_library_path` read the schema-hidden
`X-Fichero-Library-Path` header every library-scoped route depends on. The
contract: absent/empty → the required form raises HTTP 400 with a clear
message; a present value is URL-decoded (paths with spaces/slashes arrive
percent-encoded from the Swift client).
"""

from __future__ import annotations

import unicodedata
from urllib.parse import quote

import fastapi
import pytest

from fichero.api.library_header import optional_library_path, require_library_path


def _request(header_value: str | None) -> fastapi.Request:
    headers: list[tuple[bytes, bytes]] = []
    if header_value is not None:
        headers.append((b"x-fichero-library-path", header_value.encode()))
    return fastapi.Request({"type": "http", "headers": headers})


# ---------------------------------------------------------------------------
# optional_library_path
# ---------------------------------------------------------------------------


def test_optional_returns_none_when_header_absent() -> None:
    assert optional_library_path(_request(None)) is None


def test_optional_url_decodes_present_value() -> None:
    assert optional_library_path(_request("%2FUsers%2Fx%2FMy%20Lib.fichero")) == \
        "/Users/x/My Lib.fichero"


def test_optional_normalizes_unicode_path_to_nfc() -> None:
    raw = quote(unicodedata.normalize("NFD", "/tmp/Chocó.fichero"), safe="/")
    assert optional_library_path(_request(raw)) == unicodedata.normalize(
        "NFC",
        "/tmp/Chocó.fichero",
    )


def test_optional_returns_empty_string_when_header_blank() -> None:
    # Present-but-empty decodes to "" (distinct from absent -> None).
    assert optional_library_path(_request("")) == ""


# ---------------------------------------------------------------------------
# require_library_path
# ---------------------------------------------------------------------------


def test_require_returns_decoded_path() -> None:
    assert require_library_path(_request("%2Ftmp%2FLib.fichero")) == "/tmp/Lib.fichero"


def test_require_leaves_nfc_paths_unchanged() -> None:
    path = unicodedata.normalize("NFC", "/tmp/Chocó.fichero")
    assert require_library_path(_request(quote(path, safe="/"))) == path


def test_require_raises_400_when_absent() -> None:
    with pytest.raises(fastapi.HTTPException) as exc:
        require_library_path(_request(None))
    assert exc.value.status_code == 400
    assert "X-Fichero-Library-Path" in exc.value.detail


def test_require_raises_400_when_blank() -> None:
    with pytest.raises(fastapi.HTTPException) as exc:
        require_library_path(_request(""))
    assert exc.value.status_code == 400


def test_require_keeps_non_empty_unusual_values() -> None:
    # A non-empty value that isn't a real path is still returned — emptiness, not
    # validity, is what gates the 400.
    assert require_library_path(_request("0")) == "0"
