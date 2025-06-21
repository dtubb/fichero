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
        """Load the UI schema from file"""
        try:
            with open(self.schema_file, 'r', encoding='utf-8') as f:
                schema_data = yaml.safe_load(f)
            
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
    
    def populate_data(self, data: Dict[str, Any]):
        """Populate UI widgets with data - handled by schema system"""
        # The base class handles widget population through the schema system
        # This method is implemented for abstract method compliance
        # Actual population happens in create_content_from_schema()
        pass