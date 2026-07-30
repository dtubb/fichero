"""#4329 — Convert renditions: model-generated markup, sanitized + typed.

The `convert` tool sends the page image to a vision model which GENERATES the
Markdown/HTML/SVG rendition. Before anything is saved (and later rendered in
WebKit) the output is sanitized and validated:

  * whole-output code fences are stripped;
  * html/svg lose `<script>` blocks, inline `on*=` handlers, `javascript:` URLs;
  * svg must be a well-formed `<svg>` XML document — malformed output FAILS the
    file loudly instead of persisting an unrenderable artifact;
  * the saved artifact is stamped `data={"target_format": ...}` so the preview
    picks the right renderer, and carries run provenance (provider/model).

The model is mocked — assertions cover validity, artifact typing, and
renderability, not exact markup (the model owns the markup).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from fichero_server.workflows.tools.convert import sanitize_converted_markup


VALID_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
    '<rect x="10" y="10" width="80" height="30" fill="#eee"/>'
    '<text x="12" y="30">Hello</text></svg>'
)


# ---------------------------------------------------------------------------
# A. sanitize_converted_markup — pure logic
# ---------------------------------------------------------------------------

class TestSanitizeConvertedMarkup:

    def test_strips_whole_output_code_fence(self):
        fenced = f"```svg\n{VALID_SVG}\n```"
        assert sanitize_converted_markup(fenced, "svg") == VALID_SVG

    def test_markdown_keeps_internal_fences(self):
        md = "# Title\n\n```python\nprint('hi')\n```\n\nAfter."
        assert sanitize_converted_markup(md, "markdown") == md

    def test_html_strips_script_blocks(self):
        html = "<html><body><p>ok</p><script>alert(1)</script></body></html>"
        out = sanitize_converted_markup(html, "html")
        assert "<script" not in out.lower()
        assert "<p>ok</p>" in out

    def test_html_strips_inline_event_handlers(self):
        html = '<div onclick="steal()" class="x">ok</div>'
        out = sanitize_converted_markup(html, "html")
        assert "onclick" not in out.lower()
        assert 'class="x"' in out

    def test_html_neutralizes_javascript_urls(self):
        html = "<a href=\"javascript:alert(1)\">x</a>"
        out = sanitize_converted_markup(html, "html")
        assert "javascript:" not in out.lower()

    def test_svg_scripts_stripped_and_still_well_formed(self):
        svg = VALID_SVG.replace(
            "</svg>", "<script>alert(1)</script></svg>"
        )
        out = sanitize_converted_markup(svg, "svg")
        assert "<script" not in out.lower()

    def test_malformed_svg_raises(self):
        with pytest.raises(ValueError, match="well-formed"):
            sanitize_converted_markup("<svg><rect></svg>", "svg")

    def test_non_svg_output_for_svg_target_raises(self):
        with pytest.raises(ValueError, match="no <svg> root"):
            sanitize_converted_markup("Sorry, I cannot convert this.", "svg")


# ---------------------------------------------------------------------------
# B. End-to-end: mocked model → sanitized, typed, renderable artifact
# ---------------------------------------------------------------------------

def _make_png(path):
    from PIL import Image

    Image.new("RGB", (16, 16), (255, 255, 255)).save(str(path), format="PNG")


@pytest.fixture
def temp_library(tmp_path, monkeypatch):
    monkeypatch.setenv("FICHERO_SKIP_DEFAULT_WORKFLOWS", "1")
    from fichero_server.db.manager import db_manager

    lib = tmp_path / "Convert.fichero"
    lib.mkdir(parents=True, exist_ok=True)
    yield str(lib), db_manager
    try:
        db_manager.close_all()
    except Exception:
        pass


def _llm_config():
    from fichero_server.llm import LLMConfig

    return LLMConfig(provider="openai", model="gpt-4o")


async def _run_convert(library_path, db, png, *, target_format, model_output):
    from fichero_server.models import Document, DocType, FileType
    from fichero_server.workflows.tools.convert import convert

    doc = Document(
        name=png.name,
        doc_type=DocType.file,
        file_type=FileType.image,
        path=str(png),
    )
    db.save(doc)

    with patch("fichero_server.llm.vision", new=AsyncMock(return_value=model_output)):
        result = await convert(
            inputs={
                "files": [str(png)],
                "documents": [doc.model_dump()],
                "target_format": target_format,
            },
            state={"library_path": library_path, "task_id": "run-1"},
            llm_config=_llm_config(),
        )
    return doc, result


class TestConvertRenditionArtifacts:

    @pytest.mark.asyncio
    async def test_svg_rendition_sanitized_stamped_and_renderable(
        self, temp_library, tmp_path
    ):
        import xml.etree.ElementTree as ET

        from fichero_server.models import Artifact

        library_path, db_manager = temp_library
        db = db_manager.get_database(library_path)
        png = tmp_path / "page.png"
        _make_png(png)

        fenced_with_script = "```svg\n" + VALID_SVG.replace(
            "</svg>", "<script>alert(1)</script></svg>"
        ) + "\n```"
        doc, result = await _run_convert(
            library_path, db, png, target_format="svg", model_output=fenced_with_script
        )

        assert not result.get("error")
        arts = db.query(Artifact, document_id=doc.id, artifact_type="conversion")
        assert len(arts) == 1
        art = arts[0]
        # Typed for the preview renderer + provenance fields.
        assert art.data == {"target_format": "svg"}
        assert art.provider == "openai" and art.model == "gpt-4o"
        assert art.run_id == "run-1"
        # Renderable: fence gone, scripts gone, well-formed XML.
        assert art.content.startswith("<svg")
        assert "```" not in art.content and "<script" not in art.content.lower()
        ET.fromstring(art.content)

    @pytest.mark.asyncio
    async def test_markdown_rendition_stamped(self, temp_library, tmp_path):
        from fichero_server.models import Artifact

        library_path, db_manager = temp_library
        db = db_manager.get_database(library_path)
        png = tmp_path / "page.png"
        _make_png(png)

        doc, result = await _run_convert(
            library_path,
            db,
            png,
            target_format="markdown",
            model_output="```markdown\n# Deed of Sale\n\nBody text.\n```",
        )

        assert not result.get("error")
        arts = db.query(Artifact, document_id=doc.id, artifact_type="conversion")
        assert len(arts) == 1
        assert arts[0].data == {"target_format": "markdown"}
        assert arts[0].content == "# Deed of Sale\n\nBody text."

    @pytest.mark.asyncio
    async def test_html_rendition_scripts_stripped(self, temp_library, tmp_path):
        from fichero_server.models import Artifact

        library_path, db_manager = temp_library
        db = db_manager.get_database(library_path)
        png = tmp_path / "page.png"
        _make_png(png)

        doc, result = await _run_convert(
            library_path,
            db,
            png,
            target_format="html",
            model_output=(
                "<html><body onload=\"x()\"><h1>Deed</h1>"
                "<script>bad()</script></body></html>"
            ),
        )

        assert not result.get("error")
        arts = db.query(Artifact, document_id=doc.id, artifact_type="conversion")
        assert len(arts) == 1
        assert arts[0].data == {"target_format": "html"}
        assert "<script" not in arts[0].content.lower()
        assert "onload" not in arts[0].content.lower()
        assert "<h1>Deed</h1>" in arts[0].content

    @pytest.mark.asyncio
    async def test_malformed_svg_fails_loud_no_artifact(self, temp_library, tmp_path):
        from fichero_server.models import Artifact

        library_path, db_manager = temp_library
        db = db_manager.get_database(library_path)
        png = tmp_path / "page.png"
        _make_png(png)

        doc, result = await _run_convert(
            library_path,
            db,
            png,
            target_format="svg",
            model_output="<svg><rect></svg>",
        )

        assert result.get("error"), "malformed SVG must surface a per-file error"
        assert db.query(Artifact, document_id=doc.id, artifact_type="conversion") == []
