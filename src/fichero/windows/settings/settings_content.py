"""
Settings Content Component - Shared UI Logic

This component contains the settings UI logic and can be used
in both desktop windows and mobile views. It provides the complex
YAML-driven schema system for generating settings UIs.
"""

# YAML compatibility - use unified compatibility layer
from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

import logging
from typing import Dict, Any, List
from pathlib import Path
import toga
from toga.style import Pack
from toga.constants import COLUMN, ROW

# Import backend dependencies (keep where they are)
from fichero.config.ui.base_config_library import BaseConfigLibrary, UISchema
from fichero.config.core.settings_manager import SettingsManager
from fichero.config.core.plan_workflow_ui_helper import DEFAULT_PLAN_FILENAME
import gettext  # Import translation function

# Use builtin _ function installed by translation.install()
_ = gettext.gettext

logger = logging.getLogger(__name__)


class SettingsContent(BaseConfigLibrary):
    """Settings content component that can be used in windows or as content replacement"""
    
    def __init__(self, app, show_back_button=False, on_back=None):
        """Initialize the settings content"""
        # Set up paths before calling parent constructor
        self.schema_file = app.paths.app / "resources" / "config_ui_schemas" / "settings_schema.yml"
        
        # Create simplified settings manager
        self.settings_manager = SettingsManager(app)
        
        # Store back button options
        self.show_back_button = show_back_button
        self.on_back = on_back

        # Initialize with settings-specific configuration
        super().__init__(app, use_file_library=False, use_option_container=True, create_desktop_window=False)
        
        logger.info("SettingsContent initialized")
    
    def create(self):
        """Create the settings content UI"""
        # Create the main content using the schema system
        schema = self.get_schema()
        data = self.initialize_settings_data()
        
        # Create content based on schema structure
        if schema.sections:
            # Build content list for OptionContainer
            content_list = []
            for i, section in enumerate(schema.sections):
                section_title = _(section.get('title', f'Section {i}'))  # Translate section title
                section_content = self._create_sectioned_interface(section.get('sections', []), data)
                content_list.append((section_title, section_content))
            
            # Create the OptionContainer
            option_container = toga.OptionContainer(
                content=content_list,
                style=Pack(flex=1, margin=(20, 20, 0, 20))
            )
        elif schema.content_sections:
            # Direct sections become a single tab
            content = self._create_sectioned_interface(schema.content_sections, data)
            option_container = toga.OptionContainer(
                content=[(_("preferences_title"), content)],  # Translate default tab title
                style=Pack(flex=1, margin=(20, 20, 0, 20))
            )
        else:
            # No content defined
            option_container = toga.OptionContainer(
                content=[(_("preferences_title"), toga.Label(_("preferences_no_content")))],
                style=Pack(flex=1, margin=(20, 20, 0, 20))
            )
        
        # Create the main content container
        main_content = toga.Box(style=Pack(direction=COLUMN, flex=1))
        main_content.add(option_container)
        
        # Add the Restore Defaults button
        restore_btn = toga.Button(
            _("preferences_restore_defaults"),  # Translate button text
            on_press=self._handle_restore_defaults,
            style=Pack(margin=(10, 20, 10, 20))
        )
        main_content.add(restore_btn)
        
        # Add back button if requested (for main window use)
        if self.show_back_button and self.on_back:
            # Create container with back button
            container = toga.Box(
                style=Pack(
                    direction=COLUMN,
                    flex=1
                )
            )
            
            back_container = toga.Box(
                style=Pack(
                    direction=ROW,
                    margin_bottom=10
                )
            )
            
            back_button = toga.Button(
                text="← Back",
                on_press=self.on_back
            )
            
            back_container.add(back_button)
            container.add(back_container)
            container.add(main_content)
            
            return container
        
        return main_content
    
    def _handle_restore_defaults(self, widget=None):
        """Handle restore defaults button press"""
        try:
            # Get default settings data
            default_data = self.settings_manager.get_default_template()
            
            # Populate the UI with default values
            self.populate_data(default_data)
            
            # Save the default settings
            self.save_settings_data(default_data)
            
            logger.info("Settings restored to defaults")
            
        except Exception as e:
            logger.error(f"Failed to restore defaults: {e}")
    
    def create_file_manager(self):
        """Create and return the settings file manager (not used for settings)"""
        return None
    
    def get_schema(self) -> UISchema:
        """Load the UI schema from file and populate dynamic options"""
        try:
            logger.info(f"Loading settings schema from: {self.schema_file}")
            with open(self.schema_file, 'r', encoding='utf-8') as f:
                yaml_parser = YAML()
                schema_data = yaml_parser.load(f)
            
            logger.info(f"Loaded schema data: {schema_data.get('title', 'No title')}")
            logger.info(f"Schema sections: {len(schema_data.get('sections', []))}")
            
            # Populate dynamic options for default plan/workflow fields
            self._populate_dynamic_options(schema_data)
            
            schema = UISchema(
                title=schema_data.get('title', _('preferences_title')),
                description=schema_data.get('description', _('preferences_description')),
                sections=schema_data.get('sections', []),  # Main sections from schema
                content_sections=schema_data.get('content_sections', []),  # Direct content sections if no main sections
                window_title=schema_data.get('window_title'),
                window_size=schema_data.get('window_size')
            )
            
            logger.info(f"Created UISchema with {len(schema.sections)} sections")
            return schema
            
        except Exception as e:
            logger.error(f"Failed to load settings schema: {e}")
            # Return minimal schema as fallback
            return UISchema(
                title=_('preferences_title'),
                description=_('preferences_description'),
                content_sections=[
                    {
                        "title": _('preferences_error'),
                        "fields": [
                            {
                                "id": "error_message",
                                "type": "label",
                                "label": _('preferences_load_error').format(error=str(e))
                            }
                        ]
                    }
                ]
            )
    
    def _populate_dynamic_options(self, schema_data: Dict[str, Any]):
        """Populate dynamic options for plan/workflow fields using unified helper"""
        try:
            from fichero.config.core.plan_workflow_ui_helper import PlanWorkflowUIHelper
            
            # Create unified helper
            self.ui_helper = PlanWorkflowUIHelper(self.app)
            
            # Get plan options (clean list without management options)
            plan_options = self.ui_helper.get_plan_options()
            
            # Get the default plan display name by finding the plan with DEFAULT_PLAN_FILENAME
            default_plan_display = None
            for plan_display_name in plan_options:
                # Get the filename for this plan display name
                plan_filename = self.ui_helper.get_plan_filename(plan_display_name)
                if plan_filename == DEFAULT_PLAN_FILENAME.replace('.yml', ''):
                    default_plan_display = plan_display_name
                    break
            
            # Put default plan first if found
            if default_plan_display:
                plan_options = [default_plan_display] + [p for p in plan_options if p != default_plan_display]
            
            self._populate_field_options(schema_data, "defaults.plan", plan_options)

            # Remove/hide the workflow field entirely
            for section in schema_data.get('sections', []):
                for subsection in section.get('sections', []):
                    subsection['fields'] = [f for f in subsection.get('fields', []) if f.get('id') != 'defaults.workflow']
            
            # Set up plan change callback
            self._add_field_callback(schema_data, "defaults.plan", self._on_plan_selection_change)
            
            # Set up workflow change callback  
            self._add_field_callback(schema_data, "defaults.workflow", self._on_workflow_selection_change)
            
            # Find and populate default_workflow options (initially empty, will update based on plan selection)
            self._populate_field_options(schema_data, "defaults.workflow", [_('preferences_select_plan')])
            
            # Set up auto-calculate button handler
            self._add_button_handler(schema_data, "auto_calculate_workers", self._on_auto_calculate_workers)
            
        except Exception as e:
            logger.error(f"Failed to populate dynamic options: {e}")
    
    def _add_field_callback(self, schema_data: Dict[str, Any], field_id: str, callback):
        """Helper to add callback to a specific field"""
        for section in schema_data.get('sections', []):
            for subsection in section.get('sections', []):
                for field in subsection.get('fields', []):
                    if field.get('id') == field_id:
                        field['on_change'] = callback
                        return
    
    def _add_button_handler(self, schema_data: Dict[str, Any], field_id: str, callback):
        """Helper to add button handler to a specific field"""
        for section in schema_data.get('sections', []):
            for subsection in section.get('sections', []):
                for field in subsection.get('fields', []):
                    if field.get('id') == field_id:
                        field['on_press'] = callback
                        return
    
    def _on_plan_selection_change(self, widget):
        """Handle plan selection change - delegates to unified helper"""
        try:
            if not hasattr(self, 'ui_helper'):
                logger.warning("UI helper not available in plan selection change")
                return
            
            plan_value = getattr(widget, 'value', None)
            logger.info(f"Plan selection changed to: {plan_value}")
                
            workflow_widget = self.widgets.get('defaults.workflow')
            if workflow_widget:
                logger.info(f"Found workflow widget, updating options...")
                
                # Use unified helper with save_as_default=True (Settings window)
                result = self.ui_helper.handle_plan_change(
                    widget, 
                    workflow_widget, 
                    save_as_default=True
                )
                logger.info(f"Settings plan changed: {result}")
                
                # Also trigger workflow save if a workflow was selected
                if result.get('workflow'):
                    self._on_workflow_selection_change(workflow_widget)
            else:
                logger.warning("Workflow widget not found in settings")
            
        except Exception as e:
            logger.error(f"Error handling plan selection change: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    def _on_workflow_selection_change(self, widget):
        """Handle workflow selection change - delegates to unified helper"""
        try:
            if not hasattr(self, 'ui_helper'):
                return
                
            # Use unified helper with save_as_default=True (Settings window)
            workflow_name = self.ui_helper.handle_workflow_change(
                widget, 
                save_as_default=True
            )
            logger.info(f"Settings workflow changed: {workflow_name}")
            
        except Exception as e:
            logger.error(f"Error handling workflow selection change: {e}")
    
    def _on_auto_calculate_workers(self, widget):
        """Handle auto-calculate workers button press"""
        try:
            logger.info("Auto-calculating optimal worker configuration...")
            
            # Import the worker sizing utility
            from fichero.director.backends.worker_sizing import get_optimal_workers
            
            # Get current backend type from settings
            current_backend = self._get_field_value("workers.backend", self.original_data, "python")
            
            # Get optimal configuration
            optimal_config = get_optimal_workers(current_backend)
            
            logger.info(f"Optimal configuration: {optimal_config.cpu_workers} CPU, {optimal_config.io_workers} IO")
            logger.info(f"Reasoning: {optimal_config.reasoning}")
            
            # Update the worker count widgets
            cpu_widget = self.widgets.get("workers.cpu_workers")
            io_widget = self.widgets.get("workers.io_workers")
            
            if cpu_widget:
                cpu_widget.value = optimal_config.cpu_workers
                logger.info(f"Updated CPU workers to {optimal_config.cpu_workers}")
            
            if io_widget:
                io_widget.value = optimal_config.io_workers
                logger.info(f"Updated IO workers to {optimal_config.io_workers}")
            
            # Trigger save to persist the changes
            self._perform_save()
            
        except Exception as e:
            logger.error(f"Error auto-calculating workers: {e}")
    
    def _populate_field_options(self, schema_data: Dict[str, Any], field_id: str, options: List[str]):
        """Helper to find and populate options for a specific field"""
        for section in schema_data.get('sections', []):
            for subsection in section.get('sections', []):
                for field in subsection.get('fields', []):
                    if field.get('id') == field_id:
                        # Filter out error messages
                        valid_options = [opt for opt in options if opt not in [_('preferences_no_plans'), _('preferences_error_loading_plans')]]
                        if not valid_options:
                            valid_options = [_('preferences_no_options')]
                        field['options'] = valid_options
                        return

    def populate_data(self, data: Dict[str, Any]):
        """Populate UI widgets with data - handled by schema system"""
        logger.info(f"Settings populate_data called with {len(data)} keys: {list(data.keys())}")
        # The base class handles widget population through the schema system
        # This method is implemented for abstract method compliance
        # Actual population happens in create_content_from_schema()
        pass
    
    def _on_widget_change(self, widget):
        """Handle widget changes - call custom handlers then do auto-save"""
        # First call any custom change handlers
        for field_id, stored_widget in self.widgets.items():
            if stored_widget is widget:
                # Found the widget that changed
                if field_id in self.change_handlers:
                    try:
                        self.change_handlers[field_id](widget)
                    except Exception as e:
                        logger.error(f"Error in change handler for {field_id}: {e}")
                break
        
        # Then call parent's auto-save behavior
        super()._on_widget_change(widget)

    def initialize_settings_data(self) -> Dict[str, Any]:
        """SIMPLE: Load settings using simplified manager"""
        logger.info("Loading settings data")
        try:
            # Use simplified settings manager
            data = self.settings_manager.load_settings()
            logger.info(f"Settings manager returned data with {len(data)} keys: {list(data.keys())}")
            
            # Ensure defaults section exists and is populated from current app defaults
            if 'defaults' not in data:
                data['defaults'] = {}
            
            # Get current app defaults via PlanManager (which now reads from settings)
            try:
                from fichero.config.core.plan_workflow_ui_helper import PlanWorkflowUIHelper
                ui_helper = PlanWorkflowUIHelper(self.app)
                
                current_plan = ui_helper.get_app_default_plan()
                current_workflow = ui_helper.get_app_default_workflow(current_plan)
                
                # Only set if not already in settings (preserve user's settings)
                if not data['defaults'].get('plan'):
                    data['defaults']['plan'] = current_plan or ""
                if not data['defaults'].get('workflow'):
                    data['defaults']['workflow'] = current_workflow or ""
                    
                logger.info(f"Loaded app defaults: plan='{data['defaults']['plan']}', workflow='{data['defaults']['workflow']}'")
            except Exception as e:
                logger.error(f"Failed to load app defaults: {e}")
                data['defaults'].setdefault('plan', "")
                data['defaults'].setdefault('workflow', "")
            
            logger.info(f"Final settings data has {len(data)} keys: {list(data.keys())}")
            return data
            
        except Exception as e:
            logger.error(f"Failed to load settings: {e}")
            logger.info("Returning default template")
            return self.settings_manager.get_default_template()
    
    def save_settings_data(self, data: Dict[str, Any]) -> bool:
        """SIMPLE: Save settings using simplified manager"""
        logger.info(f"Saving settings data with {len(data)} keys: {list(data.keys())}")
        try:
            # The plan/workflow defaults are now in data['defaults']['plan'] and data['defaults']['workflow']
            # They will be automatically synced to shared data by the SettingsManager
            
            # Save settings using simplified manager (this will trigger sync to shared data)
            logger.info(f"Calling settings_manager.save_settings with {len(data)} keys")
            success = self.settings_manager.save_settings(data)
            if success:
                logger.info("Settings saved successfully")
                
                # Language settings removed - no longer needed
                logger.info("🌐 Language system is now automatic")
            else:
                logger.error("Failed to save settings")
            
            return success
            
        except Exception as e:
            logger.error(f"Failed to save settings data: {e}")
            return False
    
    # Public interface methods to match other content components
    def save_settings(self):
        """Save current settings"""
        return self.save_settings_data(self.get_current_data())
    
    def load_settings(self):
        """Load settings"""
        return self.initialize_settings_data()
    
    def refresh(self):
        """Refresh the settings display"""
        if hasattr(self, 'refresh'):
            super().refresh()
    
    def get_current_data(self):
        """Get current settings data"""
        if hasattr(self, 'get_current_data'):
            return super().get_current_data()
        return {} 