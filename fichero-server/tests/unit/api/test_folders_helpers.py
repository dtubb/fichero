"""Direct tests for folders.py pure helpers (#1979 Test Coverage).

The folders route module is otherwise untested (get_untested_symbols: whole
file unreached). These pure helpers decide map/geo visibility and curated-item
linking, and the descendant walk must survive malformed parent cycles. Focus is
edge cases: falsy-but-valid coordinates, partial pairs, fallback URL fields, and
cycle-safe BFS.
"""

from __future__ import annotations

from fichero_server.api.routes.folders import (
    _curated_item_has_geo,
    _curated_item_url,
    _document_has_geo,
    _folder_descendant_documents,
    _metadata_has_geo,
)
from fichero_server.models import Document


# ---------------------------------------------------------------------------
# _metadata_has_geo
# ---------------------------------------------------------------------------


def test_metadata_has_geo_none_and_non_dict_are_false() -> None:
    assert _metadata_has_geo(None) is False
    assert _metadata_has_geo("not a dict") is False
    assert _metadata_has_geo({}) is False


def test_metadata_has_geo_full_and_short_coordinate_pairs() -> None:
    assert _metadata_has_geo({"latitude": 40.0, "longitude": -3.0}) is True
    assert _metadata_has_geo({"lat": 40.0, "lon": -3.0}) is True


def test_metadata_has_geo_zero_coordinates_are_valid() -> None:
    # 0.0 is a real coordinate (Gulf of Guinea); must not be treated as absent.
    assert _metadata_has_geo({"latitude": 0, "longitude": 0}) is True
    assert _metadata_has_geo({"lat": 0.0, "lon": 0.0}) is True


def test_metadata_has_geo_partial_pair_is_false() -> None:
    assert _metadata_has_geo({"latitude": 40.0}) is False
    assert _metadata_has_geo({"longitude": -3.0}) is False
    assert _metadata_has_geo({"lat": 40.0, "lon": None}) is False


def test_metadata_has_geo_geojson_and_coordinates_keys() -> None:
    assert _metadata_has_geo({"geo": "POINT(1 2)"}) is True
    assert _metadata_has_geo({"geojson": {"type": "Point"}}) is True
    assert _metadata_has_geo({"coordinates": [1, 2]}) is True
    # Empty/falsy values under those keys do NOT count.
    assert _metadata_has_geo({"geo": "", "geojson": None, "coordinates": []}) is False


# ---------------------------------------------------------------------------
# _document_has_geo — checks metadata OR source_metadata
# ---------------------------------------------------------------------------


def test_document_has_geo_checks_both_metadata_sources() -> None:
    plain = Document(name="a.pdf")
    assert _document_has_geo(plain) is False

    in_metadata = Document(name="b.pdf", metadata={"lat": 1.0, "lon": 2.0})
    assert _document_has_geo(in_metadata) is True

    in_source = Document(name="c.pdf", source_metadata={"latitude": 1.0, "longitude": 2.0})
    assert _document_has_geo(in_source) is True


# ---------------------------------------------------------------------------
# _curated_item_url — fallback chain + type guard
# ---------------------------------------------------------------------------


def test_curated_item_url_fallback_order() -> None:
    assert _curated_item_url({"url": "u", "source_url": "s", "href": "h"}) == "u"
    assert _curated_item_url({"source_url": "s", "href": "h"}) == "s"
    assert _curated_item_url({"href": "h"}) == "h"


def test_curated_item_url_missing_empty_or_non_string_is_none() -> None:
    assert _curated_item_url({}) is None
    assert _curated_item_url({"url": ""}) is None
    assert _curated_item_url({"url": 123}) is None
    assert _curated_item_url({"url": None, "source_url": "s2"}) == "s2"


def test_curated_item_has_geo_top_level_or_nested_metadata() -> None:
    assert _curated_item_has_geo({"lat": 1.0, "lon": 2.0}) is True
    assert _curated_item_has_geo({"metadata": {"latitude": 1.0, "longitude": 2.0}}) is True
    assert _curated_item_has_geo({"name": "no geo"}) is False


# ---------------------------------------------------------------------------
# _folder_descendant_documents — BFS, dedup, cycle safety
# ---------------------------------------------------------------------------


class _StubDB:
    """Minimal db whose query(Document, parent_id=...) returns canned children."""

    def __init__(self, children_by_parent: dict[str, list[Document]]):
        self._children = children_by_parent

    def query(self, _model, parent_id=None):
        return list(self._children.get(parent_id, []))


def test_descendants_collects_full_subtree_breadth_first() -> None:
    child = Document(id="c1", name="c1")
    grandchild = Document(id="g1", name="g1")
    db = _StubDB({"root": [child], "c1": [grandchild]})
    result = _folder_descendant_documents(db, "root")
    assert {d.id for d in result} == {"c1", "g1"}


def test_descendants_survives_parent_cycle_without_infinite_loop() -> None:
    # Malformed data: a -> b -> a. The seen-set must stop the walk.
    a = Document(id="a", name="a")
    b = Document(id="b", name="b")
    db = _StubDB({"root": [a], "a": [b], "b": [a]})
    result = _folder_descendant_documents(db, "root")
    ids = [d.id for d in result]
    assert sorted(ids) == ["a", "b"]
    assert len(ids) == 2  # each visited exactly once despite the cycle


def test_descendants_empty_folder_returns_empty() -> None:
    assert _folder_descendant_documents(_StubDB({}), "root") == []
