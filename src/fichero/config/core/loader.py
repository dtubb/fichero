"""
Configuration file loader utility
Handles loading JSON and YAML configuration files
"""

import json
# Import YAML directly from ruamel.yaml
from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

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
                yaml_parser = YAML()
                return yaml_parser.load(file_content) or {}
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
                with open(file_path, 'w', encoding='utf-8') as f:
                    yaml_parser = YAML()
                    yaml_parser.dump(data, f)
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