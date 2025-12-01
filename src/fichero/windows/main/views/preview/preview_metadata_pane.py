"""
PreviewMetadataPane - Tinderbox-inspired metadata editing pane

Features:
- Tab bar: Preview | Export
- Collapsible header showing file title (truncated)
- Small disclosure triangle and settings button
- Compact horizontal field layout: [Label] [Value] (8pt font, 18px rows)
- Grey divider between fields and text
- Full-bleed text field (edge-to-edge)
- Auto-save on change
"""

import logging
from typing import Optional, Dict, Any, List

import toga
from toga.style import Pack
from toga.constants import COLUMN, ROW

from fichero.shared.views.base_view import BaseView
from fichero.shared.widgets.collapsible_section import CollapsibleSection
from fichero.shared.widgets.metadata_field import MetadataFieldWidget
from fichero.shared.widgets.field_selector_dialog import FieldSelectorDialog
from fichero.windows.main.views.preview.display_profiles import (
    get_default_profile,
    DisplayProfile
)
from fichero.windows.main.views.preview.field_registry import MetadataFieldRegistry

# Import internationalization function
try:
    from fichero.shared.utils.i18n import _
except ImportError:
    def _(text):
        return text

logger = logging.getLogger(__name__)


class PreviewMetadataPane(BaseView):
    """
    Tinderbox-inspired metadata pane with tabs, compact fields, and auto-save.

    Layout:
    [OptionContainer: Preview | Export tabs]
      Preview Tab:
        [CollapsibleSection: File Title (truncated)]
          [MetadataFieldWidget] x N  (horizontal: [Label] [Value])
        [Divider: 1px grey line]
        [MultilineTextInput: text]  (edge-to-edge)
      Export Tab:
        [Placeholder for export options]
    """

    DIVIDER_COLOR = "#D0D0D0"
    DIVIDER_HEIGHT = 1

    def __init__(self, app, is_mobile: bool = False, library_manager=None):
        """Initialize the metadata preview pane."""
        logger.info("PreviewMetadataPane.__init__ starting")

        # Store dependencies
        self.library_manager = library_manager
        self.is_mobile = is_mobile

        # Current state
        self.current_item_id: Optional[str] = None
        self.current_item_type: str = "file"
        self.current_item_name: str = "No item selected"
        self._pending_save: bool = False

        # UI components (created in _create_content)
        self.metadata_section: Optional[CollapsibleSection] = None
        self.metadata_fields: Dict[str, MetadataFieldWidget] = {}
        self.text_input: Optional[toga.MultilineTextInput] = None

        # State manager reference (lazy loaded)
        self._state_manager = None

        # Call parent init
        super().__init__(app, is_mobile)

        logger.info("PreviewMetadataPane initialization complete")

    @property
    def state_manager(self):
        """Lazy load state manager."""
        if self._state_manager is None:
            try:
                from fichero.config.core.state_manager import StateManager
                self._state_manager = StateManager(self.app)
            except Exception as e:
                logger.warning(f"Could not get state manager: {e}")
        return self._state_manager

    def _create_view_structure(self):
        """
        Override BaseView's structure to create metadata pane directly.
        """
        try:
            # Create content directly (no tabs)
            self._create_content()

            logger.debug("PreviewMetadataPane structure created")

        except Exception as e:
            logger.error(f"Failed to create PreviewMetadataPane structure: {e}")
            import traceback
            traceback.print_exc()
            # Create fallback container
            self.container = toga.Box(style=Pack(direction=COLUMN))

    def _create_content(self):
        """Create the metadata pane UI structure (no tabs)."""
        # Create main container
        self.container = toga.Box(style=Pack(direction=COLUMN, flex=1))

        # Get saved expanded state
        is_expanded = True
        if self.state_manager:
            is_expanded = self.state_manager.get_metadata_pane_expanded()

        # Create metadata section with file title (always visible, no disclosure)
        self.metadata_section = CollapsibleSection(
            title=self.current_item_name,
            is_expanded=is_expanded,
            show_settings=True,
            show_disclosure=False,  # No disclosure triangle
            on_toggle=self._on_metadata_toggle,
            on_settings_clicked=self._on_settings_clicked,
            is_mobile=self.is_mobile,
            max_title_length=35
        )
        self.container.add(self.metadata_section.container)

        # Grey divider line
        divider = toga.Box(style=Pack(
            height=self.DIVIDER_HEIGHT,
            background_color=self.DIVIDER_COLOR,
            margin=(2, 0)
        ))
        self.container.add(divider)

        # Text field (edge-to-edge, no margins)
        self.text_input = toga.MultilineTextInput(
            on_change=self._on_text_change,
            style=Pack(
                flex=1,
                margin=0  # True edge-to-edge
            )
        )
        self.container.add(self.text_input)

        # Show placeholder initially
        self._show_placeholder()

        logger.debug("Created metadata pane (no tabs)")

    def _populate_metadata_fields(self, item_type: str):
        """Create field widgets based on display profile."""
        # Clear existing fields
        self.metadata_section.clear_content()
        self.metadata_fields.clear()

        # Get visible fields for item type
        visible_fields = self._get_visible_fields(item_type)

        if not visible_fields:
            # No fields configured - show helper message
            no_fields_label = toga.Label(
                _("Click \u22EF to add fields"),
                style=Pack(
                    text_align='center',
                    margin=(6, 2),
                    color='#999',
                    font_size=9
                )
            )
            self.metadata_section.add_content(no_fields_label)
            return

        # Create widget for each field
        for field_key in visible_fields:
            field_info = MetadataFieldRegistry.get_field_info(field_key)

            # If field not in registry, create dynamic field info
            if not field_info:
                field_info = MetadataFieldRegistry.create_dynamic_field_info(field_key)
                # Register it so it's available next time
                MetadataFieldRegistry.register_dynamic_field(field_key)

            widget = MetadataFieldWidget(
                field_key=field_key,
                label=field_info.label,
                value="",
                editable=field_info.editable,
                on_change=self._on_field_change,
                is_mobile=self.is_mobile
            )
            self.metadata_fields[field_key] = widget
            self.metadata_section.add_content(widget.container)

        logger.debug(f"Populated {len(self.metadata_fields)} metadata fields for {item_type}")

    def _get_visible_fields(self, item_type: str) -> List[str]:
        """Get visible fields for item type from state or defaults."""
        # Check for user customization first
        if self.state_manager:
            custom = self.state_manager.get_display_profile(item_type)
            if custom:
                return custom

        # Fall back to defaults
        profile = get_default_profile(item_type)
        return profile.visible_fields if profile else []

    async def load_item(self, item_id: str, output_data: dict = None):
        """Load metadata for item."""
        logger.info(f"Loading metadata for item {item_id}")
        self.current_item_id = item_id

        try:
            if not self.library_manager:
                logger.warning("No library manager available")
                self._show_error(_("No library manager available"))
                return

            # Get item to determine type and name
            item = await self.library_manager.get_item(item_id)
            if not item:
                self._show_error(_("Item not found"))
                return

            self.current_item_type = getattr(item, 'type', 'file')
            self.current_item_name = getattr(item, 'name', 'Untitled')

            # Update header title with file name
            self.metadata_section.set_title(self.current_item_name)

            # Populate fields for this item type
            self._populate_metadata_fields(self.current_item_type)

            # Load field values
            await self._load_field_values(item_id)

            # Load text
            await self._load_text(item_id)

            logger.info(f"Loaded metadata for item {item_id}")

        except Exception as e:
            logger.error(f"Failed to load metadata: {e}")
            self._show_error(f"Error: {e}")

    async def _load_field_values(self, item_id: str):
        """Load values for visible metadata fields."""
        try:
            # Get catalogue data from library
            catalogue_data = await self.library_manager.get_item_catalogue_data(item_id)

            if not catalogue_data:
                catalogue_data = {}

            # Populate field widgets
            for field_key, widget in self.metadata_fields.items():
                if isinstance(catalogue_data, dict):
                    values = catalogue_data.get(field_key, [])
                    # Take first value if multiple (versioned)
                    if isinstance(values, list):
                        value = values[0] if values else ""
                    else:
                        value = str(values) if values else ""
                else:
                    value = ""
                widget.set_value(value)

        except Exception as e:
            logger.error(f"Failed to load field values: {e}")

    async def _load_text(self, item_id: str):
        """Load text content."""
        try:
            transcriptions = await self.library_manager.get_item_transcriptions(item_id)
            # Take most recent transcription
            text = transcriptions[0] if transcriptions else ""
            self.text_input.value = text

        except Exception as e:
            logger.error(f"Failed to load text: {e}")
            self.text_input.value = ""

    def _on_field_change(self, field_key: str, new_value: str):
        """Handle field value change - trigger auto-save."""
        self._schedule_autosave()

    def _on_text_change(self, widget):
        """Handle text change - trigger auto-save."""
        self._schedule_autosave()

    def _schedule_autosave(self):
        """Schedule auto-save after a brief delay."""
        if not self.current_item_id or not self.library_manager:
            return

        # Run save in background
        import asyncio
        asyncio.create_task(self._autosave())

    async def _autosave(self, app=None):
        """Auto-save all changes."""
        if not self.current_item_id or not self.library_manager:
            return

        try:
            # Collect changed field values
            updates = {}
            for field_key, field_widget in self.metadata_fields.items():
                if field_widget.is_dirty:
                    updates[field_key] = field_widget.get_value()

            # Save field updates if any
            if updates:
                success = await self.library_manager.update_item_metadata_batch(
                    self.current_item_id, updates
                )
                if success:
                    # Reset dirty flags on widgets
                    for field_key in updates:
                        if field_key in self.metadata_fields:
                            self.metadata_fields[field_key].reset_dirty()
                    logger.debug(f"Auto-saved {len(updates)} field updates")

            # Save text if dirty
            if self.text_input and self.text_input.value:
                await self.library_manager.update_item_transcription(
                    self.current_item_id,
                    self.text_input.value
                )
                logger.debug("Auto-saved text")

        except Exception as e:
            logger.error(f"Auto-save failed: {e}")

    def _on_metadata_toggle(self, is_expanded: bool):
        """Handle metadata section expand/collapse."""
        logger.debug(f"Metadata section toggled: expanded={is_expanded}")
        if self.state_manager:
            self.state_manager.set_metadata_pane_expanded(is_expanded)
            # Save state asynchronously
            import asyncio
            asyncio.create_task(self.state_manager.save_state())

    def _on_settings_clicked(self):
        """Show field selector dialog with dynamic field discovery."""
        # Get available fields - include dynamically discovered ones if we have storage
        storage = None
        if self.library_manager:
            try:
                storage = self.library_manager.storage
            except Exception:
                pass

        if storage and self.current_item_id:
            # Use dynamic discovery to find fields from the database
            available = MetadataFieldRegistry.get_available_fields_with_discovery(
                storage=storage,
                item_id=self.current_item_id,
                item_type=self.current_item_type
            )
        else:
            # Fall back to predefined fields only
            available = MetadataFieldRegistry.get_available_fields(self.current_item_type)

        current = self._get_visible_fields(self.current_item_type)

        dialog = FieldSelectorDialog(
            self.app,
            available_fields=available,
            selected_fields=current,
            on_selection_changed=self._on_fields_selection_changed
        )
        dialog.show()

    def _on_fields_selection_changed(self, selected_fields: List[str]):
        """Handle field visibility change from dialog."""
        logger.info(f"Field selection changed: {selected_fields}")

        # Save current field values before rebuilding
        saved_values = {}
        for field_key, widget in self.metadata_fields.items():
            saved_values[field_key] = widget.get_value()

        # Save to state
        if self.state_manager:
            self.state_manager.set_display_profile(self.current_item_type, selected_fields)
            # Save state asynchronously
            import asyncio
            asyncio.create_task(self.state_manager.save_state())

        # Rebuild fields
        self._populate_metadata_fields(self.current_item_type)

        # Restore saved values to new field widgets
        for field_key, widget in self.metadata_fields.items():
            if field_key in saved_values:
                widget.set_value(saved_values[field_key])

    def _show_placeholder(self):
        """Show no item selected placeholder."""
        # Clear fields
        self.metadata_section.clear_content()
        self.metadata_fields.clear()

        # Update header to show placeholder
        self.metadata_section.set_title(_("No item selected"))

        # Add placeholder to metadata section
        placeholder = toga.Label(
            _("Select an item to view metadata"),
            style=Pack(
                text_align='center',
                margin=(8, 2),
                color='#999',
                font_size=9
            )
        )
        self.metadata_section.add_content(placeholder)

        # Clear text
        if self.text_input:
            self.text_input.value = ""

    def _show_error(self, message: str):
        """Show error message."""
        self.metadata_section.clear_content()
        self.metadata_section.set_title(_("Error"))
        error_label = toga.Label(
            message,
            style=Pack(
                text_align='center',
                margin=(8, 2),
                color='#d32f2f',
                font_size=9
            )
        )
        self.metadata_section.add_content(error_label)

    def clear(self):
        """Clear the metadata preview."""
        self.current_item_id = None
        self.current_item_name = "No item selected"
        self._show_placeholder()
        logger.debug("Metadata pane cleared")

    # Scroll state management (from BaseView) - not applicable with OptionContainer

    def get_scroll_state(self) -> dict:
        """Get current scroll position (not applicable with tabs)."""
        return {}

    def restore_scroll_state(self, state: dict):
        """Restore scroll position (not applicable with tabs)."""
        pass

    def reset_scroll(self):
        """Reset scroll position (not applicable with tabs)."""
        pass
