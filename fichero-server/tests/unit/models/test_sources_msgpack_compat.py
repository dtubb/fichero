"""Regression guard for #2235.

Document dicts that enter workflow state / LangGraph checkpoints must contain
only JSON-safe primitives — no fichero_server.models enum objects.  LangGraph warns
(and future versions will block under LANGGRAPH_STRICT_MSGPACK=true) when
DocType / Status / SourceAuthority cross the msgpack boundary as raw Python
enum objects.

Fix: model_dump(mode="json") in every source tool that serialises a Document
for state.  These tests ensure the fix holds and serve as a living regression
guard against future model_dump() call-sites.
"""

import enum

from fichero_server.models import Document, DocType, FileType, SourceAuthority, Status


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_document(**overrides) -> Document:
    """Build a Document with all enum-typed fields explicitly set."""
    kwargs = dict(
        name="test-doc",
        path="/tmp/test.pdf",
        doc_type=DocType.file,
        file_type=FileType.pdf,
        status=Status.pending,
        source_authority=SourceAuthority.primary,
    )
    kwargs.update(overrides)
    return Document(**kwargs)


def _find_enum_values(obj, path: str = "root") -> list[str]:
    """Return paths of any Python enum instances found recursively in obj."""
    found: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            found.extend(_find_enum_values(v, f"{path}.{k}"))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            found.extend(_find_enum_values(v, f"{path}[{i}]"))
    elif isinstance(obj, enum.Enum):
        found.append(f"{path}={obj!r}")
    return found


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------


class TestDocumentMsgpackCompat:
    """Ensure source-tool document dicts contain primitives, not enum objects."""

    def test_plain_model_dump_keeps_enum_objects(self):
        """Baseline: model_dump() WITHOUT mode='json' keeps Enum members.

        This confirms the behaviour that caused #2235 and makes the fix's
        value obvious — if Pydantic ever changes this default, the test will
        fail and we should revisit whether mode='json' is still needed.
        """
        doc = _make_document()
        d = doc.model_dump()
        enum_paths = _find_enum_values(d)
        assert enum_paths, (
            "Expected model_dump() to return enum members (DocType, Status, "
            "SourceAuthority) but none were found.  Pydantic may have changed "
            "its default serialisation — verify that mode='json' is still "
            "required, and update this test accordingly."
        )

    def test_model_dump_mode_json_produces_only_primitives(self):
        """Fix: model_dump(mode='json') produces JSON-safe primitives only."""
        doc = _make_document()
        d = doc.model_dump(mode="json")
        enum_paths = _find_enum_values(d)
        assert not enum_paths, (
            f"Enum objects found in model_dump(mode='json') output: {enum_paths}"
        )

    def test_mode_json_string_values_are_correct(self):
        """String values match the enum's .value after mode='json' serialisation."""
        doc = _make_document(
            doc_type=DocType.folder,
            status=Status.completed,
            source_authority=SourceAuthority.secondary,
        )
        d = doc.model_dump(mode="json")
        assert d["doc_type"] == "folder"
        assert d["status"] == "completed"
        assert d["source_authority"] == "secondary"

    def test_list_comprehension_pattern_used_in_source_tools(self):
        """List-comprehension model_dump(mode='json') pattern used in sources.py."""
        docs = [
            _make_document(doc_type=DocType.page, status=Status.pending),
            _make_document(doc_type=DocType.file, status=Status.completed),
            _make_document(doc_type=DocType.folder, status=Status.failed),
        ]
        doc_data = [d.model_dump(mode="json") for d in docs]

        for d in doc_data:
            enum_paths = _find_enum_values(d)
            assert not enum_paths, f"Enum in serialised doc: {enum_paths}"

        assert doc_data[0]["doc_type"] == "page"
        assert doc_data[1]["status"] == "completed"
        assert doc_data[2]["doc_type"] == "folder"

    def test_search_tool_pattern_with_extra_fields(self):
        """Search-tool pattern: model_dump(mode='json') then add extra keys."""
        doc = _make_document()
        doc_dict = doc.model_dump(mode="json")
        doc_dict["search_score"] = 0.92
        doc_dict["highlights"] = None
        enum_paths = _find_enum_values(doc_dict)
        assert not enum_paths, f"Enum found after adding extra keys: {enum_paths}"
