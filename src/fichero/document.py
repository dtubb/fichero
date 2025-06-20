"""
Fichero Document class
Implements Toga's document-based architecture
"""

import toga
from pathlib import Path
import yaml
import uuid
import logging
from typing import Optional, Dict, Any

from .utils import _, get_app_settings
from .ui.windows.document_window import FicheroDocumentWindow

logger = logging.getLogger(__name__)


class FicheroDocument(toga.Document):
    """Fichero document class representing a document processing project"""
    
    description = "Fichero Document Processing Project"
    extensions = ["fichero"]
    
    def __init__(self, app, path: Optional[Path] = None):
        # Initialize basic properties first
        self.document_id = str(uuid.uuid4())
        self.plans_config = {}
        self.document_config = {}
        self.is_modified = False
        
        # Store the app reference temporarily
        self._temp_app = app
        
        # Set path if provided
        if path:
            self.path = path
        
        # Call super().__init__ first to set up the app reference
        super().__init__(app)
        
        # Now initialize document structure after app is available
        self._init_document_structure()
    
    def _init_document_structure(self):
        """Initialize or load document structure"""
        if hasattr(self, 'path') and self.path and self.path.exists():
            self._load_document()
        else:
            self._create_new_document()
    
    def _create_new_document(self):
        """Create a new document with default structure"""
        # For new documents, Toga will handle the path when the user saves
        # We don't set self.path directly since it's read-only
        
        # Create default plans config in memory
        self._create_default_plans()
        
        # Create default document config in memory
        self._create_default_document_config()
        
        logger.info(f"Created new document structure in memory")
    
    def _load_document(self):
        """Load existing document"""
        try:
            # Load plans.yml
            plans_file = self.path / "plans.yml"
            if plans_file.exists():
                with open(plans_file, 'r', encoding='utf-8') as f:
                    self.plans_config = yaml.safe_load(f) or {}
            
            # Load document config
            config_file = self.path / "document_config.yml"
            if config_file.exists():
                with open(config_file, 'r', encoding='utf-8') as f:
                    self.document_config = yaml.safe_load(f) or {}
            
            logger.info(f"Loaded document: {self.path}")
            
        except Exception as e:
            logger.error(f"Failed to load document {self.path}: {e}")
            # Fallback to creating new document
            self._create_new_document()
    
    def _create_default_plans(self):
        """Create default plans.yml for new document"""
        try:
            # Load template from resources
            app_ref = getattr(self, 'app', getattr(self, '_temp_app', None))
            if app_ref:
                template_path = app_ref.paths.app / "resources" / "plans" / "plans.yml"
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
            if hasattr(self, 'path') and self.path:
                template_config["title"] = f"Document - {self.path.name}"
                template_config["vars"]["name"] = self.path.name
                template_config["vars"]["project_folder"] = str(self.path)
                template_config["vars"]["documents_folder"] = str(self.path / "documents")
                template_config["vars"]["assets_folder"] = str(self.path / "assets")
            else:
                # For new documents without a path yet
                template_config["title"] = "New Document"
                template_config["vars"]["name"] = "Untitled"
            
            self.plans_config = template_config
            
            # Only save if we have a path (i.e., for existing documents)
            if hasattr(self, 'path') and self.path:
                self._save_plans_config()
            
        except Exception as e:
            logger.error(f"Failed to create default plans: {e}")
    
    def _create_default_document_config(self):
        """Create default document configuration"""
        document_name = "Untitled"
        if hasattr(self, 'path') and self.path:
            document_name = self.path.name
        
        self.document_config = {
            "document_id": self.document_id,
            "created_at": str(Path().cwd()),  # Will be replaced with actual timestamp
            "title": document_name,
            "description": "",
            "tags": [],
            "processing_status": "new",
            "window_settings": {
                "size": [650, 406],
                "position": [100, 100]
            },
            "recent_workflows": [],
            "bookmarks": []
        }
        # Only save if we have a path (i.e., for existing documents)
        if hasattr(self, 'path') and self.path:
            self._save_document_config()
    
    def _save_plans_config(self):
        """Save plans configuration to file"""
        if not (hasattr(self, 'path') and self.path):
            logger.warning("Cannot save plans config: no path available")
            return
            
        try:
            plans_file = self.path / "plans.yml"
            with open(plans_file, 'w', encoding='utf-8') as f:
                yaml.dump(self.plans_config, f, default_flow_style=False, allow_unicode=True, indent=2)
            logger.info(f"Saved plans config: {plans_file}")
        except Exception as e:
            logger.error(f"Failed to save plans config: {e}")
    
    def _save_document_config(self):
        """Save document configuration to file"""
        if not (hasattr(self, 'path') and self.path):
            logger.warning("Cannot save document config: no path available")
            return
            
        try:
            config_file = self.path / "document_config.yml"
            with open(config_file, 'w', encoding='utf-8') as f:
                yaml.dump(self.document_config, f, default_flow_style=False, allow_unicode=True, indent=2)
            logger.info(f"Saved document config: {config_file}")
        except Exception as e:
            logger.error(f"Failed to save document config: {e}")
    
    def create(self):
        """Create the document window - called automatically by Toga"""
        try:
            logger.info(f"Creating document window for document {self.document_id}")
            # Create the main window using DocumentWindow - simplified like official example
            self.main_window = FicheroDocumentWindow(
                doc=self
            )
            logger.info(f"Successfully created document window")
            return self.main_window
        except Exception as e:
            logger.error(f"Failed to create document window: {e}")
            import traceback
            traceback.print_exc()
            raise
    
    def read(self):
        """Read document data from file"""
        self._load_document()
    
    def write(self):
        """Write document data to file"""
        if hasattr(self, 'path') and self.path:
            # Ensure document directory exists
            self.path.mkdir(parents=True, exist_ok=True)
            
            # Update document config with current path info
            self.document_config["title"] = self.path.name
            if "vars" in self.plans_config:
                self.plans_config["vars"]["name"] = self.path.name
                self.plans_config["vars"]["project_folder"] = str(self.path)
                self.plans_config["vars"]["documents_folder"] = str(self.path / "documents")
                self.plans_config["vars"]["assets_folder"] = str(self.path / "assets")
            
            # Save both configurations
            self._save_plans_config()
            self._save_document_config()
            self.is_modified = False
            logger.info(f"Saved document to: {self.path}")
        else:
            logger.warning("Cannot save document: no path available")

    def show_document_settings(self):
        """Show document settings window"""
        if hasattr(self, 'main_window') and self.main_window:
            self.main_window.show_document_settings()
    
    def show_document_plans(self):
        """Show document plans window"""
        if hasattr(self, 'main_window') and self.main_window:
            self.main_window.show_document_plans() 