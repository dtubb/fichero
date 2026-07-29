"""Unit coverage for the pure transform / JSON / path helpers in
``fichero_server.workflows.resolver``. ``test_workflows.py`` covers a handful of
transforms (join/trim/upper/len/first/last) and json_repair/extract end-to-end;
this file exercises the remaining transforms and the path-navigation internals
directly, including edge cases.
"""

from __future__ import annotations

import pytest

from fichero_server.workflows.resolver import (
    _apply_transform,
    _extract_json,
    _get_nested,
    _parse_json,
    _parse_path,
    _parts_to_path,
)


# ===========================================================================
# _apply_transform — the transforms test_workflows.py doesn't cover
# ===========================================================================


def test_string_transforms():
    assert _apply_transform("HI", "lower") == "hi"
    assert _apply_transform(None, "str") == ""      # None -> empty string
    assert _apply_transform(42, "str") == "42"


def test_numeric_transforms_valid_and_empty():
    assert _apply_transform("5", "int") == 5
    assert _apply_transform("", "int") == 0         # falsy -> 0 default
    assert _apply_transform("2.5", "float") == 2.5
    assert _apply_transform("", "float") == 0.0


def test_numeric_transforms_raise_on_bad_input():
    # Intended fail-loud behaviour: a non-numeric value surfaces the error
    # rather than silently coercing to 0 (prefer-raise over silent fallback).
    with pytest.raises(ValueError):
        _apply_transform("abc", "int")
    with pytest.raises(ValueError):
        _apply_transform("xy", "float")
    with pytest.raises(TypeError):
        _apply_transform(5, "len")  # int has no len()


def test_dict_transforms():
    assert _apply_transform({"a": 1, "b": 2}, "keys") == ["a", "b"]
    assert _apply_transform({"a": 1, "b": 2}, "values") == [1, 2]
    assert _apply_transform("not a dict", "keys") == []
    assert _apply_transform("not a dict", "values") == []


def test_list_transforms():
    assert _apply_transform([[1, 2], [3], 4], "flatten") == [1, 2, 3, 4]
    assert _apply_transform([3, 1, 2], "sort") == [1, 2, 3]
    assert _apply_transform([1, 2, 3], "reverse") == [3, 2, 1]
    assert _apply_transform("abc", "reverse") == "cba"  # string reverse too


def test_unique_dedupes_by_string_form():
    # Documented quirk: uniqueness is keyed on str(item), so 1 and "1" collide.
    assert _apply_transform([1, 1, "1", 2], "unique") == [1, 2]


def test_join_and_unknown_transform():
    assert _apply_transform([1, None, 2], 'join(", ")') == "1, 2"  # None filtered
    assert _apply_transform("scalar", 'join(",")') == "scalar"     # non-list passthrough
    assert _apply_transform("x", "bogus_transform") == "x"          # unknown -> passthrough


# ===========================================================================
# _parse_json (repair)
# ===========================================================================


def test_parse_json_direct_and_non_string():
    assert _parse_json('{"a": 1}') == {"a": 1}
    assert _parse_json({"already": "parsed"}) == {"already": "parsed"}  # non-string passthrough


def test_parse_json_repairs():
    assert _parse_json('{"a": 1,}', repair=True) == {"a": 1}          # trailing comma
    assert _parse_json("{'a': 'b'}", repair=True) == {"a": "b"}        # single quotes
    assert _parse_json("{a: 1, b: 2}", repair=True) == {"a": 1, "b": 2}  # unquoted keys
    assert _parse_json('{"a": 1 // c\n}', repair=True) == {"a": 1}     # line comment


def test_parse_json_unrepairable_returns_original():
    assert _parse_json("{totally broken", repair=False) == "{totally broken"


# ===========================================================================
# _extract_json
# ===========================================================================


def test_extract_json_object_array_codeblock():
    assert _extract_json('prefix {"a": 1} suffix') == {"a": 1}
    assert _extract_json("see [1, 2, 3] here") == [1, 2, 3]
    assert _extract_json('```json\n{"x": 5}\n```') == {"x": 5}


def test_extract_json_none_and_non_string():
    assert _extract_json("no json here") == "no json here"
    assert _extract_json(123) == 123


# ===========================================================================
# _get_nested
# ===========================================================================


def test_get_nested_dot_and_index():
    assert _get_nested({"a": {"b": 1}}, "a.b") == 1
    assert _get_nested({"a": [10, 20]}, "a[1]") == 20


def test_get_nested_negative_index():
    assert _get_nested({"a": [1, 2, 3]}, "a[-1]") == 3
    assert _get_nested({"a": [1, 2, 3]}, "a[-9]") is None  # out of range


def test_get_nested_wildcard_and_list_key_map():
    assert _get_nested({"items": [{"t": "x"}, {"t": "y"}]}, "items[*].t") == ["x", "y"]
    # Dict-key on a list maps over items.
    assert _get_nested([{"k": 1}, {"k": 2}], "k") == [1, 2]


def test_get_nested_missing_returns_none():
    assert _get_nested({"a": 1}, "a.b.c") is None
    assert _get_nested({"a": [1]}, "a[5]") is None


# ===========================================================================
# _parse_path / _parts_to_path
# ===========================================================================


def test_parse_path_forms():
    assert _parse_path("foo.bar") == ["foo", "bar"]
    assert _parse_path("foo[0].bar") == ["foo", 0, "bar"]
    assert _parse_path("foo.bar[2][3]") == ["foo", "bar", 2, 3]
    assert _parse_path("foo[*].bar") == ["foo", "*", "bar"]
    assert _parse_path("foo[-1]") == ["foo", -1]


def test_parse_path_malformed_raises():
    # Missing closing bracket -> ValueError (fail loud on a bad path spec).
    with pytest.raises(ValueError):
        _parse_path("foo[0")


def test_parts_to_path_roundtrip():
    for path in ("foo.bar", "foo[0].bar", "foo.bar[2][3]", "foo[*].bar", "foo[-1]"):
        assert _parts_to_path(_parse_path(path)) == path
