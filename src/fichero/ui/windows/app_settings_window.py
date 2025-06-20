"""
App Settings Window
Specialized configuration window for application settings
Inherits from BaseConfigWindow for common functionality
"""

import yaml
from pathlib import Path
from typing import Dict, Any
import logging

from .base_config_window import BaseConfigWindow
from ...utils.config_ui_generator import UISchema
from ...utils import get_app_settings
from ..dialogs.settings_management_dialog import SettingsManagementDialog

logger = logging.getLogger(__name__)

class AppSettingsWindow(BaseConfigWindow):
    """Application settings window using the base config window foundation"""
    
    def __init__(self, app):
        # Define file paths
        settings_file = app.paths.data / "app_settings.yml"
        schema_file = app.paths.app / "resources" / "config_ui_schemas" / "app_settings_schema.yml"
        
        super().__init__(app, settings_file, schema_file)
        
        # App-specific file paths
        self.defaults_file = app.paths.app / "resources" / "settings" / "default_app_settings.yml"
    
    def get_schema(self) -> UISchema:
        """Load the UI schema from file"""
        try:
            with open(self.schema_file, 'r', encoding='utf-8') as f:
                schema_data = yaml.safe_load(f)
            
            return UISchema(
                title=schema_data.get('title', 'Settings'),
                description=schema_data.get('description', ''),
                tabs=schema_data.get('tabs', []),
                sections=schema_data.get('sections', []),
                style=schema_data.get('style', {})
            )
        except Exception as e:
            logger.error(f"Failed to load settings schema: {e}")
            # Return minimal schema as fallback
            return UISchema(
                title="Settings",
                description="Application settings",
                sections=[
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
    
    def get_default_data(self) -> Dict:
        """Load default settings from file"""
        try:
            if self.defaults_file.exists():
                with open(self.defaults_file, 'r', encoding='utf-8') as f:
                    return yaml.safe_load(f) or {}
        except Exception as e:
            logger.warning(f"Failed to load default settings: {e}")
        return {}
    
    def get_management_dialog_class(self):
        """Get the management dialog class for settings"""
        return SettingsManagementDialog
    
    def get_additional_data(self) -> Dict:
        """Merge with current app settings (for API keys from shared data)"""
        try:
            app_settings = get_app_settings(self.app)
            current_settings = app_settings.settings
            
            additional_data = {}
            
            # Merge API server settings (preserve keys from shared data)
            if 'api_servers' in current_settings:
                additional_data['api_servers'] = current_settings['api_servers']
            
            # Merge worker settings
            if 'workers' in current_settings:
                additional_data['workers'] = current_settings['workers']
            
            return additional_data
            
        except Exception as e:
            logger.warning(f"Failed to merge with app settings: {e}")
            return {}
    
    def post_save_actions(self, data: Dict):
        """App-specific post-save actions"""
        try:
            # Update app settings in shared data
            app_settings = get_app_settings(self.app)
            
            # Convert to the format expected by AppSettings
            app_format = {
                'api_servers': data.get('api_servers', {}),
                'workers': data.get('workers', {}),
                'preferences': data.get('preferences', {}),
                'processing': data.get('processing', {}),
                'ui': data.get('ui', {})
            }
            
            # Save through AppSettings (this will handle encryption and shared data)
            app_settings.save_settings(app_format)
            
            # Set environment variables
            self._set_environment_variables(data)
            
            # Reload app settings to reflect changes
            from ...utils import reload_settings
            reload_settings(self.app)
            
        except Exception as e:
            logger.error(f"Failed to perform post-save actions: {e}")
    
    def _set_environment_variables(self, data: Dict):
        """Set environment variables from settings"""
        import os
        
        api_servers = data.get('api_servers', {})
        
        # OpenAI
        if api_servers.get('openai', {}).get('api_key'):
            os.environ['OPENAI_API_KEY'] = api_servers['openai']['api_key']
        
        # Qwen
        if api_servers.get('qwen', {}).get('api_key'):
            os.environ['DASHSCOPE_API_KEY'] = api_servers['qwen']['api_key']
        
        # Claude
        if api_servers.get('claude', {}).get('api_key'):
            os.environ['ANTHROPIC_API_KEY'] = api_servers['claude']['api_key'] 