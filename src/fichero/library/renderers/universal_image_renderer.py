"""
UniversalImageRenderer - Single renderer for all visual content

Consolidates all image-based renderers (crop, enhance, rotate, segment, etc.)
into one unified renderer that handles any visual output.

Uses OpenSeadragon for zoom/pan, works with OutputPane's existing viewer.
"""
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from .base_renderer import BaseRenderer, RenderContext, RenderedOutput

logger = logging.getLogger(__name__)


class UniversalImageRenderer(BaseRenderer):
    """
    Universal renderer for all image/visual content.

    Handles:
    - Original images (JPG, PNG, TIFF, etc.)
    - PDF pages
    - Processed images (crop, enhance, rotate, etc.)
    - Thumbnails
    - Segmented images
    - Any other visual output
    """

    # Import from centralized constants
    from fichero.constants import SUPPORTED_IMAGE_EXTENSIONS, SUPPORTED_PDF_EXTENSIONS
    IMAGE_EXTENSIONS = SUPPORTED_IMAGE_EXTENSIONS | SUPPORTED_PDF_EXTENSIONS

    def can_render(self, context: RenderContext) -> bool:
        """
        Check if this renderer can handle the given context.

        Returns True for any image-like file or visual processing output.
        """
        # Check file extension
        if context.file_path:
            ext = context.file_path.suffix.lower()
            if ext in self.IMAGE_EXTENSIONS:
                return True

        # Check file type metadata
        if context.file_type in ['image', 'photo', 'picture', 'pdf']:
            return True

        # Check if this is a visual processing tool output
        visual_tools = {
            'crop', 'enhance', 'rotate', 'segment', 'split',
            'remove_background', 'prepare_images', 'original'
        }
        if context.tool_name in visual_tools:
            return True

        return False

    def render_html(self, context: RenderContext) -> RenderedOutput:
        """
        Render visual content as HTML for WebView display.

        Returns RenderedOutput with HTML content.
        """
        # Get file path (handle both Path and string)
        if isinstance(context.file_path, Path):
            file_path = context.file_path
        else:
            file_path = Path(context.file_path) if context.file_path else None

        if not file_path or not file_path.exists():
            return RenderedOutput(
                html=self._render_error("Image file not found"),
                error="Image file not found"
            )

        # Build HTML using existing image viewer
        html = self._build_openseadragon_html(file_path, context)

        return RenderedOutput(
            html=html,
            title=context.step_name
        )

    def _build_openseadragon_html(self, file_path: Path, context: RenderContext) -> str:
        """
        Build interactive image viewer HTML using the html_templates.

        This provides zoom, pan, rotate, and minimap functionality.
        """
        from .html_templates import get_interactive_image_viewer

        # Build title from context
        tool_name = context.tool_name or "Image"
        step_name = context.step_name or tool_name

        # Use the interactive viewer from html_templates
        # This has all the zoom/pan/rotate/minimap functionality
        html = get_interactive_image_viewer(
            image_path=file_path,
            title=step_name,
            use_base64=True  # Use base64 encoding for better compatibility
        )

        return html

    def _render_error(self, message: str) -> str:
        """Render error message"""
        return f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body {{
            margin: 0;
            padding: 20px;
            background: #1e1e1e;
            color: #ff6b6b;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            display: flex;
            align-items: center;
            justify-content: center;
            height: 100vh;
        }}
        .error {{
            text-align: center;
            font-size: 16px;
        }}
    </style>
</head>
<body>
    <div class="error">
        <strong>Error:</strong><br>
        {message}
    </div>
</body>
</html>
"""

    def get_editable_json(self, context: RenderContext) -> Optional[Dict[str, Any]]:
        """
        Images don't have editable parameters by default.

        Override this in subclasses if you want to support parameter editing
        for specific image processing tools.
        """
        return None

    def validate_json(self, data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """No validation needed for images"""
        return True, None

    def apply_json_edits(self, context: RenderContext, data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """No edits supported for images by default"""
        return False, "Image editing not supported"
