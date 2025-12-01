"""
Unit tests for Preview Metadata Pane components

Tests for:
- DisplayProfile and display_profiles module
- MetadataFieldRegistry
- StateManager metadata pane methods
"""

import unittest
import tempfile
import json
from pathlib import Path
from unittest.mock import MagicMock, patch


class TestDisplayProfiles(unittest.TestCase):
    """Tests for display_profiles.py"""

    def setUp(self):
        """Set up test fixtures"""
        # Import directly to avoid Toga dependency
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            'display_profiles',
            'src/fichero/windows/main/views/preview/display_profiles.py'
        )
        self.display_profiles = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.display_profiles)

    def test_display_profile_creation(self):
        """Test DisplayProfile dataclass creation"""
        profile = self.display_profiles.DisplayProfile(
            profile_id="test_profile",
            item_type="file",
            visible_fields=["title", "date", "author"],
            is_default=False
        )

        self.assertEqual(profile.profile_id, "test_profile")
        self.assertEqual(profile.item_type, "file")
        self.assertEqual(profile.visible_fields, ["title", "date", "author"])
        self.assertFalse(profile.is_default)

    def test_display_profile_add_field(self):
        """Test adding fields to profile"""
        profile = self.display_profiles.DisplayProfile(
            profile_id="test",
            item_type="file",
            visible_fields=["title", "date"]
        )

        # Add field at end
        result = profile.add_field("author")
        self.assertTrue(result)
        self.assertEqual(profile.visible_fields, ["title", "date", "author"])

        # Add field at position
        result = profile.add_field("description", position=1)
        self.assertTrue(result)
        self.assertEqual(profile.visible_fields, ["title", "description", "date", "author"])

        # Try to add duplicate
        result = profile.add_field("title")
        self.assertFalse(result)

    def test_display_profile_remove_field(self):
        """Test removing fields from profile"""
        profile = self.display_profiles.DisplayProfile(
            profile_id="test",
            item_type="file",
            visible_fields=["title", "date", "author"]
        )

        # Remove existing field
        result = profile.remove_field("date")
        self.assertTrue(result)
        self.assertEqual(profile.visible_fields, ["title", "author"])

        # Try to remove non-existent field
        result = profile.remove_field("nonexistent")
        self.assertFalse(result)

    def test_display_profile_move_field(self):
        """Test moving fields within profile"""
        profile = self.display_profiles.DisplayProfile(
            profile_id="test",
            item_type="file",
            visible_fields=["title", "date", "author", "description"]
        )

        # Move field to new position
        result = profile.move_field("author", 0)
        self.assertTrue(result)
        self.assertEqual(profile.visible_fields, ["author", "title", "date", "description"])

        # Move to end
        result = profile.move_field("title", 10)  # Beyond end
        self.assertTrue(result)
        self.assertEqual(profile.visible_fields, ["author", "date", "description", "title"])

        # Try to move non-existent field
        result = profile.move_field("nonexistent", 0)
        self.assertFalse(result)

    def test_display_profile_to_dict(self):
        """Test serialization to dict"""
        profile = self.display_profiles.DisplayProfile(
            profile_id="test_profile",
            item_type="file",
            visible_fields=["title", "date"],
            is_default=True
        )

        data = profile.to_dict()

        self.assertEqual(data["profile_id"], "test_profile")
        self.assertEqual(data["item_type"], "file")
        self.assertEqual(data["visible_fields"], ["title", "date"])
        self.assertTrue(data["is_default"])

    def test_display_profile_from_dict(self):
        """Test deserialization from dict"""
        data = {
            "profile_id": "imported_profile",
            "item_type": "folder",
            "visible_fields": ["title", "description"],
            "is_default": False
        }

        profile = self.display_profiles.DisplayProfile.from_dict(data)

        self.assertEqual(profile.profile_id, "imported_profile")
        self.assertEqual(profile.item_type, "folder")
        self.assertEqual(profile.visible_fields, ["title", "description"])
        self.assertFalse(profile.is_default)

    def test_default_profiles_exist(self):
        """Test that default profiles exist for all item types"""
        expected_types = ["file", "folder", "url", "camera", "audio"]

        for item_type in expected_types:
            self.assertIn(item_type, self.display_profiles.DEFAULT_PROFILES)
            profile = self.display_profiles.DEFAULT_PROFILES[item_type]
            self.assertEqual(profile.item_type, item_type)
            self.assertTrue(profile.is_default)
            self.assertGreater(len(profile.visible_fields), 0)

    def test_get_default_profile(self):
        """Test get_default_profile function"""
        # Get known type
        profile = self.display_profiles.get_default_profile("file")
        self.assertEqual(profile.item_type, "file")
        self.assertTrue(profile.is_default)
        self.assertIn("title", profile.visible_fields)

        # Get unknown type (should fall back to file)
        profile = self.display_profiles.get_default_profile("unknown_type")
        self.assertEqual(profile.item_type, "unknown_type")  # Uses requested type
        self.assertTrue(profile.is_default)

    def test_create_custom_profile(self):
        """Test create_custom_profile function"""
        profile = self.display_profiles.create_custom_profile(
            "file",
            ["title", "author", "subjects"]
        )

        self.assertEqual(profile.profile_id, "file_custom")
        self.assertEqual(profile.item_type, "file")
        self.assertEqual(profile.visible_fields, ["title", "author", "subjects"])
        self.assertFalse(profile.is_default)


class TestFieldRegistry(unittest.TestCase):
    """Tests for field_registry.py"""

    def setUp(self):
        """Set up test fixtures"""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            'field_registry',
            'src/fichero/windows/main/views/preview/field_registry.py'
        )
        self.field_registry = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.field_registry)

    def test_field_info_structure(self):
        """Test FieldInfo dataclass"""
        field = self.field_registry.FieldInfo(
            key="test_field",
            label="Test Field",
            description="A test field",
            schema_type="catalogue",
            field_type="str",
            editable=True
        )

        self.assertEqual(field.key, "test_field")
        self.assertEqual(field.label, "Test Field")
        self.assertEqual(field.schema_type, "catalogue")
        self.assertTrue(field.editable)

    def test_get_field_info(self):
        """Test getting field info by key"""
        Registry = self.field_registry.MetadataFieldRegistry

        # Get existing field
        field = Registry.get_field_info("title")
        self.assertIsNotNone(field)
        self.assertEqual(field.key, "title")
        self.assertEqual(field.label, "Title")
        self.assertEqual(field.schema_type, "catalogue")

        # Get non-existent field
        field = Registry.get_field_info("nonexistent")
        self.assertIsNone(field)

    def test_get_all_fields(self):
        """Test getting all fields"""
        Registry = self.field_registry.MetadataFieldRegistry

        fields = Registry.get_all_fields()

        self.assertGreater(len(fields), 0)
        self.assertTrue(all(hasattr(f, 'key') for f in fields))
        self.assertTrue(all(hasattr(f, 'label') for f in fields))

    def test_get_fields_by_schema(self):
        """Test filtering fields by schema type"""
        Registry = self.field_registry.MetadataFieldRegistry

        # Catalogue fields
        catalogue_fields = Registry.get_fields_by_schema("catalogue")
        self.assertGreater(len(catalogue_fields), 0)
        self.assertTrue(all(f.schema_type == "catalogue" for f in catalogue_fields))

        # Transcription fields
        transcription_fields = Registry.get_fields_by_schema("transcription")
        self.assertTrue(all(f.schema_type == "transcription" for f in transcription_fields))

    def test_get_editable_fields(self):
        """Test getting only editable fields"""
        Registry = self.field_registry.MetadataFieldRegistry

        editable = Registry.get_editable_fields()

        self.assertGreater(len(editable), 0)
        self.assertTrue(all(f.editable for f in editable))

    def test_get_catalogue_fields(self):
        """Test getting catalogue fields"""
        Registry = self.field_registry.MetadataFieldRegistry

        fields = Registry.get_catalogue_fields()

        expected_keys = ["title", "description", "date", "author", "location",
                        "document_type", "language", "subjects"]

        field_keys = [f.key for f in fields]
        for expected in expected_keys:
            self.assertIn(expected, field_keys)

    def test_get_available_fields(self):
        """Test getting available fields for display"""
        Registry = self.field_registry.MetadataFieldRegistry

        # Without item type filter
        fields = Registry.get_available_fields()
        self.assertGreater(len(fields), 0)

        # With item type filter (currently returns same)
        fields = Registry.get_available_fields("file")
        self.assertGreater(len(fields), 0)

    def test_get_readonly_fields(self):
        """Test getting read-only fields"""
        Registry = self.field_registry.MetadataFieldRegistry

        readonly = Registry.get_readonly_fields()

        self.assertTrue(all(not f.editable for f in readonly))
        # Check known readonly fields exist
        keys = [f.key for f in readonly]
        self.assertIn("confidence", keys)
        self.assertIn("word_count", keys)

    def test_field_exists(self):
        """Test field existence check"""
        Registry = self.field_registry.MetadataFieldRegistry

        self.assertTrue(Registry.field_exists("title"))
        self.assertTrue(Registry.field_exists("date"))
        self.assertFalse(Registry.field_exists("nonexistent"))

    def test_get_field_label(self):
        """Test getting field labels"""
        Registry = self.field_registry.MetadataFieldRegistry

        # Existing field
        label = Registry.get_field_label("document_type")
        self.assertEqual(label, "Document Type")

        # Non-existent field (should format key)
        label = Registry.get_field_label("unknown_field")
        self.assertEqual(label, "Unknown Field")

    def test_get_all_field_keys(self):
        """Test getting all field keys"""
        Registry = self.field_registry.MetadataFieldRegistry

        keys = Registry.get_all_field_keys()

        self.assertIsInstance(keys, list)
        self.assertIn("title", keys)
        self.assertIn("description", keys)


class TestStateManagerMetadataPane(unittest.TestCase):
    """Tests for StateManager preview_metadata_pane methods"""

    def setUp(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()
        self.state_file = Path(self.temp_dir) / "app_state.json"

        # Create mock app
        self.mock_app = MagicMock()
        self.mock_app.paths.data = Path(self.temp_dir)

        # Patch the state file path discovery
        self.patcher = patch(
            'fichero.config.core.state_manager.StateManager._get_state_file_path',
            return_value=self.state_file
        )
        self.patcher.start()

        # Import StateManager
        from fichero.config.core.state_manager import StateManager
        self.StateManager = StateManager

    def tearDown(self):
        """Clean up"""
        self.patcher.stop()
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_default_metadata_pane_state(self):
        """Test default preview_metadata_pane state"""
        manager = self.StateManager(self.mock_app)
        default_state = manager._default_state()

        self.assertIn("preview_metadata_pane", default_state)
        pane_state = default_state["preview_metadata_pane"]

        self.assertIn("is_expanded", pane_state)
        self.assertIn("display_profiles", pane_state)
        self.assertTrue(pane_state["is_expanded"])
        self.assertEqual(pane_state["display_profiles"], {})

    def test_get_set_metadata_pane_expanded(self):
        """Test getting/setting expanded state"""
        manager = self.StateManager(self.mock_app)

        # Default is expanded
        self.assertTrue(manager.get_metadata_pane_expanded())

        # Set to collapsed
        manager.set_metadata_pane_expanded(False)
        self.assertFalse(manager.get_metadata_pane_expanded())

        # Set back to expanded
        manager.set_metadata_pane_expanded(True)
        self.assertTrue(manager.get_metadata_pane_expanded())

    def test_get_display_profile_returns_none_for_default(self):
        """Test that get_display_profile returns None when no custom profile"""
        manager = self.StateManager(self.mock_app)

        # No custom profile set
        profile = manager.get_display_profile("file")
        self.assertIsNone(profile)

    def test_set_and_get_display_profile(self):
        """Test setting and getting custom display profiles"""
        manager = self.StateManager(self.mock_app)

        # Set custom profile for file type
        custom_fields = ["title", "author", "subjects"]
        manager.set_display_profile("file", custom_fields)

        # Get it back
        profile = manager.get_display_profile("file")
        self.assertEqual(profile, custom_fields)

        # Other types should still be None
        self.assertIsNone(manager.get_display_profile("folder"))

    def test_display_profile_is_copied(self):
        """Test that display profile lists are copied"""
        manager = self.StateManager(self.mock_app)

        original = ["title", "date"]
        manager.set_display_profile("file", original)

        # Modify original
        original.append("author")

        # Stored should be unaffected
        stored = manager.get_display_profile("file")
        self.assertEqual(stored, ["title", "date"])

    def test_clear_display_profile(self):
        """Test clearing a display profile"""
        manager = self.StateManager(self.mock_app)

        # Set profile
        manager.set_display_profile("file", ["title", "date"])
        self.assertIsNotNone(manager.get_display_profile("file"))

        # Clear it
        manager.clear_display_profile("file")
        self.assertIsNone(manager.get_display_profile("file"))

        # Clearing non-existent should not error
        manager.clear_display_profile("nonexistent")

    def test_get_all_display_profiles(self):
        """Test getting all display profiles"""
        manager = self.StateManager(self.mock_app)

        # Set multiple profiles
        manager.set_display_profile("file", ["title", "date"])
        manager.set_display_profile("folder", ["title", "description"])

        all_profiles = manager.get_all_display_profiles()

        self.assertEqual(len(all_profiles), 2)
        self.assertEqual(all_profiles["file"], ["title", "date"])
        self.assertEqual(all_profiles["folder"], ["title", "description"])

    def test_display_profiles_persist(self):
        """Test that display profiles persist across saves"""
        manager = self.StateManager(self.mock_app)

        manager.set_display_profile("file", ["title", "author"])
        manager.set_metadata_pane_expanded(False)
        manager.save_state_sync()

        # Create new manager (loads from file)
        manager2 = self.StateManager(self.mock_app)

        self.assertEqual(manager2.get_display_profile("file"), ["title", "author"])
        self.assertFalse(manager2.get_metadata_pane_expanded())


class TestCollapsibleSection(unittest.TestCase):
    """Tests for CollapsibleSection widget logic (mocked Toga)"""

    def setUp(self):
        """Set up test fixtures with mocked Toga"""
        # Mock Toga widgets
        self.toga_patcher = patch.dict('sys.modules', {
            'toga': MagicMock(),
            'toga.style': MagicMock(),
            'toga.style.Pack': MagicMock(),
            'toga.constants': MagicMock(),
        })
        self.toga_patcher.start()

        # Import after mocking
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            'collapsible_section',
            'src/fichero/shared/widgets/collapsible_section.py'
        )
        self.cs_module = importlib.util.module_from_spec(spec)

        # Set up module-level mocks
        import toga
        toga.Box = MagicMock()
        toga.Button = MagicMock()
        toga.Label = MagicMock()

        spec.loader.exec_module(self.cs_module)

    def tearDown(self):
        """Clean up mocks"""
        self.toga_patcher.stop()

    def test_disclosure_symbols(self):
        """Test disclosure triangle symbols are defined (small triangles)"""
        self.assertEqual(self.cs_module.CollapsibleSection.DISCLOSURE_EXPANDED, "\u25BE")
        self.assertEqual(self.cs_module.CollapsibleSection.DISCLOSURE_COLLAPSED, "\u25B8")

    def test_header_height(self):
        """Test header height constant (compact)"""
        self.assertEqual(self.cs_module.CollapsibleSection.HEADER_HEIGHT, 20)

    def test_initial_expanded_state(self):
        """Test section can be created in expanded state"""
        section = self.cs_module.CollapsibleSection(
            title="Test",
            is_expanded=True
        )
        self.assertTrue(section.is_expanded)

    def test_initial_collapsed_state(self):
        """Test section can be created in collapsed state"""
        section = self.cs_module.CollapsibleSection(
            title="Test",
            is_expanded=False
        )
        self.assertFalse(section.is_expanded)

    def test_toggle(self):
        """Test toggle method"""
        section = self.cs_module.CollapsibleSection(
            title="Test",
            is_expanded=True
        )
        section.toggle()
        self.assertFalse(section.is_expanded)
        section.toggle()
        self.assertTrue(section.is_expanded)

    def test_set_expanded(self):
        """Test set_expanded method"""
        section = self.cs_module.CollapsibleSection(
            title="Test",
            is_expanded=False
        )
        section.set_expanded(True)
        self.assertTrue(section.is_expanded)
        section.set_expanded(False)
        self.assertFalse(section.is_expanded)

    def test_set_expanded_no_change(self):
        """Test set_expanded doesn't trigger callback when state unchanged"""
        callback = MagicMock()
        section = self.cs_module.CollapsibleSection(
            title="Test",
            is_expanded=True,
            on_toggle=callback
        )
        section.set_expanded(True)
        callback.assert_not_called()

    def test_toggle_callback(self):
        """Test toggle callback is called"""
        callback = MagicMock()
        section = self.cs_module.CollapsibleSection(
            title="Test",
            is_expanded=True,
            on_toggle=callback
        )
        section.toggle()
        callback.assert_called_once_with(False)

    def test_set_title(self):
        """Test set_title method"""
        section = self.cs_module.CollapsibleSection(title="Original")
        section.set_title("Updated")
        self.assertEqual(section.title, "Updated")

    def test_settings_button_optional(self):
        """Test settings button can be hidden"""
        section_with = self.cs_module.CollapsibleSection(
            title="Test",
            show_settings=True
        )
        self.assertIsNotNone(section_with.settings_button)

        section_without = self.cs_module.CollapsibleSection(
            title="Test",
            show_settings=False
        )
        self.assertIsNone(section_without.settings_button)


class TestMetadataFieldWidget(unittest.TestCase):
    """Tests for MetadataFieldWidget logic (mocked Toga)"""

    def setUp(self):
        """Set up test fixtures with mocked Toga"""
        # Mock Toga widgets
        self.toga_patcher = patch.dict('sys.modules', {
            'toga': MagicMock(),
            'toga.style': MagicMock(),
            'toga.style.Pack': MagicMock(),
            'toga.constants': MagicMock(),
        })
        self.toga_patcher.start()

        # Import after mocking
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            'metadata_field',
            'src/fichero/shared/widgets/metadata_field.py'
        )
        self.mf_module = importlib.util.module_from_spec(spec)

        # Set up module-level mocks
        import toga
        toga.Box = MagicMock()
        toga.Label = MagicMock()
        toga.TextInput = MagicMock()
        toga.MultilineTextInput = MagicMock()

        spec.loader.exec_module(self.mf_module)

    def tearDown(self):
        """Clean up mocks"""
        self.toga_patcher.stop()

    def test_label_color(self):
        """Test label color constant"""
        self.assertEqual(self.mf_module.MetadataFieldWidget.LABEL_COLOR, "#666")

    def test_font_sizes(self):
        """Test font size constants (compact)"""
        self.assertEqual(self.mf_module.MetadataFieldWidget.LABEL_FONT_SIZE, 8)
        self.assertEqual(self.mf_module.MetadataFieldWidget.LABEL_FONT_SIZE_MOBILE, 9)

    def test_widget_creation(self):
        """Test basic widget creation"""
        widget = self.mf_module.MetadataFieldWidget(
            field_key="title",
            label="Title",
            value="Test Value"
        )
        self.assertEqual(widget.field_key, "title")
        self.assertFalse(widget.is_dirty)

    def test_initial_not_dirty(self):
        """Test widget starts not dirty"""
        widget = self.mf_module.MetadataFieldWidget(
            field_key="title",
            label="Title",
            value="Test"
        )
        self.assertFalse(widget.is_dirty)

    def test_set_value_resets_dirty(self):
        """Test set_value resets dirty flag"""
        widget = self.mf_module.MetadataFieldWidget(
            field_key="title",
            label="Title",
            value="Original"
        )
        widget._is_dirty = True
        widget.set_value("New Value")
        self.assertFalse(widget.is_dirty)

    def test_reset_dirty(self):
        """Test reset_dirty method"""
        widget = self.mf_module.MetadataFieldWidget(
            field_key="title",
            label="Title",
            value="Value"
        )
        widget._is_dirty = True
        widget.reset_dirty()
        self.assertFalse(widget.is_dirty)

    def test_revert(self):
        """Test revert resets dirty flag"""
        widget = self.mf_module.MetadataFieldWidget(
            field_key="title",
            label="Title",
            value="Original"
        )
        widget._is_dirty = True
        widget.revert()
        self.assertFalse(widget.is_dirty)

    def test_mobile_flag(self):
        """Test mobile flag is stored"""
        widget = self.mf_module.MetadataFieldWidget(
            field_key="title",
            label="Title",
            is_mobile=True
        )
        self.assertTrue(widget.is_mobile)

    def test_on_change_callback_stored(self):
        """Test on_change callback is stored"""
        callback = MagicMock()
        widget = self.mf_module.MetadataFieldWidget(
            field_key="title",
            label="Title",
            on_change=callback
        )
        self.assertEqual(widget.on_change, callback)

    def test_set_label(self):
        """Test set_label method updates label"""
        widget = self.mf_module.MetadataFieldWidget(
            field_key="title",
            label="Original"
        )
        widget.set_label("Updated")
        widget.field_label.text = "Updated"


if __name__ == '__main__':
    unittest.main()
