"""
TokenFieldWidget - Native macOS NSTokenField for displaying tags.

Uses NSTokenField on macOS for native Finder-style blue pill tokens.
Falls back to a Toga Button-based implementation on other platforms.

NSTokenField reference:
https://developer.apple.com/documentation/appkit/nstokenfield
"""

import sys
import logging
from typing import Optional, List, Callable

import toga
from toga.style import Pack
from toga.constants import ROW, COLUMN, CENTER

logger = logging.getLogger(__name__)

# Check platform and Rubicon availability
NATIVE_AVAILABLE = False
_appkit_loaded = False

if sys.platform == 'darwin':
    try:
        from rubicon.objc import ObjCClass, objc_method, NSObject
        from rubicon.objc.runtime import objc_id, load_library
        NATIVE_AVAILABLE = True
    except ImportError:
        logger.debug("Rubicon-ObjC not available, using fallback token display")


def _ensure_appkit_loaded():
    """Ensure AppKit framework is loaded for NSTokenField access."""
    global _appkit_loaded
    if _appkit_loaded:
        return True

    if not NATIVE_AVAILABLE:
        return False

    try:
        from rubicon.objc.runtime import load_library
        load_library('AppKit')
        _appkit_loaded = True
        return True
    except Exception as e:
        logger.warning(f"Failed to load AppKit: {e}")
        return False


# Fallback colors (for non-native implementation)
TAG_BACKGROUND = '#E8F4FD'  # Pale blue
TAG_TEXT_COLOR = '#1A73E8'  # Dark blue


def parse_metadata_value(value) -> List[str]:
    """
    Parse a metadata value into a list of tags.

    Handles:
    - Single string: "value" -> ["value"]
    - Python list: ["a", "b"] -> ["a", "b"]
    - JSON array string: '["a", "b"]' -> ["a", "b"]
    - JSON object string: '{"key": "value"}' -> flattened values
    - Semicolon list: "a; b; c" -> ["a", "b", "c"]
    - Comma list: "a, b, c" -> ["a", "b", "c"]
    """
    import json

    if value is None:
        return []

    # Already a list
    if isinstance(value, list):
        result = []
        for v in value:
            if v:
                # Recursively parse nested values
                parsed = parse_metadata_value(v)
                result.extend(parsed)
        return result

    # Already a dict - extract values
    if isinstance(value, dict):
        result = []
        for k, v in value.items():
            if v:
                parsed = parse_metadata_value(v)
                result.extend(parsed)
        return result

    value_str = str(value).strip()

    if not value_str:
        return []

    # Try to parse as JSON first (handles '["a", "b"]' and '{"key": "val"}')
    if value_str.startswith('[') or value_str.startswith('{'):
        try:
            parsed = json.loads(value_str)
            return parse_metadata_value(parsed)  # Recursively handle
        except (json.JSONDecodeError, ValueError):
            pass  # Not valid JSON, continue with string parsing

    # Try semicolon split first
    if ';' in value_str:
        return [v.strip() for v in value_str.split(';') if v.strip()]

    # Try comma split (but only if it looks like a list, not a sentence)
    if ',' in value_str and len(value_str) < 200:
        parts = [v.strip() for v in value_str.split(',') if v.strip()]
        # Only use comma split if parts are short (likely a list, not prose)
        if all(len(p) < 50 for p in parts):
            return parts

    # Single value
    return [value_str]


class TokenFieldWidget:
    """
    A widget that displays values as native macOS tokens (blue pills).

    On macOS: Uses NSTokenField for native Finder-style appearance
    On other platforms: Falls back to styled Toga buttons

    Usage:
        token_field = TokenFieldWidget(
            values=["1931", "Istmina", "Antonio Asprilla"],
            on_token_click=lambda token: search_for(token),
        )
        container.add(token_field.native if token_field.native else token_field.container)
    """

    def __init__(
        self,
        values: List[str] = None,
        on_token_click: Callable[[str], None] = None,
        editable: bool = False,
        placeholder: str = "",
        width: int = 250,
        height: int = 24,
    ):
        """
        Initialize token field widget.

        Args:
            values: List of token values to display
            on_token_click: Callback when a token is clicked (receives token text)
            editable: If True, allows editing tokens (macOS only)
            placeholder: Placeholder text when empty
            width: Width of the field
            height: Height of the field
        """
        self.values = values or []
        self.on_token_click = on_token_click
        self.editable = editable
        self.placeholder = placeholder
        self.width = width
        self.height = height

        # Native widget (macOS only)
        self.native = None
        self._token_field = None
        self._scroll_view = None

        # Fallback container (non-macOS)
        self.container = None

        # Build appropriate UI
        if NATIVE_AVAILABLE and _ensure_appkit_loaded():
            self._create_native_ui()
        else:
            self._create_fallback_ui()

    def _create_native_ui(self):
        """Create native macOS NSTokenField."""
        try:
            from rubicon.objc import ObjCClass

            NSTokenField = ObjCClass('NSTokenField')
            NSScrollView = ObjCClass('NSScrollView')
            NSColor = ObjCClass('NSColor')

            # Create the token field
            self._token_field = NSTokenField.alloc().initWithFrame_(
                ((0, 0), (self.width, self.height))
            )

            # Configure token field
            self._token_field.setEditable_(self.editable)
            self._token_field.setBezeled_(True)
            self._token_field.setDrawsBackground_(True)

            # Set token style to rounded (blue pills)
            # NSTokenStyleRounded = 2
            self._token_field.setTokenStyle_(2)

            # Set placeholder
            if self.placeholder:
                self._token_field.setPlaceholderString_(self.placeholder)

            # Set initial values
            if self.values:
                # NSTokenField expects an array of strings
                from rubicon.objc import ObjCClass
                NSArray = ObjCClass('NSArray')
                ns_array = NSArray.arrayWithArray_(self.values)
                self._token_field.setObjectValue_(ns_array)

            # Wrap in scroll view for horizontal scrolling if needed
            self._scroll_view = NSScrollView.alloc().initWithFrame_(
                ((0, 0), (self.width, self.height))
            )
            self._scroll_view.setDocumentView_(self._token_field)
            self._scroll_view.setHasHorizontalScroller_(False)
            self._scroll_view.setHasVerticalScroller_(False)
            self._scroll_view.setBorderType_(0)  # NSNoBorder

            # The native view to embed
            self.native = self._scroll_view

            logger.debug(f"Created native NSTokenField with {len(self.values)} tokens")

        except Exception as e:
            logger.warning(f"Failed to create native NSTokenField: {e}, using fallback")
            self._create_fallback_ui()

    def _create_fallback_ui(self):
        """Create fallback Toga-based token display."""
        # Main container
        self.container = toga.Box(style=Pack(
            direction=ROW,
            flex=1,
            margin=(2, 0)
        ))

        self._refresh_fallback_tokens()

    def _refresh_fallback_tokens(self):
        """Rebuild fallback token display."""
        if not self.container:
            return

        self.container.clear()

        if not self.values:
            # Show placeholder
            if self.placeholder:
                placeholder_label = toga.Label(
                    self.placeholder,
                    style=Pack(color='#999', font_size=10)
                )
                self.container.add(placeholder_label)
            return

        # Create a pill for each value
        for value in self.values:
            if value and str(value).strip():
                pill = self._create_fallback_pill(str(value).strip())
                self.container.add(pill)

    def _create_fallback_pill(self, text: str) -> toga.Box:
        """Create a fallback token pill using Toga widgets."""
        pill = toga.Box(style=Pack(
            direction=ROW,
            background_color=TAG_BACKGROUND,
            margin=(1, 4, 1, 0),
            align_items=CENTER
        ))

        # Clickable button
        button = toga.Button(
            text,
            on_press=lambda w, t=text: self._handle_token_click(t),
            style=Pack(
                font_size=10,
                height=20,
                margin=0
            )
        )
        pill.add(button)

        return pill

    def _handle_token_click(self, token_text: str):
        """Handle click on a token."""
        logger.debug(f"Token clicked: {token_text}")
        if self.on_token_click:
            self.on_token_click(token_text)

    def set_values(self, values: List[str]):
        """Update the displayed values."""
        self.values = values or []

        if self._token_field:
            # Update native token field
            try:
                from rubicon.objc import ObjCClass
                NSArray = ObjCClass('NSArray')
                ns_array = NSArray.arrayWithArray_(self.values)
                self._token_field.setObjectValue_(ns_array)
            except Exception as e:
                logger.error(f"Failed to update native token field: {e}")
        elif self.container:
            # Update fallback
            self._refresh_fallback_tokens()

    def get_values(self) -> List[str]:
        """Get current token values."""
        if self._token_field:
            try:
                obj_value = self._token_field.objectValue()
                if obj_value:
                    return [str(obj_value.objectAtIndex_(i)) for i in range(obj_value.count())]
            except Exception as e:
                logger.error(f"Failed to get native token values: {e}")
        return self.values.copy()

    def get_toga_widget(self) -> toga.Widget:
        """
        Get a Toga-compatible widget for embedding.

        On macOS: Returns a toga.Box containing the native view
        On other platforms: Returns the fallback container
        """
        if self.native:
            # Wrap native view in a Toga Box
            # Toga can embed native views via the _impl attribute
            wrapper = toga.Box(style=Pack(
                width=self.width,
                height=self.height
            ))
            # Add native view to wrapper's implementation
            try:
                wrapper._impl.native.addSubview_(self.native)
                return wrapper
            except Exception as e:
                logger.warning(f"Failed to embed native view: {e}")
                # Fall through to fallback

        return self.container


class NativeTokenFieldWrapper(toga.Widget):
    """
    A Toga Widget wrapper for native NSTokenField.

    This allows embedding NSTokenField directly in Toga layouts.
    """

    def __init__(
        self,
        values: List[str] = None,
        on_token_click: Callable[[str], None] = None,
        editable: bool = False,
        placeholder: str = "",
        style=None,
        **kwargs
    ):
        super().__init__(style=style, **kwargs)
        self.values = values or []
        self.on_token_click = on_token_click
        self.editable = editable
        self.placeholder = placeholder

        self._token_widget = TokenFieldWidget(
            values=self.values,
            on_token_click=self.on_token_click,
            editable=self.editable,
            placeholder=self.placeholder,
        )

    def _create_impl(self):
        """Create the implementation for this widget."""
        # This is called by Toga to create the native implementation
        # We'll return our token field's native view
        return self._token_widget.native or self._token_widget.container._impl

    @property
    def native(self):
        """Return the native macOS view."""
        return self._token_widget.native

    def set_values(self, values: List[str]):
        """Update displayed values."""
        self._token_widget.set_values(values)

    def get_values(self) -> List[str]:
        """Get current values."""
        return self._token_widget.get_values()
