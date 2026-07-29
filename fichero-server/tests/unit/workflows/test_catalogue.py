"""
Tests for the catalogue tool.

Guards the parts of the nine-section catalogue pipeline that don't need a
running LLM or DuckDB:
  - Prompt construction (language + schema substitution)
  - Markdown rendering of the nine sections (empty-section skip behaviour)
  - Per-section artifact extraction (one readable artifact per populated section)
  - Container document resolution (folder / common parent / fallbacks)
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from fichero_server.workflows.tools.catalogue import (
    _build_prompt,
    _iter_section_artifacts,
    _render_markdown,
    _resolve_container_doc,
    _resolve_write_target,
    _strip_narrative_header,
)


class TestStripNarrativeHeader:
    """Small models stick a leading title on the catalogue narrative
    despite the prompt saying 'no headers'. Belt-and-braces strip (#828)."""

    def test_strips_bold_catalogue_entry(self):
        text = "**Catalogue Entry**\n\nThis document is a narrative…"
        assert _strip_narrative_header(text) == "This document is a narrative…"

    def test_strips_plain_catalogue_entry_colon(self):
        text = "Catalogue Entry:\n\nThis document records…"
        assert _strip_narrative_header(text) == "This document records…"

    def test_strips_summary_label(self):
        text = "Summary:\nThe folder contains…"
        assert _strip_narrative_header(text) == "The folder contains…"

    def test_strips_markdown_h1(self):
        text = "# Catalogue Entry\n\nBody starts here."
        assert _strip_narrative_header(text) == "Body starts here."

    def test_passthrough_when_no_header(self):
        text = "This document is a narrative by David Sánchez Juliao."
        assert _strip_narrative_header(text) == text

    def test_passthrough_empty(self):
        assert _strip_narrative_header("") == ""

    def test_strips_spanish_resumen_label(self):
        text = "Resumen:\nEste documento describe…"
        assert _strip_narrative_header(text) == "Este documento describe…"

    def test_only_strips_one_leading_block(self):
        # Inline **bold** later in the body must NOT be stripped.
        text = "**Catalogue Entry**\n\nBody with **bold** word."
        assert _strip_narrative_header(text) == "Body with **bold** word."


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

class TestBuildPrompt:
    def test_default_language_is_spanish(self):
        prompt = _build_prompt("Spanish")
        assert "Spanish" in prompt
        assert "nine-section" not in prompt  # prompt describes sections by name, not count

    def test_english_substitution(self):
        prompt = _build_prompt("English")
        assert "English" in prompt
        assert "Spanish" not in prompt.split("\n\n")[0]

    def test_prompt_asks_for_narrative_paragraph(self):
        prompt = _build_prompt("English")
        # New prompt is a single archival paragraph, not a JSON schema
        assert "paragraph" in prompt.lower()
        assert "no headings" in prompt.lower() or "no bullet" in prompt.lower()


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------

class TestRenderMarkdown:
    def test_empty_data_returns_empty_string(self):
        assert _render_markdown({}) == ""

    def test_skips_sections_with_no_items(self):
        data = {"summary": "A summary."}
        rendered = _render_markdown(data)
        assert "## Summary" in rendered
        assert "## People" not in rendered
        assert "## Rivers" not in rendered

    def test_table_renders_all_rows(self):
        data = {
            "people": [
                {"name": "Alice", "context": "Role A"},
                {"name": "Bob", "context": "Role B"},
            ]
        }
        rendered = _render_markdown(data)
        assert "## People" in rendered
        assert "Alice" in rendered and "Bob" in rendered
        assert "| Name | Context |" in rendered

    def test_alt_spellings_list_flattens_with_commas(self):
        data = {
            "rivers": [
                {
                    "name": "Río Condoto",
                    "alternative_spellings": ["Conduto", "Condoto"],
                    "context": "flood site",
                }
            ]
        }
        rendered = _render_markdown(data)
        assert "Conduto, Condoto" in rendered

    def test_pipe_in_content_is_escaped(self):
        data = {"events": [{"event": "a|b", "context": "x"}]}
        rendered = _render_markdown(data)
        assert "a\\|b" in rendered

    def test_newlines_in_content_are_collapsed(self):
        data = {"events": [{"event": "line1\nline2", "context": ""}]}
        rendered = _render_markdown(data)
        # Markdown tables can't contain real newlines; must be single-line rows.
        lines = [line for line in rendered.splitlines() if "line1" in line]
        assert lines and all("\n" not in line for line in lines)


# ---------------------------------------------------------------------------
# Per-section artifact extraction
# ---------------------------------------------------------------------------

class TestIterSectionArtifacts:
    def test_only_populated_sections_emit(self):
        data = {"summary": "A summary.", "people": []}
        artifacts = list(_iter_section_artifacts(data))
        types = [t for t, _ in artifacts]
        assert "summary" in types
        assert "people" not in types  # empty list filtered out

    def test_keywords_list_renders_as_semicolon_joined(self):
        data = {"keywords": ["kw1", "kw2", "kw3"]}
        (atype, payload), = list(_iter_section_artifacts(data))
        assert atype == "keywords"
        assert payload["content"] == "kw1; kw2; kw3"
        assert payload["data"] == {"keywords": ["kw1", "kw2", "kw3"]}

    def test_people_row_has_primary_and_context(self):
        data = {
            "people": [
                {"name": "Alice", "context": "Lead investigator"},
            ]
        }
        (atype, payload), = list(_iter_section_artifacts(data))
        assert atype == "people"
        assert "Alice" in payload["content"]
        assert "Lead investigator" in payload["content"]
        assert payload["data"] == {"items": data["people"]}

    def test_dates_orders_normalized_first(self):
        data = {
            "dates": [
                {
                    "date": "Feb 28, 1925",
                    "date_normalized": "1925-02-28",
                    "context": "Dispatch",
                }
            ]
        }
        (_, payload), = list(_iter_section_artifacts(data))
        # The primary field for dates is the normalized form
        assert payload["content"].startswith("1925-02-28")

    def test_rivers_alt_spellings_flattened_in_content(self):
        data = {
            "rivers": [
                {
                    "name": "Río Condoto",
                    "alternative_spellings": ["Conduto", "Fondo"],
                    "context": "main channel",
                }
            ]
        }
        (_, payload), = list(_iter_section_artifacts(data))
        assert "Conduto, Fondo" in payload["content"]

    def test_all_nine_section_types_emit_expected_artifact_types(self):
        data = {
            "summary": "s",
            "keywords": ["k"],
            "people": [{"name": "n"}],
            "dates": [{"date_normalized": "2020-01-01"}],
            "legal_references": [{"name": "n"}],
            "rivers": [{"name": "n"}],
            "events": [{"event": "e"}],
            "mines": [{"name": "n"}],
            "properties": [{"name": "n"}],
        }
        types = [t for t, _ in _iter_section_artifacts(data)]
        assert types == [
            "summary",
            "keywords",
            "people",
            "dates",
            "legal_references",
            "rivers",
            "events",
            "mines",
            "properties",
        ]


# ---------------------------------------------------------------------------
# Container resolution
# ---------------------------------------------------------------------------

class _FakeDoc:
    def __init__(
        self,
        id: str,
        doc_type,
        parent_id: str | None = None,
        name: str = "n",
        file_type=None,
    ):
        self.id = id
        self.doc_type = doc_type
        self.parent_id = parent_id
        self.name = name
        self.file_type = file_type


class TestResolveContainerDoc:
    def _patch_db(self, docs_by_id: dict):
        """Return a patch context that makes db_manager.get_database resolve
        a synthetic DB whose .get() returns the requested doc."""
        db = MagicMock()
        db.get.side_effect = lambda _cls, did: docs_by_id.get(did)
        return patch(
            "fichero_server.workflows.tools.catalogue.db_manager.get_database",
            return_value=db,
        )

    def test_returns_none_without_library_or_selection(self):
        assert _resolve_container_doc([], "") is None
        assert _resolve_container_doc(["x"], "") is None
        assert _resolve_container_doc([], "/tmp") is None

    def test_single_folder_selected_is_the_container(self):
        from fichero_server.models import DocType
        folder = _FakeDoc("F", DocType.folder)
        with self._patch_db({"F": folder}):
            result = _resolve_container_doc(["F"], "/tmp")
        assert result is folder

    def test_single_pdf_file_selected_is_itself(self):
        from fichero_server.models import DocType, FileType
        pdf = _FakeDoc("pdf", DocType.file, file_type=FileType.pdf)
        with self._patch_db({"pdf": pdf}):
            result = _resolve_container_doc(["pdf"], "/tmp")
        assert result is pdf

    def test_common_parent_wins_when_all_files_share_a_parent(self):
        from fichero_server.models import DocType
        parent = _FakeDoc("P", DocType.folder)
        f1 = _FakeDoc("f1", DocType.file, parent_id="P")
        f2 = _FakeDoc("f2", DocType.file, parent_id="P")
        with self._patch_db({"P": parent, "f1": f1, "f2": f2}):
            result = _resolve_container_doc(["f1", "f2"], "/tmp")
        assert result is parent

    def test_page_child_resolves_to_parent_pdf(self):
        from fichero_server.models import DocType, FileType
        pdf = _FakeDoc("pdf", DocType.file, file_type=FileType.pdf)
        page = _FakeDoc("p1", DocType.page, parent_id="pdf")
        with self._patch_db({"pdf": pdf, "p1": page}):
            result = _resolve_container_doc(["p1"], "/tmp")
        assert result is pdf

    def test_fallback_to_first_folder_when_parents_differ(self):
        from fichero_server.models import DocType
        folder = _FakeDoc("F", DocType.folder)
        f1 = _FakeDoc("f1", DocType.file, parent_id="A")
        f2 = _FakeDoc("f2", DocType.file, parent_id="B")
        with self._patch_db({"F": folder, "f1": f1, "f2": f2}):
            # The presence of a folder in selection should take precedence
            # when no common parent exists.
            result = _resolve_container_doc(["F", "f1", "f2"], "/tmp")
        assert result is folder

    def test_falls_back_to_first_doc_when_no_shared_parent(self):
        """Multiple files without a shared parent fall back to the first doc."""
        from fichero_server.models import DocType
        f1 = _FakeDoc("f1", DocType.file, parent_id=None)
        f2 = _FakeDoc("f2", DocType.file, parent_id=None)
        with self._patch_db({"f1": f1, "f2": f2}):
            result = _resolve_container_doc(["f1", "f2"], "/tmp")
        assert result is f1


class TestResolveWriteTarget:
    """`_resolve_write_target` adds a fallback over `_resolve_container_doc`
    so single-file selections (md/txt/jpg etc) still get a write target —
    catalogue + KG writes attach to the file itself instead of being
    silently discarded (#1087, #1105)."""

    def _patch_db(self, docs_by_id: dict):
        db = MagicMock()
        db.get.side_effect = lambda _cls, did: docs_by_id.get(did)
        return patch(
            "fichero_server.workflows.tools.catalogue.db_manager.get_database",
            return_value=db,
        )

    def test_prefers_container_when_resolvable(self):
        from fichero_server.models import DocType
        folder = _FakeDoc("F", DocType.folder)
        with self._patch_db({"F": folder}):
            assert _resolve_write_target(["F"], "/tmp") is folder

    def test_falls_back_to_single_file_when_no_container(self):
        from fichero_server.models import DocType
        f1 = _FakeDoc("f1", DocType.file, parent_id=None)
        with self._patch_db({"f1": f1}):
            assert _resolve_write_target(["f1"], "/tmp") is f1

    def test_falls_back_to_first_doc_for_multi_file_no_container(self):
        from fichero_server.models import DocType
        f1 = _FakeDoc("f1", DocType.file, parent_id=None)
        f2 = _FakeDoc("f2", DocType.file, parent_id=None)
        with self._patch_db({"f1": f1, "f2": f2}):
            # _resolve_container_doc returns None (no shared folder); the
            # write target falls back to the first valid selected doc.
            assert _resolve_write_target(["f1", "f2"], "/tmp") is f1

    def test_returns_none_without_library_or_selection(self):
        assert _resolve_write_target([], "") is None
        assert _resolve_write_target([], "/tmp") is None
        assert _resolve_write_target(["x"], "") is None

    def test_returns_none_when_no_doc_loads(self):
        with self._patch_db({}):
            # selection refers to a doc id we can't load; nothing to write to.
            assert _resolve_write_target(["missing"], "/tmp") is None
