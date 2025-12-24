"""Image Viewer - Display images with zoom, pan, rotate, and magnifier.

Uses WKWebView with an interactive HTML viewer that provides:
- Smooth zoom (scroll wheel + Cmd, double-click, buttons)
- Pan/drag navigation
- Rotation (90-degree increments)
- Minimap overlay showing viewport position
- Selection box (Shift+drag) with zoom-to-selection
- Magnifier panel (togglable, resizable, 0.5x-20x zoom)
- Viewer state persistence (zoom, rotation, scroll position)

Usage:
    from fichero.app.main_window.views.library.viewers import ImageViewer

    viewer = ImageViewer()
    viewer.load(document)  # or viewer.load_path("/path/to/image.jpg")

    # Zoom controls (call JavaScript in WebView)
    viewer.zoom_in()
    viewer.zoom_to_fit()
    viewer.zoom_actual_size()
    viewer.toggle_magnifier()
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, TYPE_CHECKING

from rubicon.objc import ObjCClass, objc_method, objc_property

from fichero.app.main_window.views.library.viewers.base import EditorProtocol

if TYPE_CHECKING:
    from fichero.models import Document

logger = logging.getLogger(__name__)

# =============================================================================
# Constants
# =============================================================================

_AUTORESIZE_FLEX = 18  # NSViewWidthSizable | NSViewHeightSizable

# Supported image extensions
IMAGE_EXTENSIONS = frozenset({
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".tiff", ".tif",
    ".bmp", ".heic", ".heif", ".jxl", ".avif"
})


# =============================================================================
# Cocoa Classes
# =============================================================================

NSView = ObjCClass("NSView")
NSColor = ObjCClass("NSColor")

# WKWebView for rendering HTML
WKWebView = ObjCClass("WKWebView")
WKWebViewConfiguration = ObjCClass("WKWebViewConfiguration")
WKUserContentController = ObjCClass("WKUserContentController")


# =============================================================================
# Image Viewer
# =============================================================================

class ImageViewer(EditorProtocol):
    """Interactive image viewer using WKWebView.

    Renders images using an HTML template with JavaScript-powered controls.
    Supports zoom, pan, rotate, minimap, selection, and magnifier.
    """

    def __init__(self):
        self._path: Path | None = None
        self._document: Document | None = None

        # Create WKWebView with configuration
        config = WKWebViewConfiguration.alloc().init()
        self._web_view = WKWebView.alloc().initWithFrame_configuration_(
            ((0, 0), (400, 400)), config
        )
        self._web_view.setAutoresizingMask_(_AUTORESIZE_FLEX)

        # Allow file access for local images
        try:
            self._web_view.configuration.preferences.setValue_forKey_(True, "allowFileAccessFromFileURLs")
        except Exception:
            pass  # Older macOS may not support this

        logger.info("ImageViewer created (WKWebView)")

    @property
    def native(self) -> Any:
        """The native WKWebView."""
        return self._web_view

    @property
    def path(self) -> Path | None:
        """Currently loaded image path."""
        return self._path

    @property
    def document(self) -> Document | None:
        """Currently loaded document."""
        return self._document

    # -------------------------------------------------------------------------
    # Load Methods
    # -------------------------------------------------------------------------

    def load(self, item: Any) -> None:
        """Load a Document or path.

        Args:
            item: Document model, path string, or Path object
        """
        from fichero.models import Document

        if isinstance(item, Document):
            self._document = item
            path = item.path or getattr(item, 'display_path', None) or getattr(item, 'full_path', None)
            if path:
                self.load_path(Path(path))
            else:
                logger.warning(f"Document has no path: {item.name}")
                self._show_placeholder()
        elif isinstance(item, Path):
            self._document = None
            self.load_path(item)
        elif isinstance(item, str):
            self._document = None
            self.load_path(Path(item))
        else:
            logger.warning(f"ImageViewer cannot load: {type(item)}")
            self._show_placeholder()

    def load_path(self, path: Path) -> None:
        """Load image from file path.

        Args:
            path: Path to image file
        """
        self._path = path

        if not path or not path.exists():
            logger.warning(f"Image not found: {path}")
            self._show_placeholder()
            return

        # Check if it's an image file
        if path.suffix.lower() not in IMAGE_EXTENSIONS:
            logger.warning(f"Not an image file: {path}")
            self._show_placeholder()
            return

        # Generate HTML using the template
        try:
            from fichero.library.renderers.html_templates import get_interactive_image_viewer

            html = get_interactive_image_viewer(
                image_path=path,
                title=path.name,
                use_base64=True  # Better compatibility
            )

            # Load HTML into WebView
            self._web_view.loadHTMLString_baseURL_(html, None)
            logger.debug(f"ImageViewer loaded: {path.name}")

        except Exception as e:
            logger.error(f"Failed to load image {path}: {e}")
            self._show_error(f"Failed to load: {e}")

    def _show_placeholder(self) -> None:
        """Show placeholder when no image is loaded."""
        html = """<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0;display:flex;align-items:center;justify-content:center;
    height:100vh;background:#969696;color:#666;font-family:system-ui;">
    <div style="text-align:center">
        <div style="font-size:48px">Select an image</div>
    </div>
</body>
</html>"""
        self._web_view.loadHTMLString_baseURL_(html, None)

    def _show_error(self, message: str) -> None:
        """Show error message."""
        html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0;display:flex;align-items:center;justify-content:center;
    height:100vh;background:#969696;color:#d32f2f;font-family:system-ui;">
    <div style="text-align:center">
        <div style="font-size:24px">{message}</div>
    </div>
</body>
</html>"""
        self._web_view.loadHTMLString_baseURL_(html, None)

    def clear(self) -> None:
        """Clear the image."""
        self._path = None
        self._document = None
        self._show_placeholder()

    # -------------------------------------------------------------------------
    # Zoom Controls (call JavaScript functions)
    # -------------------------------------------------------------------------

    def _eval_js(self, script: str) -> None:
        """Execute JavaScript in the WebView."""
        try:
            self._web_view.evaluateJavaScript_completionHandler_(script, None)
        except Exception as e:
            logger.debug(f"JS eval failed: {e}")

    def zoom_in(self) -> None:
        """Zoom in."""
        self._eval_js("zoomIn()")

    def zoom_out(self) -> None:
        """Zoom out."""
        self._eval_js("zoomOut()")

    def zoom_to_fit(self) -> None:
        """Zoom to fit image in view."""
        self._eval_js("fitToWindow()")

    def zoom_actual_size(self) -> None:
        """Reset to 100% zoom."""
        self._eval_js("actualSize()")

    def zoom_to_width(self) -> None:
        """Zoom to fit width."""
        self._eval_js("fitToWidth()")

    def zoom_to_height(self) -> None:
        """Zoom to fit height."""
        self._eval_js("fitToHeight()")

    def zoom_to_selection(self) -> None:
        """Zoom to current selection box."""
        self._eval_js("zoomToCurrentSelection()")

    # -------------------------------------------------------------------------
    # Rotation
    # -------------------------------------------------------------------------

    def rotate_left(self) -> None:
        """Rotate image 90 degrees counter-clockwise."""
        self._eval_js("rotateLeft()")

    def rotate_right(self) -> None:
        """Rotate image 90 degrees clockwise."""
        self._eval_js("rotateRight()")

    # -------------------------------------------------------------------------
    # Magnifier
    # -------------------------------------------------------------------------

    def toggle_magnifier(self) -> None:
        """Toggle the magnifier panel."""
        self._eval_js("toggleMagnifier()")

    def magnifier_zoom_in(self) -> None:
        """Increase magnifier zoom level."""
        self._eval_js("magnifierZoomIn()")

    def magnifier_zoom_out(self) -> None:
        """Decrease magnifier zoom level."""
        self._eval_js("magnifierZoomOut()")

    # -------------------------------------------------------------------------
    # State Persistence
    # -------------------------------------------------------------------------

    async def get_viewer_state(self) -> dict:
        """Get current zoom/scroll state from JavaScript.

        Returns:
            Dict with scale, rotation, scroll_x, scroll_y
        """
        # Note: This requires async JavaScript evaluation
        # For now, return empty dict - state is maintained in JS
        return {}

    async def restore_viewer_state(self, state: dict) -> None:
        """Restore zoom/scroll state.

        Args:
            state: Dict with scale, rotation, scroll_x, scroll_y
        """
        if not state:
            return

        scale = state.get('scale', 1.0)
        rotation = state.get('rotation', 0)
        scroll_x = state.get('scroll_x', 0)
        scroll_y = state.get('scroll_y', 0)

        self._eval_js(f"restoreViewerState({scale}, {rotation}, {scroll_x}, {scroll_y})")
