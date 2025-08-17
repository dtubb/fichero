"""
Prompts Library
Configuration library for prompts/LLM configs with file browser
"""

# Conditional imports for iOS compatibility
try:
    import srsly
    SRSLY_AVAILABLE = True
except ImportError:
    SRSLY_AVAILABLE = False
    # Create fallback functions for srsly functionality
    class srsly:
        @staticmethod
        def read_json(path):
            import json
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        
        @staticmethod
        def write_json(path, data):
            import json
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

from fichero.utils import yaml_compat as yaml
from pathlib import Path
from typing import Dict, Any, List
import logging

from fichero.config.ui.base_config_library import BaseConfigLibrary
from fichero.config.ui.base_config_library import UISchema
from fichero.config.core.prompts_file_manager import PromptsManager

logger = logging.getLogger(__name__)


class PromptsLibrary(BaseConfigLibrary):
    """Prompts library with file browser and editor"""
    
    def __init__(self, app):
        # Prompts-specific configuration - set BEFORE calling super()
        self.schema_file = app.paths.app / "resources" / "config_ui_schemas" / "prompts_schema.yml"
        
        super().__init__(app)
    
    def create_file_manager(self):
        """Create and return the prompts file manager"""
        return PromptsManager(self.app)
    
    def get_schema(self) -> UISchema:
        """Load the UI schema from file"""
        try:
            with open(self.schema_file, 'r', encoding='utf-8') as f:
                schema_data = yaml.safe_load(f)
            
            # Format the title with the current file name if we have one
            if self.current_file:
                schema_data['title'] = schema_data['title'].format(config_file=self.current_file)
            
            return UISchema(
                title=schema_data.get('title', 'Prompts'),
                description=schema_data.get('description', ''),
                sections=schema_data.get('sections', []),  # Main sections from schema
                content_sections=schema_data.get('content_sections', [])  # Direct content sections if no main sections
            )
        except Exception as e:
            logger.error(f"Failed to load prompts schema: {e}")
            # Return minimal schema as fallback
            return UISchema(
                title="Prompts",
                description="LLM configuration",
                content_sections=[
                    {
                        "title": "Error",
                        "fields": [
                            {
                                "id": "error_message",
                                "type": "label",
                                "label": f"Failed to load prompts schema: {e}"
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