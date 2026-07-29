"""Unit coverage for the pure IIIF-JSON extraction helpers in
``fichero_server.importers.iiif_import``. The existing ``test_iiif_import.py`` covers a
few end-to-end import flows; this file exercises the ~16 small parsing helpers
(v2/v3 labels, W3C selectors, entity typing, id sanitisation) directly. No
filesystem/network except ``_local_path``/``_safe_external_id`` string work.
"""

from __future__ import annotations

from pathlib import Path


from fichero_server.importers.iiif_import import (
    _body_text,
    _canvas_text,
    _entity_from_annotation,
    _entity_type,
    _json_id,
    _json_type,
    _label_text,
    _language,
    _local_path,
    _metadata_dict,
    _motivations,
    _nav_date,
    _safe_external_id,
    _selector,
    _selector_end,
    _selector_exact,
    _selector_start,
    _text_from_pages,
)

BASE = Path("/base")


# ===========================================================================
# _json_type / _json_id
# ===========================================================================


def test_json_type():
    assert _json_type({"type": "sc:Canvas"}) == "sc:Canvas"
    assert _json_type({"@type": ["http://iiif.io/Manifest"]}) == "Manifest"  # slash-stripped
    assert _json_type({}) is None


def test_json_id():
    assert _json_id({"id": "a"}) == "a"
    assert _json_id({"@id": "b"}) == "b"
    assert _json_id(None) is None
    assert _json_id({}) is None


# ===========================================================================
# _label_text / _metadata_dict
# ===========================================================================


def test_label_text_forms():
    assert _label_text({"label": "Title"}) == "Title"
    assert _label_text({"label": {"en": ["English"], "fr": ["Fr"]}}) == "English"
    assert _label_text({"label": {"de": ["Deutsch"]}}) == "Deutsch"  # first fallback
    assert _label_text({}) is None


def test_metadata_dict_pairs_incl_language_maps():
    obj = {"metadata": [
        {"label": "Author", "value": "Doe"},
        {"label": {"en": ["Year"]}, "value": {"en": ["1999"]}},
        "not-a-dict-row",
    ]}
    assert _metadata_dict(obj) == {"Author": "Doe", "Year": "1999"}


# ===========================================================================
# _nav_date / _language
# ===========================================================================


def test_nav_date_sources():
    assert _nav_date({"navDate": "2020"}, {}) == "2020"
    assert _nav_date({"nav_date": "2019"}, {}) == "2019"
    assert _nav_date({}, {"Date": "1888"}) == "1888"
    assert _nav_date({}, {}) is None


def test_language():
    assert _language({"language": ["es", "en"]}) == "es"
    assert _language({"language": "fr"}) == "fr"
    assert _language({}) is None


# ===========================================================================
# _body_text
# ===========================================================================


def test_body_text_variants():
    assert _body_text("hi") == "hi"
    assert _body_text(["a", "", {"value": "b"}]) == "a\nb"  # joins non-empty
    assert _body_text({"value": "V"}) == "V"
    assert _body_text({"exact": "E"}) == "E"
    assert _body_text({"label": {"en": ["L"]}}) == "L"  # nested label map
    assert _body_text(42) is None


# ===========================================================================
# _motivations
# ===========================================================================


def test_motivations():
    assert _motivations({"motivation": "painting"}) == {"painting"}
    assert _motivations({"motivatedBy": ["a", "b"]}) == {"a", "b"}
    assert _motivations({}) == set()


# ===========================================================================
# _selector + start/end/exact
# ===========================================================================


def test_selector_prefers_text_quote_or_position():
    sel = _selector({"selector": [{"type": "FragmentSelector"}, {"type": "TextQuoteSelector", "exact": "q"}]})
    assert sel["type"] == "TextQuoteSelector"


def test_selector_single_dict_and_list_target():
    assert _selector({"selector": {"start": "3"}}) == {"start": "3"}
    assert _selector([{"selector": {"exact": "x"}}]) == {"exact": "x"}
    assert _selector("not a dict") is None


def test_selector_start_end():
    assert _selector_start({"start": "5"}) == 5
    assert _selector_start({"start": 5}) == 5
    assert _selector_start({"start": "-1"}) is None  # non-digit rejected
    assert _selector_start(None) is None
    assert _selector_end({"end": "12"}) == 12
    assert _selector_end({}) is None


def test_selector_exact():
    assert _selector_exact({"exact": "hello"}) == "hello"
    assert _selector_exact({}) is None
    assert _selector_exact(None) is None


# ===========================================================================
# _local_path / _safe_external_id
# ===========================================================================


def test_local_path():
    assert _local_path("file:///a/b.jpg", BASE) == "/a/b.jpg"
    assert _local_path("http://x/y", BASE) == "http://x/y"  # remote left as-is
    assert _local_path("img.jpg", BASE) == str(BASE / "img.jpg")  # relative -> under base
    assert _local_path("/abs/x.jpg", BASE) == "/abs/x.jpg"
    assert _local_path(None, BASE) is None


def test_safe_external_id():
    assert _safe_external_id("https://ex.org/iiif/abc") == "https__ex.org__iiif__abc"
    assert _safe_external_id("file:///a/b.jpg") == "a__b.jpg"  # scheme stripped, leading _ trimmed


# ===========================================================================
# _entity_type
# ===========================================================================


def test_entity_type_mapping():
    assert _entity_type({"dc:type": "Location"}) == "location"
    assert _entity_type({"entity_type": ["Person"]}) == "person"  # list -> first
    assert _entity_type({"dc:type": "Zzz"}) == "other"  # unknown -> other
    assert _entity_type({}) == "other"  # default


# ===========================================================================
# _canvas_text / _text_from_pages
# ===========================================================================


def test_canvas_text_finds_supplementing_body():
    canvas = {"items": [{"items": [{"motivation": "supplementing", "body": {"value": "the transcript"}}]}]}
    assert _canvas_text(canvas) == "the transcript"


def test_canvas_text_none_without_supplementing():
    canvas = {"items": [{"items": [{"motivation": "painting", "body": {"value": "x"}}]}]}
    assert _canvas_text(canvas) is None


def test_text_from_pages():
    assert _text_from_pages([{"items": [{"motivation": ["supplementing"], "body": "T"}]}]) == "T"


# ===========================================================================
# _entity_from_annotation
# ===========================================================================


def test_entity_from_annotation_descends_into_source():
    ann = {
        "id": "ann-1",
        "target": {"selector": {"type": "TextQuoteSelector", "exact": "San Pablo"}},
        "body": {
            "type": "SpecificResource",
            "source": {"id": "ent-1", "value": "San Pablo", "dc:type": "Location"},
        },
    }
    entity = _entity_from_annotation(ann, canvas_external_id="canvas-1")
    assert entity["canonical_name"] == "San Pablo"
    assert entity["entity_type"] == "location"
    assert entity["external_id"] == "ent-1"
    assert entity["metadata"]["canvas_external_id"] == "canvas-1"
    # Documented: aliases is always [] (canonical_name == text, so the alias
    # condition can never fire).
    assert entity["aliases"] == []


def test_entity_from_annotation_skips_without_text():
    # A plain text-quote highlight with no name/value is not an entity.
    ann = {"id": "ann-2", "body": {"type": "TextualBody"}}
    assert _entity_from_annotation(ann, canvas_external_id="c") is None
