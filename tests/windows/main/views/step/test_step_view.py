"""
Unit tests for StepView - Processing steps browser view.

Tests the StepView component that implements BaseViewInterface.
"""

import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import toga
from toga.style import Pack

from fichero.windows.main.views.step import StepView
from fichero.shared.views.view_types import ViewType


class TestStepViewInterface(unittest.TestCase):
    """Test StepView implements BaseViewInterface correctly"""

    def setUp(self):
        """Set up test fixtures"""
        self.view = StepView(view_id="test-step-view-1")

    def test_view_id_property(self):
        """Test view_id property returns correct ID"""
        self.assertEqual(self.view.view_id, "test-step-view-1")

    def test_view_type_property(self):
        """Test view_type property returns ViewType.STEP"""
        self.assertEqual(self.view.view_type, ViewType.STEP)

    def test_container_property(self):
        """Test container property returns toga.Box"""
        self.assertIsInstance(self.view.container, toga.Box)

    def test_initial_focus_state(self):
        """Test initial focus state is False"""
        self.assertFalse(self.view.is_focused)

    def test_set_focused_true(self):
        """Test set_focused(True) applies focus"""
        self.view.set_focused(True)
        self.assertTrue(self.view.is_focused)

    def test_set_focused_false(self):
        """Test set_focused(False) removes focus"""
        self.view.set_focused(True)
        self.assertTrue(self.view.is_focused)

        self.view.set_focused(False)
        self.assertFalse(self.view.is_focused)

    def test_get_state_empty(self):
        """Test get_state() with no steps loaded"""
        state = self.view.get_state()

        self.assertEqual(state['view_id'], 'test-step-view-1')
        self.assertEqual(state['view_type'], 'step')
        self.assertEqual(state['current_index'], 0)
        self.assertEqual(state['total_steps'], 0)
        self.assertEqual(state['step_names'], [])

    def test_get_state_with_steps(self):
        """Test get_state() with steps loaded"""
        steps = [
            {'step_name': 'Original', 'tool_name': 'original', 'file_type': 'image'},
            {'step_name': 'transcribe', 'tool_name': 'transcribe', 'file_type': 'text'},
            {'step_name': 'enhance', 'tool_name': 'enhance', 'file_type': 'image'}
        ]
        self.view.load_steps(steps, current_index=1)

        state = self.view.get_state()

        self.assertEqual(state['view_id'], 'test-step-view-1')
        self.assertEqual(state['view_type'], 'step')
        self.assertEqual(state['current_index'], 1)
        self.assertEqual(state['total_steps'], 3)
        self.assertEqual(state['step_names'], ['Original', 'transcribe', 'enhance'])

    def test_restore_state(self):
        """Test restore_state() restores selection"""
        steps = [
            {'step_name': 'Original', 'tool_name': 'original', 'file_type': 'image'},
            {'step_name': 'transcribe', 'tool_name': 'transcribe', 'file_type': 'text'}
        ]
        self.view.load_steps(steps, current_index=0)

        # Save state at index 1
        state = {'current_index': 1, 'total_steps': 2}

        # Restore state
        self.view.restore_state(state)

        # Check restored
        self.assertEqual(self.view.current_index, 1)

    def test_restore_state_invalid_index(self):
        """Test restore_state() handles invalid index gracefully"""
        steps = [
            {'step_name': 'Original', 'tool_name': 'original', 'file_type': 'image'}
        ]
        self.view.load_steps(steps, current_index=0)

        # Try to restore out-of-range index
        state = {'current_index': 999}
        self.view.restore_state(state)

        # Should remain at valid index
        self.assertEqual(self.view.current_index, 0)


class TestStepViewStepManagement(unittest.TestCase):
    """Test step loading and management"""

    def setUp(self):
        """Set up test fixtures"""
        self.view = StepView(view_id="test-step-view-2")
        self.callback_called = False
        self.callback_index = None

    def callback(self, index):
        """Test callback for step selection"""
        self.callback_called = True
        self.callback_index = index

    def test_load_steps_empty(self):
        """Test loading empty steps list"""
        self.view.load_steps([], current_index=0)

        self.assertEqual(len(self.view.steps), 0)
        self.assertEqual(self.view.current_index, 0)

    def test_load_steps_single(self):
        """Test loading single step"""
        steps = [
            {'step_name': 'Original', 'tool_name': 'original', 'file_type': 'image'}
        ]
        self.view.load_steps(steps, current_index=0)

        self.assertEqual(len(self.view.steps), 1)
        self.assertEqual(self.view.current_index, 0)

    def test_load_steps_multiple(self):
        """Test loading multiple steps"""
        steps = [
            {'step_name': 'Original', 'tool_name': 'original', 'file_type': 'image'},
            {'step_name': 'transcribe', 'tool_name': 'transcribe', 'file_type': 'text'},
            {'step_name': 'enhance', 'tool_name': 'enhance', 'file_type': 'image'}
        ]
        self.view.load_steps(steps, current_index=1)

        self.assertEqual(len(self.view.steps), 3)
        self.assertEqual(self.view.current_index, 1)

    def test_load_steps_triggers_callback(self):
        """Test load_steps triggers initial callback"""
        self.view.on_step_selected = self.callback

        steps = [
            {'step_name': 'Original', 'tool_name': 'original', 'file_type': 'image'}
        ]
        self.view.load_steps(steps, current_index=0)

        self.assertTrue(self.callback_called)
        self.assertEqual(self.callback_index, 0)

    def test_set_current_index_valid(self):
        """Test set_current_index with valid index"""
        steps = [
            {'step_name': 'Original', 'tool_name': 'original', 'file_type': 'image'},
            {'step_name': 'transcribe', 'tool_name': 'transcribe', 'file_type': 'text'}
        ]
        self.view.load_steps(steps, current_index=0)
        self.callback_called = False  # Reset after load_steps

        self.view.on_step_selected = self.callback
        self.view.set_current_index(1)

        self.assertEqual(self.view.current_index, 1)
        self.assertTrue(self.callback_called)
        self.assertEqual(self.callback_index, 1)

    def test_set_current_index_invalid(self):
        """Test set_current_index with invalid index (no-op)"""
        steps = [
            {'step_name': 'Original', 'tool_name': 'original', 'file_type': 'image'}
        ]
        self.view.load_steps(steps, current_index=0)

        # Try to set invalid index
        self.view.set_current_index(999)

        # Should remain at 0 (set_current_index checks bounds)
        self.assertEqual(self.view.current_index, 0)

    def test_get_current_step(self):
        """Test get_current_step returns correct step data"""
        steps = [
            {'step_name': 'Original', 'tool_name': 'original', 'file_type': 'image'},
            {'step_name': 'transcribe', 'tool_name': 'transcribe', 'file_type': 'text'}
        ]
        self.view.load_steps(steps, current_index=1)

        current_step = self.view.get_current_step()

        self.assertIsNotNone(current_step)
        self.assertEqual(current_step['step_name'], 'transcribe')
        self.assertEqual(current_step['tool_name'], 'transcribe')

    def test_get_current_step_no_steps(self):
        """Test get_current_step with no steps returns None"""
        current_step = self.view.get_current_step()
        self.assertIsNone(current_step)

    def test_clear(self):
        """Test clear() removes all steps"""
        steps = [
            {'step_name': 'Original', 'tool_name': 'original', 'file_type': 'image'}
        ]
        self.view.load_steps(steps, current_index=0)

        self.view.clear()

        self.assertEqual(len(self.view.steps), 0)
        self.assertEqual(self.view.current_index, 0)


class TestStepViewMultipleInstances(unittest.TestCase):
    """Test multiple StepView instances are independent"""

    def test_multiple_views_independent_state(self):
        """Test multiple views maintain independent state"""
        view1 = StepView(view_id="view-1")
        view2 = StepView(view_id="view-2")

        steps1 = [
            {'step_name': 'Original', 'tool_name': 'original', 'file_type': 'image'}
        ]
        steps2 = [
            {'step_name': 'Original', 'tool_name': 'original', 'file_type': 'image'},
            {'step_name': 'transcribe', 'tool_name': 'transcribe', 'file_type': 'text'}
        ]

        view1.load_steps(steps1, current_index=0)
        view2.load_steps(steps2, current_index=1)

        # Check independence
        self.assertEqual(view1.view_id, "view-1")
        self.assertEqual(view2.view_id, "view-2")
        self.assertEqual(len(view1.steps), 1)
        self.assertEqual(len(view2.steps), 2)
        self.assertEqual(view1.current_index, 0)
        self.assertEqual(view2.current_index, 1)

    def test_multiple_views_independent_focus(self):
        """Test multiple views maintain independent focus state"""
        view1 = StepView(view_id="view-1")
        view2 = StepView(view_id="view-2")

        view1.set_focused(True)

        self.assertTrue(view1.is_focused)
        self.assertFalse(view2.is_focused)


class TestStepViewCallbacks(unittest.TestCase):
    """Test callback system"""

    def setUp(self):
        """Set up test fixtures"""
        self.view = StepView(view_id="test-step-view-3")
        self.callback_count = 0
        self.callback_indices = []

    def callback(self, index):
        """Test callback"""
        self.callback_count += 1
        self.callback_indices.append(index)

    def test_callback_on_load(self):
        """Test callback is called on initial load"""
        self.view.on_step_selected = self.callback

        steps = [
            {'step_name': 'Original', 'tool_name': 'original', 'file_type': 'image'}
        ]
        self.view.load_steps(steps, current_index=0)

        self.assertEqual(self.callback_count, 1)
        self.assertEqual(self.callback_indices, [0])

    def test_callback_on_set_current_index(self):
        """Test callback is called when changing index"""
        steps = [
            {'step_name': 'Original', 'tool_name': 'original', 'file_type': 'image'},
            {'step_name': 'transcribe', 'tool_name': 'transcribe', 'file_type': 'text'}
        ]
        self.view.load_steps(steps, current_index=0)

        # Reset after initial load
        self.callback_count = 0
        self.callback_indices = []

        self.view.on_step_selected = self.callback
        self.view.set_current_index(1)

        self.assertEqual(self.callback_count, 1)
        self.assertEqual(self.callback_indices, [1])

    def test_no_callback_when_none_set(self):
        """Test no error when callback is None"""
        steps = [
            {'step_name': 'Original', 'tool_name': 'original', 'file_type': 'image'}
        ]
        # Should not raise error
        self.view.load_steps(steps, current_index=0)


class TestStepViewEdgeCases(unittest.TestCase):
    """Test edge cases and error conditions"""

    def test_restore_state_with_none(self):
        """Test restore_state with None state"""
        view = StepView(view_id="test")
        # Should not raise error
        view.restore_state(None)

    def test_restore_state_with_empty_dict(self):
        """Test restore_state with empty dict"""
        view = StepView(view_id="test")
        # Should not raise error
        view.restore_state({})

    def test_load_steps_preserves_extra_data(self):
        """Test load_steps preserves extra step data"""
        view = StepView(view_id="test")

        steps = [
            {
                'step_name': 'Original',
                'tool_name': 'original',
                'file_type': 'image',
                'custom_field': 'custom_value',
                'another_field': 123
            }
        ]
        view.load_steps(steps, current_index=0)

        current_step = view.get_current_step()
        self.assertEqual(current_step['custom_field'], 'custom_value')
        self.assertEqual(current_step['another_field'], 123)

    def test_set_current_index_before_load(self):
        """Test set_current_index before loading steps (no-op)"""
        view = StepView(view_id="test")
        # Should not raise error
        view.set_current_index(0)


class TestStepViewImport(unittest.TestCase):
    """Test module imports"""

    def test_import_from_module(self):
        """Test StepView can be imported from module"""
        from fichero.windows.main.views.step import StepView as SV
        self.assertEqual(SV.__name__, 'StepView')

    def test_import_directly(self):
        """Test StepView can be imported directly"""
        from fichero.windows.main.views.step.step_view import StepView as SV
        self.assertEqual(SV.__name__, 'StepView')


if __name__ == '__main__':
    unittest.main()
