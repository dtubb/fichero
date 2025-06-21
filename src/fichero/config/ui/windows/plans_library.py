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
        # The base class handles widget population through the schema system
        # This method is implemented for abstract method compliance
        # Actual population happens in create_content_from_schema()
        pass