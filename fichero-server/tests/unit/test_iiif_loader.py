"""Coverage for the pure parsing surface of ``fichero_server.loaders.iiif_loader``
(previously untested). No network: only the manifest/canvas/label parsing
helpers are exercised (``load`` / ``_download_image`` are async HTTP and are
not touched here).

Includes a regression for a fixed crash: a IIIF 3.0 canvas whose image body
has no ``service`` (direct-image case) used to raise AttributeError.
"""

from __future__ import annotations

import pytest

from fichero_server.loaders.iiif_loader import IIIFLoader


@pytest.fixture
def loader():
    return IIIFLoader(max_dimension=1000)


# ===========================================================================
# can_handle
# ===========================================================================


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://ex.org/iiif/x/manifest", True),
        ("https://ex.org/item/manifest.json", True),
        ("https://ex.org/presentation/abc", True),
        ("http://ex.org/iiif/thing", True),
        ("https://ex.org/some/page", False),   # http(s) but no IIIF marker
        ("/local/path/manifest", False),        # not http(s)
        ("ftp://ex.org/iiif/x", False),
    ],
)
def test_can_handle(loader, url, expected):
    assert loader.can_handle(url) is expected


# ===========================================================================
# _detect_version
# ===========================================================================


def test_detect_version_v3_from_context(loader):
    assert loader._detect_version({"@context": "http://iiif.io/api/presentation/3/context.json"}) == "3.0"


def test_detect_version_v3_from_items(loader):
    assert loader._detect_version({"items": []}) == "3.0"


def test_detect_version_v2_default(loader):
    assert loader._detect_version({"@context": "http://iiif.io/api/presentation/2/context.json"}) == "2.x"


def test_detect_version_context_as_list(loader):
    manifest = {"@context": ["x", "http://iiif.io/api/presentation/3/context.json"]}
    assert loader._detect_version(manifest) == "3.0"


# ===========================================================================
# _get_canvases
# ===========================================================================


def test_get_canvases_v3_items(loader):
    assert loader._get_canvases({"items": [1, 2]}) == [1, 2]


def test_get_canvases_v2_sequences(loader):
    assert loader._get_canvases({"sequences": [{"canvases": [3, 4]}]}) == [3, 4]


def test_get_canvases_none_found(loader):
    assert loader._get_canvases({"foo": 1}) == []
    assert loader._get_canvases({"sequences": [{}]}) == []  # sequence without canvases


# ===========================================================================
# _get_image_url — v3 + v2, service + direct, and the fixed no-service crash
# ===========================================================================


def _v3_canvas(body):
    return {"items": [{"items": [{"body": body}]}]}


def test_v3_service_list(loader):
    canvas = _v3_canvas({"service": [{"@id": "https://ex.org/iiif/a"}]})
    assert loader._get_image_url(canvas) == "https://ex.org/iiif/a/full/!1000,1000/0/default.jpg"


def test_v3_service_dict(loader):
    canvas = _v3_canvas({"service": {"id": "https://ex.org/iiif/b"}})
    assert loader._get_image_url(canvas) == "https://ex.org/iiif/b/full/!1000,1000/0/default.jpg"


def test_v3_direct_image_without_service_regression(loader):
    # Regression: a body with no 'service' key used to raise AttributeError
    # (service defaulted to [] then .get was called on the list). Must now fall
    # back to the direct image id.
    canvas = _v3_canvas({"id": "https://ex.org/img.jpg", "type": "Image"})
    assert loader._get_image_url(canvas) == "https://ex.org/img.jpg"


def test_v3_empty_service_list_falls_back_to_id(loader):
    canvas = _v3_canvas({"service": [], "id": "https://ex.org/d.jpg"})
    assert loader._get_image_url(canvas) == "https://ex.org/d.jpg"


def test_v2_service(loader):
    canvas = {"images": [{"resource": {"service": {"@id": "https://ex.org/iiif/v2"}}}]}
    assert loader._get_image_url(canvas) == "https://ex.org/iiif/v2/full/!1000,1000/0/default.jpg"


def test_v2_direct_resource(loader):
    canvas = {"images": [{"resource": {"@id": "https://ex.org/direct2.jpg"}}]}
    assert loader._get_image_url(canvas) == "https://ex.org/direct2.jpg"


def test_get_image_url_none_when_unrecognised(loader):
    assert loader._get_image_url({"foo": 1}) is None
    # Malformed v3 (empty items) is swallowed -> None, not a crash.
    assert loader._get_image_url({"items": []}) is None


# ===========================================================================
# _build_image_url
# ===========================================================================


def test_build_image_url_strips_trailing_slash(loader):
    assert loader._build_image_url("https://ex.org/iiif/id/") == "https://ex.org/iiif/id/full/!1000,1000/0/default.jpg"


def test_build_image_url_uses_max_dimension():
    assert IIIFLoader(max_dimension=500)._build_image_url("https://ex.org/x") == "https://ex.org/x/full/!500,500/0/default.jpg"


# ===========================================================================
# _get_label
# ===========================================================================


def test_label_plain_string(loader):
    assert loader._get_label({"label": "A Title"}) == "A Title"


def test_label_v3_prefers_english(loader):
    assert loader._get_label({"label": {"en": ["English"], "fr": ["Français"]}}) == "English"


def test_label_v3_first_available_when_no_english(loader):
    assert loader._get_label({"label": {"de": ["Deutsch"]}}) == "Deutsch"


def test_label_missing_or_empty(loader):
    assert loader._get_label({}) == ""
    assert loader._get_label({"label": {}}) == ""
