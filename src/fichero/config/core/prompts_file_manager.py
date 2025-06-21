"""
Prompts File Manager
Handles prompts-specific file operations and business logic
"""

import srsly
import json
from pathlib import Path
from typing import Dict, Any, List
import logging

from .file_manager import FileManager
from .settings import get_app_settings

logger = logging.getLogger(__name__)


class PromptsManager(FileManager):
    """File manager for LLM prompts/configurations"""
    
    def get_file_type(self) -> str:
        """Get the file type name"""
        return "prompts"
    
    def get_file_extensions(self) -> List[str]:
        """Get supported file extensions for prompts"""
        return ['.jsonl', '.json', '.yml', '.yaml']
    
    def get_default_template(self) -> Dict[str, Any]:
        """Get default data structure for new prompt files"""
        return {
            "name": "New LLM Config",
            "description": "A new LLM processing configuration",
            "intelligent_chunking": True,
            "chunk_overlap": 200,
            "llm": {
                "backend": "openai",
                "model": "gpt-4o-mini",
                "temperature": 0.1,
                "max_tokens": 4000,
                "top_p": 0.9,
                "frequency_penalty": 0.0,
                "presence_penalty": 0.0,
                "timeout": 120,
                "retry_attempts": 3,
                "retry_delay": 5
            },
            "prompts": {
                "system_prompt": "You are a helpful assistant that processes documents accurately and thoroughly.",
                "user_prompt_template": "Please process the following content:\n\n{content}"
            },
            "steps": [
                {
                    "name": "document_analysis",
                    "description": "Analyze and process document content",
                    "prompt": "Analyze the following document content and provide a summary:",
                    "output_format": "markdown"
                }
            ]
        }
    
    def load_file(self, file_path: Path) -> Dict[str, Any]:
        """Override to handle JSONL format specifically"""
        try:
            if not file_path.exists():
                return {}
            
            # Check cache first
            cache_key = str(file_path)
            if cache_key in self._cache:
                return self._cache[cache_key].copy()
            
            # For JSONL configs, we expect a single JSON object
            if file_path.suffix.lower() == '.jsonl':
                with open(file_path, 'r', encoding='utf-8') as f:
                    lines = [line.strip() for line in f if line.strip()]
                    if lines:
                        data = json.loads(lines[0]) if len(lines) == 1 else {"raw_lines": lines}
                    else:
                        data = {}
            else:
                # Use parent method for YAML/JSON
                data = super().load_file(file_path)
            
            # Cache the data
            self._cache[cache_key] = data.copy()
            
            return data
                    
        except Exception as e:
            logger.warning(f"Failed to load JSONL from {file_path}: {e}")
            return {}
    
    def save_file(self, file_path: Path, data: Dict[str, Any]) -> bool:
        """Override to save as JSONL format and perform post-save actions"""
        try:
            # Ensure parent directory exists
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Save based on file extension
            if file_path.suffix.lower() == '.jsonl':
                # Save as single line JSON for now (could be enhanced for multi-step configs)
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(json.dumps(data, indent=2))
            else:
                # Use parent method for YAML/JSON
                from .loader import ConfigLoader
                ConfigLoader.save_config_file(file_path, data)
            
            # Update cache
            cache_key = str(file_path)
            self._cache[cache_key] = data.copy()
            
            # Validate configuration after save
            errors = self._validate_prompts_config(data)
            if errors:
                logger.warning(f"Configuration saved but has validation warnings: {', '.join(errors)}")
            else:
                logger.info("Valid prompts configuration saved!")
            
            logger.info(f"Saved {file_path.name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save {file_path}: {e}")
            return False
    
    def _validate_prompts_config(self, data: Dict) -> List[str]:
        """Validate prompts configuration data"""
        errors = []
        
        # Check required fields
        if not data.get("name"):
            errors.append("Configuration name is required")
        
        if not data.get("llm", {}).get("backend"):
            errors.append("LLM backend is required")
        
        if not data.get("llm", {}).get("model"):
            errors.append("LLM model is required")
        
        # Check numeric ranges
        llm = data.get("llm", {})
        if llm.get("temperature", 0) < 0 or llm.get("temperature", 0) > 2:
            errors.append("Temperature must be between 0 and 2")
        
        if llm.get("top_p", 1) < 0 or llm.get("top_p", 1) > 1:
            errors.append("Top P must be between 0 and 1")
        
        return errors
    
    def get_active_file(self) -> Path:
        """Get the currently active prompts file"""
        try:
            if not self.app:
                return None
            
            # Use simple shared storage for active file tracking
            from fichero.shared_data import get_shared_data, DataType
            shared_data = get_shared_data(namespace="fichero")
            active_file_str = shared_data.get(DataType.SETTINGS, "active_prompts")
            
            if active_file_str:
                active_file = Path(active_file_str)
                if active_file.exists():
                    return active_file
            
            return None
        except Exception as e:
            logger.error(f"Failed to get active prompts file: {e}")
            return None
    
    def set_active_file(self, file_path: Path) -> bool:
        """Set the active prompts file"""
        try:
            if not self.app:
                return False
            
            # Use simple shared storage for active file tracking
            from fichero.shared_data import get_shared_data, DataType
            shared_data = get_shared_data(namespace="fichero")
            shared_data.set(DataType.SETTINGS, "active_prompts", str(file_path), immediate_save=True)
            
            logger.info(f"Set active prompts file: {file_path.name}")
            return True
        except Exception as e:
            logger.error(f"Failed to set active prompts file: {e}")
            return False
    
    def get_llm_config(self, file_path: Path) -> Dict[str, Any]:
        """Get LLM configuration from prompts file"""
        try:
            prompts_data = self.load_file(file_path)
            return prompts_data.get("llm", {})
        except Exception as e:
            logger.error(f"Failed to get LLM config for {file_path}: {e}")
            return {}
    
    def get_prompts(self, file_path: Path) -> Dict[str, str]:
        """Get prompts from prompts file"""
        try:
            prompts_data = self.load_file(file_path)
            return prompts_data.get("prompts", {})
        except Exception as e:
            logger.error(f"Failed to get prompts for {file_path}: {e}")
            return {} 