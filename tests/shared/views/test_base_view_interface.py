"""
Unit tests for BaseViewInterface and ViewType.

Tests the abstract interface contract that all views must implement
for the universal navigation system.
"""

import unittest
from typing import Dict, Any
import toga
from toga.style import Pack

from fichero.shared.views.base_view_interface import BaseViewInterface
from fichero.shared.views.view_types import ViewType


class TestViewType(unittest.TestCase):
    """Test ViewType enum"""

    def test_all_view_types_exist(self):
        """Verify all expected view types are defined"""
        expected_types = [
            'LIBRARY', 'COLLECTION', 'STEP', 'ADJUST',
            'PREVIEW', 'INSPECTOR', 'ACTIVITY', 'SETTINGS', 'PLANS'
        ]

        for type_name in expected_types:
            self.assertTrue(
                hasattr(ViewType, type_name),
                f"ViewType.{type_name} should exist"
            )

    def test_view_type_values_are_unique(self):
        """Verify each ViewType enum value is unique"""
        values = [vt.value for vt in ViewType]
        self.assertEqual(
            len(values),
            len(set(values)),
            "All ViewType values should be unique"
        )

    def test_view_type_names_are_unique(self):
        """Verify each ViewType enum name is unique"""
        names = [vt.name for vt in ViewType]
        self.assertEqual(
            len(names),
            len(set(names)),
            "All ViewType names should be unique"
        )

    def test_view_type_values_are_lowercase(self):
        """Verify ViewType values are lowercase strings"""
        for vt in ViewType:
            self.assertIsInstance(vt.value, str)
            self.assertEqual(
                vt.value.lower(),
                vt.value,
                f"ViewType.{vt.name} value should be lowercase"
            )

    def test_library_view_type(self):
        """Test LIBRARY view type specifically"""
        self.assertEqual(ViewType.LIBRARY.value, "library")

    def test_collection_view_type(self):
        """Test COLLECTION view type specifically"""
        self.assertEqual(ViewType.COLLECTION.value, "collection")

    def test_step_view_type(self):
        """Test STEP view type specifically"""
        self.assertEqual(ViewType.STEP.value, "step")

    def test_preview_view_type(self):
        """Test PREVIEW view type specifically"""
        self.assertEqual(ViewType.PREVIEW.value, "preview")


class MockView(BaseViewInterface):
    """
    Mock view implementation for testing BaseViewInterface.

    Implements all required methods to verify the interface contract.
    """

    def __init__(self, view_id: str = "mock_view", view_type: ViewType = ViewType.LIBRARY):
        self._view_id = view_id
        self._view_type = view_type
        self._is_focused = False
        self._container = toga.Box(style=Pack(direction='column', flex=1))
        self._toolbar = toga.Box(style=Pack(direction='row'))
        self._state = {}
        self._can_close = True

    @property
    def view_id(self) -> str:
        return self._view_id

    @property
    def view_type(self) -> ViewType:
        return self._view_type

    @property
    def container(self) -> toga.Box:
        return self._container

    @property
    def toolbar(self) -> toga.Box:
        return self._toolbar

    @property
    def is_focused(self) -> bool:
        return self._is_focused

    def set_focused(self, focused: bool):
        self._is_focused = focused

    def get_state(self) -> Dict[str, Any]:
        return {
            'view_id': self._view_id,
            'view_type': self._view_type.value,
            'is_focused': self._is_focused,
            **self._state
        }

    def restore_state(self, state: Dict[str, Any]):
        if 'is_focused' in state:
            self._is_focused = state['is_focused']
        self._state = {k: v for k, v in state.items()
                      if k not in ['view_id', 'view_type', 'is_focused']}

    def can_close(self) -> bool:
        return self._can_close

    def on_close(self):
        # Cleanup mock resources
        self._state = {}

    def get_title(self) -> str:
        return f"Mock {self._view_type.value.capitalize()}"


class TestBaseViewInterface(unittest.TestCase):
    """Test BaseViewInterface implementation and contract"""

    def setUp(self):
        """Set up test fixtures"""
        self.view = MockView(view_id="test_view", view_type=ViewType.LIBRARY)

    def test_view_id_property(self):
        """Test view_id property returns correct value"""
        self.assertEqual(self.view.view_id, "test_view")

    def test_view_type_property(self):
        """Test view_type property returns ViewType enum"""
        self.assertIsInstance(self.view.view_type, ViewType)
        self.assertEqual(self.view.view_type, ViewType.LIBRARY)

    def test_container_property(self):
        """Test container property returns toga.Box"""
        self.assertIsInstance(self.view.container, toga.Box)

    def test_toolbar_property(self):
        """Test toolbar property returns toga.Box or None"""
        toolbar = self.view.toolbar
        self.assertTrue(
            toolbar is None or isinstance(toolbar, toga.Box),
            "toolbar should be None or toga.Box"
        )

    def test_is_focused_property_initial_state(self):
        """Test is_focused starts as False"""
        self.assertFalse(self.view.is_focused)

    def test_set_focused_updates_state(self):
        """Test set_focused updates focus state"""
        self.assertFalse(self.view.is_focused)

        self.view.set_focused(True)
        self.assertTrue(self.view.is_focused)

        self.view.set_focused(False)
        self.assertFalse(self.view.is_focused)

    def test_get_state_returns_dict(self):
        """Test get_state returns dictionary"""
        state = self.view.get_state()
        self.assertIsInstance(state, dict)

    def test_get_state_includes_view_id(self):
        """Test get_state includes view_id"""
        state = self.view.get_state()
        self.assertIn('view_id', state)
        self.assertEqual(state['view_id'], "test_view")

    def test_get_state_includes_view_type(self):
        """Test get_state includes view_type"""
        state = self.view.get_state()
        self.assertIn('view_type', state)
        self.assertEqual(state['view_type'], ViewType.LIBRARY.value)

    def test_restore_state_basic(self):
        """Test restore_state restores view state"""
        # Set initial state
        self.view.set_focused(True)
        self.view._state = {'custom_key': 'custom_value'}

        # Get state
        state = self.view.get_state()

        # Create new view and restore state
        new_view = MockView()
        new_view.restore_state(state)

        # Verify state was restored
        self.assertEqual(new_view.is_focused, True)
        self.assertEqual(new_view._state.get('custom_key'), 'custom_value')

    def test_restore_state_handles_missing_keys(self):
        """Test restore_state handles missing keys gracefully"""
        # Should not raise exception when keys are missing
        try:
            self.view.restore_state({})
            self.view.restore_state({'unknown_key': 'value'})
        except KeyError:
            self.fail("restore_state should handle missing keys gracefully")

    def test_can_close_returns_bool(self):
        """Test can_close returns boolean"""
        result = self.view.can_close()
        self.assertIsInstance(result, bool)

    def test_can_close_default_true(self):
        """Test can_close defaults to True"""
        self.assertTrue(self.view.can_close())

    def test_on_close_callable(self):
        """Test on_close can be called without error"""
        try:
            self.view.on_close()
        except Exception as e:
            self.fail(f"on_close should be callable without error: {e}")

    def test_get_title_returns_string(self):
        """Test get_title returns string"""
        title = self.view.get_title()
        self.assertIsInstance(title, str)

    def test_get_title_default_implementation(self):
        """Test get_title default implementation"""
        title = self.view.get_title()
        self.assertTrue(len(title) > 0, "Title should not be empty")

    def test_get_menu_commands_returns_list(self):
        """Test get_menu_commands returns list"""
        commands = self.view.get_menu_commands()
        self.assertIsInstance(commands, list)

    def test_get_menu_commands_default_empty(self):
        """Test get_menu_commands defaults to empty list"""
        commands = self.view.get_menu_commands()
        self.assertEqual(len(commands), 0)


class TestBaseViewInterfaceMultipleViews(unittest.TestCase):
    """Test BaseViewInterface with multiple view instances"""

    def test_multiple_views_have_unique_ids(self):
        """Test multiple views can have unique IDs"""
        view1 = MockView(view_id="view_1", view_type=ViewType.LIBRARY)
        view2 = MockView(view_id="view_2", view_type=ViewType.COLLECTION)

        self.assertNotEqual(view1.view_id, view2.view_id)

    def test_multiple_views_can_have_different_types(self):
        """Test multiple views can have different types"""
        view1 = MockView(view_id="view_1", view_type=ViewType.LIBRARY)
        view2 = MockView(view_id="view_2", view_type=ViewType.PREVIEW)

        self.assertNotEqual(view1.view_type, view2.view_type)

    def test_focus_state_independent_per_view(self):
        """Test focus state is independent for each view"""
        view1 = MockView(view_id="view_1")
        view2 = MockView(view_id="view_2")

        view1.set_focused(True)
        view2.set_focused(False)

        self.assertTrue(view1.is_focused)
        self.assertFalse(view2.is_focused)

    def test_state_independent_per_view(self):
        """Test state is independent for each view"""
        view1 = MockView(view_id="view_1")
        view2 = MockView(view_id="view_2")

        view1._state = {'key': 'value1'}
        view2._state = {'key': 'value2'}

        state1 = view1.get_state()
        state2 = view2.get_state()

        # States should not be equal (different view_ids at minimum)
        self.assertNotEqual(state1, state2)


class TestBaseViewInterfaceEdgeCases(unittest.TestCase):
    """Test edge cases and error handling"""

    def test_toolbar_can_be_none(self):
        """Test toolbar property can return None"""
        view = MockView()
        view._toolbar = None
        self.assertIsNone(view.toolbar)

    def test_empty_state_restoration(self):
        """Test restoring from empty state dictionary"""
        view = MockView()
        view.restore_state({})
        # Should not raise error
        self.assertIsNotNone(view.view_id)

    def test_state_with_complex_data(self):
        """Test state can handle complex nested data"""
        view = MockView()
        view._state = {
            'nested': {'key': 'value'},
            'list': [1, 2, 3],
            'mixed': {'list': [{'nested': 'data'}]}
        }

        state = view.get_state()
        self.assertIn('nested', state)
        self.assertIn('list', state)
        self.assertIn('mixed', state)

    def test_all_view_types_can_be_used(self):
        """Test all ViewType enums can be used to create views"""
        for view_type in ViewType:
            view = MockView(view_id=f"view_{view_type.value}", view_type=view_type)
            self.assertEqual(view.view_type, view_type)


class TestBackwardCompatibility(unittest.TestCase):
    """Test backward compatibility features"""

    def test_view_type_import_from_views_module(self):
        """Test ViewType can be imported from shared.views"""
        from fichero.shared.views import NavigationViewType
        self.assertEqual(NavigationViewType.LIBRARY.value, "library")

    def test_base_view_interface_import(self):
        """Test BaseViewInterface can be imported from shared.views"""
        from fichero.shared.views import BaseViewInterface as BVI
        self.assertTrue(hasattr(BVI, 'view_id'))
        self.assertTrue(hasattr(BVI, 'view_type'))


if __name__ == '__main__':
    unittest.main()
