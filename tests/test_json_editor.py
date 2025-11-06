"""
Unit tests for JsonEditor component

Tests for:
- JSON loading and editing
- Validation (valid and invalid JSON)
- Save/cancel callbacks
- Read-only mode
- Error display
"""

import pytest
from fichero.shared.components import JsonEditor


class TestJsonEditor:
    """Test JsonEditor component"""

    def test_create_json_editor(self):
        """Test creating a JsonEditor"""
        editor = JsonEditor()

        assert editor._data is None
        assert editor.read_only is False
        assert editor._container is not None

    def test_create_read_only_editor(self):
        """Test creating a read-only JsonEditor"""
        editor = JsonEditor(read_only=True)

        assert editor.read_only is True
        assert editor._json_input.readonly is True

    def test_set_data(self):
        """Test loading JSON data"""
        editor = JsonEditor()
        data = {"key": "value", "number": 42}

        editor.set_data(data)

        assert editor._data == data
        assert '  "key": "value"' in editor._json_input.value or '"key":"value"' in editor._json_input.value
        assert "42" in editor._json_input.value

    def test_set_empty_data(self):
        """Test loading empty dict"""
        editor = JsonEditor()

        editor.set_data({})

        assert editor._json_input.value == "{}"

    def test_set_none_data(self):
        """Test loading None as data"""
        editor = JsonEditor()

        editor.set_data(None)

        assert editor._json_input.value == "{}"

    def test_get_data_valid(self):
        """Test getting data when JSON is valid"""
        editor = JsonEditor()
        data = {"key": "value"}
        editor.set_data(data)

        result = editor.get_data()

        assert result == data

    def test_get_data_invalid(self):
        """Test getting data when JSON is invalid"""
        editor = JsonEditor()
        editor.set_data({"key": "value"})
        # Make JSON invalid
        editor._json_input.value = "{invalid json"

        result = editor.get_data()

        assert result is None

    def test_validate_valid_json(self):
        """Test validation with valid JSON"""
        editor = JsonEditor()
        editor.set_data({"key": "value"})

        is_valid, error = editor.validate()

        assert is_valid is True
        assert error is None

    def test_validate_invalid_json(self):
        """Test validation with invalid JSON"""
        editor = JsonEditor()
        editor.set_data({"key": "value"})
        editor._json_input.value = "{invalid"

        is_valid, error = editor.validate()

        assert is_valid is False
        assert error is not None
        assert "Invalid JSON" in error or "line" in error

    def test_validate_empty_json(self):
        """Test validation with empty JSON"""
        editor = JsonEditor()
        editor._json_input.value = ""

        is_valid, error = editor.validate()

        # Empty string should be treated as {} which is valid
        assert is_valid is True

    def test_save_callback(self):
        """Test save callback is called with validated data"""
        saved_data = None

        def on_save(data):
            nonlocal saved_data
            saved_data = data

        editor = JsonEditor(on_save=on_save)
        test_data = {"key": "value"}
        editor.set_data(test_data)

        # Simulate save button press
        editor._handle_save(None)

        assert saved_data == test_data

    def test_save_callback_not_called_on_invalid(self):
        """Test save callback not called when JSON is invalid"""
        saved_data = None

        def on_save(data):
            nonlocal saved_data
            saved_data = data

        editor = JsonEditor(on_save=on_save)
        editor.set_data({"key": "value"})
        editor._json_input.value = "{invalid"

        # Simulate save button press
        editor._handle_save(None)

        assert saved_data is None

    def test_cancel_callback(self):
        """Test cancel callback is called"""
        cancel_called = False

        def on_cancel():
            nonlocal cancel_called
            cancel_called = True

        editor = JsonEditor(on_cancel=on_cancel)
        editor.set_data({"key": "value"})

        # Simulate cancel button press
        editor._handle_cancel(None)

        assert cancel_called is True

    def test_cancel_restores_original(self):
        """Test cancel restores original JSON"""
        editor = JsonEditor()
        original = {"key": "value"}
        editor.set_data(original)
        original_json = editor._json_input.value

        # Modify JSON
        editor._json_input.value = '{"key": "modified"}'

        # Cancel
        editor._handle_cancel(None)

        assert editor._json_input.value == original_json

    def test_has_unsaved_changes(self):
        """Test detecting unsaved changes"""
        editor = JsonEditor()
        editor.set_data({"key": "value"})

        # Initially no changes
        assert editor.has_unsaved_changes() is False

        # Modify JSON
        editor._json_input.value = '{"key": "modified"}'

        assert editor.has_unsaved_changes() is True

    def test_is_valid(self):
        """Test is_valid helper method"""
        editor = JsonEditor()
        editor.set_data({"key": "value"})

        assert editor.is_valid() is True

        # Make invalid
        editor._json_input.value = "{invalid"

        assert editor.is_valid() is False

    def test_reset(self):
        """Test reset method"""
        editor = JsonEditor()
        editor.set_data({"key": "value"})
        original = editor._json_input.value

        # Modify and add error
        editor._json_input.value = "{modified}"
        editor._show_error("Test error")

        # Reset
        editor.reset()

        assert editor._json_input.value == original
        assert editor._current_error is None

    def test_set_read_only(self):
        """Test changing read-only mode"""
        editor = JsonEditor(read_only=False)

        assert editor._json_input.readonly is False

        # Set read-only
        editor.set_read_only(True)

        assert editor.read_only is True
        assert editor._json_input.readonly is True

        # Unset read-only
        editor.set_read_only(False)

        assert editor.read_only is False
        assert editor._json_input.readonly is False

    def test_format_json(self):
        """Test JSON formatting"""
        editor = JsonEditor()
        # Set unformatted JSON
        editor._json_input.value = '{"key":"value","number":42}'

        editor.format_json()

        # Should be formatted with indentation
        assert '  "key"' in editor._json_input.value or '"key"' in editor._json_input.value
        assert "42" in editor._json_input.value

    def test_format_invalid_json(self):
        """Test formatting invalid JSON shows error"""
        editor = JsonEditor()
        editor._json_input.value = '{invalid'

        editor.format_json()

        # Should show error
        assert editor._current_error is not None
        assert "Cannot format" in editor._error_label.text or "invalid" in editor._error_label.text.lower()

    def test_as_box_returns_container(self):
        """Test that as_box returns a Toga Box"""
        editor = JsonEditor()

        box = editor.as_box()

        assert box is not None
        assert box == editor._container

    def test_nested_json_data(self):
        """Test handling nested JSON data"""
        editor = JsonEditor()
        data = {
            "level1": {
                "level2": {
                    "level3": "value"
                }
            }
        }

        editor.set_data(data)
        result = editor.get_data()

        assert result == data
        assert result["level1"]["level2"]["level3"] == "value"

    def test_json_with_arrays(self):
        """Test handling JSON with arrays"""
        editor = JsonEditor()
        data = {
            "items": [1, 2, 3],
            "names": ["Alice", "Bob", "Charlie"]
        }

        editor.set_data(data)
        result = editor.get_data()

        assert result == data
        assert len(result["items"]) == 3
        assert "Alice" in result["names"]

    def test_json_with_special_types(self):
        """Test handling JSON with special types"""
        editor = JsonEditor()
        data = {
            "string": "value",
            "number": 42,
            "float": 3.14,
            "boolean": True,
            "null": None
        }

        editor.set_data(data)
        result = editor.get_data()

        assert result["string"] == "value"
        assert result["number"] == 42
        assert result["float"] == 3.14
        assert result["boolean"] is True
        assert result["null"] is None

    def test_error_display(self):
        """Test error message display"""
        editor = JsonEditor()

        editor._show_error("Test error message")

        assert "Test error message" in editor._error_label.text
        assert editor._current_error == "Test error message"

    def test_success_display(self):
        """Test success message display"""
        editor = JsonEditor()

        editor._show_success("Success message")

        assert "Success message" in editor._error_label.text
        assert editor._current_error is None

    def test_clear_error(self):
        """Test clearing error message"""
        editor = JsonEditor()
        editor._show_error("Test error")

        editor._clear_error()

        assert editor._error_label.text == ""
        assert editor._current_error is None


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
