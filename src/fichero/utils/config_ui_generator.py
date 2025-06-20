"""
Schema-Driven UI Generator for Toga
Automatically generates UIs from configuration schemas for plans, prompts, and settings. Schemas are stored in YAML files, located in the resources/config_ui_schemas directory. These are used by the BaseConfigWindow class to generate the UI for the plans, prompts, and settings windows.
"""

import toga
from toga.style import Pack
from toga.constants import COLUMN, ROW, LEFT, CENTER, RIGHT
import srsly
import yaml
from pathlib import Path
from typing import Dict, Any, List, Optional, Union, Callable
from enum import Enum
import logging

logger = logging.getLogger(__name__)

class WidgetType(Enum):
    """Supported widget types for auto-generation"""
    TEXT_INPUT = "text_input"
    PASSWORD_INPUT = "password_input"
    NUMBER_INPUT = "number_input"
    MULTILINE_TEXT = "multiline_text"
    SWITCH = "switch"
    SELECTION = "selection"
    SLIDER = "slider"
    LABEL = "label"
    BUTTON = "button"
    SECTION = "section"
    GROUP = "group"
    TABS = "tabs"

class UISchema:
    """Represents a UI schema for automatic generation"""
    
    def __init__(self, title: str, description: str = "", tabs: List[Dict] = None, 
                 sections: List[Dict] = None, style: Dict = None):
        self.title = title
        self.description = description
        self.tabs = tabs or []
        self.sections = sections or []
        self.style = style or {}

class SchemaUIGenerator:
    """Generates Toga UIs from schema definitions"""
    
    def __init__(self, app=None):
        self.app = app
        self.widgets = {}  # Store widget references for data binding
        self.validators = {}  # Store validation functions
        self.change_handlers = {}  # Store change event handlers
        
    def create_window_from_schema(self, schema: UISchema, data: Dict = None, 
                                 on_restore_defaults: Callable = None,
                                 on_save: Callable = None, on_cancel: Callable = None) -> toga.Window:
        """Create a complete window from schema"""
        
        window = toga.Window(
            title=schema.title or "Configuration",
            size=schema.style.get("size", (690, 625)),
            resizable=schema.style.get("resizable", False)
        )
        
        # Store window reference and callbacks
        self.window = window
        self.on_save = on_save
        self.on_cancel = on_cancel
        
        # Main container for content + action buttons
        main_container = toga.Box(style=Pack(direction=COLUMN, flex=1))
        
        # Create content based on schema structure
        if schema.tabs:
            content = self._create_sidebar_interface(schema.tabs, data, on_restore_defaults)
        elif schema.sections:
            content = self._create_sectioned_interface(schema.sections, data)
        else:
            content = toga.Label("No content defined in schema")
        
        main_container.add(content)
        
        # Add action buttons if save/cancel handlers provided
        if on_save or on_cancel:
            action_buttons = self._create_action_buttons()
            main_container.add(action_buttons)
        
        window.content = main_container
        return window
    
    def _create_sidebar_interface(self, tabs: List[Dict], data: Dict = None, on_restore_defaults: Callable = None) -> toga.SplitContainer:
        """Create a sidebar navigation interface using DetailedList"""
        # Store restore defaults handler for later use
        if on_restore_defaults:
            self._restore_defaults_handler = on_restore_defaults
            
        # Direct split container (like workflow app)
        container = toga.SplitContainer(style=Pack(flex=1))
        
        # Prepare data for DetailedList
        sidebar_data = []
        for tab in tabs:
            # Handle icon files - create toga.Icon objects if icon path provided
            icon = None
            title = tab.get('title', '')
            
            if tab.get('icon'):
                try:
                    # Only try to load actual icon files (no emoji fallbacks)
                    if tab['icon'].endswith(('.png', '.jpg', '.jpeg', '.icns', '.ico')):
                        if hasattr(self, 'app') and self.app:
                            icon_path = self.app.paths.app / tab['icon']
                            if icon_path.exists():
                                icon = toga.Icon(icon_path)
                        else:
                            # Fallback - try relative to resources
                            icon_path = Path(__file__).parent.parent / tab['icon']
                            if icon_path.exists():
                                icon = toga.Icon(icon_path)
                    
                    # If icon file doesn't exist, just use None (no fallback to text)
                        
                except Exception:
                    # If icon loading fails, just use None (no fallback to text)
                    pass
            
            sidebar_data.append({
                "icon": icon,
                "title": title,
                "subtitle": "",  # Empty subtitle for single-line display
                "id": tab['id']  # Store ID for reference
            })
        
        # Create DetailedList for sidebar navigation
        self.sidebar_list = toga.DetailedList(
            data=sidebar_data,
            on_select=lambda widget, **kwargs: self._on_sidebar_select(widget, tabs, data),
            style=Pack(
                flex=1,
                margin=0,  # Zero margin all around  
                width=150,  # Fixed width for sidebar
            )
        )
        
        # Content area (right column) - wrapped in ScrollContainer for overflow handling
        self.content_area = toga.Box(
            style=Pack(
                direction=COLUMN,
                margin=(3, 40, 3, 3)  # top, right, bottom, left - 40px margin on right
            )
        )
        
        # Wrap content area in a scroll container
        self.scroll_container = toga.ScrollContainer(
            content=self.content_area,
            vertical=True,
            horizontal=False,
            style=Pack(flex=1)
        )
        
        # Initialize with first section
        self.current_section = tabs[0]["id"] if tabs else None
        
        # Set container content with proportions (like workflow app)
        container.content = [(self.sidebar_list, 150), (self.scroll_container, 540)]
        
        # Show initial section and set initial window title
        if tabs:
            self._switch_section(self.current_section, tabs, data)
        
        # Give the sidebar focus (like the workflow app)
        try:
            self.sidebar_list.focus()
        except AttributeError:
            # focus() method might not be available on DetailedList
            pass
        
        return container
    
    def _on_sidebar_select(self, widget, tabs: List[Dict], data: Dict = None):
        """Handle sidebar selection"""
        row = widget.selection
        if row is None:
            return
            
        section_id = getattr(row, 'id', '')
        if section_id:
            self._switch_section(section_id, tabs, data)

    def _switch_section(self, section_id: str, tabs: List[Dict], data: Dict = None):
        """Switch between sidebar sections"""
        self.current_section = section_id
        
        # Find and display section content
        section_config = next((t for t in tabs if t['id'] == section_id), None)
        if not section_config:
            return
        
        # Update window title based on selected section
        if hasattr(self, 'window') and self.window:
            window_title = section_config.get('window_title') or section_config.get('title', '') or 'Configuration'
            self.window.title = window_title
        
        # Clear and rebuild content
        self.content_area.clear()
        
        # No section title since it's shown in the sidebar selection
        
        if 'sections' in section_config:
            content = self._create_sectioned_interface(section_config['sections'], data)
            self.content_area.add(content)
            
            # Add file management button at bottom of content
            if hasattr(self, '_restore_defaults_handler'):
                manage_btn = toga.Button(
                    "Manage Files...",
                    on_press=lambda w: self._restore_defaults_handler(),
                    style=Pack(
                        width=120,
                        margin=(20, 0, 10, 20),  # top, right, bottom, left
                        font_size=9
                    )
                )
                self.content_area.add(manage_btn)
    
    def _create_sectioned_interface(self, sections: List[Dict], data: Dict = None) -> toga.Box:
        """Create interface with sections"""
        container = toga.Box(style=Pack(direction=COLUMN, flex=1))
        
        for section in sections:
            section_box = self._create_section(section, data)
            container.add(section_box)
        
        return container
    
    def _create_section(self, section: Dict, data: Dict = None) -> toga.Box:
        """Create a single section with fields"""
        section_box = toga.Box(style=Pack(direction=COLUMN, margin=(10, 0, 3, 10)))  # 10pt top, 3pt bottom, 10pt left margin
        
        # Section title
        if section.get('title'):
            title_text = section['title']
            if not title_text.endswith(':'):
                title_text += ':'
            title_label = toga.Label(
                title_text,
                style=Pack(
                    margin_bottom=3,
                    font_size=9
                )
            )
            section_box.add(title_label)
        
        # Section description
        if section.get('description'):
            desc_label = toga.Label(
                section['description'],
                style=Pack(
                    margin_bottom=3,
                    font_size=9
                )
            )
            section_box.add(desc_label)
        
        # Fields
        for field in section.get('fields', []):
            field_widget = self._create_field_widget(field, data)
            if field_widget:
                section_box.add(field_widget)
        
        return section_box
    
    def _create_field_widget(self, field: Dict, data: Dict = None) -> toga.Box:
        """Create a widget for a single field with horizontal layout"""
        field_id = field['id']
        field_type = WidgetType(field['type'])
        current_value = self._get_field_value(field_id, data, field.get('default'))
        
        # Container for the field - horizontal layout
        field_box = toga.Box(style=Pack(direction=ROW, margin_bottom=5))  # 5pt spacing between rows
        
        # Add 10px indent from left
        indent_spacer = toga.Box(style=Pack(width=10))
        field_box.add(indent_spacer)
        
        # Field label (left side)
        if field.get('label'):
            label = toga.Label(
                field['label'],
                style=Pack(
                    width=120,  # Reasonable width for labels
                    margin_right=3,
                    text_align=RIGHT,
                    font_size=9
                )
            )
            field_box.add(label)
        else:
            # Add spacer if no label
            spacer = toga.Box(style=Pack(width=120, margin_right=3))
            field_box.add(spacer)
        
        # Widget container (right side)
        widget_container = toga.Box(style=Pack(direction=COLUMN, flex=1))
        
        # Create the appropriate widget
        widget = None
        
        if field_type == WidgetType.TEXT_INPUT:
            widget = toga.TextInput(
                value=str(current_value) if current_value is not None else "",
                placeholder=field.get('placeholder', ''),
                style=Pack(margin_bottom=3, font_size=9)
            )
        
        elif field_type == WidgetType.PASSWORD_INPUT:
            widget = toga.PasswordInput(
                value=str(current_value) if current_value is not None else "",
                placeholder=field.get('placeholder', ''),
                style=Pack(margin_bottom=3, font_size=9)
            )
        
        elif field_type == WidgetType.NUMBER_INPUT:
            widget = toga.NumberInput(
                value=float(current_value) if current_value is not None else field.get('default', 0),
                min=field.get('min'),
                max=field.get('max'),
                step=field.get('step', 1),
                style=Pack(margin_bottom=3, font_size=9)
            )
        
        elif field_type == WidgetType.MULTILINE_TEXT:
            widget = toga.MultilineTextInput(
                value=str(current_value) if current_value is not None else "",
                placeholder=field.get('placeholder', ''),
                style=Pack(margin_bottom=3, height=field.get('height', 100), font_size=9)
            )
        
        elif field_type == WidgetType.SWITCH:
            widget = toga.Switch(
                field.get('label', ''),
                value=bool(current_value) if current_value is not None else field.get('default', False),
                style=Pack(margin_bottom=3, font_size=9)
            )
        
        elif field_type == WidgetType.SELECTION:
            widget = toga.Selection(
                items=field.get('options', []),
                value=current_value if current_value in field.get('options', []) else None,
                style=Pack(margin_bottom=3, font_size=9)
            )
        
        if widget:
            # Store widget reference for data extraction
            self.widgets[field_id] = widget
            
            # Add validation if specified
            if field.get('validation'):
                self.validators[field_id] = field['validation']
            
            # Add change handler if specified
            if field.get('on_change'):
                self.change_handlers[field_id] = field['on_change']
            
            widget_container.add(widget)
        
        # Help text (below widget)
        if field.get('help'):
            help_label = toga.Label(
                field['help'],
                style=Pack(
                    margin_top=3,
                    font_size=9
                )
            )
            widget_container.add(help_label)
        
        field_box.add(widget_container)
        return field_box
    
    def _get_field_value(self, field_id: str, data: Dict, default: Any = None) -> Any:
        """Get field value from data using dot notation"""
        if not data:
            return default
        
        keys = field_id.split('.')
        value = data
        
        try:
            for key in keys:
                if isinstance(value, dict) and key in value:
                    value = value[key]
                else:
                    return default
            return value
        except:
            return default
    

    
    def extract_data(self) -> Dict:
        """Extract data from all widgets"""
        data = {}
        
        for field_id, widget in self.widgets.items():
            try:
                if isinstance(widget, (toga.TextInput, toga.PasswordInput, toga.MultilineTextInput)):
                    value = widget.value
                elif isinstance(widget, toga.NumberInput):
                    value = widget.value
                elif isinstance(widget, toga.Switch):
                    value = widget.value
                elif isinstance(widget, toga.Selection):
                    value = widget.value
                else:
                    continue
                
                # Set nested values using dot notation
                self._set_nested_value(data, field_id, value)
                
            except Exception as e:
                logger.warning(f"Failed to extract value for {field_id}: {e}")
        
        return data
    
    def _set_nested_value(self, data: Dict, field_id: str, value: Any):
        """Set nested dictionary value using dot notation"""
        keys = field_id.split('.')
        current = data
        
        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]
        
        current[keys[-1]] = value
    
    def validate_data(self, data: Dict) -> List[str]:
        """Validate extracted data"""
        errors = []
        
        for field_id, validation_rules in self.validators.items():
            value = self._get_field_value(field_id, data)
            
            # Add validation logic here based on rules
            if validation_rules.get('required') and not value:
                errors.append(f"{field_id} is required")
            
            if validation_rules.get('min_length') and len(str(value)) < validation_rules['min_length']:
                errors.append(f"{field_id} must be at least {validation_rules['min_length']} characters")
        
        return errors
    
    def _create_action_buttons(self) -> toga.Box:
        """Create Save/Cancel action buttons"""
        button_box = toga.Box(
            style=Pack(
                direction=ROW,
                margin=(10, 20, 20, 20),
                margin_top=10
            )
        )
        
        # Spacer to push buttons to the right
        button_box.add(toga.Box(style=Pack(flex=1)))
        
        # Cancel button
        if self.on_cancel:
            cancel_btn = toga.Button(
                "Cancel",
                on_press=self._handle_cancel_click,
                style=Pack(
                    width=80,
                    height=32,
                    margin_right=10,
                    font_size=12
                )
            )
            button_box.add(cancel_btn)
        
        # Save button
        if self.on_save:
            save_btn = toga.Button(
                "Save",
                on_press=self._handle_save_click,
                style=Pack(
                    width=80,
                    height=32,
                    font_size=12
                )
            )
            button_box.add(save_btn)
        
        return button_box
    
    def _handle_save_click(self, widget):
        """Handle save button click"""
        if self.on_save:
            try:
                data = self.extract_data()
                errors = self.validate_data(data)
                
                if errors:
                    error_msg = "Validation errors:\n" + "\n".join(errors)
                    print(f"❌ {error_msg}")
                    return
                
                self.on_save(data)
            except Exception as e:
                print(f"❌ Save failed: {e}")
                logger.error(f"Save failed: {e}")
    
    def _handle_cancel_click(self, widget):
        """Handle cancel button click"""
        if self.on_cancel:
            self.on_cancel()

def load_ui_schema_from_file(file_path: Path) -> UISchema:
    """Load UI schema from YAML or JSON file"""
    try:
        if file_path.suffix.lower() in ['.yml', '.yaml']:
            with open(file_path, 'r', encoding='utf-8') as f:
                schema_data = yaml.safe_load(f)
        else:
            schema_data = srsly.read_json(file_path)
        
        return UISchema(
            title=schema_data.get('title', 'Configuration'),
            description=schema_data.get('description', ''),
            tabs=schema_data.get('tabs', []),
            sections=schema_data.get('sections', []),
            style=schema_data.get('style', {})
        )
    
    except Exception as e:
        logger.error(f"Failed to load UI schema from {file_path}: {e}")
        raise

# Example usage and schema definitions
PLANS_UI_SCHEMA = {
    "title": "Project Plans Configuration",
    "description": "Configure project workflows, variables, and commands",
    "style": {"size": (800, 900), "resizable": True},
    "tabs": [
        {
            "id": "general",
            "title": "General",
            "sections": [
                {
                    "title": "Project Information",
                    "fields": [
                        {
                            "id": "title",
                            "type": "text_input",
                            "label": "Project Title",
                            "placeholder": "Enter project title",
                            "validation": {"required": True}
                        },
                        {
                            "id": "description",
                            "type": "multiline_text",
                            "label": "Description",
                            "height": 80,
                            "placeholder": "Project description..."
                        }
                    ]
                }
            ]
        },
        {
            "id": "vars",
            "title": "Variables",
            "sections": [
                {
                    "title": "Basic Variables",
                    "fields": [
                        {
                            "id": "vars.name",
                            "type": "text_input",
                            "label": "Project Name",
                            "validation": {"required": True}
                        },
                        {
                            "id": "vars.language",
                            "type": "selection",
                            "label": "Language",
                            "options": ["es", "en", "fr", "de"]
                        },
                        {
                            "id": "vars.version",
                            "type": "text_input",
                            "label": "Version"
                        }
                    ]
                },
                {
                    "title": "Image Formats",
                    "fields": [
                        {
                            "id": "vars.crop_format",
                            "type": "selection",
                            "label": "Crop Format",
                            "options": ["jpg", "png", "jxl"]
                        },
                        {
                            "id": "vars.split_format",
                            "type": "selection",
                            "label": "Split Format",
                            "options": ["jpg", "png", "jxl"]
                        }
                    ]
                }
            ]
        },
        {
            "id": "workflows",
            "title": "Workflows",
            "sections": [
                {
                    "title": "Available Workflows",
                    "description": "Configure workflow sequences",
                    "fields": [
                        {
                            "id": "workflows_info",
                            "type": "label",
                            "label": "Workflows will be displayed here (complex editing)"
                        }
                    ]
                }
            ]
        }
    ]
}

JSONL_CONFIG_UI_SCHEMA = {
    "title": "LLM Configuration Editor",
    "description": "Configure LLM processing steps and prompts",
    "style": {"size": (900, 800)},
    "tabs": [
        {
            "id": "general",
            "title": "General",
            "sections": [
                {
                    "title": "Configuration Info",
                    "fields": [
                        {
                            "id": "name",
                            "type": "text_input",
                            "label": "Configuration Name",
                            "validation": {"required": True}
                        },
                        {
                            "id": "description",
                            "type": "multiline_text",
                            "label": "Description",
                            "height": 60
                        }
                    ]
                }
            ]
        },
        {
            "id": "llm",
            "title": "LLM Settings",
            "sections": [
                {
                    "title": "Model Configuration",
                    "fields": [
                        {
                            "id": "llm.backend",
                            "type": "selection",
                            "label": "Backend",
                            "options": ["openai", "anthropic", "local"]
                        },
                        {
                            "id": "llm.model",
                            "type": "text_input",
                            "label": "Model Name"
                        },
                        {
                            "id": "llm.temperature",
                            "type": "number_input",
                            "label": "Temperature",
                            "min": 0.0,
                            "max": 2.0,
                            "step": 0.1
                        },
                        {
                            "id": "llm.max_tokens",
                            "type": "number_input",
                            "label": "Max Tokens",
                            "min": 1,
                            "max": 1000000
                        }
                    ]
                }
            ]
        }
    ]
} 