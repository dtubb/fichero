"""
Unit tests for the improved interactive image viewer

Tests the macOS-style improvements:
1. Zoom towards mouse position (not center)
2. macOS-style selection box (white/blue with resize handles)
3. Smooth zoom animation with requestAnimationFrame
"""

import unittest
import tempfile
import os
from pathlib import Path


class TestInteractiveImageViewerHTML(unittest.TestCase):
    """Test the HTML generation for the interactive image viewer"""

    @classmethod
    def setUpClass(cls):
        """Create a test image file"""
        # Create a minimal valid PNG (1x1 pixel, red)
        cls.temp_dir = tempfile.mkdtemp()
        cls.test_image_path = Path(cls.temp_dir) / "test_image.png"

        # Minimal PNG file (1x1 red pixel)
        png_data = bytes([
            0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A,  # PNG signature
            0x00, 0x00, 0x00, 0x0D, 0x49, 0x48, 0x44, 0x52,  # IHDR chunk
            0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,  # 1x1 dimensions
            0x08, 0x02, 0x00, 0x00, 0x00, 0x90, 0x77, 0x53,
            0xDE, 0x00, 0x00, 0x00, 0x0C, 0x49, 0x44, 0x41,  # IDAT chunk
            0x54, 0x08, 0xD7, 0x63, 0xF8, 0xFF, 0xFF, 0x3F,
            0x00, 0x05, 0xFE, 0x02, 0xFE, 0xDC, 0xCC, 0x59,
            0xE7, 0x00, 0x00, 0x00, 0x00, 0x49, 0x45, 0x4E,  # IEND chunk
            0x44, 0xAE, 0x42, 0x60, 0x82
        ])
        with open(cls.test_image_path, 'wb') as f:
            f.write(png_data)

    @classmethod
    def tearDownClass(cls):
        """Clean up test files"""
        import shutil
        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def get_viewer_html(self):
        """Helper to get the viewer HTML"""
        from fichero.library.renderers.html_templates import get_interactive_image_viewer
        return get_interactive_image_viewer(self.test_image_path, title="Test Image")


class TestMacOSStyleSelectionBox(TestInteractiveImageViewerHTML):
    """Test macOS-style selection box styling"""

    def test_selection_box_has_white_border(self):
        """Selection box should have white border (not green)"""
        html = self.get_viewer_html()
        # Should have white border
        self.assertIn("rgba(255, 255, 255, 0.9)", html)
        # Should NOT have green dashed border for selection
        self.assertNotIn("border: 2px dashed #4CAF50", html)

    def test_selection_box_has_blue_background(self):
        """Selection box should have macOS blue background"""
        html = self.get_viewer_html()
        # macOS system blue: rgb(0, 122, 255)
        self.assertIn("rgba(0, 122, 255", html)

    def test_selection_box_has_resize_handles(self):
        """Selection box should have 8 resize handles"""
        html = self.get_viewer_html()
        # Check for all 8 handle classes
        handles = ['nw', 'n', 'ne', 'e', 'se', 's', 'sw', 'w']
        for handle in handles:
            self.assertIn(f'class="selection-handle {handle}"', html)

    def test_resize_handles_have_correct_cursors(self):
        """Resize handles should have appropriate cursor styles"""
        html = self.get_viewer_html()
        # Corner handles
        self.assertIn("cursor: nwse-resize", html)  # nw, se
        self.assertIn("cursor: nesw-resize", html)  # ne, sw
        # Edge handles
        self.assertIn("cursor: ns-resize", html)    # n, s
        self.assertIn("cursor: ew-resize", html)    # e, w

    def test_minimap_viewport_has_macos_style(self):
        """Minimap viewport should also use macOS blue style"""
        html = self.get_viewer_html()
        # Should have white border and blue background
        self.assertIn("#minimapViewport", html)
        # Check the viewport has the updated style (blue, not green)
        self.assertNotIn("border: 2px solid #4CAF50", html.split("#selectionBox")[0])


class TestZoomToMousePosition(TestInteractiveImageViewerHTML):
    """Test zoom-to-mouse-position functionality"""

    def test_has_mouse_position_tracking(self):
        """Should track mouse position for zoom"""
        html = self.get_viewer_html()
        self.assertIn("lastMouseX", html)
        self.assertIn("lastMouseY", html)

    def test_has_zoom_at_point_function(self):
        """Should have zoomAtPoint function for zoom-to-point"""
        html = self.get_viewer_html()
        self.assertIn("function zoomAtPoint", html)

    def test_zoom_at_point_adjusts_scroll(self):
        """zoomAtPoint should adjust scroll position to keep point stationary"""
        html = self.get_viewer_html()
        # Check for scroll adjustment logic
        self.assertIn("container.scrollLeft = imagePointX * scale - pointX", html)
        self.assertIn("container.scrollTop = imagePointY * scale - pointY", html)

    def test_wheel_handler_uses_mouse_position(self):
        """Wheel zoom handler should use current mouse position"""
        html = self.get_viewer_html()
        # Check that wheel handler gets mouse position
        self.assertIn("const mouseX = e.clientX - rect.left", html)
        self.assertIn("const mouseY = e.clientY - rect.top", html)


class TestSmoothZoomAnimation(TestInteractiveImageViewerHTML):
    """Test smooth zoom animation"""

    def test_has_smooth_zoom_function(self):
        """Should have smoothZoomAtPoint function"""
        html = self.get_viewer_html()
        self.assertIn("function smoothZoomAtPoint", html)

    def test_uses_request_animation_frame(self):
        """Should use requestAnimationFrame for smooth animation"""
        html = self.get_viewer_html()
        self.assertIn("requestAnimationFrame", html)

    def test_has_ease_out_animation(self):
        """Should use ease-out curve for natural deceleration"""
        html = self.get_viewer_html()
        # Ease-out cubic: 1 - Math.pow(1 - progress, 3)
        self.assertIn("1 - Math.pow(1 - progress, 3)", html)

    def test_has_animation_duration_constant(self):
        """Should have configurable animation duration"""
        html = self.get_viewer_html()
        self.assertIn("ZOOM_DURATION", html)

    def test_smaller_zoom_factor(self):
        """Should use smaller zoom factor for smoother feel"""
        html = self.get_viewer_html()
        # Should use 1.05 (5%) instead of 1.2 (20%)
        self.assertIn("ZOOM_FACTOR = 1.05", html)

    def test_wheel_differentiates_trackpad_vs_mouse(self):
        """Should handle trackpad (continuous) vs mouse wheel (discrete) differently"""
        html = self.get_viewer_html()
        # Should check deltaY magnitude to differentiate
        self.assertIn("Math.abs(e.deltaY) > 50", html)


class TestSelectionBoxInteraction(TestInteractiveImageViewerHTML):
    """Test selection box interaction features"""

    def test_selection_can_be_dragged(self):
        """Selection box should be draggable"""
        html = self.get_viewer_html()
        self.assertIn("isDraggingSelection", html)
        self.assertIn("cursor: move", html)

    def test_selection_can_be_resized(self):
        """Selection box should be resizable via handles"""
        html = self.get_viewer_html()
        self.assertIn("isResizingSelection", html)
        self.assertIn("activeHandle", html)

    def test_escape_cancels_selection(self):
        """Pressing Escape should cancel selection"""
        html = self.get_viewer_html()
        self.assertIn("e.key === 'Escape'", html)
        self.assertIn("hideSelection()", html)

    def test_enter_zooms_to_selection(self):
        """Pressing Enter should zoom to selection"""
        html = self.get_viewer_html()
        self.assertIn("e.key === 'Enter'", html)
        self.assertIn("zoomToSelection", html)

    def test_double_click_zooms_to_selection(self):
        """Double-clicking selection should zoom to it"""
        html = self.get_viewer_html()
        self.assertIn("selectionBox.addEventListener('dblclick'", html)

    def test_has_zoom_to_current_selection_function(self):
        """Should have zoomToCurrentSelection function for menu command"""
        html = self.get_viewer_html()
        self.assertIn("function zoomToCurrentSelection()", html)

    def test_zoom_to_current_selection_checks_visibility(self):
        """zoomToCurrentSelection should check if selection is visible"""
        html = self.get_viewer_html()
        self.assertIn("selectionBox.style.display === 'none'", html)


class TestDoubleClickZoom(TestInteractiveImageViewerHTML):
    """Test double-click zoom behavior"""

    def test_double_click_zooms_at_point(self):
        """Double-click should zoom in at clicked point"""
        html = self.get_viewer_html()
        # Should get click position
        self.assertIn("const clickX = e.clientX - rect.left", html)
        self.assertIn("const clickY = e.clientY - rect.top", html)

    def test_double_click_uses_smooth_zoom(self):
        """Double-click should use smooth zoom animation"""
        html = self.get_viewer_html()
        # Should call smoothZoomAtPoint on double-click
        self.assertIn("smoothZoomAtPoint(scale * 2, clickX, clickY", html)

    def test_double_click_fits_window_at_max_zoom(self):
        """Double-click should fit to window when at max zoom (4x)"""
        html = self.get_viewer_html()
        # Should check if at max zoom (scale >= 4) and call fitToWindow
        self.assertIn("scale >= 4", html)
        self.assertIn("fitToWindow()", html)


class TestMagnifier(TestInteractiveImageViewerHTML):
    """Test magnifier feature"""

    def test_has_magnifier_element(self):
        """Should have magnifier panel element"""
        html = self.get_viewer_html()
        self.assertIn('id="magnifier"', html)
        self.assertIn('id="magnifierCanvas"', html)

    def test_has_toggle_magnifier_function(self):
        """Should have toggleMagnifier function"""
        html = self.get_viewer_html()
        self.assertIn("function toggleMagnifier()", html)

    def test_magnifier_tracks_mouse(self):
        """Magnifier should update on mouse move"""
        html = self.get_viewer_html()
        self.assertIn("updateMagnifier", html)
        self.assertIn("magnifierActive", html)

    def test_magnifier_has_zoom_control(self):
        """Magnifier zoom level should be adjustable"""
        html = self.get_viewer_html()
        self.assertIn("magnifierZoom", html)
        self.assertIn("setMagnifierZoom", html)

    def test_magnifier_wheel_changes_zoom(self):
        """Scroll wheel on magnifier should change zoom level"""
        html = self.get_viewer_html()
        self.assertIn("magnifier.addEventListener('wheel'", html)

    def test_magnifier_zoom_in_function(self):
        """Should have magnifierZoomIn function"""
        html = self.get_viewer_html()
        self.assertIn("function magnifierZoomIn()", html)

    def test_magnifier_zoom_out_function(self):
        """Should have magnifierZoomOut function"""
        html = self.get_viewer_html()
        self.assertIn("function magnifierZoomOut()", html)

    def test_magnifier_has_resize_handle(self):
        """Magnifier should have a resize handle for height adjustment"""
        html = self.get_viewer_html()
        self.assertIn('id="magnifierResizeHandle"', html)
        self.assertIn("cursor: ns-resize", html)

    def test_magnifier_height_adjustable(self):
        """Should have setMagnifierHeight function"""
        html = self.get_viewer_html()
        self.assertIn("function setMagnifierHeight(", html)

    def test_magnifier_resize_handle_drag(self):
        """Resize handle should track dragging state"""
        html = self.get_viewer_html()
        self.assertIn("isResizingMagnifier", html)


class TestHTMLStructure(TestInteractiveImageViewerHTML):
    """Test the overall HTML structure"""

    def test_valid_html_structure(self):
        """Generated HTML should have valid structure"""
        html = self.get_viewer_html()
        self.assertIn("<!DOCTYPE html>", html)
        self.assertIn("<html>", html)
        self.assertIn("</html>", html)
        self.assertIn("<head>", html)
        self.assertIn("</head>", html)
        self.assertIn("<body>", html)
        self.assertIn("</body>", html)

    def test_has_image_container(self):
        """Should have image container element"""
        html = self.get_viewer_html()
        self.assertIn('id="imageContainer"', html)

    def test_has_minimap(self):
        """Should have minimap element"""
        html = self.get_viewer_html()
        self.assertIn('id="minimap"', html)
        self.assertIn('id="minimapCanvas"', html)
        self.assertIn('id="minimapViewport"', html)

    def test_has_selection_box_with_handles(self):
        """Should have selection box with resize handles"""
        html = self.get_viewer_html()
        self.assertIn('id="selectionBox"', html)
        # Should have handles inside selection box
        selection_section = html.split('id="selectionBox"')[1].split('</div>')[0]
        self.assertIn('selection-handle', selection_section)


if __name__ == '__main__':
    unittest.main()
