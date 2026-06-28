"""Geo extraction + geocoding tests (#2266)."""

from __future__ import annotations

from fichero import geo
from fichero.workflows.tools.geo_extract import _coerce_place_names
from fichero.api.routes.documents import _points_from_metadata


# --- geocoding ---------------------------------------------------------------

def test_geocode_gazetteer_hit_and_normalization():
    p = geo.geocode("Popayán")
    assert p is not None
    assert abs(p.lat - 2.4448) < 0.01 and abs(p.lon + 76.6147) < 0.01
    # accent-folded + cached → same object
    assert geo.geocode("popayan") is p


def test_geocode_miss_and_empty():
    assert geo.geocode("Nowhere-on-Earth-12345") is None
    assert geo.geocode("") is None
    assert geo.geocode(None) is None  # type: ignore[arg-type]


def test_geocode_offline_does_not_hit_network():
    # online=False must never reach Nominatim, even for unknown names.
    assert geo.geocode("Some Unmapped Hamlet", online=False) is None


def test_geocode_places_skips_unresolved_and_dedupes():
    out = geo.geocode_places(["Quito", "Madrid", "Quito", "???unknown???"])
    assert set(out) == {"Quito", "Madrid"}
    for point in out.values():
        assert -90 <= point.lat <= 90 and -180 <= point.lon <= 180


# --- place-name coercion from messy LLM output -------------------------------

def test_coerce_place_names_flat_list():
    assert _coerce_place_names(["Quito", " Madrid ", ""]) == ["Quito", "Madrid"]


def test_coerce_place_names_dicts_and_wrapped():
    assert _coerce_place_names([{"name": "Lima"}, {"place": "Cusco"}]) == ["Lima", "Cusco"]
    assert _coerce_place_names({"places": ["Bogotá"]}) == ["Bogotá"]


def test_coerce_place_names_json_string():
    assert _coerce_place_names('["Cali", "Cartagena"]') == ["Cali", "Cartagena"]


# --- endpoint metadata extraction --------------------------------------------

def test_points_from_metadata_geo_points_list():
    pts = _points_from_metadata(
        {"geo_points": [{"place_name": "Quito", "lat": -0.18, "lon": -78.46}]}
    )
    assert len(pts) == 1
    assert pts[0].place_name == "Quito" and pts[0].source == "metadata"


def test_points_from_metadata_legacy_flat():
    pts = _points_from_metadata({"latitude": 40.4, "longitude": -3.7}, place_default="Doc")
    assert len(pts) == 1 and pts[0].place_name == "Doc"


def test_points_from_metadata_ignores_garbage():
    assert _points_from_metadata(None) == []
    assert _points_from_metadata({"geo_points": "not-a-list"}) == []
    assert _points_from_metadata({"geo_points": [{"lat": 1}]}) == []  # missing lon
