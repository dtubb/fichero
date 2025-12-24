"""
PreviewImagePane - Dedicated pane for displaying images

Handles:
- Image display with zoom/pan
- Image metadata
- Processing step images
- Simple, focused image viewing
"""

import logging
from typing import Optional, Dict, Any
from pathlib import Path

import toga
from toga.style import Pack
from toga.constants import COLUMN

from fichero.shared.views.base_view import BaseView

# Import internationalization function
try:
    from fichero.shared.utils.i18n import _
except ImportError:
    def _(text):
        return text

logger = logging.getLogger(__name__)


class PreviewImagePane(BaseView):
    """
    Dedicated pane for image preview - simple and focused

    Shows the latest/best processed image for a selected item.
    """

    def __init__(self, app, is_mobile: bool = False, library_manager=None):
        """Initialize the image preview pane"""
        logger.info("🖼️ PreviewImagePane.__init__ starting")

        # Store dependencies
        self.library_manager = library_manager
        self.is_mobile = is_mobile

        # Current state
        self.current_item_id: Optional[str] = None
        self.current_image_path: Optional[str] = None

        # UI components (will be created in _create_content)
        self.image_webview = None
        self.status_label = None

        # Call parent init
        super().__init__(app, is_mobile)

        logger.info("✅ PreviewImagePane initialization complete")

    def _create_content(self):
        """Create the image preview content"""
        # Status label for current image info
        self.status_label = toga.Label(
            "No image selected",
            style=Pack(text_align='center', margin=(10, 10, 5, 10))
        )
        self.content_container.add(self.status_label)

        # Interactive HTML image viewer with zoom/pan capabilities
        self.image_webview = toga.WebView(
            style=Pack(
                flex=1,
                margin=5
            )
        )

        # Load initial placeholder content
        placeholder_html = self._create_placeholder_html()
        self.image_webview.set_content("", placeholder_html)

        self.content_container.add(self.image_webview)

    async def load_item(self, item_id: str, output_data: dict = None, item_metadata: dict = None):
        """Load an image for the given item from metadata or library"""
        logger.info(f"🖼️ Loading image for item {item_id} from metadata")
        self.current_item_id = item_id

        try:
            # First try to get image path from metadata (faster, direct)
            image_path = None
            if item_metadata:
                image_path = item_metadata.get('original_path') or item_metadata.get('file_path') or item_metadata.get('source_path')
                logger.info(f"📋 Using metadata path: {image_path}")

            # Fallback to library manager if no metadata or path
            if not image_path and self.library_manager:
                logger.info(f"📋 Fallback: getting path via library manager")
                file_path = await self.library_manager.get_item_file(item_id)
                if file_path:
                    image_path = str(file_path)

            if image_path and self._is_image_file(image_path):
                self.current_image_path = image_path
                from pathlib import Path
                filename = Path(image_path).name
                self.status_label.text = f"📸 {filename}"
                logger.info(f"✅ Found image file for item {item_id}: {filename}")

                # Render the image using the interactive HTML viewer
                await self._render_image(image_path)
            else:
                self.current_image_path = None
                self.status_label.text = "🔍 No image file found"
                self._show_placeholder()
                logger.info(f"⚠️ No image file found for item {item_id}")

        except Exception as e:
            logger.error(f"Failed to load image for item {item_id}: {e}")
            self.status_label.text = "❌ Error loading image"
            self._show_placeholder()

    def _find_best_image(self, output_data) -> Optional[Dict[str, str]]:
        """Find the best image to display from processing steps"""
        if not output_data:
            return None

        # Handle both dict and ProcessingStep object formats
        processing_steps = []

        # Debug: Log what we actually received
        logger.info(f"🔍 Output data type: {type(output_data)}")
        logger.info(f"🔍 Output data attributes: {dir(output_data) if hasattr(output_data, '__dict__') else 'No attributes'}")

        if hasattr(output_data, 'processing_steps'):
            processing_steps = output_data.processing_steps
            logger.info(f"🔍 Found processing_steps attribute with {len(processing_steps)} steps")
        elif isinstance(output_data, dict):
            processing_steps = output_data.get('processing_steps', [])
            logger.info(f"🔍 Found dict with {len(processing_steps)} processing_steps")
        elif hasattr(output_data, '__iter__') and not isinstance(output_data, str):
            # If it's already a list of processing steps
            processing_steps = output_data
            logger.info(f"🔍 Treating as list with {len(processing_steps)} items")

        if not processing_steps:
            logger.info("🔍 No processing steps found")
            return None

        # Look for processed images, prioritizing enhanced/cropped over originals
        best_image = None
        priority = 0

        for i, step in enumerate(processing_steps):
            logger.info(f"🔍 Step {i}: type={type(step)}, attributes={dir(step) if hasattr(step, '__dict__') else 'No attributes'}")

            # Handle different step formats
            if hasattr(step, 'tool'):
                tool_name = step.tool
                outputs = getattr(step, 'outputs', {})
            elif hasattr(step, 'get'):
                tool_name = step.get('tool', '')
                outputs = step.get('outputs', {})
            elif isinstance(step, dict):
                tool_name = step.get('tool', '')
                outputs = step.get('outputs', {})
            else:
                logger.info(f"🔍 Unknown step format: {step}")
                continue

            logger.info(f"🔍 Tool: {tool_name}, outputs type: {type(outputs)}")

            # Handle different output formats
            output_path = None
            if isinstance(outputs, dict) and 'output_path' in outputs:
                output_path = outputs['output_path']
            elif hasattr(outputs, 'output_path'):
                output_path = outputs.output_path

            if not output_path:
                continue

            # Check if it's actually an image file
            if not self._is_image_file(output_path):
                continue

            # Prioritize different types of processed images
            current_priority = 0
            if 'enhance' in tool_name:
                current_priority = 5
            elif 'crop' in tool_name:
                current_priority = 4
            elif 'prepare' in tool_name:
                current_priority = 3
            elif 'rotate' in tool_name:
                current_priority = 2
            else:
                current_priority = 1

            if current_priority > priority:
                priority = current_priority
                best_image = {
                    'path': output_path,
                    'info': f"{tool_name} - {Path(output_path).name}"
                }
                logger.info(f"🔍 Found better image: {best_image}")

        return best_image

    def _is_image_file(self, file_path: str) -> bool:
        """Check if file is an image based on extension"""
        image_extensions = {'.jpg', '.jpeg', '.png', '.tiff', '.tif', '.bmp', '.webp'}
        return Path(file_path).suffix.lower() in image_extensions

    def clear(self):
        """Clear the image preview"""
        self.current_item_id = None
        self.current_image_path = None
        self.status_label.text = "No image selected"
        self._show_placeholder()
        logger.debug("🖼️ Image pane cleared")

    def _create_placeholder_html(self) -> str:
        """Create placeholder HTML for when no image is selected"""
        return """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            background: #f0f0f0;
            width: 100%;
            height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
        }
        .placeholder {
            text-align: center;
            color: #666;
            font-size: 16px;
        }
        .emoji {
            font-size: 48px;
            margin-bottom: 10px;
        }
    </style>
</head>
<body>
    <div class="placeholder">
        <div class="emoji">🖼️</div>
        <div>Select an image to preview</div>
    </div>
</body>
</html>"""

    def _show_placeholder(self):
        """Show the placeholder content"""
        placeholder_html = self._create_placeholder_html()
        self.image_webview.set_content("", placeholder_html)

    async def _render_image(self, image_path: str):
        """Render an image using the interactive HTML viewer"""
        try:
            from fichero.library.renderers.html_templates import get_interactive_image_viewer
            from pathlib import Path

            path_obj = Path(image_path)

            # Generate HTML for the interactive image viewer
            image_html = get_interactive_image_viewer(
                image_path=path_obj,
                title=path_obj.name,
                use_base64=True  # Use base64 for better compatibility
            )

            # Load the HTML into the WebView
            self.image_webview.set_content("", image_html)
            logger.info(f"✅ Rendered image HTML for: {path_obj.name}")

        except Exception as e:
            logger.error(f"Failed to render image {image_path}: {e}")
            # Show error message
            error_html = self._create_error_html(f"Failed to load image: {e}")
            self.image_webview.set_content("", error_html)

    async def get_viewer_state(self) -> dict:
        """
        Get current zoom/scroll state from the JavaScript viewer.

        Returns:
            Dict with scale, rotation, scroll_x, scroll_y or empty dict if unavailable
        """
        if not self.image_webview:
            return {}

        try:
            # Execute JavaScript to get state from the viewer
            result = await self.image_webview.evaluate_javascript("getViewerState()")
            if result:
                import json
                return json.loads(result)
        except Exception as e:
            logger.debug(f"Could not get viewer state: {e}")

        return {}

    async def restore_viewer_state(self, state: dict):
        """
        Restore zoom/scroll state to the JavaScript viewer.

        Args:
            state: Dict with scale, rotation, scroll_x, scroll_y
        """
        if not self.image_webview or not state:
            return

        try:
            scale = state.get('scale', 1.0)
            rotation = state.get('rotation', 0)
            scroll_x = state.get('scroll_x', 0)
            scroll_y = state.get('scroll_y', 0)

            # Execute JavaScript to restore state
            js_call = f"restoreViewerState({scale}, {rotation}, {scroll_x}, {scroll_y})"
            await self.image_webview.evaluate_javascript(js_call)
            logger.debug(f"Restored viewer state: scale={scale}, rotation={rotation}")
        except Exception as e:
            logger.warning(f"Could not restore viewer state: {e}")

    async def fit_to_window(self):
        """Reset viewer to fit-to-window (called when changing items)."""
        if not self.image_webview:
            return

        try:
            await self.image_webview.evaluate_javascript("fitToWindow()")
            logger.debug("Reset viewer to fit-to-window")
        except Exception as e:
            logger.debug(f"Could not fit to window: {e}")

    def _create_error_html(self, error_message: str) -> str:
        """Create error HTML for when image loading fails"""
        return f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            background: #f0f0f0;
            width: 100%;
            height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
        }}
        .error {{
            text-align: center;
            color: #d32f2f;
            font-size: 16px;
            max-width: 300px;
        }}
        .emoji {{
            font-size: 48px;
            margin-bottom: 10px;
        }}
    </style>
</head>
<body>
    <div class="error">
        <div class="emoji">⚠️</div>
        <div>{error_message}</div>
    </div>
</body>
</html>"""