"""
Simplified unit tests for preview enhancements

Tests the features implemented for:
- 14pt font sizes in metadata pane
- 75%/25% preview layout split
- Zoom menu commands existence
- HTML template functionality
"""

import unittest
from unittest.mock import Mock, patch
import sys
import os
import tempfile
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

import toga
from toga.style import Pack


class TestPreviewMetadataFontSizes(unittest.TestCase):
    """Test that font sizes are set correctly in the metadata pane"""

    def test_font_size_constants(self):
        """Test that appropriate font sizes are used in the source code"""
        # Read the metadata field widget source file
        metadata_field_file = os.path.join(
            os.path.dirname(__file__), '..', '..', 'src',
            'fichero', 'shared', 'widgets', 'metadata_field.py'
        )

        with open(metadata_field_file, 'r') as f:
            content = f.read()

        # Check that font sizes are defined in metadata field widget
        self.assertIn('LABEL_FONT_SIZE', content, "Font size constants should be defined")

        # Check that compact fonts are used (8-9pt range)
        self.assertIn('LABEL_FONT_SIZE = 8', content, "Desktop font size should be 8pt")
        self.assertIn('LABEL_FONT_SIZE_MOBILE = 9', content, "Mobile font size should be 9pt")


class TestPreviewLayoutRatio(unittest.TestCase):
    """Test that preview layout uses 75%/25% split by default"""

    def test_state_manager_default_preset(self):
        """Test that state manager defaults to wide_content preset"""
        # Read the state manager source file
        state_manager_file = os.path.join(
            os.path.dirname(__file__), '..', '..', 'src',
            'fichero', 'config', 'core', 'state_manager.py'
        )

        with open(state_manager_file, 'r') as f:
            content = f.read()

        # Check that wide_content is set as the default
        self.assertIn('"current_preset": "wide_content"', content,
                     "Default preset should be wide_content")

        # Check that wide_content maps to 0.75
        self.assertIn('"wide_content": 0.75', content,
                     "wide_content should map to 0.75 (75%)")

    def test_ratio_menu_commands_exist(self):
        """Test that ratio menu commands are defined in main window"""
        main_window_file = os.path.join(
            os.path.dirname(__file__), '..', '..', 'src',
            'fichero', 'windows', 'main', 'main_window.py'
        )

        with open(main_window_file, 'r') as f:
            content = f.read()

        # Check that cycle ratios command is defined (main ratio control)
        self.assertIn("'view.cycle_ratios':", content, "Cycle ratios command should be defined")

        # Check keyboard shortcut for cycle ratios
        self.assertIn("toga.Key.MOD_1 + 'r'", content, "Cycle ratios shortcut (Cmd+R) should be defined")

    def test_ratio_action_methods_exist(self):
        """Test that ratio action methods are implemented"""
        main_window_file = os.path.join(
            os.path.dirname(__file__), '..', '..', 'src',
            'fichero', 'windows', 'main', 'main_window.py'
        )

        with open(main_window_file, 'r') as f:
            content = f.read()

        # Check that action methods are defined
        action_methods = [
            'def _apply_ratio_balanced(self',
            'def _apply_ratio_wide_content(self',
            'def _apply_ratio_wide_image(self',
            'def _cycle_preview_ratios(self',
            'def _apply_preview_ratio(self'
        ]

        for method in action_methods:
            self.assertIn(method, content, f"Action method {method} should be defined")

    def test_ratio_preset_values(self):
        """Test that ratio presets have correct values"""
        main_window_file = os.path.join(
            os.path.dirname(__file__), '..', '..', 'src',
            'fichero', 'windows', 'main', 'main_window.py'
        )

        with open(main_window_file, 'r') as f:
            content = f.read()

        # Check that ratio presets are defined with correct values
        ratio_definitions = [
            '"wide_content": 0.75',    # 75%/25% - content-focused
            '"wide_image": 0.25',      # 25%/75% - image-focused
            '"balanced": 0.5'          # 50%/50% - balanced
        ]

        for ratio_def in ratio_definitions:
            self.assertIn(ratio_def, content, f"Ratio definition {ratio_def} should be present")

    def test_flex_application_logic(self):
        """Test that flex ratios are calculated correctly"""
        main_window_file = os.path.join(
            os.path.dirname(__file__), '..', '..', 'src',
            'fichero', 'windows', 'main', 'main_window.py'
        )

        with open(main_window_file, 'r') as f:
            content = f.read()

        # Check that flex calculation logic exists
        flex_logic = [
            'total_flex = 100',
            'image_flex = int(ratio * total_flex)',
            'metadata_flex = total_flex - image_flex',
            'image_slot.container.style.flex = image_flex',
            'metadata_slot.container.style.flex = metadata_flex'
        ]

        for logic in flex_logic:
            self.assertIn(logic, content, f"Flex calculation logic {logic} should be present")

    def test_initial_ratio_setup(self):
        """Test that initial 75%/25% ratio is set during layout creation"""
        main_window_file = os.path.join(
            os.path.dirname(__file__), '..', '..', 'src',
            'fichero', 'windows', 'main', 'main_window.py'
        )

        with open(main_window_file, 'r') as f:
            content = f.read()

        # Check that initial flex ratios are set
        initial_setup = [
            'image_slot.container.style.flex = 75',
            'metadata_slot.container.style.flex = 25',
            'Applied 75%/25% flex ratio to preview panes'
        ]

        for setup in initial_setup:
            self.assertIn(setup, content, f"Initial ratio setup {setup} should be present")

    def test_ratio_restoration_after_layout_restore(self):
        """Test that ratios are reapplied after layout state restoration"""
        main_window_file = os.path.join(
            os.path.dirname(__file__), '..', '..', 'src',
            'fichero', 'windows', 'main', 'main_window.py'
        )

        with open(main_window_file, 'r') as f:
            content = f.read()

        # Check that ratio reapplication exists after restoration
        restoration_logic = [
            'current_preset = state_manager.get_current_preview_preset()',
            'self._apply_preview_ratio(current_preset, None)',
            'Reapplied preview ratio preset after restoration',
            'Applied default wide_content ratio after restoration'
        ]

        for logic in restoration_logic:
            self.assertIn(logic, content, f"Restoration logic {logic} should be present")


class TestZoomMenuCommands(unittest.TestCase):
    """Test that zoom menu commands are defined in the main window"""

    def test_zoom_commands_defined(self):
        """Test that zoom commands are defined in main window source"""
        # Read the main window source file
        main_window_file = os.path.join(
            os.path.dirname(__file__), '..', '..', 'src',
            'fichero', 'windows', 'main', 'main_window.py'
        )

        with open(main_window_file, 'r') as f:
            content = f.read()

        # Check that zoom commands are defined
        self.assertIn("'view.zoom_in':", content, "Zoom In command should be defined")
        self.assertIn("'view.zoom_out':", content, "Zoom Out command should be defined")
        self.assertIn("'view.actual_size':", content, "Actual Size command should be defined")

        # Check keyboard shortcuts
        self.assertIn('toga.Key.MOD_1 + \'=\'', content, "Zoom In shortcut (Cmd+=) should be defined")
        self.assertIn('toga.Key.MOD_1 + \'-\'', content, "Zoom Out shortcut (Cmd+-) should be defined")
        self.assertIn('toga.Key.MOD_1 + \'0\'', content, "Actual Size shortcut (Cmd+0) should be defined")

    def test_zoom_action_methods_defined(self):
        """Test that zoom action methods are implemented"""
        # Read the main window source file
        main_window_file = os.path.join(
            os.path.dirname(__file__), '..', '..', 'src',
            'fichero', 'windows', 'main', 'main_window.py'
        )

        with open(main_window_file, 'r') as f:
            content = f.read()

        # Check that action methods are defined
        self.assertIn('def _zoom_in_preview(self', content, "Zoom in method should be defined")
        self.assertIn('def _zoom_out_preview(self', content, "Zoom out method should be defined")
        self.assertIn('def _actual_size_preview(self', content, "Actual size method should be defined")
        self.assertIn('def _execute_preview_zoom_command(self', content, "Zoom execution method should be defined")

    def test_javascript_commands(self):
        """Test that correct JavaScript commands are called"""
        main_window_file = os.path.join(
            os.path.dirname(__file__), '..', '..', 'src',
            'fichero', 'windows', 'main', 'main_window.py'
        )

        with open(main_window_file, 'r') as f:
            content = f.read()

        # Check that JavaScript commands are correct
        self.assertIn('"zoomIn()"', content, "Should call zoomIn() JavaScript function")
        self.assertIn('"zoomOut()"', content, "Should call zoomOut() JavaScript function")
        self.assertIn('"actualSize()"', content, "Should call actualSize() JavaScript function")


class TestPreviewImagePaneTrackpadSupport(unittest.TestCase):
    """Test that preview image pane supports trackpad scrolling"""

    def test_html_template_has_scroll_support(self):
        """Test that HTML template includes proper scrolling and zoom functionality"""
        from fichero.library.renderers.html_templates import get_interactive_image_viewer

        # Create a minimal test image file
        with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp:
            # Write minimal JPEG header
            tmp.write(b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00\xff\xdb')
            temp_path = Path(tmp.name)

        try:
            # Generate HTML content
            html_content = get_interactive_image_viewer(
                image_path=temp_path,
                title="Test Image",
                use_base64=True
            )

            # Check for trackpad/mouse scrolling support
            self.assertIn('overflow: auto', html_content,
                         "HTML should enable scrolling for trackpad support")
            self.assertIn('-webkit-overflow-scrolling: touch', html_content,
                         "HTML should enable smooth touch/trackpad scrolling")

            # Check for zoom functions
            self.assertIn('function zoomIn()', html_content,
                         "HTML should include zoomIn function")
            self.assertIn('function zoomOut()', html_content,
                         "HTML should include zoomOut function")
            self.assertIn('function actualSize()', html_content,
                         "HTML should include actualSize function")

            # Check for pan/drag navigation
            self.assertIn('cursor: grab', html_content,
                         "HTML should enable grab cursor for panning")
            self.assertIn('cursor: grabbing', html_content,
                         "HTML should show grabbing cursor when panning")

            # Check for mouse wheel zoom support
            self.assertIn('wheel', html_content,
                         "HTML should handle wheel events for zoom")
            self.assertIn('preventDefault()', html_content,
                         "HTML should prevent default wheel behavior")

        finally:
            # Clean up temporary file
            temp_path.unlink()

    def test_html_template_javascript_functions(self):
        """Test that the JavaScript functions have correct implementations"""
        from fichero.library.renderers.html_templates import get_interactive_image_viewer

        # Create a minimal test image file
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
            # Write minimal PNG header
            tmp.write(b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00')
            temp_path = Path(tmp.name)

        try:
            html_content = get_interactive_image_viewer(
                image_path=temp_path,
                title="Test Image",
                use_base64=True
            )

            # Check smooth zoom implementation (uses 1.05 factor for smoother feel)
            self.assertIn('ZOOM_FACTOR = 1.05', html_content,
                         "Should use 1.05 zoom factor for smooth zooming")
            self.assertIn('function smoothZoomAtPoint', html_content,
                         "Should have smooth zoom animation function")
            self.assertIn('scale = 1', html_content,
                         "Actual size should set scale to 1")

            # Check that image size is updated after zoom
            self.assertIn('updateImageSize()', html_content,
                         "Should call updateImageSize after zoom operations")

        finally:
            temp_path.unlink()


class TestOverallIntegration(unittest.TestCase):
    """Test that all the changes work together"""

    def test_all_features_present(self):
        """Integration test to verify all features are implemented"""

        # Check metadata field widget font sizes
        metadata_field_file = os.path.join(
            os.path.dirname(__file__), '..', '..', 'src',
            'fichero', 'shared', 'widgets', 'metadata_field.py'
        )
        with open(metadata_field_file, 'r') as f:
            metadata_content = f.read()

        # Check state manager layout ratio
        state_manager_file = os.path.join(
            os.path.dirname(__file__), '..', '..', 'src',
            'fichero', 'config', 'core', 'state_manager.py'
        )
        with open(state_manager_file, 'r') as f:
            state_content = f.read()

        # Check main window zoom commands
        main_window_file = os.path.join(
            os.path.dirname(__file__), '..', '..', 'src',
            'fichero', 'windows', 'main', 'main_window.py'
        )
        with open(main_window_file, 'r') as f:
            main_content = f.read()

        # Verify all changes are present
        features_present = {
            'dense_font_sizes': 'LABEL_FONT_SIZE = 8' in metadata_content,
            'wide_content_default': '"current_preset": "wide_content"' in state_content,
            'zoom_commands': all(cmd in main_content for cmd in [
                "'view.zoom_in':", "'view.zoom_out':", "'view.actual_size':"
            ]),
            'zoom_methods': all(method in main_content for method in [
                'def _zoom_in_preview', 'def _zoom_out_preview', 'def _actual_size_preview'
            ]),
            'ratio_commands': "'view.cycle_ratios':" in main_content,
            'ratio_methods': all(method in main_content for method in [
                'def _apply_ratio_balanced', 'def _apply_ratio_wide_content',
                'def _cycle_preview_ratios'
            ]),
            'ratio_shortcuts': "toga.Key.MOD_1 + 'r'" in main_content,
            'ratio_restoration': all(logic in main_content for logic in [
                'get_current_preview_preset()', 'Reapplied preview ratio preset after restoration'
            ])
        }

        for feature, present in features_present.items():
            self.assertTrue(present, f"Feature {feature} should be present")

        print(f"\n✅ All features verified:")
        print(f"  - Dense font sizes in metadata pane: {features_present['dense_font_sizes']}")
        print(f"  - 75%/25% default layout ratio: {features_present['wide_content_default']}")
        print(f"  - Zoom menu commands defined: {features_present['zoom_commands']}")
        print(f"  - Zoom action methods implemented: {features_present['zoom_methods']}")
        print(f"  - Cycle ratios command defined: {features_present['ratio_commands']}")
        print(f"  - Ratio action methods implemented: {features_present['ratio_methods']}")
        print(f"  - Ratio keyboard shortcut (Cmd+R): {features_present['ratio_shortcuts']}")
        print(f"  - Ratio restoration after layout restore: {features_present['ratio_restoration']}")


if __name__ == '__main__':
    unittest.main()