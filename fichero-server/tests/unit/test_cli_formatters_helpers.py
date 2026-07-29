"""Direct tests for cli/formatters.py private helpers (#1982 Test Coverage).

`render()` is well-tested, but the structural helpers it delegates to
(`_to_jsonable`, `_human`, `_line`, `_kv`, `_first`, `_truncate`,
`_align_columns`) had no direct coverage. They are pure string/structure
functions — test the edges: empty/None payloads, falsy-but-present values,
envelope unwrapping, column padding, and the deliberate `_truncate` overflow
behaviour.
"""

from __future__ import annotations

from pydantic import BaseModel

from fichero_server.cli import formatters as fmt


# ---------------------------------------------------------------------------
# _truncate
# ---------------------------------------------------------------------------


def test_truncate_shorter_or_equal_is_unchanged() -> None:
    assert fmt._truncate("abc", 5) == "abc"
    assert fmt._truncate("abc", 3) == "abc"  # len == width is NOT truncated
    assert fmt._truncate("", 0) == ""


def test_truncate_longer_appends_ellipsis() -> None:
    # Note: result is intentionally longer than width (width chars + "...").
    assert fmt._truncate("abcdef", 3) == "abc..."
    assert fmt._truncate("a", 0) == "..."


# ---------------------------------------------------------------------------
# _align_columns
# ---------------------------------------------------------------------------


def test_align_columns_pads_and_joins() -> None:
    assert fmt._align_columns([("a", "b")], [3, 3]) == "a   | b  "


def test_align_columns_multiple_rows() -> None:
    out = fmt._align_columns([("a", "b"), ("cc", "d")], [2, 2])
    assert out == "a  | b \ncc | d "


def test_align_columns_does_not_truncate_overlong_fields() -> None:
    # ljust never shortens; an over-width field stays intact.
    assert fmt._align_columns([("toolong", "x")], [3, 3]) == "toolong | x  "


def test_align_columns_zips_to_shortest() -> None:
    # Extra fields without a matching width are dropped (zip stops short).
    assert fmt._align_columns([("a", "b", "c")], [2]) == "a "


def test_align_columns_stringifies_non_str_fields() -> None:
    assert fmt._align_columns([(1, True)], [3, 5]) == "1   | True "


# ---------------------------------------------------------------------------
# _first — first present (non-None, non-empty) key, stringified
# ---------------------------------------------------------------------------


def test_first_returns_first_present_value() -> None:
    assert fmt._first({"id": "x"}, fmt._ID_KEYS) == "x"


def test_first_skips_none_and_empty_string() -> None:
    assert fmt._first({"id": None, "doc_id": "", "document_id": "y"}, fmt._ID_KEYS) == "y"


def test_first_treats_zero_and_false_as_present() -> None:
    # 0 / False are not None and not "" — they are real values, stringified.
    assert fmt._first({"id": 0}, fmt._ID_KEYS) == "0"
    assert fmt._first({"id": False}, fmt._ID_KEYS) == "False"


def test_first_returns_none_when_no_key_matches() -> None:
    assert fmt._first({"unrelated": "z"}, fmt._ID_KEYS) is None


# ---------------------------------------------------------------------------
# _kv
# ---------------------------------------------------------------------------


def test_kv_scalar_and_indent() -> None:
    assert fmt._kv("name", "Ada", 0) == "name: Ada"
    assert fmt._kv("name", "Ada", 2) == "    name: Ada"


def test_kv_empty_container_is_marked_empty() -> None:
    assert fmt._kv("tags", [], 0) == "tags: (empty)"
    assert fmt._kv("meta", {}, 0) == "meta: (empty)"


def test_kv_nonempty_container_nests() -> None:
    assert fmt._kv("tags", ["a"], 0) == "tags:\n  - a"


# ---------------------------------------------------------------------------
# _line
# ---------------------------------------------------------------------------


def test_line_non_dict_item() -> None:
    assert fmt._line("hello", 0) == "- hello"


def test_line_dict_combines_id_label_and_detail() -> None:
    item = {"id": "e1", "canonical_name": "Madrid", "entity_type": "place"}
    assert fmt._line(item, 0) == "- e1  Madrid  [place]"


def test_line_dict_without_known_keys_is_placeholder() -> None:
    assert fmt._line({"unknown": "v"}, 0) == "- (item)"


# ---------------------------------------------------------------------------
# _human
# ---------------------------------------------------------------------------


def test_human_none_and_empty_list() -> None:
    assert fmt._human(None) == "(no data)"
    assert fmt._human([]) == "(empty)"


def test_human_scalar_and_list_of_scalars() -> None:
    assert fmt._human(42) == "42"
    assert fmt._human(["a", "b"]) == "- a\n- b"


def test_human_unwraps_envelope_key() -> None:
    out = fmt._human({"documents": [{"id": "d1", "filename": "a.pdf"}]})
    assert out.startswith("documents (1):")
    assert "- d1" in out


def test_human_empty_envelope_is_marked_empty() -> None:
    assert fmt._human({"entities": []}) == "entities: (empty)"


# ---------------------------------------------------------------------------
# _to_jsonable
# ---------------------------------------------------------------------------


class _Model(BaseModel):
    a: int
    b: str


def test_to_jsonable_unwraps_models_recursively() -> None:
    assert fmt._to_jsonable(_Model(a=1, b="x")) == {"a": 1, "b": "x"}
    nested = {"top": [_Model(a=2, b="y")]}
    assert fmt._to_jsonable(nested) == {"top": [{"a": 2, "b": "y"}]}


def test_to_jsonable_passes_through_plain_values() -> None:
    assert fmt._to_jsonable("plain") == "plain"
    assert fmt._to_jsonable([1, {"k": 2}]) == [1, {"k": 2}]
