"""
Unit tests for the renderer system

Tests for:
- RenderContext creation
- RendererRegistry behavior
- Type-specific renderers
- Fallback rendering
"""

import pytest
import tempfile
import json
from pathlib import Path
from fichero.library.renderers import (
    BaseRenderer,
    RenderContext,
    RenderedOutput,
    FallbackRenderer,
    ImageRenderer,
    TextRenderer,
    JsonRenderer,
    RendererRegistry
)


class TestRenderContext:
    """Test RenderContext dataclass"""

    def test_create_render_context(self):
        """Test creating a basic RenderContext"""
        ctx = RenderContext(
            item_id="test123",
            step_index=0,
            step_name="prepare_images",
            tool_name="prepare_images",
            file_path=Path("/path/to/image.jpg"),
            file_type="image"
        )

        assert ctx.item_id == "test123"
        assert ctx.step_index == 0
        assert ctx.step_name == "prepare_images"
        assert ctx.tool_name == "prepare_images"
        assert ctx.file_path == Path("/path/to/image.jpg")
        assert ctx.file_type == "image"

    def test_render_context_with_metadata(self):
        """Test RenderContext with manifest data"""
        manifest_entry = {
            "input_file": "input.jpg",
            "output_file": "output.jpg",
            "processing_time": 1.23
        }

        ctx = RenderContext(
            item_id="test123",
            step_index=0,
            step_name="prepare_images",
            tool_name="prepare_images",
            file_path=Path("/path/to/image.jpg"),
            file_type="image",
            manifest_entry=manifest_entry,
            show_metadata=True,
            show_content=True
        )

        assert ctx.manifest_entry == manifest_entry
        assert ctx.show_metadata is True
        assert ctx.show_content is True

    def test_render_context_to_dict(self):
        """Test converting RenderContext to dictionary"""
        ctx = RenderContext(
            item_id="test123",
            step_index=0,
            step_name="prepare_images",
            tool_name="prepare_images",
            file_path=Path("/path/to/image.jpg"),
            file_type="image"
        )

        ctx_dict = ctx.to_dict()
        assert ctx_dict['item_id'] == "test123"
        assert ctx_dict['step_index'] == 0
        assert ctx_dict['file_type'] == "image"


class TestRenderedOutput:
    """Test RenderedOutput dataclass"""

    def test_create_rendered_output(self):
        """Test creating a RenderedOutput"""
        output = RenderedOutput(
            html="<h1>Test</h1>",
            text="Test",
            title="Test Step",
            description="Test Description"
        )

        assert output.html == "<h1>Test</h1>"
        assert output.text == "Test"
        assert output.title == "Test Step"
        assert output.description == "Test Description"
        assert not output.is_error
        assert output.has_content

    def test_rendered_output_with_error(self):
        """Test RenderedOutput with error"""
        output = RenderedOutput(
            error="Something went wrong"
        )

        assert output.is_error
        assert not output.has_content
        assert output.error == "Something went wrong"


class TestFallbackRenderer:
    """Test the fallback renderer"""

    def test_fallback_renderer_text_cli(self):
        """Test fallback rendering of text in CLI mode"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("Hello, world!")
            temp_path = Path(f.name)

        try:
            ctx = RenderContext(
                item_id="test123",
                step_index=0,
                step_name="test_tool",
                tool_name="test_tool",
                file_path=temp_path,
                file_type="text",
                file_content="Hello, world!"
            )

            renderer = FallbackRenderer()
            output = renderer.render_cli(ctx)

            assert not output.is_error
            assert output.has_content
            assert "Hello, world!" in output.text
            assert "test_tool" in output.text

        finally:
            temp_path.unlink()

    def test_fallback_renderer_json_html(self):
        """Test fallback rendering of JSON in HTML mode"""
        test_data = {"key": "value", "number": 42}

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(test_data, f)
            temp_path = Path(f.name)

        try:
            ctx = RenderContext(
                item_id="test123",
                step_index=0,
                step_name="test_tool",
                tool_name="test_tool",
                file_path=temp_path,
                file_type="json",
                file_content=test_data
            )

            renderer = FallbackRenderer()
            output = renderer.render_html(ctx)

            assert not output.is_error
            assert output.has_content
            assert '"key": "value"' in output.html or '"key":"value"' in output.html
            assert "42" in output.html

        finally:
            temp_path.unlink()


class TestImageRenderer:
    """Test ImageRenderer base class"""

    def test_image_renderer_cli(self):
        """Test image rendering in CLI mode"""
        # Create a fake image file (we won't actually load it)
        with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as f:
            temp_path = Path(f.name)

        try:
            ctx = RenderContext(
                item_id="test123",
                step_index=0,
                step_name="prepare_images",
                tool_name="prepare_images",
                file_path=temp_path,
                file_type="image"
            )

            renderer = ImageRenderer()
            output = renderer.render_cli(ctx)

            assert not output.is_error
            assert output.has_content
            assert "prepare_images" in output.text
            assert str(temp_path) in output.text

        finally:
            temp_path.unlink()


class TestTextRenderer:
    """Test TextRenderer base class"""

    def test_text_renderer_cli(self):
        """Test text rendering in CLI mode"""
        test_content = "Line 1\nLine 2\nLine 3"

        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write(test_content)
            temp_path = Path(f.name)

        try:
            ctx = RenderContext(
                item_id="test123",
                step_index=0,
                step_name="transcribe_qwen_max",
                tool_name="transcribe_qwen_max",
                file_path=temp_path,
                file_type="text",
                file_content=test_content
            )

            renderer = TextRenderer()
            output = renderer.render_cli(ctx)

            assert not output.is_error
            assert output.has_content
            assert "Line 1" in output.text
            assert "Line 2" in output.text
            assert "3" in output.text  # Line count

        finally:
            temp_path.unlink()

    def test_text_renderer_truncates_long_content(self):
        """Test that text renderer truncates very long content in CLI"""
        # Create content with more than 50 lines
        lines = [f"Line {i}" for i in range(100)]
        test_content = "\n".join(lines)

        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write(test_content)
            temp_path = Path(f.name)

        try:
            ctx = RenderContext(
                item_id="test123",
                step_index=0,
                step_name="test_tool",
                tool_name="test_tool",
                file_path=temp_path,
                file_type="text",
                file_content=test_content
            )

            renderer = TextRenderer()
            output = renderer.render_cli(ctx)

            assert not output.is_error
            # Should show first 50 lines
            assert "Line 0" in output.text
            assert "Line 49" in output.text
            # Should indicate truncation
            assert "more lines" in output.text or "..." in output.text

        finally:
            temp_path.unlink()


class TestJsonRenderer:
    """Test JsonRenderer base class"""

    def test_json_renderer_cli(self):
        """Test JSON rendering in CLI mode"""
        test_data = {
            "items": [
                {"id": 1, "name": "Item 1"},
                {"id": 2, "name": "Item 2"}
            ],
            "count": 2
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(test_data, f)
            temp_path = Path(f.name)

        try:
            ctx = RenderContext(
                item_id="test123",
                step_index=0,
                step_name="llm_process",
                tool_name="llm_process",
                file_path=temp_path,
                file_type="json",
                file_content=test_data
            )

            renderer = JsonRenderer()
            output = renderer.render_cli(ctx)

            assert not output.is_error
            assert output.has_content
            assert "Item 1" in output.text
            assert "Item 2" in output.text

        finally:
            temp_path.unlink()

    def test_json_renderer_provides_editable_json(self):
        """Test that JSON renderer provides editable JSON"""
        test_data = {"key": "value"}

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(test_data, f)
            temp_path = Path(f.name)

        try:
            ctx = RenderContext(
                item_id="test123",
                step_index=0,
                step_name="test_tool",
                tool_name="test_tool",
                file_path=temp_path,
                file_type="json",
                file_content=test_data
            )

            renderer = JsonRenderer()
            editable = renderer.get_editable_json(ctx)

            assert editable == test_data

        finally:
            temp_path.unlink()


class TestRendererRegistry:
    """Test RendererRegistry singleton and registration system"""

    def test_registry_singleton(self):
        """Test that RendererRegistry is a singleton"""
        registry1 = RendererRegistry()
        registry2 = RendererRegistry()
        assert registry1 is registry2

    def test_registry_has_type_renderers(self):
        """Test that registry initializes with type renderers"""
        registry = RendererRegistry()
        types = registry.list_registered_types()

        assert 'image' in types
        assert 'text' in types
        assert 'json' in types
        assert 'document' in types
        assert 'folder' in types
        assert 'svg' in types

    def test_register_custom_renderer(self):
        """Test registering a custom renderer"""
        class CustomRenderer(BaseRenderer):
            def render_html(self, ctx):
                return RenderedOutput(html="<p>Custom</p>")

            def render_cli(self, ctx):
                return RenderedOutput(text="Custom")

        RendererRegistry.register('custom_tool', CustomRenderer)

        renderer = RendererRegistry.get_renderer('custom_tool')
        assert isinstance(renderer, CustomRenderer)

    def test_get_renderer_for_file_type(self):
        """Test getting renderer by file type"""
        renderer = RendererRegistry.get_renderer_for_file_type('image')
        assert isinstance(renderer, ImageRenderer)

        renderer = RendererRegistry.get_renderer_for_file_type('text')
        assert isinstance(renderer, TextRenderer)

        renderer = RendererRegistry.get_renderer_for_file_type('json')
        assert isinstance(renderer, JsonRenderer)

    def test_get_renderer_for_step_fallback_chain(self):
        """Test the fallback chain for get_renderer_for_step"""
        # Test with unknown tool but known file type
        renderer = RendererRegistry.get_renderer_for_step(
            tool_name='unknown_tool',
            file_type='image'
        )
        assert isinstance(renderer, ImageRenderer)

        # Test with unknown tool and file path
        renderer = RendererRegistry.get_renderer_for_step(
            tool_name='unknown_tool',
            file_path=Path('test.jpg')
        )
        assert isinstance(renderer, ImageRenderer)

        # Test complete fallback to FallbackRenderer
        renderer = RendererRegistry.get_renderer_for_step(
            tool_name='unknown_tool'
        )
        assert isinstance(renderer, FallbackRenderer)

    def test_guess_file_type_from_extension(self):
        """Test file type guessing from extension"""
        assert RendererRegistry._guess_file_type_from_extension(Path('test.jpg')) == 'image'
        assert RendererRegistry._guess_file_type_from_extension(Path('test.png')) == 'image'
        assert RendererRegistry._guess_file_type_from_extension(Path('test.txt')) == 'text'
        assert RendererRegistry._guess_file_type_from_extension(Path('test.json')) == 'json'
        assert RendererRegistry._guess_file_type_from_extension(Path('test.docx')) == 'document'
        assert RendererRegistry._guess_file_type_from_extension(Path('test.svg')) == 'svg'
        assert RendererRegistry._guess_file_type_from_extension(Path('test.unknown')) is None


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
