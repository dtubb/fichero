"""Coverage for geographic place-name coercion."""

from fichero_server.workflows.tools.geo_extract import _coerce_place_names


def test_coerce_place_names_accepts_json_lists_and_nested_shapes():
    assert _coerce_place_names('["Quito", " Madrid "]') == ["Quito", "Madrid"]
    assert _coerce_place_names({"places": [{"name": "Lima"}, {"place": "Cusco"}]}) == [
        "Lima", "Cusco"
    ]
    assert _coerce_place_names(["", 4, {"value": "Bogota"}]) == ["Bogota"]
