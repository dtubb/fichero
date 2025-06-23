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

logger = logging.getLogger(__name__)


class SettingsLibrary(BaseConfigLibrary):
    """Settings library with file browser and editor"""
    
    def __init__(self, app):
        super().__init__(app)
        
        # App-specific configuration
        self.schema_file = app.paths.app / "resources" / "config_ui_schemas" / "app_settings_schema.yml"
    
    def create_file_manager(self):
        """Create and return the settings file manager"""
        return SettingsManager(self.app)
    
    def get_schema(self) -> UISchema:
        """Load the UI schema from file and populate dynamic options"""
        try:
            with open(self.schema_file, 'r', encoding='utf-8') as f:
                schema_data = yaml.safe_load(f)
            
            # Populate dynamic options for default plan/workflow fields
            self._populate_dynamic_options(schema_data)
            
            return UISchema(
                title=schema_data.get('title', 'Settings'),
                description=schema_data.get('description', ''),
                sections=schema_data.get('sections', []),  # Main sections from schema
                content_sections=schema_data.get('content_sections', [])  # Direct content sections if no main sections
            )
        except Exception as e:
            logger.error(f"Failed to load settings schema: {e}")
            # Return minimal schema as fallback
            return UISchema(
                title="Settings",
                description="Application settings",
                content_sections=[
                    {
                        "title": "Error",
                        "fields": [
                            {
                                "id": "error_message",
                                "type": "label",
                                "label": f"Failed to load settings schema: {e}"
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
            self._populate_field_options(schema_data, "default_plan", plan_options)
            
            # Set up plan change callback
            self._add_field_callback(schema_data, "default_plan", self._on_plan_selection_change)
            
            # Set up workflow change callback  
            self._add_field_callback(schema_data, "default_workflow", self._on_workflow_selection_change)
            
            # Find and populate default_workflow options (initially empty, will update based on plan selection)
            self._populate_field_options(schema_data, "default_workflow", ["Select plan first"])
            
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
    
    def _on_plan_selection_change(self, widget):
        """Handle plan selection change - delegates to unified helper"""
        try:
            if not hasattr(self, 'ui_helper'):
                logger.warning("UI helper not available in plan selection change")
                return
            
            plan_value = getattr(widget, 'value', None)
            logger.info(f"Plan selection changed to: {plan_value}")
                
            workflow_widget = self.widgets.get('default_workflow')
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
    
    def _populate_field_options(self, schema_data: Dict[str, Any], field_id: str, options: List[str]):
        """Helper to find and populate options for a specific field"""
        for section in schema_data.get('sections', []):
            for subsection in section.get('sections', []):
                for field in subsection.get('fields', []):
                    if field.get('id') == field_id:
                        # Filter out error messages
                        valid_options = [opt for opt in options if opt not in ["No plans found", "Error loading plans"]]
                        if not valid_options:
                            valid_options = ["No options available"]
                        field['options'] = valid_options
                        return

    def load_data_for_ui(self) -> Dict[str, Any]:
        """Load data for UI, including shared data preferences"""
        # Get regular settings data
        data = super().load_data_for_ui()
        
        # Add shared data preferences
        try:
            from ....shared_data import get_shared_data
            shared_data = get_shared_data()
            
            data['default_plan'] = shared_data.get_setting('default_plan') or ""
            data['default_workflow'] = shared_data.get_setting('default_workflow') or ""
            
        except Exception as e:
            logger.error(f"Failed to load shared data preferences: {e}")
            data['default_plan'] = ""
            data['default_workflow'] = ""
        
        return data

    def save_data_from_ui(self, data: Dict[str, Any]) -> bool:
        """Save data from UI, handling shared data preferences separately"""
        try:
            # Extract shared data preferences
            default_plan = data.pop('default_plan', None)
            default_workflow = data.pop('default_workflow', None)
            
            # Save regular settings data
            success = super().save_data_from_ui(data)
            
            # Save shared data preferences
            from ....shared_data import get_shared_data
            from ...core.plan_manager import PlanManager
            shared_data = get_shared_data()
            
            if default_plan:
                shared_data.set_setting('default_plan', default_plan)
                logger.info(f"Set default plan: {default_plan}")
            else:
                shared_data.delete_setting('default_plan')
                logger.info("Cleared default plan")
                
            if default_workflow:
                shared_data.set_setting('default_workflow', default_workflow) 
                logger.info(f"Set default workflow: {default_workflow}")
            else:
                shared_data.delete_setting('default_workflow')
                logger.info("Cleared default workflow")
            
            return success
            
        except Exception as e:
            logger.error(f"Failed to save shared data preferences: {e}")
            return False

    def populate_data(self, data: Dict[str, Any]):
        """Populate UI widgets with data - handled by schema system"""
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