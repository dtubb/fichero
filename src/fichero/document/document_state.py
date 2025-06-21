"""
Document State Management
Handles document metadata, plans, and state persistence
"""

import yaml
import datetime
import logging
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class DocumentStateManager:
    """Manages document state, metadata, and plans configuration"""
    
    def __init__(self, document):
        self.document = document
        self.plans_config: Dict[str, Any] = {}
        self.document_config: Dict[str, Any] = {}
    
    def create_default_plans(self):
        """Create default plans.yml for new document"""
        try:
            # Load template from resources
            app_ref = getattr(self.document, 'app', getattr(self.document, '_temp_app', getattr(self.document, '_app', None)))
            if app_ref:
                template_path = app_ref.paths.app / "resources" / "config_defaults" / "plans" / "Default Plan.yml"
            else:
                template_path = None
            
            if template_path and template_path.exists():
                with open(template_path, 'r', encoding='utf-8') as f:
                    template_config = yaml.safe_load(f) or {}
            else:
                # Fallback minimal config
                template_config = {
                    "title": "New Document",
                    "description": "Document processing workflow",
                    "vars": {
                        "name": "New Document",
                        "language": "en",
                        "version": "1.0.0"
                    },
                    "workflows": {
                        "default": ["build_documents_manifest"]
                    },
                    "commands": []
                }
            
            # Customize for this document
            if hasattr(self.document, 'path') and self.document.path:
                template_config["title"] = f"Document - {self.document.path.name}"
                template_config["vars"]["name"] = self.document.path.name
                template_config["vars"]["project_folder"] = str(self.document.path)
                template_config["vars"]["documents_folder"] = str(self.document.path / "documents")
                template_config["vars"]["assets_folder"] = str(self.document.path / "assets")
            else:
                # For new documents without a path yet
                template_config["title"] = "New Document"
                template_config["vars"]["name"] = "Untitled"
            
            self.plans_config = template_config
            
            # Only save if we have a path (i.e., for existing documents)
            if hasattr(self.document, 'path') and self.document.path:
                self.save_plans_config()
            
        except Exception as e:
            logger.error(f"Failed to create default plans: {e}")
    
    def create_default_document_config(self):
        """Create default document configuration"""
        document_name = "Untitled"
        if hasattr(self.document, 'path') and self.document.path:
            document_name = self.document.path.name
        
        self.document_config = {
            "document_id": self.document.document_id,
            "created_at": datetime.datetime.now().isoformat(),
            "title": document_name,
            "description": "",
            "tags": [],
            "processing_status": "new",
            "window_settings": {
                "size": [650, 406],
                "position": [100, 100],
                "open_files": []  # Track files open in this document
            },
            "recent_workflows": [],
            "bookmarks": [],
            # Document-specific processing settings
            "processing_settings": {
                "input_folder": "",
                "selected_plan": "Default Plan",
                "selected_workflow": "default", 
                "custom_steps": [],
                "workflow_variables": {},
                "output_format": "word",
                "language": "en"
            },
            # User preferences for this document
            "user_preferences": {
                "auto_process_on_import": False,
                "show_advanced_options": False,
                "default_transcription_model": "qwen_max"
            }
        }
        
        # Only save if we have a path (i.e., for existing documents)
        if hasattr(self.document, 'path') and self.document.path:
            self.save_document_config()
    
    def load_document(self, path: Path):
        """Load existing document configuration"""
        try:
            # Load plans.yml
            plans_file = path / "plans.yml"
            if plans_file.exists():
                with open(plans_file, 'r', encoding='utf-8') as f:
                    self.plans_config = yaml.safe_load(f) or {}
            
            # Load document config
            config_file = path / "document_config.yml"
            if config_file.exists():
                with open(config_file, 'r', encoding='utf-8') as f:
                    self.document_config = yaml.safe_load(f) or {}
            
            logger.info(f"Loaded document state: {path}")
            
        except Exception as e:
            logger.error(f"Failed to load document {path}: {e}")
            # Fallback to creating new document
            self.create_default_plans()
            self.create_default_document_config()
    
    def save_plans_config(self):
        """Save plans configuration to file"""
        if not (hasattr(self.document, 'path') and self.document.path):
            logger.warning("Cannot save plans config: no path available")
            return
            
        try:
            plans_file = self.document.path / "plans.yml"
            with open(plans_file, 'w', encoding='utf-8') as f:
                yaml.dump(self.plans_config, f, default_flow_style=False, allow_unicode=True, indent=2)
            logger.info(f"Saved plans config: {plans_file}")
        except Exception as e:
            logger.error(f"Failed to save plans config: {e}")
    
    def save_document_config(self):
        """Save document configuration to file"""
        if not (hasattr(self.document, 'path') and self.document.path):
            logger.warning("Cannot save document config: no path available")
            return
            
        try:
            config_file = self.document.path / "document_config.yml"
            with open(config_file, 'w', encoding='utf-8') as f:
                yaml.dump(self.document_config, f, default_flow_style=False, allow_unicode=True, indent=2)
            logger.info(f"Saved document config: {config_file}")
        except Exception as e:
            logger.error(f"Failed to save document config: {e}")
    
    def has_meaningful_changes(self) -> bool:
        """Check if document has meaningful changes from default state"""
        # Check if title was changed from default
        if self.document_config.get("title", "Untitled") not in ["Untitled", "New Document"]:
            return True
        
        # Check if description was added
        if self.document_config.get("description", "").strip():
            return True
        
        # Check if processing settings were changed
        processing_settings = self.document_config.get("processing_settings", {})
        if processing_settings.get("input_folder", "").strip():
            return True
        if processing_settings.get("selected_plan", "Default Plan") != "Default Plan":
            return True
        if processing_settings.get("selected_workflow", "default") != "default":
            return True
        if processing_settings.get("custom_steps", []):
            return True
        if processing_settings.get("workflow_variables", {}):
            return True
        
        # Check if plans config was modified
        if self.plans_config.get("title", "") not in ["New Document", ""]:
            return True
        
        return False
    
    # Processing settings management methods
    def set_input_folder(self, folder_path: str):
        """Set the input folder for processing"""
        if "processing_settings" not in self.document_config:
            self.document_config["processing_settings"] = {}
        self.document_config["processing_settings"]["input_folder"] = folder_path
        self.document.mark_modified()
    
    def get_input_folder(self) -> str:
        """Get the input folder for processing"""
        return self.document_config.get("processing_settings", {}).get("input_folder", "")
    
    def update_title(self, new_title: str):
        """Update document title and trigger auto-save"""
        if "vars" in self.plans_config:
            self.plans_config["vars"]["name"] = new_title
        self.plans_config["title"] = f"Document - {new_title}"
        self.document_config["title"] = new_title
        self.document.mark_modified()
    
    def update_description(self, new_description: str):
        """Update document description and trigger auto-save"""
        self.document_config["description"] = new_description
        self.document.mark_modified() 