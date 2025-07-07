"""
Settings Library
Configuration library for application settings with file browser
"""

import yaml
from pathlib import Path
from typing import Dict, Any, List
import logging

from ..base_config_library import BaseConfigLibrary
from ..base_config_library import UISchema
from ...core.settings_manager import SettingsManager
from ....ui.i18n import _  # Import translation function

logger = logging.getLogger(__name__)


class SettingsLibrary(BaseConfigLibrary):
    """Settings library with OptionContainer navigation and single settings file"""
    
    def __init__(self, app):
        # Set up paths before calling parent constructor
        self.schema_file = app.paths.app / "resources" / "config_ui_schemas" / "settings_schema.yml"
        
        # Create simplified settings manager
        self.settings_manager = SettingsManager(app)

        # Initialize with settings-specific configuration
        super().__init__(app, use_file_library=False, use_option_container=True)
    
    def create_file_manager(self):
        """Create and return the settings file manager (not used for settings)"""
        return None
    
    def get_schema(self) -> UISchema:
        """Load the UI schema from file and populate dynamic options"""
        try:
            logger.info(f"Loading settings schema from: {self.schema_file}")
            with open(self.schema_file, 'r', encoding='utf-8') as f:
                schema_data = yaml.safe_load(f)
            
            logger.info(f"Loaded schema data: {schema_data.get('title', 'No title')}")
            logger.info(f"Schema sections: {len(schema_data.get('sections', []))}")
            
            # Populate dynamic options for default plan/workflow fields
            self._populate_dynamic_options(schema_data)
            
            schema = UISchema(
                title=schema_data.get('title', _('preferences_title', 'Settings')),
                description=schema_data.get('description', _('preferences_description', 'Application settings')),
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
                title=_('preferences_title', 'Settings'),
                description=_('preferences_description', 'Application settings'),
                content_sections=[
                    {
                        "title": _('preferences_error', 'Error'),
                        "fields": [
                            {
                                "id": "error_message",
                                "type": "label",
                                "label": _('preferences_load_error', 'Failed to load settings schema: {error}').format(error=str(e))
                            }
                        ]
                    }
                ]
            )
    
    def _populate_dynamic_options(self, schema_data: Dict[str, Any]):
        """Populate dynamic options for plan/workflow fields using unified helper"""
        try:
            from ...core.plan_workflow_ui_helper import PlanWorkflowUIHelper
            
            # Create unified helper
            self.ui_helper = PlanWorkflowUIHelper(self.app)
            
            # Get plan options (clean list without management options)
            plan_options = self.ui_helper.get_plan_options()
            self._populate_field_options(schema_data, "defaults.plan", plan_options)
            
            # Set up plan change callback
            self._add_field_callback(schema_data, "defaults.plan", self._on_plan_selection_change)
            
            # Set up workflow change callback  
            self._add_field_callback(schema_data, "defaults.workflow", self._on_workflow_selection_change)
            
            # Find and populate default_workflow options (initially empty, will update based on plan selection)
            self._populate_field_options(schema_data, "defaults.workflow", [_('preferences_select_plan', 'Select plan first')])
            
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
                        valid_options = [opt for opt in options if opt not in [_('preferences_no_plans', 'No plans found'), _('preferences_error_loading_plans', 'Error loading plans')]]
                        if not valid_options:
                            valid_options = [_('preferences_no_options', 'No options available')]
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
                from ...core.plan_workflow_ui_helper import PlanWorkflowUIHelper
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
                
                # Update language system if language changed
                try:
                    from fichero.ui.i18n import update_language_from_settings
                    update_language_from_settings()
                    logger.info("🌐 Language system updated from settings")
                except Exception as e:
                    logger.error(f"Failed to update language system: {e}")
            else:
                logger.error("Failed to save settings")
            
            return success
            
        except Exception as e:
            logger.error(f"Failed to save settings data: {e}")
            return False