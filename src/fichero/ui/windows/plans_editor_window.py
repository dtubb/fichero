"""
Plans Editor Window
Specialized configuration window for plans.yml files
Inherits from BaseConfigWindow for common functionality
"""

import yaml
from pathlib import Path
from typing import Dict, Any
import logging

from .base_config_window import BaseConfigWindow
from ...utils.config_ui_generator import UISchema
from ..dialogs.plans_management_dialog import PlansManagementDialog

logger = logging.getLogger(__name__)

class PlansEditorWindow(BaseConfigWindow):
    """Plans.yml editor window using the base config window foundation"""
    
    def __init__(self, app, plans_file: Path = None):
        # Use default plans file if none provided
        if not plans_file:
            if hasattr(app, 'paths') and app.paths and hasattr(app.paths, 'app') and app.paths.app:
                plans_file = app.paths.app / "resources" / "plans" / "plans.yml"
            else:
                plans_file = Path.cwd() / "plans.yml"
        
        # Set schema file path
        schema_file = app.paths.app / "resources" / "config_ui_schemas" / "plans_schema.yml"
        
        super().__init__(app, plans_file, schema_file)
        
        # Enable auto-save for plans
        self.set_auto_save(True)
    
    def get_schema(self) -> UISchema:
        """Load the UI schema from file"""
        try:
            with open(self.schema_file, 'r', encoding='utf-8') as f:
                schema_data = yaml.safe_load(f)
            
            # Format the title with the current file name
            schema_data['title'] = schema_data['title'].format(config_file=self.config_file)
            
            return UISchema(
                title=schema_data.get('title', 'Plans Editor'),
                description=schema_data.get('description', ''),
                tabs=schema_data.get('tabs', []),
                sections=schema_data.get('sections', []),
                style=schema_data.get('style', {})
            )
        except Exception as e:
            logger.error(f"Failed to load plans schema: {e}")
            # Return minimal schema as fallback
            return UISchema(
                title="Plans Editor",
                description="Plans configuration",
                sections=[
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
    
    def get_default_data(self) -> Dict:
        """Get default data for plans configuration"""
        return {
            "title": "New Project",
            "description": "",
            "vars": {
                "name": "untitled_project",
                "language": "en",
                "text_direction": "horizontal-lr",
                "version": "1.0.0",
                "crop_format": "jpg",
                "split_format": "jpg",
                "rotate_format": "jpg",
                "enhance_format": "jpg",
                "background_removed_format": "png",
                "lmstudio_url": "http://localhost:1234",
                "lmstudio_model": "",
                "prompt": "Please process the following content accurately.",
                "project_folder": "${vars.name}",
                "documents_folder": "${vars.project_folder}/documents",
                "assets_folder": "${vars.project_folder}/assets"
            }
        }
    
    def get_management_dialog_class(self):
        """Get the management dialog class for plans"""
        return PlansManagementDialog
    
    def post_save_actions(self, data: Dict):
        """Plans-specific post-save actions"""
        try:
            # Log the project name if available
            project_name = data.get("vars", {}).get("name", "Unknown")
            print(f"📋 Plans configuration saved for project: {project_name}")
                
        except Exception as e:
            logger.error(f"Failed to perform plans post-save actions: {e}")
    
    def show_save_success(self):
        """Custom save success message for plans"""
        print(f"✅ Plans configuration saved: {self.config_file.name}")
    
    def show_save_error(self, error: Exception):
        """Custom save error message for plans"""
        print(f"❌ Failed to save plans configuration {self.config_file.name}: {error}") 