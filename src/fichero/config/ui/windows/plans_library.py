"""
Plans Library
Configuration library for plans with file browser
"""

import yaml
from pathlib import Path
from typing import Dict, Any, List
import logging

from ..base_config_library import BaseConfigLibrary
from ..base_config_library import UISchema
from ...core.plans_file_manager import PlansManager

logger = logging.getLogger(__name__)


class PlansLibrary(BaseConfigLibrary):
    """Plans library with file browser and editor"""
    
    def __init__(self, app):
        super().__init__(app)
        
        # Plans-specific configuration
        self.schema_file = app.paths.app / "resources" / "config_ui_schemas" / "plans_schema.yml"
        
        # Store original workflow and command data for complex editing
        self.original_workflows = {}
        self.original_commands = []
    
    def create_file_manager(self):
        """Create and return the plans file manager"""
        return PlansManager(self.app)
    
    def get_schema(self) -> UISchema:
        """Load the UI schema from file"""
        try:
            with open(self.schema_file, 'r', encoding='utf-8') as f:
                schema_data = yaml.safe_load(f)
            
            # Format the title with the current file name if we have one
            if self.current_file:
                schema_data['title'] = schema_data['title'].format(config_file=self.current_file)
            
            return UISchema(
                title=schema_data.get('title', 'Plans'),
                description=schema_data.get('description', ''),
                sections=schema_data.get('sections', []),  # Main sections from schema
                content_sections=schema_data.get('content_sections', [])  # Direct content sections if no main sections
            )
        except Exception as e:
            logger.error(f"Failed to load plans schema: {e}")
            # Return minimal schema as fallback
            return UISchema(
                title="Plans",
                description="Plans configuration",
                content_sections=[
                    {
                        "title": "Error",
                        "fields": [
                            {
                                "id": "error_message",
                                "type": "label",
                                "label": f"Failed to load plans schema: {e}"
                            }
                        ]
                    }
                ]
            )
    
    def populate_data(self, data: Dict[str, Any]):
        """Populate UI widgets with data - handled by schema system"""
        # Store original workflow and command data for complex editing
        self.original_workflows = data.get('workflows', {})
        self.original_commands = data.get('commands', [])
        
        # The workflow_manager widget is handled by the base class's workflow editor
        # No special population needed as it reads directly from data during creation
        
        # For commands editor, convert commands list to YAML string
        if 'commands_editor' in self.widgets:
            try:
                commands_yaml = yaml.dump(self.original_commands, default_flow_style=False, sort_keys=False)
                self.widgets['commands_editor'].value = commands_yaml
            except Exception as e:
                logger.error(f"Failed to populate commands editor: {e}")
                self.widgets['commands_editor'].value = "# Error loading commands"
    
    def extract_data(self) -> Dict:
        """Extract data from all widgets, with special handling for workflows and commands"""
        # Get basic data from parent class
        data = super().extract_data()
        
        # Handle workflow manager specially
        if 'workflow_manager' in self.widgets:
            workflow_widget = self.widgets['workflow_manager']
            if hasattr(workflow_widget, '_workflow_step_widgets') and hasattr(workflow_widget, '_workflow_selector'):
                try:
                    # Get the currently selected workflow
                    selected_workflow = workflow_widget._workflow_selector
                    if selected_workflow and selected_workflow.value:
                        workflow_name = selected_workflow.value
                        
                        # Extract enabled steps from checkboxes
                        enabled_steps = []
                        for step_name, checkbox in workflow_widget._workflow_step_widgets.items():
                            if checkbox.value:  # If checkbox is checked
                                enabled_steps.append(step_name)
                        
                        # Update the workflows data
                        updated_workflows = self.original_workflows.copy()
                        updated_workflows[workflow_name] = enabled_steps
                        data['workflows'] = updated_workflows
                    else:
                        data['workflows'] = self.original_workflows
                except Exception as e:
                    logger.error(f"Error processing workflow manager: {e}")
                    data['workflows'] = self.original_workflows
            else:
                data['workflows'] = self.original_workflows
        else:
            # Keep original workflows if no workflow manager
            data['workflows'] = self.original_workflows
        
        # Handle commands editor specially
        if 'commands_editor' in self.widgets:
            try:
                commands_text = self.widgets['commands_editor'].value
                if commands_text and commands_text.strip():
                    commands_data = yaml.safe_load(commands_text)
                    if commands_data:
                        data['commands'] = commands_data
                    else:
                        data['commands'] = self.original_commands
                else:
                    data['commands'] = self.original_commands
            except yaml.YAMLError as e:
                logger.error(f"Invalid YAML in commands editor: {e}")
                data['commands'] = self.original_commands
            except Exception as e:
                logger.error(f"Error processing commands editor: {e}")
                data['commands'] = self.original_commands
        else:
            # Keep original commands if no commands editor
            data['commands'] = self.original_commands
        
        # Remove the editor field IDs from data since they're not part of the actual config
        data.pop('workflow_manager', None)
        data.pop('commands_editor', None)
        
        return data
    
    def _load_file(self, file_path: Path):
        """Override to handle complex data loading"""
        try:
            # Load file data using file manager
            data = self.file_manager.load_file(file_path)
            self.original_data = data.copy()
            self.current_file = file_path
            self.is_editing_default = self.file_manager.is_default_file(file_path)
            
            # Set as active file in file manager immediately
            self.file_manager.set_active_file(file_path)
            
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
            
            # Populate complex data after UI is created
            self.populate_data(data)
            
        except Exception as e:
            logger.error(f"Failed to load file {file_path}: {e}")