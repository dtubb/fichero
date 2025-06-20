"""
Prompts Editor Window
Specialized configuration window for LLM config files (JSONL format)
Inherits from BaseConfigWindow for common functionality
"""

import srsly
import yaml
from pathlib import Path
from typing import Dict, Any
import logging

from .base_config_window import BaseConfigWindow
from ...utils.config_ui_generator import UISchema
from ..dialogs.prompts_management_dialog import PromptsManagementDialog

logger = logging.getLogger(__name__)

class PromptsEditorWindow(BaseConfigWindow):
    """Prompts editor window for JSONL config files"""
    
    def __init__(self, app, config_file: Path):
        # Set schema file path
        schema_file = app.paths.app / "resources" / "config_ui_schemas" / "prompts_schema.yml"
        
        super().__init__(app, config_file, schema_file)
        
        # Enable auto-save for prompts configs
        self.set_auto_save(True)
    
    def load_data_from_file(self, file_path: Path) -> Dict:
        """Override to handle JSONL format specifically"""
        try:
            if not file_path.exists():
                return {}
            
            # For JSONL configs, we expect a single JSON object
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = [line.strip() for line in f if line.strip()]
                if lines:
                    return srsly.read_json(lines[0]) if len(lines) == 1 else {"raw_lines": lines}
                else:
                    return {}
                    
        except Exception as e:
            logger.warning(f"Failed to load JSONL from {file_path}: {e}")
            return {}
    
    def save_data_to_file(self, data: Dict, file_path: Path):
        """Override to save as JSONL format"""
        # Create backup
        if file_path.exists():
            backup_file = file_path.with_suffix(file_path.suffix + '.backup')
            import shutil
            shutil.copy2(file_path, backup_file)
        
        # Ensure parent directory exists
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Save as single line JSON for now (could be enhanced for multi-step configs)
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(srsly.json_dumps(data, indent=2))
    
    def get_schema(self) -> UISchema:
        """Load the UI schema from file"""
        try:
            with open(self.schema_file, 'r', encoding='utf-8') as f:
                schema_data = yaml.safe_load(f)
            
            # Format the title with the current file name
            schema_data['title'] = schema_data['title'].format(config_file=self.config_file)
            
            return UISchema(
                title=schema_data.get('title', 'Prompts Editor'),
                description=schema_data.get('description', ''),
                tabs=schema_data.get('tabs', []),
                sections=schema_data.get('sections', []),
                style=schema_data.get('style', {})
            )
        except Exception as e:
            logger.error(f"Failed to load prompts schema: {e}")
            # Return minimal schema as fallback
            return UISchema(
                title="Prompts Editor",
                description="LLM configuration",
                sections=[
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
    
    def get_default_data(self) -> Dict:
        """Get default data for prompts configuration"""
        return {
            "name": f"Config {self.config_file.stem}",
            "description": "LLM processing configuration",
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
            "steps": []
        }
    
    def get_management_dialog_class(self):
        """Get the management dialog class for prompts"""
        return PromptsManagementDialog
    
    def _validate_prompts_config(self, data: Dict) -> list:
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
    
    def post_save_actions(self, data: Dict):
        """Prompts config specific post-save actions"""
        try:
            # Validate configuration after save
            errors = self._validate_prompts_config(data)
            if errors:
                print(f"⚠️ Configuration saved but has validation warnings: {', '.join(errors)}")
            else:
                print("✅ Valid prompts configuration saved!")
                
        except Exception as e:
            logger.error(f"Failed to perform prompts config post-save actions: {e}")
    
    def show_save_success(self):
        """Custom save success message for prompts configs"""
        print(f"✅ Prompts configuration saved: {self.config_file.name}")
    
    def show_save_error(self, error: Exception):
        """Custom save error message for prompts configs"""
        print(f"❌ Failed to save prompts configuration {self.config_file.name}: {error}") 