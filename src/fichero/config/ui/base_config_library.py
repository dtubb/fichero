"""
Base Configuration Library
# This module creates a three-column window layout. The left column is a library panel for managing configuration files. (.g. Settings, Plans, Pro)
# The middle column contains a category list, and the right column is a scrollable container displaying settings. 
# Both the category list and settings are dynamically generated from a schema definition, which is used to construct the UI.
"""

import toga
from toga.style import Pack
from toga.constants import COLUMN, ROW, Direction, CENTER, LEFT, RIGHT
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Callable, Union
from abc import ABC, abstractmethod
from enum import Enum
import logging
import yaml
import srsly
import asyncio

from ..core.loader import ConfigLoader
from .components.file_library_panel import FileLibraryPanel

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
    CATEGORIES = "categories"
    WORKFLOW_EDITOR = "workflow_editor"


class UISchema:
    """Represents a UI schema for automatic generation"""
    
    def __init__(self, title: str, description: str = "", sections: List[Dict] = None, 
                 content_sections: List[Dict] = None, window_title: str = None, window_size: List[int] = None):
        self.title = title
        self.description = description
        self.sections = sections or []  # These are the "tabs" from YAML
        self.content_sections = content_sections or []  # Direct sections if no tabs
        self.window_title = window_title
        self.window_size = tuple(window_size) if window_size else None


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
            sections=schema_data.get('sections', []),  # Main sections from schema
            content_sections=schema_data.get('content_sections', []),  # Direct content sections if no main sections
            window_title=schema_data.get('window_title'),
            window_size=schema_data.get('window_size')
        )
    
    except Exception as e:
        logger.error(f"Failed to load UI schema from {file_path}: {e}")
        raise


class BaseConfigLibrary(ABC):
    """
    Base configuration library with flexible layout support:
    - Three-panel layout: Library panel (left) + Section sidebar (middle) + Content panel (right) - for Plans/Prompts
    - Two-panel layout: OptionContainer tabs + Content panel - for Settings
    """
    
    def __init__(self, app, use_file_library=True, use_option_container=False):
        self.app = app
        self.use_file_library = use_file_library
        self.use_option_container = use_option_container
        
        # Only create file manager if we're using file library
        self.file_manager = self.create_file_manager() if use_file_library else None
        
        # Data state
        self.current_file = None
        self.original_data = {}
        self.is_editing_default = False
        
        # UI state
        self.current_section = None
        self.window = None
        self.library_panel = None
        self.section_panel = None
        self.content_panel = None
        self.option_container = None  # For settings layout
        
        # Field tracking for data extraction and validation
        self.widgets = {}
        self.validators = {}
        self.change_handlers = {}
        self.button_handlers = {}
        
        self._create_window()
        self._setup_window_close_handler()
        # Load the default file/content after window is created
        self._load_default_file()
    
    # Abstract methods that subclasses must implement
    
    @abstractmethod
    def create_file_manager(self):
        """Create and return the appropriate file manager (optional for settings)"""
        pass
    
    @abstractmethod
    def get_schema(self) -> UISchema:
        """Get the UI schema for this config window"""
        pass
    
    @abstractmethod
    def populate_data(self, data: Dict[str, Any]):
        """Populate UI widgets with data"""
        pass
    
    def initialize_settings_data(self) -> Dict[str, Any]:
        """Initialize settings data (override for settings windows)"""
        return {}
    
    def save_settings_data(self, data: Dict[str, Any]) -> bool:
        """Save settings data (override for settings windows)"""
        return True
    
    # Core functionality
    
    def show(self):
        """Show the configuration window"""
        if not self.window:
            # Window was closed, create a new one
            self._create_window()
            self._setup_window_close_handler()
            # Load the current active file or default
            self._load_default_file()
        
        if self.window:
            self.window.show()
    
    def hide(self):
        """Hide the configuration window"""
        if self.window:
            self.window.hide()
    
    def close(self):
        """Close the configuration window"""
        if self.window:
            # Trigger save before closing
            if self.current_file:
                self._perform_save()
            self.window.close()
            self.window = None 

    def _setup_window_close_handler(self):
        """Set up window close handler to save before closing"""
        if self.window:
            # Simple close handler - just save and allow close
            def close_with_save(widget):
                if self.current_file:
                    self._perform_save()
                # Clean up window reference
                self.window = None
                return True  # Allow window to close
            
            self.window.on_close = close_with_save

    def _create_window(self):
        """Create the integrated window with flexible layout support"""
        if self.use_option_container:
            # Settings window
            # Try to get window properties from schema
            try:
                schema = self.get_schema()
                window_title = getattr(schema, 'window_title', "Fichero Settings")
                window_size = getattr(schema, 'window_size', None)
                if window_size is None:
                    window_size = (425, 500)
            except Exception as e:
                logger.warning(f"Could not load schema for window properties: {e}")
                window_title = "Fichero Settings"
                window_size = (425, 500)
        else:
            # Plans/Prompts window
            window_title = f"{self.file_manager.get_file_type().title()}" if self.file_manager else "Configuration"
            # Try to get window properties from schema
            try:
                schema = self.get_schema()
                window_title = getattr(schema, 'window_title', window_title)
                window_size = getattr(schema, 'window_size', None)
                if window_size is None:
                    window_size = (1000, 700)
            except Exception as e:
                logger.warning(f"Could not load schema for window properties: {e}")
                window_size = (1000, 700)

        self.window = toga.Window(
            title=window_title,
            size=window_size,
            resizable=True
        )
        
        if self.use_option_container:
            # Two-panel layout for settings: OptionContainer + Content
            self._create_option_container_layout()
        else:
            # Three-panel layout for plans/prompts: Library + Section + Content
            self._create_three_panel_layout()
    
    def _create_three_panel_layout(self):
        """Create the traditional three-panel layout (Library + Section + Content)"""
        # Create three panels using consistent helper methods
        self.library_panel = self._create_library_panel()
        self.section_panel = self._create_section_panel()  
        self.content_panel = self._create_content_panel()
        
        # Window content - horizontal layout with three panels
        window_content = toga.Box(style=Pack(direction=ROW, flex=1))
        window_content.add(self.library_panel)
        window_content.add(self.section_panel)
        window_content.add(self.content_panel)
        
        self.window.content = window_content
    
    def _create_option_container_layout(self):
        """Create the two-panel layout with OptionContainer for settings"""
        # Create OptionContainer for navigation
        self.option_container = toga.OptionContainer(style=Pack(flex=1, margin=(20, 20, 0, 20)))  # 20px margins on top, right, left, but not bottom
        
        # Create content panel (will be used by individual tabs)
        self.content_panel = self._create_content_panel()
        
        # Create Restore Defaults button
        restore_btn = toga.Button(
            "Restore Defaults",
            on_press=self._handle_restore_defaults,
            style=Pack(margin=(10, 20, 10, 20), width=100)  # Normal height, 100px width, 20px left/right margins
        )
        
        # Window content - OptionContainer takes most space, button at bottom
        window_content = toga.Box(style=Pack(direction=COLUMN, flex=1))
        window_content.add(self.option_container)
        window_content.add(restore_btn)
        
        self.window.content = window_content
        
    def _create_library_panel(self) -> FileLibraryPanel:
        """Create the file library panel using the dedicated component"""
        if not self.use_file_library:
            # Return a dummy panel for settings (should not be used)
            return toga.Box(style=Pack(width=0))
        
        return FileLibraryPanel(
            file_manager=self.file_manager,
            on_file_select=self._on_file_select,
            on_new_file=self._handle_new,
            on_delete_file=self._handle_delete,
            on_duplicate_file=self._handle_duplicate,
            on_import_file=self._handle_import,
            on_export_file=self._handle_export,
            on_restore_defaults=self._handle_restore_defaults
        )
    
    def _create_section_panel(self) -> toga.Box:
        """Create the section navigation panel (center)"""
        return toga.Box(
            style=Pack(direction=COLUMN, width=200, margin_left=3, margin_right=3)
        )
    
    def _create_content_panel(self) -> toga.ScrollContainer:
        """Create the main content panel (right) - scrollable settings area"""
        return toga.ScrollContainer(
            vertical=True,
            horizontal=False,
            style=Pack(flex=1, margin=(0, 0, 0, 0),
                       background_color="transparent") # Content Panel - flexible width that takes up remainder of window. 
        )

    # UI Generation Methods (integrated from ui_generator)
    
    def create_content_from_schema(self, schema: UISchema, data: Dict = None, 
                                   on_restore_defaults: Callable = None,
                                   on_title_change: Callable = None):
        """Create UI content from schema - populates category and content areas directly"""
        
        logger.info(f"create_content_from_schema called with schema: {schema.title}, data: {len(data) if data else 0} keys")
        
        # Store callback handlers for later use
        if on_restore_defaults:
            self._restore_defaults_handler = on_restore_defaults
        if on_title_change:
            self._title_change_handler = on_title_change
        
        if self.use_option_container:
            # OptionContainer layout for settings
            logger.info("Using OptionContainer layout for settings")
            self._populate_option_container(schema, data)
        else:
            # Traditional three-panel layout for plans/prompts
            logger.info("Using three-panel layout for plans/prompts")
            self._populate_three_panel_layout(schema, data)
    
    def _populate_three_panel_layout(self, schema: UISchema, data: Dict = None):
        """Populate the traditional three-panel layout"""
        # Create content based on schema structure
        if schema.sections:
            self._populate_section_sidebar(schema.sections, data)
            # Initialize with first section
            self.current_section = schema.sections[0]["id"] if schema.sections else None
            if schema.sections:
                self._switch_section(self.current_section, schema.sections, data)
        elif schema.content_sections:
            # For direct sections, show empty section panel and content directly
            self.section_panel.clear()
            content = self._create_sectioned_interface(schema.content_sections, data)
            self.content_panel.content = content
        else:
            self.content_panel.content = toga.Label("No content defined in schema")
    
    def _populate_option_container(self, schema: UISchema, data: Dict = None):
        """Populate the OptionContainer layout for settings"""
        logger.info(f"Populating OptionContainer with schema: {schema.title}, data: {len(data) if data else 0} keys")
        if data:
            logger.info(f"Data keys: {list(data.keys())}")
        logger.info(f"Schema sections: {len(schema.sections)}")
        logger.info(f"Schema content_sections: {len(schema.content_sections)}")
        
        # Create content based on schema structure
        if schema.sections:
            logger.info(f"Creating tabs from {len(schema.sections)} sections")
            # Build content list for OptionContainer
            content_list = []
            for i, section in enumerate(schema.sections):
                section_title = section.get('title', f'Section {i}')
                logger.info(f"Creating tab: {section_title}")
                section_content = self._create_sectioned_interface(section.get('sections', []), data)
                
                # Add tab without icon (macOS doesn't support OptionContainer icons)
                content_list.append((section_title, section_content))
                logger.info(f"Added tab: {section_title}")
            
            # Recreate the OptionContainer with the new content
            self.option_container = toga.OptionContainer(
                content=content_list,
                style=Pack(flex=1, margin=(20, 20, 0, 20))
            )
        elif schema.content_sections:
            logger.info(f"Creating single tab from {len(schema.content_sections)} content sections")
            # Direct sections become a single tab
            content = self._create_sectioned_interface(schema.content_sections, data)
            self.option_container = toga.OptionContainer(
                content=[("Settings", content)],
                style=Pack(flex=1, margin=(20, 20, 0, 20))
            )
        else:
            logger.warning("No sections or content_sections found in schema")
            # No content defined
            self.option_container = toga.OptionContainer(
                content=[("Settings", toga.Label("No content defined in schema"))],
                style=Pack(flex=1, margin=(20, 20, 0, 20))
            )
        
        # Update the window content to use the new OptionContainer
        window_content = toga.Box(style=Pack(direction=COLUMN, flex=1))
        window_content.add(self.option_container)
        
        # Re-add the Restore Defaults button
        restore_btn = toga.Button(
            "Restore Defaults",
            on_press=self._handle_restore_defaults,
            style=Pack(margin=(10, 20, 10, 20), width=100)
        )
        window_content.add(restore_btn)
        
        self.window.content = window_content
        
        logger.info(f"OptionContainer now has {len(self.option_container.content)} tabs")
    
    def _populate_section_sidebar(self, sections: List[Dict], data: Dict = None):
        """Populate the section panel with navigation tree"""
        # Clear existing content
        self.section_panel.clear()
        
        # Create section tree
        self.section_tree = toga.Tree(
            headings=["Section"],
            accessors=["name"],
            on_select=lambda widget: self._on_section_select(widget, sections, data),
            style=Pack(flex=1, margin=0)
        )
        
        # Add sections to tree
        for section in sections:
            title = section.get('title', '')
            section_id = section.get('id', f"section_{len(self.section_tree.data)}")  # Generate ID if missing
            self.section_tree.data.append({
                "name": title,
                "id": section_id  # Store ID for reference
            })
        
        self.section_panel.add(self.section_tree)
    
    def _auto_select_first_section(self):
        """Auto-select the first section in the tree - Tree.selection is read-only, so this is a no-op"""
        # Note: Tree.selection property has no setter, so we can't programmatically select items
        # The user will need to manually select a section to start editing
        pass
    
    def _on_section_select(self, widget, sections: List[Dict], data: Dict = None):
        """Handle section selection"""
        selection = widget.selection
        if selection is None:
            return
            
        section_id = getattr(selection, 'id', '')
        if section_id:
            self._switch_section(section_id, sections, data)

    def _switch_section(self, section_id: str, sections: List[Dict], data: Dict = None):
        """Switch between sidebar sections"""
        self.current_section = section_id
        
        # Find and display section content
        section_config = next((s for s in sections if s.get('id') == section_id), None)
        if not section_config:
            return
        
        # Notify parent about section change (for window title updates)
        if hasattr(self, '_title_change_handler') and self._title_change_handler:
            section_title = section_config.get('title', '')
            self._title_change_handler(section_title)
        
        # Create and set content directly
        if 'sections' in section_config:
            content = self._create_sectioned_interface(section_config['sections'], data)
            self.content_panel.content = content
    
    def _create_sectioned_interface(self, sections: List[Dict], data: Dict = None) -> toga.Box:
        """Create interface with sections"""
        container = toga.Box(style=Pack(
            direction=COLUMN, 
            flex=1,
            margin=(20, 20, 0, 20)   # 20px margins on top, right, left, but not bottom
        ))
        
        for section in sections:
            section_box = self._create_section(section, data)
            container.add(section_box)
        
        return container
    
    def _create_section(self, section: Dict, data: Dict = None) -> toga.Box:
        """Create a single section with fields"""
        section_box = toga.Box(style=Pack(direction=COLUMN, margin=(10, 0, 3, 0)))  # 10pt top, 3pt bottom, no left margin
        
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
        logger.debug(f"Creating widget for {field_id}: type={field_type}, value={current_value}")
        
        # Container for the field - horizontal layout
        field_box = toga.Box(style=Pack(direction=ROW, margin_bottom=5))  # 5pt spacing between rows
        
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
                style=Pack(margin_bottom=3, font_size=9),
                on_change=self._on_widget_change
            )
        
        elif field_type == WidgetType.PASSWORD_INPUT:
            widget = toga.PasswordInput(
                value=str(current_value) if current_value is not None else "",
                placeholder=field.get('placeholder', ''),
                style=Pack(margin_bottom=3, font_size=9),
                on_change=self._on_widget_change
            )
        
        elif field_type == WidgetType.NUMBER_INPUT:
            widget = toga.NumberInput(
                value=float(current_value) if current_value is not None else field.get('default', 0),
                min=field.get('min'),
                max=field.get('max'),
                step=field.get('step', 1),
                style=Pack(margin_bottom=3, font_size=9),
                on_change=self._on_widget_change
            )
        
        elif field_type == WidgetType.MULTILINE_TEXT:
            widget = toga.MultilineTextInput(
                value=str(current_value) if current_value is not None else "",
                placeholder=field.get('placeholder', ''),
                style=Pack(margin_bottom=3, height=field.get('height', 100), font_size=9),
                on_change=self._on_widget_change
            )
        
        elif field_type == WidgetType.SWITCH:
            widget = toga.Switch(
                field.get('label', ''),
                value=bool(current_value) if current_value is not None else field.get('default', False),
                style=Pack(margin_bottom=3, font_size=9),
                on_change=self._on_widget_change
            )
        
        elif field_type == WidgetType.SELECTION:
            widget = toga.Selection(
                items=field.get('options', []),
                value=current_value if current_value in field.get('options', []) else None,
                style=Pack(margin_bottom=3, font_size=9),
                on_change=self._on_widget_change
            )
        
        elif field_type == WidgetType.BUTTON:
            widget = toga.Button(
                field.get('label', 'Button'),
                style=Pack(margin_bottom=3, font_size=9, width=120),
                on_press=self._on_button_press
            )
        
        elif field_type == WidgetType.WORKFLOW_EDITOR:
            # Create workflow editor - a combination of selection and step management
            widget = self._create_workflow_editor_widget(field, data)
        
        if widget:
            # Store widget reference for data extraction
            self.widgets[field_id] = widget
            
            # Add validation if specified
            if field.get('validation'):
                self.validators[field_id] = field['validation']
            
            # Add change handler if specified
            if field.get('on_change'):
                self.change_handlers[field_id] = field['on_change']
            
            # Add button handler if specified
            if field.get('on_press'):
                self.button_handlers[field_id] = field['on_press']
            
            widget_container.add(widget)
        
        # Help text (below widget)
        if field.get('help'):
            help_label = toga.Label(
                field['help'],
                style=Pack(
                    margin_top=3,
                    font_size=9,
                    width=280  # Constrain width to force wrapping
                )
            )
            widget_container.add(help_label)
        
        field_box.add(widget_container)
        return field_box
    
    def _create_workflow_editor_widget(self, field: Dict, data: Dict = None) -> toga.Box:
        """Create a sophisticated workflow editor widget"""
        container = toga.Box(style=Pack(direction=COLUMN, margin_bottom=3))
        
        # Get available workflows and commands from data
        workflows = data.get('workflows', {}) if data else {}
        commands = data.get('commands', []) if data else []
        
        # Create workflow selection dropdown
        workflow_names = list(workflows.keys()) if workflows else ["default"]
        workflow_selector = toga.Selection(
            items=workflow_names,
            style=Pack(margin_bottom=5, font_size=9)
        )
        
        # Label for workflow selector
        selector_label = toga.Label("Select Workflow:", style=Pack(font_size=9, margin_bottom=3))
        container.add(selector_label)
        
        # Workflow selector with management buttons
        workflow_management_box = toga.Box(style=Pack(direction=ROW, margin_bottom=5))
        workflow_management_box.add(workflow_selector)
        
        # Add workflow management buttons
        new_workflow_btn = toga.Button(
            "New",
            style=Pack(margin_left=5, width=50, font_size=8),
            on_press=lambda widget: self._create_new_workflow(workflows, workflow_selector, step_widgets)
        )
        
        copy_workflow_btn = toga.Button(
            "Copy",
            style=Pack(margin_left=5, width=50, font_size=8),
            on_press=lambda widget: self._copy_current_workflow(workflows, workflow_selector, step_widgets)
        )
        
        workflow_management_box.add(new_workflow_btn)
        workflow_management_box.add(copy_workflow_btn)
        
        container.add(workflow_management_box)
        
        # Create step management area
        steps_label = toga.Label("Workflow Steps:", style=Pack(font_size=9, margin_bottom=3, margin_top=10))
        container.add(steps_label)
        
        # Scrollable container for steps
        steps_container = toga.ScrollContainer(
            vertical=True,
            style=Pack(height=200, margin_bottom=5)
        )
        
        steps_box = toga.Box(style=Pack(direction=COLUMN))
        
        # Get available command names for step options
        available_commands = [cmd.get('name', '') for cmd in commands if cmd.get('name')]
        
        # Create step checkboxes for current workflow
        current_workflow = workflow_names[0] if workflow_names else "default"
        current_steps = workflows.get(current_workflow, []) if workflows else []
        
        step_widgets = {}
        
        # Build dependency information for visualization
        command_dependencies = {}
        for cmd in commands:
            cmd_name = cmd.get('name', '')
            dependencies = cmd.get('depends_on', [])
            command_dependencies[cmd_name] = dependencies
        
        for command_name in available_commands:
            step_enabled = command_name in current_steps
            
            # Create step container with checkbox and dependency info
            step_container = toga.Box(style=Pack(direction=COLUMN, margin_bottom=3))
            
            # Main checkbox for the step
            step_checkbox = toga.Switch(
                command_name,
                value=step_enabled,
                style=Pack(margin_bottom=1, font_size=9),
                on_change=self._on_workflow_step_change
            )
            
            step_container.add(step_checkbox)
            
            # Add dependency information if available
            dependencies = command_dependencies.get(command_name, [])
            if dependencies:
                dep_text = f"   ↳ Depends on: {', '.join(dependencies)}"
                dep_label = toga.Label(
                    dep_text,
                    style=Pack(font_size=8, margin_left=15, margin_bottom=2, color="#666666")
                )
                step_container.add(dep_label)
            
            steps_box.add(step_container)
            step_widgets[command_name] = step_checkbox
        
        steps_container.content = steps_box
        container.add(steps_container)
        
        # Store step widgets for later access in the main widgets dictionary
        # This allows the PlansLibrary to access them during data extraction
        container._workflow_step_widgets = step_widgets
        container._workflow_selector = workflow_selector
        
        # Set up workflow selector change handler
        def on_workflow_change(widget):
            selected_workflow = widget.value
            if selected_workflow and workflows:
                workflow_steps = workflows.get(selected_workflow, [])
                # Update step checkboxes
                for cmd_name, checkbox in step_widgets.items():
                    checkbox.value = cmd_name in workflow_steps
            self._on_widget_change(widget)
        
        workflow_selector.on_change = on_workflow_change
        
        # Select first workflow by default
        if workflow_names:
            workflow_selector.value = workflow_names[0]
        
        return container
    
    def _on_workflow_step_change(self, widget):
        """Handle workflow step enable/disable changes"""
        self._on_widget_change(widget)
    
    def _create_new_workflow(self, workflows, workflow_selector, step_widgets):
        """Create a new workflow"""
        try:
            # Generate a unique workflow name
            base_name = "new_workflow"
            counter = 1
            new_name = base_name
            
            while new_name in workflows:
                new_name = f"{base_name}_{counter}"
                counter += 1
            
            # Add new empty workflow
            workflows[new_name] = []
            
            # Update selector items
            workflow_selector.items = list(workflows.keys())
            workflow_selector.value = new_name
            
            # Clear all step checkboxes
            for checkbox in step_widgets.values():
                checkbox.value = False
            
            self._on_widget_change(workflow_selector)
            
        except Exception as e:
            logger.error(f"Failed to create new workflow: {e}")
    
    def _copy_current_workflow(self, workflows, workflow_selector, step_widgets):
        """Copy the currently selected workflow"""
        try:
            current_workflow = workflow_selector.value
            if not current_workflow or current_workflow not in workflows:
                return
            
            # Generate a unique name for the copy
            base_name = f"{current_workflow}_copy"
            counter = 1
            new_name = base_name
            
            while new_name in workflows:
                new_name = f"{current_workflow}_copy_{counter}"
                counter += 1
            
            # Copy the workflow steps
            workflows[new_name] = workflows[current_workflow].copy()
            
            # Update selector items
            workflow_selector.items = list(workflows.keys())
            workflow_selector.value = new_name
            
            # Update checkboxes to match copied workflow
            copied_steps = workflows[new_name]
            for cmd_name, checkbox in step_widgets.items():
                checkbox.value = cmd_name in copied_steps
            
            self._on_widget_change(workflow_selector)
            
        except Exception as e:
            logger.error(f"Failed to copy workflow: {e}")
    
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
            logger.debug(f"Field {field_id}: {value} (default: {default})")
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
                    # Convert Decimal to int or float to avoid YAML serialization issues
                    raw_value = widget.value
                    if raw_value is not None:
                        # Convert to int if it's a whole number, otherwise float
                        if raw_value == int(raw_value):
                            value = int(raw_value)
                        else:
                            value = float(raw_value)
                    else:
                        value = None
                elif isinstance(widget, toga.Switch):
                    value = widget.value
                elif isinstance(widget, toga.Selection):
                    value = widget.value
                else:
                    continue
                
                logger.debug(f"Extracted {field_id}: {value}")
                
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
    
    def _load_default_file(self):
        """Load the first available file or active file"""
        if not self.use_file_library:
            # For settings, initialize with default data
            logger.info("Loading settings data (use_file_library=False)")
            data = self.initialize_settings_data()
            logger.info(f"Settings data loaded: {len(data)} keys")
            self.original_data = data.copy()
            self.current_file = None  # Settings don't have a specific file
            
            # Create UI content
            schema = self.get_schema()
            logger.info(f"Creating UI content with schema: {schema.title}")
            self.create_content_from_schema(
                schema=schema,
                data=data,
                on_restore_defaults=self._handle_restore_defaults,
                on_title_change=lambda section: self._update_window_title("Settings", section)
            )
            return
        
        # Traditional file-based loading for plans/prompts
        # Try to get active file first (if file manager supports it)
        active_file = None
        try:
            active_file = self.file_manager.get_active_file()
        except Exception:
            # File manager doesn't support active file tracking
            pass
        
        if active_file and active_file.exists():
            self._load_file(active_file)
        else:
            # Load first available file
            files = self.file_manager.discover_files()
            if files:
                file_path = files[0]["path"]
                self._load_file(file_path)
    
    def _on_file_select(self, file_path: Path, file_info: Dict):
        """Handle file selection from the library panel"""
        if not self.use_file_library:
            # Settings don't have file selection
            return
        
        self._load_file(file_path)
        self.current_file = file_path
        # Update the active file indicator without refreshing the tree
        if self.library_panel:
            self.library_panel.update_active_file_indicator()
    
    def _load_file(self, file_path: Path):
        """Load a configuration file into the editor"""
        if not self.use_file_library:
            # Settings don't load individual files
            return
        
        try:
            # Load file data using file manager
            data = self.file_manager.load_file(file_path)
            self.original_data = data.copy()
            self.current_file = file_path
            self.is_editing_default = self.file_manager.is_default_file(file_path)
            
            # Try to set as active file in file manager (if supported)
            try:
                self.file_manager.set_active_file(file_path)
            except Exception:
                # File manager doesn't support active file tracking
                pass
            
            # Update window title with file name
            self._update_window_title(file_path.stem)
            
            # Create UI content using integrated generator
            schema = self.get_schema()
            self.create_content_from_schema(
                schema=schema,
                data=data,
                on_restore_defaults=self._handle_restore_defaults,
                on_title_change=lambda section: self._update_window_title(file_path.stem, section)
            )
            
            # Call populate_data if the subclass has overridden it
            if hasattr(self, 'populate_data') and self.populate_data != BaseConfigLibrary.populate_data:
                self.populate_data(data)
            
        except Exception as e:
            logger.error(f"Failed to load file {file_path}: {e}")
    
    def _update_window_title(self, file_name: str, current_section: str = None):
        """Update window title with file name and current section"""
        if self.window:
            if current_section:
                self.window.title = f"{file_name} ({current_section})"
            else:
                self.window.title = file_name
    
    # Button handlers
    
    def _perform_save(self):
        """Perform save operation - used by both manual and auto-save"""
        if not self.use_file_library:
            # For settings, save to shared data
            try:
                logger.info("Performing settings save...")
                # Extract data from currently visible UI widgets
                widget_data = self.extract_data()
                logger.info(f"Extracted widget data: {list(widget_data.keys())}")
                
                # Merge with original data to preserve sections not currently visible
                merged_data = self.original_data.copy() if self.original_data else {}
                self._deep_merge_data(merged_data, widget_data)
                logger.info(f"Merged data keys: {list(merged_data.keys())}")
                
                # Save to shared data (settings-specific)
                success = self.save_settings_data(merged_data)
                if success:
                    # Update original data to the merged result
                    self.original_data = merged_data.copy()
                    logger.info("✅ Settings save completed successfully")
                else:
                    logger.error("❌ Settings save failed")
                
                return success
                
            except Exception as e:
                logger.error(f"Settings save failed: {e}")
                return False
        
        # Traditional file-based saving for plans/prompts
        if not self.current_file:
            return False
        
        try:
            # Extract data from currently visible UI widgets
            widget_data = self.extract_data()
            
            # Merge with original data to preserve sections not currently visible
            # Start with original data as base
            merged_data = self.original_data.copy() if self.original_data else {}
            
            # Deep merge widget data into original data
            self._deep_merge_data(merged_data, widget_data)
            
            # If editing a default file, save to user directory instead
            if self.is_editing_default:
                save_path = self.file_manager.get_user_save_path(self.current_file.name)
                if save_path and self.file_manager.save_file(save_path, merged_data):
                    # Update current file to the user version
                    self.current_file = save_path
                    self.is_editing_default = False
                    
                    # Update window title
                    self._update_window_title(save_path.stem)
                else:
                    return False
            else:
                # Save to current file
                if not self.file_manager.save_file(self.current_file, merged_data):
                    return False
            
            # Update original data to the merged result
            self.original_data = merged_data.copy()
            
            # Set as currently editing file and update indicator
            self.file_manager.set_active_file(self.current_file)
            if self.library_panel:
                self.library_panel.update_active_file_indicator()
            
            return True
            
        except Exception as e:
            logger.error(f"Auto-save failed: {e}")
            return False
    
    def _deep_merge_data(self, base: Dict, updates: Dict):
        """Deep merge updates into base dictionary, preserving nested structure"""
        for key, value in updates.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                # Recursively merge nested dictionaries
                self._deep_merge_data(base[key], value)
            else:
                # Replace/add the value
                base[key] = value
    
    def _handle_restore_defaults(self, widget=None):
        """Handle restore defaults button"""
        if not self.use_file_library:
            # For settings, delete user settings file and reload defaults
            try:
                self.settings_manager.delete_user_settings()
                # Reload UI with default data
                default_data = self.initialize_settings_data()
                self.original_data = default_data.copy()
                schema = self.get_schema()
                self.create_content_from_schema(
                    schema=schema,
                    data=default_data,
                    on_restore_defaults=self._handle_restore_defaults,
                    on_title_change=lambda section: self._update_window_title("Settings", section)
                )
            except Exception as e:
                logger.error(f"Failed to restore settings defaults: {e}")
            return
        
        # Traditional file-based restore for plans/prompts
        if not self.current_file:
            return
        
        try:
            # If this is a user file, try to find the corresponding default
            if not self.is_editing_default:
                default_dir, user_dir = self.file_manager.get_directories()
                if default_dir:
                    default_file = default_dir / self.current_file.name
                    if default_file.exists():
                        # Load the default file and update indicator
                        self._load_file(default_file)
                        if self.library_panel:
                            self.library_panel.update_active_file_indicator()
                        return
            
            # If already editing default or no default found, just reload current file
            self._load_file(self.current_file)
            if self.library_panel:
                self.library_panel.update_active_file_indicator()
            
        except Exception as e:
            logger.error(f"Failed to restore defaults: {e}")
    
    def _handle_new(self):
        """Handle new file creation"""
        if not self.use_file_library:
            # Settings don't create new files
            return
        
        try:
            new_file_path = self.file_manager.create_new_file()
            if new_file_path:
                # Load new file first (this sets it as active), then refresh library panel
                self._load_file(new_file_path)
                if self.library_panel:
                    self.library_panel.refresh_files()
                    self.library_panel.update_active_file_indicator()
            
        except Exception as e:
            logger.error(f"Failed to create new file: {e}")
    
    def _handle_delete(self, file_info: Dict):
        """Handle file deletion"""
        if not self.use_file_library:
            # Settings don't delete files
            return
        
        try:
            file_path = file_info["file_path"]
            
            # Check if it's a default file
            if file_info.get("is_default", False):
                # Show error dialog for default files
                async def show_error():
                    await self.window.dialog(toga.ErrorDialog(
                        "Cannot Delete",
                        "Default files cannot be deleted."
                    ))
                asyncio.create_task(show_error())
                return

            # Ask for confirmation
            async def confirm_delete():
                confirm = await self.window.dialog(toga.ConfirmDialog(
                    "Confirm Delete",
                    f"Are you sure you want to delete '{file_path.name}'?"
                ))
                if confirm:
                    if self.file_manager.delete_file(file_path):
                        # Clear editor if this was the current file
                        if self.current_file == file_path:
                            self.current_file = None
                            window_title = f"{self.file_manager.get_file_type().title()}" if self.file_manager else "Configuration"
                            self.window.title = window_title
                            self.content_panel.content = toga.Label("Select a file to edit")
                            self.section_panel.clear()
                        
                        # Refresh library panel
                        if self.library_panel:
                            self.library_panel.refresh_files()
            
            asyncio.create_task(confirm_delete())
            
        except Exception as e:
            logger.error(f"Failed to delete file: {e}")
            async def show_error():
                await self.window.dialog(toga.ErrorDialog(
                    "Delete Error",
                    f"Failed to delete file: {e}"
                ))
            asyncio.create_task(show_error())
    
    def _handle_duplicate(self, file_info: Dict):
        """Handle file duplication"""
        if not self.use_file_library:
            # Settings don't duplicate files
            return
        
        try:
            source_file = file_info["file_path"]
            
            new_file_path = self.file_manager.duplicate_file(source_file)
            if new_file_path:
                # Load duplicated file first (this sets it as active), then refresh library panel
                self._load_file(new_file_path)
                if self.library_panel:
                    self.library_panel.refresh_files()
                    self.library_panel.update_active_file_indicator()
            
        except Exception as e:
            logger.error(f"Failed to duplicate file: {e}")
    
    def _handle_import(self):
        """Handle file import with file picker"""
        if not self.use_file_library:
            # Settings don't import files
            return
        
        try:
            file_type = self.file_manager.get_file_type() if self.file_manager else "file"
            extensions = self.file_manager.get_file_extensions() if self.file_manager else ['.yml', '.json']
            
            # Create file filter for supported extensions
            file_filter = []
            for ext in extensions:
                file_filter.append(f"*{ext}")
            
            # Show open file dialog (this will work on supported platforms)
            self.window.open_file_dialog(
                title=f"Import {file_type.title()} File",
                file_types=file_filter,
                on_result=self._on_import_file_selected
            )
            
        except Exception as e:
            logger.error(f"Failed to show import dialog: {e}")
    
    def _on_import_file_selected(self, widget, path, **kwargs):
        """Handle file selected for import"""
        try:
            if not path:
                return  # User cancelled
            
            import_path = Path(path)
            if not import_path.exists():
                return
            
            # Generate new filename in user directory
            user_dir = self.file_manager.get_user_save_path("dummy").parent
            new_filename = import_path.name
            
            # Ensure unique filename
            counter = 1
            original_stem = import_path.stem
            extension = import_path.suffix
            
            while (user_dir / new_filename).exists():
                new_filename = f"{original_stem}_imported_{counter}{extension}"
                counter += 1
            
            new_path = user_dir / new_filename
            
            # Copy the file
            import shutil
            shutil.copy2(import_path, new_path)
            
            # Load imported file first (this sets it as active), then refresh library panel
            self._load_file(new_path)
            self.library_panel.refresh_files()
            self.library_panel.update_active_file_indicator()
            
        except Exception as e:
            logger.error(f"Failed to import file: {e}")
    
    def _handle_export(self, file_info: Dict):
        """Handle file export with file picker"""
        if not self.use_file_library:
            # Settings don't export files
            return
        
        try:
            file_path = file_info["file_path"]
            
            # Show save file dialog
            self.window.save_file_dialog(
                title=f"Export {file_path.name}",
                suggested_filename=file_path.name,
                on_result=lambda widget, path, **kwargs: self._on_export_file_selected(widget, path, file_path, **kwargs)
            )
            
        except Exception as e:
            logger.error(f"Failed to show export dialog: {e}")
    
    def _on_export_file_selected(self, widget, path, source_file_path, **kwargs):
        """Handle location selected for export"""
        try:
            if not path:
                return  # User cancelled
            
            export_path = Path(path)
            
            # Copy the file
            import shutil
            shutil.copy2(source_file_path, export_path)
            
        except Exception as e:
            logger.error(f"Failed to export file: {e}")
    

    
    def _on_widget_change(self, widget):
        """Handle widget value changes - trigger immediate auto-save"""
        # For settings windows (use_file_library=False), current_file is None but we still want to save
        # For file-based windows, only save if we have a current file
        if self.use_file_library and not self.current_file:
            return
        
        logger.info(f"Widget changed, triggering auto-save (use_file_library={self.use_file_library})")
        self._perform_save()
    
    def _on_button_press(self, widget):
        """Handle button presses - delegate to settings window if available"""
        # Find which button was pressed
        for field_id, stored_widget in self.widgets.items():
            if stored_widget is widget:
                logger.info(f"Button pressed: {field_id}")
                
                # Call custom button handler if available
                if field_id in self.button_handlers:
                    try:
                        self.button_handlers[field_id](widget)
                    except Exception as e:
                        logger.error(f"Error in button handler for {field_id}: {e}")
                break
    
    # Keep old method name for backward compatibility
    def _handle_save(self, widget=None):
        """Handle manual save button (if present) - delegates to _perform_save"""
        self._perform_save() 