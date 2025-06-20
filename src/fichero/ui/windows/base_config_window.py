"""
Base Configuration Window
Generic, reusable configuration window using schema-driven UI generation
"""

import toga
import yaml
import srsly
from pathlib import Path
from typing import Dict, Any, Optional, Callable
import logging
from abc import ABC, abstractmethod

from ...utils.config_ui_generator import SchemaUIGenerator, UISchema

logger = logging.getLogger(__name__)

class BaseConfigWindow(ABC):
    """
    Base class for all configuration windows using schema-driven UI generation.
    Provides common functionality for loading, saving, and managing config files.
    """
    
    def __init__(self, app, config_file: Path, schema_file: Optional[Path] = None):
        self.app = app
        self.config_file = config_file
        self.schema_file = schema_file
        self.window = None
        self.ui_generator = SchemaUIGenerator(app)
        self.original_data = None
        self.modified_data = None
        self._enable_auto_save = True
        self._enable_restore_defaults = True
        
    # Abstract methods that subclasses must implement
    
    @abstractmethod
    def get_schema(self) -> UISchema:
        """Get the UI schema for this config window"""
        pass
    
    @abstractmethod
    def get_default_data(self) -> Dict:
        """Get default data for this config type"""
        pass
    
    @abstractmethod
    def get_management_dialog_class(self):
        """Get the management dialog class for this config type"""
        pass
    
    # Data format handling - override in subclasses if needed
    
    def load_data_from_file(self, file_path: Path) -> Dict:
        """Load data from file - override for custom formats"""
        try:
            if not file_path.exists():
                return {}
            
            if file_path.suffix.lower() in ['.yml', '.yaml']:
                with open(file_path, 'r', encoding='utf-8') as f:
                    return yaml.safe_load(f) or {}
            elif file_path.suffix.lower() in ['.json', '.jsonl']:
                return srsly.read_json(file_path)
            else:
                # Generic text file
                with open(file_path, 'r', encoding='utf-8') as f:
                    return {"content": f.read()}
                    
        except Exception as e:
            logger.warning(f"Failed to load from {file_path}: {e}")
            return {}
    
    def save_data_to_file(self, data: Dict, file_path: Path):
        """Save data to file - override for custom formats"""
        # Create backup
        if file_path.exists():
            backup_file = file_path.with_suffix(file_path.suffix + '.backup')
            import shutil
            shutil.copy2(file_path, backup_file)
        
        # Ensure parent directory exists
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        if file_path.suffix.lower() in ['.yml', '.yaml']:
            with open(file_path, 'w', encoding='utf-8') as f:
                yaml.dump(data, f, default_flow_style=False, allow_unicode=True, indent=2)
        elif file_path.suffix.lower() in ['.json', '.jsonl']:
            srsly.write_json(file_path, data, indent=2)
        else:
            # Generic text file
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(data.get('content', ''))
    
    # Core functionality
    
    def load_settings_data(self) -> Dict:
        """Load settings data with fallback hierarchy"""
        data = {}
        
        # 1. Start with defaults
        try:
            default_data = self.get_default_data()
            if default_data:
                data.update(default_data)
                logger.info("Loaded default settings")
        except Exception as e:
            logger.warning(f"Failed to load defaults: {e}")
        
        # 2. Override with user config file
        try:
            if self.config_file.exists():
                user_data = self.load_data_from_file(self.config_file)
                data = self._merge_settings(data, user_data)
                logger.info(f"Loaded user settings from {self.config_file}")
        except Exception as e:
            logger.warning(f"Failed to load user settings: {e}")
        
        # 3. Allow subclasses to merge additional data
        try:
            additional_data = self.get_additional_data()
            if additional_data:
                data = self._merge_settings(data, additional_data)
        except Exception as e:
            logger.warning(f"Failed to merge additional data: {e}")
        
        self.original_data = data.copy()
        return data
    
    def get_additional_data(self) -> Dict:
        """Override in subclasses to provide additional data sources"""
        return {}
    
    def _merge_settings(self, base: Dict, override: Dict) -> Dict:
        """Deep merge settings dictionaries"""
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._merge_settings(result[key], value)
            else:
                result[key] = value
        return result
    
    def save_settings_data(self, data: Dict):
        """Save settings data and perform post-save actions"""
        try:
            self.save_data_to_file(data, self.config_file)
            logger.info(f"Saved settings to {self.config_file}")
            
            # Allow subclasses to perform additional save actions
            self.post_save_actions(data)
            
            self.modified_data = data
            
        except Exception as e:
            logger.error(f"Failed to save settings: {e}")
            raise
    
    def post_save_actions(self, data: Dict):
        """Override in subclasses for additional save actions"""
        pass
    
    # Window management
    
    def show(self):
        """Show the configuration window"""
        if self.window:
            self.window.show()
            return
        
        try:
            # Load schema and data
            schema = self.get_schema()
            data = self.load_settings_data()
            
            # Only pass restore_defaults callback - no save/cancel for auto-save behavior
            callbacks = {}
            if self._enable_restore_defaults:
                callbacks['on_restore_defaults'] = self._handle_file_management
            
            # Create window using UI generator (NO on_save/on_cancel for auto-save behavior)
            self.window = self.ui_generator.create_window_from_schema(
                schema=schema,
                data=data,
                **callbacks
            )
            
            # Setup auto-save on close if enabled
            if self._enable_auto_save:
                self.window.on_close = self._handle_window_close
            
            # Show the window
            self.window.show()
            
            # Post-show actions
            self.post_show_actions()
            
        except Exception as e:
            logger.error(f"Failed to show config window: {e}")
            print(f"❌ Failed to open config window: {e}")
    
    def post_show_actions(self):
        """Override in subclasses for actions after window is shown"""
        pass
    
    # Event handlers
    
    def _handle_file_management(self):
        """Handle file management - show management dialog"""
        try:
            # Get the management dialog class from subclass
            dialog_class = self.get_management_dialog_class()
            
            # Create and show management dialog
            management_dialog = dialog_class(self.app, self.config_file)
            management_dialog.show()
            
            print(f"📁 Opened file management dialog")
            
        except Exception as e:
            print(f"❌ Failed to open file management: {e}")
            logger.error(f"Failed to open file management: {e}")
    
    def _handle_window_close(self, widget, **kwargs):
        """Handle window close with auto-save"""
        if not self._enable_auto_save:
            self.window = None
            return True
        
        try:
            # Extract current data from UI
            if hasattr(self.ui_generator, 'extract_data'):
                current_data = self.ui_generator.extract_data()
                
                # Save the current settings
                self.save_settings_data(current_data)
                print("✅ Settings auto-saved on close")
                
        except Exception as e:
            print(f"⚠️ Failed to auto-save settings: {e}")
            logger.warning(f"Failed to auto-save settings: {e}")
        
        # Clear window reference
        self.window = None
        return True  # Allow the window to close
    
    # Utility methods
    
    def show_save_success(self):
        """Show save success message - override for custom UI"""
        print(f"✅ Configuration saved successfully to {self.config_file}")
    
    def show_save_error(self, error: Exception):
        """Show save error message - override for custom UI"""
        print(f"❌ Failed to save configuration: {error}")
    
    def close(self):
        """Close the configuration window"""
        if self.window:
            self.window.close()
            self.window = None
    
    def reload(self):
        """Reload configuration from file"""
        self.close()
        self.show()
    
    # Configuration
    
    def set_auto_save(self, enabled: bool):
        """Enable or disable auto-save on window close"""
        self._enable_auto_save = enabled
    
    def set_restore_defaults(self, enabled: bool):
        """Enable or disable restore defaults functionality"""
        self._enable_restore_defaults = enabled 