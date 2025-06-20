"""
Configuration file loader utility
Handles loading JSON and YAML configuration files
"""

import json
import yaml
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
                return yaml.safe_load(file_content) or {}
            elif file_path.suffix.lower() in ['.json', '.jsonl']:
                return json.loads(file_content)
            else:
                raise ValueError(f"Unsupported file format: {file_path.suffix}")
                
        except yaml.YAMLError as e:
            logger.error(f"Failed to parse YAML file {file_path}: {e}")
            raise ValueError(f"Invalid YAML format in {file_path}: {e}")
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON file {file_path}: {e}")
            raise ValueError(f"Invalid JSON format in {file_path}: {e}")
        except Exception as e:
            logger.error(f"Failed to load config file {file_path}: {e}")
            raise ValueError(f"Failed to load configuration file: {e}")
    
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
                    yaml.dump(data, f, default_flow_style=False, allow_unicode=True, indent=2)
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