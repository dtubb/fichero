"""
Type-Specific Renderers - Base classes for different file types

Provides specialized rendering logic for:
- Images (prepare_images, rotate, crop, enhance, etc.)
- Text (transcription outputs)
- JSON (catalog data, metadata)
- Documents (Word, Excel outputs)
- SVG files
- Folders (group-level operations)
"""

import logging
import json
from pathlib import Path
from typing import Dict, Any, Optional
from PIL import Image

from .base_renderer import BaseRenderer, RenderContext, RenderedOutput

logger = logging.getLogger(__name__)


class ImageRenderer(BaseRenderer):
    """
    Base class for image processing tool renderers.

    Provides common image handling functionality like:
    - Loading images
    - Generating thumbnails
    - Displaying image metadata (dimensions, format, etc.)
    - Creating image galleries
    """

    def get_image_metadata(self, image_path: Path) -> Dict[str, Any]:
        """
        Extract metadata from an image file.

        Args:
            image_path: Path to image file

        Returns:
            Dictionary of image metadata
        """
        try:
            with Image.open(image_path) as img:
                return {
                    'width': img.width,
                    'height': img.height,
                    'format': img.format,
                    'mode': img.mode,
                    'size_bytes': image_path.stat().st_size,
                    'size_mb': round(image_path.stat().st_size / (1024 * 1024), 2)
                }
        except Exception as e:
            self.logger.error(f"Error reading image metadata: {e}")
            return {}

    def render_html(self, context: RenderContext) -> RenderedOutput:
        """Default HTML rendering for images with interactive editor toolbar"""
        # Use image editor with toolbar for GUI display
        if context.interactive and context.show_content:
            from .html_templates_image_editor import get_image_editor
            html = get_image_editor(
                image_path=context.file_path,
                title=context.step_name,
                use_base64=True,  # Use base64 for security and compatibility
                crop_box=None  # No crop box for general images
            )

            # Declare toolbar commands for image viewing
            # These will be dynamically registered in OutputView when this content is displayed
            toolbar_commands = [
                {
                    'id': 'rotate_left',
                    'label': 'Rotate Left',
                    'icon': 'resources/icons/toolbar/rotate.left@10x.png',
                    'js_function': 'rotateLeft',  # JavaScript function in image editor
                    'shortcut': 'Cmd+L',
                    'description': 'Rotate image 90° counter-clockwise',
                    'toolbar_position': 'left'
                },
                {
                    'id': 'rotate_right',
                    'label': 'Rotate Right',
                    'icon': 'resources/icons/toolbar/rotate.right@10x.png',
                    'js_function': 'rotateRight',
                    'shortcut': 'Cmd+R',
                    'description': 'Rotate image 90° clockwise',
                    'toolbar_position': 'left'
                },
                {
                    'id': 'crop',
                    'label': 'Crop',
                    'icon': 'resources/icons/toolbar/crop@10x.png',
                    'js_function': 'activateTool',
                    'js_args': ['crop'],  # Pass 'crop' as argument
                    'shortcut': 'Cmd+K',
                    'description': 'Crop image',
                    'toolbar_position': 'left'
                },
                {
                    'id': 'reset',
                    'label': 'Reset',
                    'icon': 'resources/icons/toolbar/arrow.up.left.and.arrow.down.right@10x.png',
                    'js_function': 'resetTransforms',  # Reset all transformations
                    'shortcut': 'Cmd+Shift+R',
                    'description': 'Reset image to original state',
                    'toolbar_position': 'left'
                }
            ]

            # Get filename for description
            is_url = isinstance(context.file_path, str) and context.file_path.startswith(('http://', 'https://'))
            filename = context.file_path.split('/')[-1] if is_url else context.file_path.name

            return RenderedOutput(
                html=html,
                title=context.step_name,
                description=f'Image: {filename}',
                toolbar_commands=toolbar_commands  # Renderer declares its toolbar needs
            )

        # Fallback: simple HTML for non-interactive contexts
        html_parts = []

        # Title
        html_parts.append(f'<h2>{context.step_name}</h2>')

        # Image
        if context.show_content:
            # Check if file_path is a URL or local file
            is_url = isinstance(context.file_path, str) and context.file_path.startswith(('http://', 'https://'))
            img_src = context.file_path if is_url else f'file://{context.file_path}'

            html_parts.append(f'<div class="image-container">')
            html_parts.append(f'<img src="{img_src}" style="max-width: 100%; height: auto;" />')
            html_parts.append('</div>')

        # Metadata
        if context.show_metadata:
            # Only get image metadata for local files (not URLs)
            is_url = isinstance(context.file_path, str) and context.file_path.startswith(('http://', 'https://'))
            if not is_url:
                metadata = self.get_image_metadata(context.file_path)
                html_parts.append('<div class="metadata">')
                html_parts.append('<h3>Image Info</h3>')
                html_parts.append('<table>')
                for key, value in metadata.items():
                    html_parts.append(f'<tr><th>{key}</th><td>{value}</td></tr>')
                html_parts.append('</table>')
                html_parts.append('</div>')

            # Manifest data
            if context.manifest_entry:
                html_parts.append('<h3>Processing Info</h3>')
                html_parts.append('<pre>')
                html_parts.append(json.dumps(context.manifest_entry, indent=2))
                html_parts.append('</pre>')

        # Get filename for description
        is_url = isinstance(context.file_path, str) and context.file_path.startswith(('http://', 'https://'))
        filename = context.file_path.split('/')[-1] if is_url else context.file_path.name

        return RenderedOutput(
            html='\n'.join(html_parts),
            title=context.step_name,
            description=f'Image: {filename}'
        )

    def render_cli(self, context: RenderContext) -> RenderedOutput:
        """Default CLI rendering for images"""
        text_parts = []

        # Title
        text_parts.append(f'Step {context.step_index}: {context.step_name}')
        text_parts.append('=' * 60)
        text_parts.append('')

        # Image metadata
        metadata = self.get_image_metadata(context.file_path)
        text_parts.append('Image Info:')
        for key, value in metadata.items():
            text_parts.append(f'  {key}: {value}')

        # File path
        text_parts.append(f'  path: {context.file_path}')

        # Processing info
        if context.manifest_entry:
            text_parts.append('')
            text_parts.append('Processing Info:')
            text_parts.append(json.dumps(context.manifest_entry, indent=2))

        return RenderedOutput(
            text='\n'.join(text_parts),
            title=context.step_name,
            description=f'Image: {context.file_path.name}'
        )


class TextRenderer(BaseRenderer):
    """
    Base class for text processing tool renderers.

    Handles transcription outputs and other text files.
    """

    def render_html(self, context: RenderContext) -> RenderedOutput:
        """Default HTML rendering for text"""
        html_parts = []

        # Title
        html_parts.append(f'<h2>{context.step_name}</h2>')

        # Content
        if context.show_content and context.file_content:
            html_parts.append('<div class="text-content">')
            html_parts.append('<pre style="white-space: pre-wrap; font-family: monospace;">')
            html_parts.append(context.file_content)
            html_parts.append('</pre>')
            html_parts.append('</div>')

        # Metadata
        if context.show_metadata:
            file_size = context.file_path.stat().st_size
            line_count = len(context.file_content.split('\n')) if context.file_content else 0
            char_count = len(context.file_content) if context.file_content else 0

            html_parts.append('<div class="metadata">')
            html_parts.append('<h3>Text Info</h3>')
            html_parts.append('<table>')
            html_parts.append(f'<tr><th>Lines</th><td>{line_count}</td></tr>')
            html_parts.append(f'<tr><th>Characters</th><td>{char_count}</td></tr>')
            html_parts.append(f'<tr><th>Size</th><td>{file_size} bytes</td></tr>')
            html_parts.append('</table>')
            html_parts.append('</div>')

            # Manifest
            if context.manifest_entry:
                html_parts.append('<h3>Processing Info</h3>')
                html_parts.append('<pre>')
                html_parts.append(json.dumps(context.manifest_entry, indent=2))
                html_parts.append('</pre>')

        return RenderedOutput(
            html='\n'.join(html_parts),
            title=context.step_name,
            description=f'Text: {context.file_path.name}'
        )

    def render_cli(self, context: RenderContext) -> RenderedOutput:
        """Default CLI rendering for text"""
        text_parts = []

        # Title
        text_parts.append(f'Step {context.step_index}: {context.step_name}')
        text_parts.append('=' * 60)
        text_parts.append('')

        # Content (with line limit for CLI)
        if context.show_content and context.file_content:
            lines = context.file_content.split('\n')
            max_lines = 50  # Show first 50 lines in CLI

            text_parts.append('Content:')
            text_parts.append('-' * 60)
            text_parts.extend(lines[:max_lines])

            if len(lines) > max_lines:
                text_parts.append('')
                text_parts.append(f'... ({len(lines) - max_lines} more lines)')

        # Metadata
        if context.show_metadata:
            file_size = context.file_path.stat().st_size
            line_count = len(context.file_content.split('\n')) if context.file_content else 0
            char_count = len(context.file_content) if context.file_content else 0

            text_parts.append('')
            text_parts.append('Text Info:')
            text_parts.append(f'  Lines: {line_count}')
            text_parts.append(f'  Characters: {char_count}')
            text_parts.append(f'  Size: {file_size} bytes')
            text_parts.append(f'  Path: {context.file_path}')

        return RenderedOutput(
            text='\n'.join(text_parts),
            title=context.step_name,
            description=f'Text: {context.file_path.name}'
        )


class JsonRenderer(BaseRenderer):
    """
    Base class for JSON data renderers.

    Handles catalog data, metadata files, and other JSON outputs.
    """

    def render_html(self, context: RenderContext) -> RenderedOutput:
        """Default HTML rendering for JSON"""
        html_parts = []

        # Title
        html_parts.append(f'<h2>{context.step_name}</h2>')

        # Content
        if context.show_content and context.file_content:
            html_parts.append('<div class="json-content">')
            html_parts.append('<pre style="background-color: #f5f5f5; padding: 10px; border-radius: 5px;">')
            html_parts.append(json.dumps(context.file_content, indent=2, ensure_ascii=False))
            html_parts.append('</pre>')
            html_parts.append('</div>')

        # Metadata
        if context.show_metadata:
            file_size = context.file_path.stat().st_size

            html_parts.append('<div class="metadata">')
            html_parts.append('<h3>JSON Info</h3>')
            html_parts.append('<table>')
            html_parts.append(f'<tr><th>Size</th><td>{file_size} bytes</td></tr>')

            if isinstance(context.file_content, list):
                html_parts.append(f'<tr><th>Items</th><td>{len(context.file_content)}</td></tr>')
            elif isinstance(context.file_content, dict):
                html_parts.append(f'<tr><th>Keys</th><td>{len(context.file_content)}</td></tr>')

            html_parts.append('</table>')
            html_parts.append('</div>')

        return RenderedOutput(
            html='\n'.join(html_parts),
            title=context.step_name,
            description=f'JSON: {context.file_path.name}'
        )

    def render_cli(self, context: RenderContext) -> RenderedOutput:
        """Default CLI rendering for JSON"""
        text_parts = []

        # Title
        text_parts.append(f'Step {context.step_index}: {context.step_name}')
        text_parts.append('=' * 60)
        text_parts.append('')

        # Content
        if context.show_content and context.file_content:
            text_parts.append('Content:')
            text_parts.append('-' * 60)
            text_parts.append(json.dumps(context.file_content, indent=2, ensure_ascii=False))

        # Metadata
        if context.show_metadata:
            file_size = context.file_path.stat().st_size

            text_parts.append('')
            text_parts.append('JSON Info:')
            text_parts.append(f'  Size: {file_size} bytes')

            if isinstance(context.file_content, list):
                text_parts.append(f'  Items: {len(context.file_content)}')
            elif isinstance(context.file_content, dict):
                text_parts.append(f'  Keys: {len(context.file_content)}')

            text_parts.append(f'  Path: {context.file_path}')

        return RenderedOutput(
            text='\n'.join(text_parts),
            title=context.step_name,
            description=f'JSON: {context.file_path.name}'
        )

    def get_editable_json(self, context: RenderContext) -> Optional[Dict[str, Any]]:
        """JSON files are directly editable"""
        return context.file_content


class DocumentRenderer(BaseRenderer):
    """
    Base class for document file renderers.

    Handles Word documents, Excel files, and other document outputs.
    """

    def render_html(self, context: RenderContext) -> RenderedOutput:
        """Default HTML rendering for documents"""
        html_parts = []

        # Title
        html_parts.append(f'<h2>{context.step_name}</h2>')

        # Document info
        html_parts.append('<div class="document-info">')
        file_size = context.file_path.stat().st_size
        file_ext = context.file_path.suffix

        html_parts.append('<h3>Document Info</h3>')
        html_parts.append('<table>')
        html_parts.append(f'<tr><th>Type</th><td>{file_ext}</td></tr>')
        html_parts.append(f'<tr><th>Size</th><td>{round(file_size / 1024, 2)} KB</td></tr>')
        html_parts.append(f'<tr><th>Path</th><td>{context.file_path}</td></tr>')
        html_parts.append('</table>')
        html_parts.append('</div>')

        # Download link
        html_parts.append('<div class="actions">')
        html_parts.append(f'<a href="file://{context.file_path}">Open Document</a>')
        html_parts.append('</div>')

        # Manifest
        if context.manifest_entry:
            html_parts.append('<div class="metadata">')
            html_parts.append('<h3>Processing Info</h3>')
            html_parts.append('<pre>')
            html_parts.append(json.dumps(context.manifest_entry, indent=2))
            html_parts.append('</pre>')
            html_parts.append('</div>')

        return RenderedOutput(
            html='\n'.join(html_parts),
            title=context.step_name,
            description=f'Document: {context.file_path.name}'
        )

    def render_cli(self, context: RenderContext) -> RenderedOutput:
        """Default CLI rendering for documents"""
        text_parts = []

        # Title
        text_parts.append(f'Step {context.step_index}: {context.step_name}')
        text_parts.append('=' * 60)
        text_parts.append('')

        # Document info
        file_size = context.file_path.stat().st_size
        file_ext = context.file_path.suffix

        text_parts.append('Document Info:')
        text_parts.append(f'  Type: {file_ext}')
        text_parts.append(f'  Size: {round(file_size / 1024, 2)} KB')
        text_parts.append(f'  Path: {context.file_path}')

        # Processing info
        if context.manifest_entry:
            text_parts.append('')
            text_parts.append('Processing Info:')
            text_parts.append(json.dumps(context.manifest_entry, indent=2))

        return RenderedOutput(
            text='\n'.join(text_parts),
            title=context.step_name,
            description=f'Document: {context.file_path.name}'
        )


class SvgRenderer(BaseRenderer):
    """
    Base class for SVG file renderers.
    """

    def render_html(self, context: RenderContext) -> RenderedOutput:
        """HTML rendering for SVG files"""
        html_parts = []

        # Title
        html_parts.append(f'<h2>{context.step_name}</h2>')

        # SVG content (inline)
        if context.show_content:
            try:
                svg_content = context.file_path.read_text(encoding='utf-8')
                html_parts.append('<div class="svg-container">')
                html_parts.append(svg_content)  # Inline SVG
                html_parts.append('</div>')
            except Exception as e:
                html_parts.append(f'<p>Error loading SVG: {e}</p>')

        # Metadata
        if context.show_metadata:
            file_size = context.file_path.stat().st_size

            html_parts.append('<div class="metadata">')
            html_parts.append('<h3>SVG Info</h3>')
            html_parts.append('<table>')
            html_parts.append(f'<tr><th>Size</th><td>{file_size} bytes</td></tr>')
            html_parts.append(f'<tr><th>Path</th><td>{context.file_path}</td></tr>')
            html_parts.append('</table>')
            html_parts.append('</div>')

        return RenderedOutput(
            html='\n'.join(html_parts),
            title=context.step_name,
            description=f'SVG: {context.file_path.name}'
        )

    def render_cli(self, context: RenderContext) -> RenderedOutput:
        """CLI rendering for SVG files"""
        text_parts = []

        # Title
        text_parts.append(f'Step {context.step_index}: {context.step_name}')
        text_parts.append('=' * 60)
        text_parts.append('')

        # SVG info
        file_size = context.file_path.stat().st_size

        text_parts.append('SVG Info:')
        text_parts.append(f'  Size: {file_size} bytes')
        text_parts.append(f'  Path: {context.file_path}')

        return RenderedOutput(
            text='\n'.join(text_parts),
            title=context.step_name,
            description=f'SVG: {context.file_path.name}'
        )


class FolderRenderer(BaseRenderer):
    """
    Base class for folder-level operation renderers.

    Handles tools that operate on entire folders and produce
    summaries or group-level outputs.
    """

    def render_html(self, context: RenderContext) -> RenderedOutput:
        """HTML rendering for folder operations"""
        html_parts = []

        # Title
        html_parts.append(f'<h2>{context.step_name}</h2>')

        # Folder info
        html_parts.append('<div class="folder-info">')
        html_parts.append('<h3>Folder Processing</h3>')
        html_parts.append('<table>')
        html_parts.append(f'<tr><th>Path</th><td>{context.file_path}</td></tr>')

        if context.file_path.exists() and context.file_path.is_dir():
            file_count = len(list(context.file_path.iterdir()))
            html_parts.append(f'<tr><th>Files</th><td>{file_count}</td></tr>')

        html_parts.append('</table>')
        html_parts.append('</div>')

        # Manifest details
        if context.manifest_entry:
            html_parts.append('<div class="metadata">')
            html_parts.append('<h3>Processing Details</h3>')
            html_parts.append('<pre>')
            html_parts.append(json.dumps(context.manifest_entry, indent=2))
            html_parts.append('</pre>')
            html_parts.append('</div>')

        return RenderedOutput(
            html='\n'.join(html_parts),
            title=context.step_name,
            description=f'Folder: {context.file_path.name}'
        )

    def render_cli(self, context: RenderContext) -> RenderedOutput:
        """CLI rendering for folder operations"""
        text_parts = []

        # Title
        text_parts.append(f'Step {context.step_index}: {context.step_name}')
        text_parts.append('=' * 60)
        text_parts.append('')

        # Folder info
        text_parts.append('Folder Info:')
        text_parts.append(f'  Path: {context.file_path}')

        if context.file_path.exists() and context.file_path.is_dir():
            file_count = len(list(context.file_path.iterdir()))
            text_parts.append(f'  Files: {file_count}')

        # Processing details
        if context.manifest_entry:
            text_parts.append('')
            text_parts.append('Processing Details:')
            text_parts.append(json.dumps(context.manifest_entry, indent=2))

        return RenderedOutput(
            text='\n'.join(text_parts),
            title=context.step_name,
            description=f'Folder: {context.file_path.name}'
        )
