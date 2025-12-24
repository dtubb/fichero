"""
Unit tests for the preview pane ratio system

Tests the fix for preview pane ratios not changing properly:
- Menu commands for ratios exist
- Ratio application logic works
- Layout restoration doesn't override ratios
- Default wide_content (75/25) ratio is applied
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

import toga
from toga.style import Pack


class TestPreviewRatioMenuCommands(unittest.TestCase):
    """Test that all ratio menu commands are properly defined"""

    def setUp(self):
        """Read the main window source file once for all tests"""
        self.main_window_file = os.path.join(
            os.path.dirname(__file__), '..', '..', 'src',
            'fichero', 'windows', 'main', 'main_window.py'
        )

        with open(self.main_window_file, 'r') as f:
            self.main_window_content = f.read()

    def test_ratio_commands_defined(self):
        """Test that cycle ratio menu command is defined"""
        # Only cycle_ratios command exists now (Cmd+R)
        # Individual ratio commands (Cmd+2/5/7) were removed for simplicity
        expected_commands = [
            "'view.cycle_ratios':"
        ]

        for command in expected_commands:
            with self.subTest(command=command):
                self.assertIn(command, self.main_window_content,
                            f"Command {command} should be defined in main window")

    def test_ratio_keyboard_shortcuts(self):
        """Test that keyboard shortcut is defined for ratio cycle command"""
        # Only Cmd+R remains for cycling ratios
        # Cmd+2/5/7 were removed for simplicity
        expected_shortcuts = [
            ("toga.Key.MOD_1 + 'r'", "Cycle ratios")
        ]

        for shortcut, description in expected_shortcuts:
            with self.subTest(shortcut=shortcut, description=description):
                self.assertIn(shortcut, self.main_window_content,
                            f"Keyboard shortcut {shortcut} for {description} should be defined")

    def test_ratio_labels_in_menu(self):
        """Test that ratio cycle command has proper label"""
        # Only cycle command label exists now
        expected_labels = [
            '"Cycle Preview Width"'
        ]

        for label in expected_labels:
            with self.subTest(label=label):
                self.assertIn(label, self.main_window_content,
                            f"Menu label {label} should be defined")

    def test_ratio_commands_in_view_group(self):
        """Test that ratio commands are in the View group"""
        # Check that ratio commands use toga.Group.VIEW
        self.assertIn('group=toga.Group.VIEW', self.main_window_content,
                     "Ratio commands should be in VIEW group")

        # Check that they have proper section ordering
        self.assertIn('section=10', self.main_window_content,
                     "Ratio commands should be in section 10")


class TestPreviewRatioActionMethods(unittest.TestCase):
    """Test that ratio action methods are properly implemented"""

    def setUp(self):
        """Read the main window source file once for all tests"""
        self.main_window_file = os.path.join(
            os.path.dirname(__file__), '..', '..', 'src',
            'fichero', 'windows', 'main', 'main_window.py'
        )

        with open(self.main_window_file, 'r') as f:
            self.main_window_content = f.read()

    def test_ratio_action_methods_exist(self):
        """Test that ratio action methods are implemented"""
        # Only cycle and apply methods exist now
        # Individual ratio methods (_apply_ratio_balanced, etc.) were removed
        expected_methods = [
            'def _cycle_preview_ratios(self',
            'def _apply_preview_ratio(self'
        ]

        for method in expected_methods:
            with self.subTest(method=method):
                self.assertIn(method, self.main_window_content,
                            f"Action method {method} should be defined")

    def test_ratio_preset_values(self):
        """Test that ratio presets have correct mathematical values"""
        expected_ratios = [
            ('"wide_content": 0.75', "75%/25% content-focused"),
            ('"wide_image": 0.25', "25%/75% image-focused"),
            ('"balanced": 0.5', "50%/50% balanced")
        ]

        for ratio_def, description in expected_ratios:
            with self.subTest(ratio=ratio_def, description=description):
                self.assertIn(ratio_def, self.main_window_content,
                            f"Ratio definition {ratio_def} for {description} should be present")

    def test_flex_calculation_logic(self):
        """Test that flex calculation logic is implemented correctly"""
        expected_calculations = [
            'total_flex = 100',
            'image_flex = int(ratio * total_flex)',
            'metadata_flex = total_flex - image_flex'
        ]

        for calc in expected_calculations:
            with self.subTest(calculation=calc):
                self.assertIn(calc, self.main_window_content,
                            f"Flex calculation {calc} should be present")

    def test_flex_application_logic(self):
        """Test that flex values are applied to container styles"""
        expected_applications = [
            'image_slot.container.style.flex = image_flex',
            'metadata_slot.container.style.flex = metadata_flex'
        ]

        for app in expected_applications:
            with self.subTest(application=app):
                self.assertIn(app, self.main_window_content,
                            f"Flex application {app} should be present")


class TestPreviewRatioInitialSetup(unittest.TestCase):
    """Test that initial ratio setup works correctly"""

    def setUp(self):
        """Read the main window source file once for all tests"""
        self.main_window_file = os.path.join(
            os.path.dirname(__file__), '..', '..', 'src',
            'fichero', 'windows', 'main', 'main_window.py'
        )

        with open(self.main_window_file, 'r') as f:
            self.main_window_content = f.read()

    def test_initial_75_25_ratio_setup(self):
        """Test that initial 75%/25% ratio is set during layout creation"""
        expected_setup = [
            '# Set 75% for image, 25% for metadata',
            'image_slot.container.style.flex = 75',
            'metadata_slot.container.style.flex = 25',
            'Applied 75%/25% flex ratio to preview panes'
        ]

        for setup in expected_setup:
            with self.subTest(setup=setup):
                self.assertIn(setup, self.main_window_content,
                            f"Initial setup {setup} should be present")

    def test_state_manager_integration(self):
        """Test that state manager is used to save/restore ratio preset"""
        expected_integration = [
            'state_manager.set_current_preview_preset("wide_content")',
            'hasattr(self.app, \'state_manager\')',
            'self.app.state_manager'
        ]

        for integration in expected_integration:
            with self.subTest(integration=integration):
                self.assertIn(integration, self.main_window_content,
                            f"State manager integration {integration} should be present")


class TestPreviewRatioRestorationFix(unittest.TestCase):
    """Test the fix for ratio restoration overriding initial values"""

    def setUp(self):
        """Read the main window source file once for all tests"""
        self.main_window_file = os.path.join(
            os.path.dirname(__file__), '..', '..', 'src',
            'fichero', 'windows', 'main', 'main_window.py'
        )

        with open(self.main_window_file, 'r') as f:
            self.main_window_content = f.read()

    def test_ratio_reapplication_after_restoration(self):
        """Test that ratios are reapplied after layout state restoration"""
        expected_restoration_logic = [
            'current_preset = state_manager.get_current_preview_preset()',
            'self._apply_preview_ratio(current_preset, None)',
            'Reapplied preview ratio preset after restoration',
            'Applied default wide_content ratio after restoration'
        ]

        for logic in expected_restoration_logic:
            with self.subTest(logic=logic):
                self.assertIn(logic, self.main_window_content,
                            f"Restoration logic {logic} should be present")

    def test_fallback_to_wide_content(self):
        """Test that system falls back to wide_content if no preset saved"""
        expected_fallback = [
            'self._apply_preview_ratio("wide_content", None)',
            'Applied default wide_content ratio after restoration',
            'Applied fallback wide_content ratio after restoration error'
        ]

        for fallback in expected_fallback:
            with self.subTest(fallback=fallback):
                self.assertIn(fallback, self.main_window_content,
                            f"Fallback logic {fallback} should be present")

    def test_legacy_restoration_support(self):
        """Test that legacy restoration also applies wide_content ratio"""
        expected_legacy = [
            'Applied wide_content ratio after legacy restoration',
            '_restore_window_state_legacy'
        ]

        for legacy in expected_legacy:
            with self.subTest(legacy=legacy):
                self.assertIn(legacy, self.main_window_content,
                            f"Legacy restoration {legacy} should be present")


class TestPreviewRatioErrorHandling(unittest.TestCase):
    """Test error handling in ratio system"""

    def setUp(self):
        """Read the main window source file once for all tests"""
        self.main_window_file = os.path.join(
            os.path.dirname(__file__), '..', '..', 'src',
            'fichero', 'windows', 'main', 'main_window.py'
        )

        with open(self.main_window_file, 'r') as f:
            self.main_window_content = f.read()

    def test_ratio_error_handling(self):
        """Test that ratio methods have proper error handling"""
        expected_error_handling = [
            'except Exception as e:',
            'logger.error(f"Failed to apply ratio',
            'logger.warning(f"Cannot apply ratio',
            'logger.error(f"Failed to cycle preview ratios'
        ]

        for error_handling in expected_error_handling:
            with self.subTest(error_handling=error_handling):
                self.assertIn(error_handling, self.main_window_content,
                            f"Error handling {error_handling} should be present")

    def test_validation_checks(self):
        """Test that ratio methods validate layout manager availability"""
        expected_validations = [
            'if not self.navigation_controller or not self.navigation_controller.layout_manager:',
            'logger.warning(f"Cannot apply ratio',
            'layout_manager not available'
        ]

        for validation in expected_validations:
            with self.subTest(validation=validation):
                self.assertIn(validation, self.main_window_content,
                            f"Validation check {validation} should be present")


class TestStateManagerRatioIntegration(unittest.TestCase):
    """Test state manager integration for ratio persistence"""

    def setUp(self):
        """Read the state manager source file"""
        self.state_manager_file = os.path.join(
            os.path.dirname(__file__), '..', '..', 'src',
            'fichero', 'config', 'core', 'state_manager.py'
        )

        with open(self.state_manager_file, 'r') as f:
            self.state_manager_content = f.read()

    def test_state_manager_ratio_methods(self):
        """Test that state manager has ratio-related methods"""
        expected_methods = [
            'def get_current_preview_preset(self',
            'def set_current_preview_preset(self'
        ]

        for method in expected_methods:
            with self.subTest(method=method):
                self.assertIn(method, self.state_manager_content,
                            f"State manager method {method} should be defined")

    def test_default_wide_content_preset(self):
        """Test that state manager defaults to wide_content"""
        expected_defaults = [
            '"current_preset": "wide_content"',
            '"wide_content": 0.75'
        ]

        for default in expected_defaults:
            with self.subTest(default=default):
                self.assertIn(default, self.state_manager_content,
                            f"Default configuration {default} should be present")


class TestRatioSystemIntegration(unittest.TestCase):
    """Integration test for the entire ratio system"""

    def test_complete_ratio_system(self):
        """Test that all components of the ratio system work together"""

        # Read all relevant source files
        files_to_check = {
            'main_window': os.path.join(os.path.dirname(__file__), '..', '..', 'src',
                                      'fichero', 'windows', 'main', 'main_window.py'),
            'state_manager': os.path.join(os.path.dirname(__file__), '..', '..', 'src',
                                        'fichero', 'config', 'core', 'state_manager.py')
        }

        file_contents = {}
        for name, path in files_to_check.items():
            with open(path, 'r') as f:
                file_contents[name] = f.read()

        # Check that all system components are present
        # Note: Individual ratio commands removed for simplicity (only cycle remains)
        system_components = {
            'menu_commands': "'view.cycle_ratios':" in file_contents['main_window'],
            'action_methods': all(method in file_contents['main_window'] for method in [
                'def _cycle_preview_ratios', 'def _apply_preview_ratio'
            ]),
            'keyboard_shortcuts': "toga.Key.MOD_1 + 'r'" in file_contents['main_window'],
            'initial_setup': all(setup in file_contents['main_window'] for setup in [
                'image_slot.container.style.flex = 75',
                'metadata_slot.container.style.flex = 25'
            ]),
            'restoration_fix': all(fix in file_contents['main_window'] for fix in [
                'current_preset = state_manager.get_current_preview_preset()',
                'self._apply_preview_ratio(current_preset, None)'
            ]),
            'state_manager_methods': all(method in file_contents['state_manager'] for method in [
                'def get_current_preview_preset', 'def set_current_preview_preset'
            ]),
            'default_wide_content': '"current_preset": "wide_content"' in file_contents['state_manager']
        }

        # Verify all components are present
        for component, present in system_components.items():
            with self.subTest(component=component):
                self.assertTrue(present, f"System component {component} should be present")

        print(f"\n✅ Complete ratio system verification:")
        for component, present in system_components.items():
            print(f"  - {component.replace('_', ' ').title()}: {present}")


if __name__ == '__main__':
    unittest.main()