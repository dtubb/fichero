"""
Plans File Manager
Handles plans-specific file operations and business logic
"""

import yaml
from pathlib import Path
from typing import Dict, Any, List
import logging

from .file_manager import FileManager
from .settings import get_app_settings

logger = logging.getLogger(__name__)


class PlansManager(FileManager):
    """File manager for project plans"""
    
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
    
    def save_file(self, file_path: Path, data: Dict[str, Any]) -> bool:
        """Override to perform post-save actions"""
        try:
            # Save to file
            success = super().save_file(file_path, data)
            if not success:
                return False
            
            # Log the project name if available
            project_name = data.get("vars", {}).get("name", "Unknown")
            logger.info(f"Plans configuration saved for project: {project_name}")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to perform plans post-save actions: {e}")
            return False
    
    def get_active_file(self) -> Path:
        """DEPRECATED: Plans don't need active file tracking"""
        logger.warning("get_active_file() is deprecated - plans don't use active file tracking")
        return None
    
    def set_active_file(self, file_path: Path) -> bool:
        """DEPRECATED: Plans don't need active file tracking"""
        logger.warning("set_active_file() is deprecated - plans don't use active file tracking")
        return True
    
    def get_workflows(self, file_path: Path) -> List[str]:
        """Get list of workflows for a specific plan"""
        try:
            plan_data = self.load_file(file_path)
            workflows = plan_data.get('workflows', {})
            return sorted(workflows.keys())
        except Exception as e:
            logger.error(f"Failed to get workflows for {file_path}: {e}")
            return []
    
    def get_project_name(self, file_path: Path) -> str:
        """Get project name from plan file"""
        try:
            plan_data = self.load_file(file_path)
            return plan_data.get("vars", {}).get("name", file_path.stem)
        except Exception as e:
            logger.error(f"Failed to get project name for {file_path}: {e}")
            return file_path.stem 