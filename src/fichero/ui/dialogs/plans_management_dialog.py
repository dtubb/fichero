"""
Plans Management Dialog
Specialized file management dialog for plan files
"""

from pathlib import Path
from typing import Dict, Any, List

from .base_management_dialog import BaseManagementDialog


class PlansManagementDialog(BaseManagementDialog):
    """Management dialog for plan files (.yml/.yaml/.json/.jsonl)"""
    
    def get_file_type(self) -> str:
        """Get the file type name"""
        return "plans"
    
    def get_file_extensions(self) -> List[str]:
        """Get supported file extensions for plans"""
        return ['.yml', '.yaml', '.json', '.jsonl']
    

    
    def get_default_template(self) -> Dict[str, Any]:
        """Get default data structure for new plan files"""
        return {
            "title": "New Project",
            "description": "A new project plan",
            "vars": {
                "name": "untitled_project",
                "language": "en",
                "text_direction": "horizontal-lr",
                "version": "1.0.0",
                "crop_format": "jpg",
                "split_format": "jpg",
                "rotate_format": "jpg",
                "enhance_format": "jpg",
                "background_removed_format": "png",
                "lmstudio_url": "http://localhost:1234",
                "lmstudio_model": "",
                "prompt": "Please process the following content accurately.",
                "project_folder": "${vars.name}",
                "documents_folder": "${vars.project_folder}/documents",
                "assets_folder": "${vars.project_folder}/assets"
            },
            "workflows": {
                "default": {
                    "description": "Default processing workflow",
                    "steps": [
                        {
                            "name": "process_documents",
                            "description": "Process all documents in the folder"
                        }
                    ]
                }
            }
        } 