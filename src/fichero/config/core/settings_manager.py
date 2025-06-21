"""
Settings File Manager
Handles settings-specific file operations and business logic
"""

import yaml
from pathlib import Path
from typing import Dict, Any, List
import logging

from .file_manager import FileManager

logger = logging.getLogger(__name__)


class SettingsManager(FileManager):
    """File manager for application settings"""
    
    def get_file_type(self) -> str:
        """Get the file type name"""
        return "settings"
    
    def get_file_extensions(self) -> List[str]:
        """Get supported file extensions for settings"""
        return ['.yml', '.yaml', '.json']
    
    def get_default_template(self) -> Dict[str, Any]:
        """Get default data structure for new settings files"""
        return {
            "title": "Custom Application Settings",
            "description": "User-defined application settings",
            "preferences": {
                "language": "en"
            },
            "workers": {
                "backend": "python",
                "cpu_workers": 4,
                "io_workers": 8,
                "memory_per_worker_mb": 2048
            },
            "api_servers": {
                "openai": {
                    "api_key": "",
                    "base_url": "https://api.openai.com/v1"
                },
                "qwen": {
                    "api_key": "",
                    "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1"
                },
                "claude": {
                    "api_key": "",
                    "base_url": "https://api.anthropic.com"
                },
                "ollama": {
                    "base_url": "http://localhost:11434"
                },
                "lmstudio": {
                    "base_url": "http://localhost:1234/v1"
                },
                "blackfish": {
                    "base_url": "https://blackfish.example.com"
                },
                "huggingface": {
                    "api_key": "",
                    "base_url": "https://api-inference.huggingface.co"
                }
            }
        }
    
    def load_file(self, file_path: Path) -> Dict[str, Any]:
        """Simple load: just get file data and merge with defaults"""
        try:
            # Load file data
            file_data = super().load_file(file_path)
            
            # Note: API key decryption will be handled by AppSettings after loading
            # to avoid circular dependency during initialization
            
            # Just merge with default template to ensure all fields exist
            default_data = self.get_default_template()
            merged_data = self._merge_settings(default_data, file_data)
            
            return merged_data
            
        except Exception as e:
            logger.warning(f"Failed to load file data: {e}")
            return self.get_default_template()
    
    def save_file(self, file_path: Path, data: Dict[str, Any]) -> bool:
        """Save settings file and set environment variables"""
        try:
            # Note: API key encryption should be handled by AppSettings before calling save_file
            # to avoid circular dependency issues
            
            # Save to file
            success = super().save_file(file_path, data)
            if not success:
                return False
            
            # Note: Environment variables are only set by director.py when spawning workers
            logger.info(f"Saved settings from {file_path.name}")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to save settings file: {e}")
            return False
    
    def _merge_settings(self, base: Dict, override: Dict) -> Dict:
        """Deep merge settings dictionaries"""
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._merge_settings(result[key], value)
            else:
                result[key] = value
        return result
    

    
    def get_active_file(self) -> Path:
        """Get the currently active settings file"""
        try:
            # Use app preferences for active file tracking
            from .app_preferences import get_app_preferences
            app_prefs = get_app_preferences(self.app)
            return app_prefs.get_active_settings_file()
        except Exception as e:
            logger.error(f"Failed to get active settings file: {e}")
            return None
    
    def set_active_file(self, file_path: Path) -> bool:
        """Set the active settings file"""
        try:
            # Use app preferences for active file tracking
            from .app_preferences import get_app_preferences
            app_prefs = get_app_preferences(self.app)
            success = app_prefs.set_active_settings_file(file_path)
            
            if success:
                logger.info(f"Set active settings file: {file_path.name}")
            return success
        except Exception as e:
            logger.error(f"Failed to set active settings file: {e}")
            return False 