"""
Configuration file loader utility
Handles loading JSON and YAML configuration files
"""

import json
# Conditional imports for iOS compatibility
try:
    from ruamel.yaml import YAML
    RUAMEL_YAML_AVAILABLE = True
except ImportError:
    RUAMEL_YAML_AVAILABLE = False
    # Fallback to PyYAML or simple YAML parsing
    try:
        import yaml
        YAML_AVAILABLE = True
    except ImportError:
        YAML_AVAILABLE = False
        # Create a simple fallback
        class YAML:
            def __init__(self):
                pass
            
            def load(self, content):
                # Simple fallback - just return empty dict
                return {}
            
            def dump(self, data, f):
                # Simple fallback - just write empty YAML
                f.write("# Fallback YAML\n")

from pathlib import Path
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)


class ConfigLoader:
    """Universal configuration file loader supporting JSON and YAML formats"""
    
    @staticmethod
    def load_config_file(file_path: Path) -> Dict[str, Any]:
        """
        Load configuration file (JSON or YAML) and return as dictionary
        
        Args:
            file_path: Path to the configuration file
            
        Returns:
            Dictionary containing the configuration data
            
        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If file format is unsupported or invalid
        """
        if not file_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {file_path}")
        
        try:
            file_content = file_path.read_text(encoding='utf-8')
            
            if file_path.suffix.lower() in ['.yml', '.yaml']:
                if RUAMEL_YAML_AVAILABLE:
                    yaml = YAML()
                    yaml.preserve_quotes = True
                    yaml.width = 4096  # Prevent line wrapping
                    return yaml.load(file_content) or {}
                elif YAML_AVAILABLE:
                    return yaml.safe_load(file_content) or {}
                else:
                    # Fallback for iOS - return empty dict
                    return {}
            elif file_path.suffix.lower() in ['.json', '.jsonl']:
                return json.loads(file_content)
            else:
                raise ValueError(f"Unsupported file format: {file_path.suffix}")
                
        except Exception as yaml_error:
            # Try to give more specific error messages
            if file_path.suffix.lower() in ['.yml', '.yaml']:
                logger.error(f"Failed to parse YAML file {file_path}: {yaml_error}")
                raise ValueError(f"Invalid YAML format in {file_path}: {yaml_error}")
            elif file_path.suffix.lower() in ['.json', '.jsonl']:
                logger.error(f"Failed to parse JSON file {file_path}: {yaml_error}")
                raise ValueError(f"Invalid JSON format in {file_path}: {yaml_error}")
            else:
                logger.error(f"Failed to load config file {file_path}: {yaml_error}")
                raise ValueError(f"Failed to load configuration file: {yaml_error}")
    
    @staticmethod
    def save_config_file(file_path: Path, data: Dict[str, Any]) -> None:
        """
        Save configuration data to file in appropriate format
        
        Args:
            file_path: Path where to save the file
            data: Configuration data to save
        """
        try:
            # Ensure parent directory exists
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            if file_path.suffix.lower() in ['.yml', '.yaml']:
                if RUAMEL_YAML_AVAILABLE:
                    yaml = YAML()
                    yaml.preserve_quotes = True
                    yaml.default_flow_style = False
                    yaml.allow_unicode = True
                    yaml.width = 4096  # Prevent line wrapping
                    yaml.indent(mapping=2, sequence=4, offset=2)
                    
                    with open(file_path, 'w', encoding='utf-8') as f:
                        yaml.dump(data, f)
                elif YAML_AVAILABLE:
                    with open(file_path, 'w', encoding='utf-8') as f:
                        yaml.dump(data, f, default_flow_style=False, allow_unicode=True)
                else:
                    # Fallback for iOS - write simple YAML
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write("# iOS Fallback YAML\n")
                        f.write("# Settings not available on this platform\n")
            elif file_path.suffix.lower() in ['.json', '.jsonl']:
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
            else:
                raise ValueError(f"Unsupported file format for saving: {file_path.suffix}")
                
        except Exception as e:
            logger.error(f"Failed to save config file {file_path}: {e}")
            raise ValueError(f"Failed to save configuration file: {e}")
    
    @staticmethod
    def get_supported_extensions() -> list:
        """Get list of supported file extensions"""
        return ['.yml', '.yaml', '.json', '.jsonl'] 