"""
Collection Settings Dialog for Fichero

Modal dialog for configuring collection settings using the existing config system.
"""

import toga
from toga.style import Pack
from toga.constants import COLUMN, ROW
import logging
from typing import Optional, Dict, Any, Callable

from ...config.ui_generator import UIGenerator
from ...config.core.settings_manager import SettingsManager

logger = logging.getLogger(__name__)


class CollectionSettingsDialog:
    """Modal dialog for configuring collection settings"""
    
    def __init__(self, app, collection_data: Optional[Dict[str, Any]] = None):
        """Initialize collection settings dialog"""
        self.app = app
        self.collection_data = collection_data or {}
        
        # Dialog window
        self.window: Optional[toga.Window] = None
        
        # UI generator for the dialog
        self.ui_generator = UIGenerator(app)
        
        # Settings manager
        self.settings_manager = SettingsManager(app)
        
        # Callbacks
        self.on_save: Optional[Callable] = None
        self.on_cancel: Optional[Callable] = None
        
        # Create dialog
        self._create_dialog()
        
        logger.info("Collection settings dialog initialized successfully")
    
    def _create_dialog(self):
        """Create the collection settings dialog"""
        try:
            # Create window
            self.window = toga.Window(
                title="Collection Settings",
                size=(450, 600),
                resizable=True
            )
            
            # Create main container
            main_container = toga.Box(
                style=Pack(
                    direction=COLUMN,
                    margin=20
                )
            )
            
            # Create header
            header_label = toga.Label(
                "Configure Collection Settings",
                style=Pack(
                    font_size=18,
                    font_weight="bold",
                    margin=(0, 0, 20, 0),
                    color="#333333"
                )
            )
            main_container.add(header_label)
            
            # Create form using UIGenerator
            form_container = self._create_form()
            main_container.add(form_container)
            
            # Create button bar
            button_bar = self._create_button_bar()
            main_container.add(button_bar)
            
            # Set content
            self.window.content = main_container
            
            # Set up window close handler
            self.window.on_close = self._on_window_close
            
        except Exception as e:
            logger.error(f"Failed to create collection settings dialog: {e}")
    
    def _create_form(self) -> toga.Widget:
        """Create the form using UIGenerator"""
        try:
            # Load collection settings schema
            schema_path = "resources/config_ui_schemas/collection_settings_schema.yml"
            
            # Create form using UIGenerator
            form_widget = self.ui_generator.create_form(
                schema_path,
                initial_data=self.collection_data,
                on_field_change=self._on_field_change
            )
            
            return form_widget
            
        except Exception as e:
            logger.error(f"Failed to create form: {e}")
            # Return fallback form
            return self._create_fallback_form()
    
    def _create_fallback_form(self) -> toga.Widget:
        """Create a fallback form if UIGenerator fails"""
        try:
            form_container = toga.Box(
                style=Pack(
                    direction=COLUMN,
                    margin=10
                )
            )
            
            # Basic fields
            fields = [
                ("Name", "name", "text_input"),
                ("Description", "description", "text_area"),
                ("Type", "type", "selection", ["copy", "link"]),
                ("Processing Location", "processing_location", "selection", ["internal", "external"]),
                ("Processing Path", "processing_path", "text_input"),
                ("Tags", "tags", "text_input"),
                ("Category", "category", "text_input"),
                ("Priority", "priority", "selection", ["low", "normal", "high"]),
                ("Auto Process", "auto_process", "checkbox"),
                ("Process on Add", "process_on_add", "checkbox"),
                ("Retention Policy", "retention_policy", "selection", ["keep_forever", "keep_30_days", "keep_90_days", "keep_1_year"])
            ]
            
            for field_label, field_id, field_type, *field_options in fields:
                field_container = toga.Box(
                    style=Pack(
                        direction=COLUMN,
                        margin=(5, 0)
                    )
                )
                
                # Field label
                label = toga.Label(
                    field_label,
                    style=Pack(
                        font_size=12,
                        font_weight="bold",
                        margin=(0, 0, 5, 0),
                        color="#333333"
                    )
                )
                field_container.add(label)
                
                # Field widget
                if field_type == "text_input":
                    widget = toga.TextInput(
                        value=self.collection_data.get(field_id, ""),
                        style=Pack(
                            margin=(8, 12),
                            border_color="#E0E0E0",
                            border_width=1
                        )
                    )
                    setattr(self, f"_{field_id}_widget", widget)
                elif field_type == "text_area":
                    widget = toga.MultilineTextInput(
                        value=self.collection_data.get(field_id, ""),
                        style=Pack(
                            margin=(8, 12),
                            border_color="#E0E0E0",
                            border_width=1,
                            height=80
                        )
                    )
                    setattr(self, f"_{field_id}_widget", widget)
                elif field_type == "selection":
                    widget = toga.Selection(
                        items=field_options[0] if field_options else [],
                        on_select=lambda widget, selection, field_id=field_id: self._on_selection_change(field_id, selection),
                        style=Pack(
                            margin=(8, 12),
                            border_color="#E0E0E0",
                            border_width=1
                        )
                    )
                    setattr(self, f"_{field_id}_widget", widget)
                elif field_type == "checkbox":
                    widget = toga.Switch(
                        value=self.collection_data.get(field_id, False),
                        on_change=lambda widget, value, field_id=field_id: self._on_checkbox_change(field_id, value),
                        style=Pack(
                            margin=(5, 0)
                        )
                    )
                    setattr(self, f"_{field_id}_widget", widget)
                
                field_container.add(widget)
                form_container.add(field_container)
            
            return form_container
            
        except Exception as e:
            logger.error(f"Failed to create fallback form: {e}")
            # Return error message
            return toga.Label(
                "Error creating form. Please check the logs.",
                style=Pack(
                    color="#FF0000",
                    margin=(20, 0)
                )
            )
    
    def _create_button_bar(self) -> toga.Widget:
        """Create the button bar for the dialog"""
        try:
            button_container = toga.Box(
                style=Pack(
                    direction=ROW,
                    margin=(20, 0, 0, 0),
                    alignment="center"
                )
            )
            
            # Save button
            save_button = toga.Button(
                "Save",
                on_press=self._on_save,
                style=Pack(
                    margin=(0, 10, 0, 0),
                    margin=(15, 25),
                    background_color="#007AFF"
                )
            )
            button_container.add(save_button)
            
            # Cancel button
            cancel_button = toga.Button(
                "Cancel",
                on_press=self._on_cancel,
                style=Pack(
                    margin=(0, 0, 0, 10),
                    margin=(15, 25),
                    background_color="#8E8E93"
                )
            )
            button_container.add(cancel_button)
            
            return button_container
            
        except Exception as e:
            logger.error(f"Failed to create button bar: {e}")
            return toga.Box()
    
    def _on_field_change(self, field_id: str, value: Any):
        """Handle field value changes"""
        try:
            logger.debug(f"Field {field_id} changed to: {value}")
            
            # Update collection data
            self.collection_data[field_id] = value
            
            # Handle dependent fields
            self._handle_dependent_fields(field_id, value)
            
        except Exception as e:
            logger.error(f"Failed to handle field change: {e}")
    
    def _on_selection_change(self, field_id: str, selection: Any):
        """Handle selection field changes"""
        try:
            logger.debug(f"Selection {field_id} changed to: {selection}")
            
            # Update collection data
            self.collection_data[field_id] = selection
            
            # Handle dependent fields
            self._handle_dependent_fields(field_id, selection)
            
        except Exception as e:
            logger.error(f"Failed to handle selection change: {e}")
    
    def _on_checkbox_change(self, field_id: str, value: bool):
        """Handle checkbox field changes"""
        try:
            logger.debug(f"Checkbox {field_id} changed to: {value}")
            
            # Update collection data
            self.collection_data[field_id] = value
            
            # Handle dependent fields
            self._handle_dependent_fields(field_id, value)
            
        except Exception as e:
            logger.error(f"Failed to handle checkbox change: {e}")
    
    def _handle_dependent_fields(self, field_id: str, value: Any):
        """Handle dependent field logic"""
        try:
            if field_id == "processing_location":
                # Show/hide processing path field based on location
                processing_path_widget = getattr(self, "_processing_path_widget", None)
                if processing_path_widget:
                    if value == "external":
                        processing_path_widget.style.visibility = "visible"
                    else:
                        processing_path_widget.style.visibility = "hidden"
            
            elif field_id == "auto_process":
                # Enable/disable process on add field based on auto process
                process_on_add_widget = getattr(self, "_process_on_add_widget", None)
                if process_on_add_widget:
                    process_on_add_widget.enabled = value
            
        except Exception as e:
            logger.error(f"Failed to handle dependent fields: {e}")
    
    def _on_save(self, widget):
        """Handle save button press"""
        try:
            logger.debug("Save button pressed")
            
            # Validate required fields
            if not self._validate_form():
                return
            
            # Call save callback
            if self.on_save:
                self.on_save(self.collection_data)
            
            # Close dialog
            self.close()
            
        except Exception as e:
            logger.error(f"Failed to save collection settings: {e}")
    
    def _on_cancel(self, widget):
        """Handle cancel button press"""
        try:
            logger.debug("Cancel button pressed")
            
            # Call cancel callback
            if self.on_cancel:
                self.on_cancel()
            
            # Close dialog
            self.close()
            
        except Exception as e:
            logger.error(f"Failed to cancel collection settings: {e}")
    
    def _on_window_close(self, window):
        """Handle window close event"""
        try:
            logger.debug("Collection settings dialog window closing")
            
            # Call cancel callback if no save was performed
            if self.on_cancel:
                self.on_cancel()
            
        except Exception as e:
            logger.error(f"Failed to handle window close: {e}")
    
    def _validate_form(self) -> bool:
        """Validate the form data"""
        try:
            # Check required fields
            required_fields = ["name", "type", "processing_location"]
            
            for field_id in required_fields:
                value = self.collection_data.get(field_id)
                if not value:
                    self._show_validation_error(f"Field '{field_id}' is required")
                    return False
            
            # Validate processing path if external
            if self.collection_data.get("processing_location") == "external":
                processing_path = self.collection_data.get("processing_path")
                if not processing_path:
                    self._show_validation_error("Processing path is required for external processing")
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to validate form: {e}")
            return False
    
    def _show_validation_error(self, message: str):
        """Show a validation error message"""
        try:
            # Create error dialog
            error_dialog = toga.Window(
                title="Validation Error",
                size=(400, 150)
            )
            
            error_container = toga.Box(
                style=Pack(
                    direction=COLUMN,
                    margin=20
                )
            )
            
            error_label = toga.Label(
                message,
                style=Pack(
                    color="#FF0000",
                    margin=(0, 0, 20, 0)
                )
            )
            error_container.add(error_label)
            
            ok_button = toga.Button(
                "OK",
                on_press=lambda widget: error_dialog.close(),
                style=Pack(
                    margin=(10, 20),
                    background_color="#007AFF"
                )
            )
            error_container.add(ok_button)
            
            error_dialog.content = error_container
            error_dialog.show()
            
        except Exception as e:
            logger.error(f"Failed to show validation error: {e}")
    
    def show(self):
        """Show the collection settings dialog"""
        try:
            if self.window:
                self.window.show()
                logger.debug("Collection settings dialog shown")
            
        except Exception as e:
            logger.error(f"Failed to show collection settings dialog: {e}")
    
    def close(self):
        """Close the collection settings dialog"""
        try:
            if self.window:
                self.window.close()
                logger.debug("Collection settings dialog closed")
            
        except Exception as e:
            logger.error(f"Failed to close collection settings dialog: {e}")
    
    def set_collection_data(self, collection_data: Dict[str, Any]):
        """Set the collection data for editing"""
        try:
            self.collection_data = collection_data.copy()
            
            # Update form fields if they exist
            self._update_form_fields()
            
            logger.debug(f"Collection data set: {collection_data}")
            
        except Exception as e:
            logger.error(f"Failed to set collection data: {e}")
    
    def _update_form_fields(self):
        """Update form fields with current collection data"""
        try:
            # Update each field widget if it exists
            for field_id, value in self.collection_data.items():
                widget = getattr(self, f"_{field_id}_widget", None)
                if widget:
                    if hasattr(widget, 'value'):
                        widget.value = value
                    elif hasattr(widget, 'text'):
                        widget.text = str(value)
            
        except Exception as e:
            logger.error(f"Failed to update form fields: {e}")
    
    def get_collection_data(self) -> Dict[str, Any]:
        """Get the current collection data"""
        return self.collection_data.copy()
    
    def register_callbacks(self, 
                         on_save: Optional[Callable] = None,
                         on_cancel: Optional[Callable] = None):
        """Register callbacks for dialog actions"""
        self.on_save = on_save
        self.on_cancel = on_cancel
        
        logger.debug("Collection settings dialog callbacks registered") 