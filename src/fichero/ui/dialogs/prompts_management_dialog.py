"""
Prompts Management Dialog
Specialized file management dialog for prompt/LLM config files
"""

from pathlib import Path
from typing import Dict, Any, List

from .base_management_dialog import BaseManagementDialog


class PromptsManagementDialog(BaseManagementDialog):
    """Management dialog for prompts/LLM config files (.jsonl/.json/.yml/.yaml)"""
    
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