"""
JsonEditor Component

Reusable JSON editor with syntax highlighting, validation, and edit capabilities.
Inspired by the inspector pattern.
"""

import toga
from toga.style import Pack
from typing import Dict, Any, Optional, Tuple, Callable
import json


class JsonEditor:
    """
    Reusable JSON editor component for editing structured data.

    Follows inspector pattern:
    - Update without recreating widgets via set_data()
    - Return toga.Box for composition
    - Use callbacks for user actions
    - Self-contained and reusable

    Example usage:
        # Read-only mode
        editor = JsonEditor(read_only=True)
        editor.set_data({"key": "value"})
        container.add(editor.as_box())

        # Edit mode with callbacks
        def on_save(data):
            print(f"Saving: {data}")

        editor = JsonEditor(on_save=on_save)
        editor.set_data({"key": "value"})
        container.add(editor.as_box())
    """

    def __init__(
        self,
        on_save: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_cancel: Optional[Callable[[], None]] = None,
        read_only: bool = False
    ):
        """
        Initialize JSON editor.

        Args:
            on_save: Callback when user saves (receives validated dict)
            on_cancel: Callback when user cancels
            read_only: If True, display only (no editing)
        """
        self.on_save = on_save
        self.on_cancel = on_cancel
        self.read_only = read_only
        self._data: Optional[Dict[str, Any]] = None
        self._original_json: str = ""
        self._current_error: Optional[str] = None
        self._container = None
        self._build_ui()

    def _build_ui(self):
        """Build the UI components"""
        # Title label
        self._title_label = toga.Label(
            "JSON Editor",
            style=Pack(
                font_size=14,
                font_weight='bold',
                margin_bottom=10
            )
        )

        # JSON text input (multiline for editing)
        self._json_input = toga.MultilineTextInput(
            style=Pack(
                flex=1,
                font_family='monospace',
                font_size=11,
                margin_bottom=10
            ),
            readonly=self.read_only
        )

        # Error label (hidden by default)
        self._error_label = toga.Label(
            "",
            style=Pack(
                color='#CC0000',
                font_size=10,
                margin_bottom=10,
                margin=5
            )
        )

        # Buttons container
        self._buttons_box = toga.Box(
            style=Pack(
                direction='row',
                margin_top=10
            )
        )

        if not self.read_only:
            # Cancel button
            self._cancel_button = toga.Button(
                "Cancel",
                on_press=self._handle_cancel,
                style=Pack(
                    margin_right=10,
                    width=100
                )
            )

            # Validate button
            self._validate_button = toga.Button(
                "Validate",
                on_press=self._handle_validate,
                style=Pack(
                    margin_right=10,
                    width=100
                )
            )

            # Save button
            self._save_button = toga.Button(
                "Save",
                on_press=self._handle_save,
                style=Pack(
                    width=100
                )
            )

            self._buttons_box.add(self._cancel_button)
            self._buttons_box.add(self._validate_button)
            self._buttons_box.add(self._save_button)

        # Main container
        self._container = toga.Box(
            style=Pack(
                direction='column',
                margin=10,
                flex=1
            )
        )

        self._container.add(self._title_label)
        self._container.add(self._json_input)
        self._container.add(self._error_label)

        if not self.read_only:
            self._container.add(self._buttons_box)

    def set_data(self, data: Dict[str, Any]):
        """
        Load JSON data into editor.

        Args:
            data: Dictionary to edit as JSON
        """
        self._data = data
        self._original_json = json.dumps(data, indent=2, ensure_ascii=False) if data else "{}"
        self._json_input.value = self._original_json
        self._clear_error()

    def get_data(self) -> Optional[Dict[str, Any]]:
        """
        Get current JSON as dict.

        Returns:
            Dictionary if JSON is valid, None otherwise
        """
        is_valid, error = self.validate()
        if not is_valid:
            return None

        try:
            return json.loads(self._json_input.value)
        except json.JSONDecodeError:
            return None

    def validate(self) -> Tuple[bool, Optional[str]]:
        """
        Validate current JSON.

        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            json_text = self._json_input.value or "{}"
            json.loads(json_text)
            return True, None
        except json.JSONDecodeError as e:
            error_msg = f"Invalid JSON at line {e.lineno}, column {e.colno}: {e.msg}"
            return False, error_msg
        except Exception as e:
            return False, str(e)

    def as_box(self) -> toga.Box:
        """Return the component as a Toga Box for embedding"""
        return self._container

    def _handle_validate(self, widget):
        """Handle validate button press"""
        is_valid, error = self.validate()

        if is_valid:
            self._show_success("JSON is valid")
        else:
            self._show_error(error)

    def _handle_save(self, widget):
        """Handle save button press"""
        is_valid, error = self.validate()

        if not is_valid:
            self._show_error(error)
            return

        data = self.get_data()
        if data is not None and self.on_save:
            self._clear_error()
            self.on_save(data)
            # Update original JSON after successful save
            self._original_json = self._json_input.value

    def _handle_cancel(self, widget):
        """Handle cancel button press"""
        # Restore original JSON
        self._json_input.value = self._original_json
        self._clear_error()

        if self.on_cancel:
            self.on_cancel()

    def _show_error(self, error: str):
        """
        Show error message.

        Args:
            error: Error message to display
        """
        self._current_error = error
        self._error_label.text = f"⚠ {error}"
        self._error_label.style.margin = 5

    def _show_success(self, message: str):
        """
        Show success message.

        Args:
            message: Success message to display
        """
        self._current_error = None
        self._error_label.text = f"✓ {message}"
        self._error_label.style.margin = 5
        # Clear success message after a moment would be nice, but Toga doesn't have timers
        # So we'll just leave it until next action

    def _clear_error(self):
        """Clear error/success message"""
        self._current_error = None
        self._error_label.text = ""
        self._error_label.style.margin = 0

    def has_unsaved_changes(self) -> bool:
        """
        Check if there are unsaved changes.

        Returns:
            True if current JSON differs from original
        """
        return self._json_input.value != self._original_json

    def is_valid(self) -> bool:
        """
        Check if current JSON is valid.

        Returns:
            True if JSON is valid
        """
        is_valid, _ = self.validate()
        return is_valid

    def get_error(self) -> Optional[str]:
        """
        Get current error message.

        Returns:
            Error message if there is one, None otherwise
        """
        return self._current_error

    def reset(self):
        """Reset editor to original state"""
        self._json_input.value = self._original_json
        self._clear_error()

    def set_read_only(self, read_only: bool):
        """
        Set read-only mode.

        Args:
            read_only: If True, disable editing
        """
        self.read_only = read_only
        self._json_input.readonly = read_only

        # Hide/show buttons based on read-only mode
        if hasattr(self, '_buttons_box'):
            # Toga doesn't have a simple way to hide/show widgets
            # So we would need to rebuild the UI or keep buttons but disable them
            if hasattr(self, '_cancel_button'):
                self._cancel_button.enabled = not read_only
            if hasattr(self, '_validate_button'):
                self._validate_button.enabled = not read_only
            if hasattr(self, '_save_button'):
                self._save_button.enabled = not read_only

    def format_json(self):
        """Format current JSON with proper indentation (if valid)"""
        try:
            data = json.loads(self._json_input.value)
            formatted = json.dumps(data, indent=2, ensure_ascii=False)
            self._json_input.value = formatted
            self._show_success("JSON formatted")
        except json.JSONDecodeError:
            self._show_error("Cannot format invalid JSON")
