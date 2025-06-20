"""
Document Manager for Fichero
Handles document-based architecture where each window represents a document
with its own plans.yml configuration and processing settings
"""

import toga
from toga.style import Pack
from pathlib import Path
import yaml
import srsly
from typing import Dict, Any, Optional, List
import logging
import uuid


from ..utils import _, get_app_settings

logger = logging.getLogger(__name__)

class DocumentWindow:
    """Represents a single document window with its own configuration"""
    
    def __init__(self, app, document_path: Optional[Path] = None, document_id: str = None):
        self.app = app
        self.document_id = document_id or str(uuid.uuid4())
        self.document_path = document_path
        self.window = None
        self.is_modified = False
        self.plans_config = {}
        self.document_config = {}
        
        # Initialize document structure
        self._init_document_structure()
        
    def _init_document_structure(self):
        """Initialize or load document structure"""
        if self.document_path and self.document_path.exists():
            self._load_document()
        else:
            self._create_new_document()
    
    def _create_new_document(self):
        """Create a new document with default structure"""
        # Create temporary document path if none provided
        if not self.document_path:
            self.document_path = self.app.paths.data / "documents" / f"untitled_{self.document_id}"
        
        # Ensure document directory exists
        self.document_path.mkdir(parents=True, exist_ok=True)
        
        # Create default plans.yml from template
        self._create_default_plans()
        
        # Create default document config
        self._create_default_document_config()
        
        logger.info(f"Created new document: {self.document_path}")
    
    def _load_document(self):
        """Load existing document"""
        try:
            # Load plans.yml
            plans_file = self.document_path / "plans.yml"
            if plans_file.exists():
                with open(plans_file, 'r', encoding='utf-8') as f:
                    self.plans_config = yaml.safe_load(f) or {}
            
            # Load document config
            config_file = self.document_path / "document_config.yml"
            if config_file.exists():
                with open(config_file, 'r', encoding='utf-8') as f:
                    self.document_config = yaml.safe_load(f) or {}
            
            logger.info(f"Loaded document: {self.document_path}")
            
        except Exception as e:
            logger.error(f"Failed to load document {self.document_path}: {e}")
            # Fallback to creating new document
            self._create_new_document()
    
    def _create_default_plans(self):
        """Create default plans.yml for new document"""
        try:
            # Load template from resources
            template_path = self.app.paths.app / "resources" / "plans" / "plans.yml"
            if template_path.exists():
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
            template_config["title"] = f"Document - {self.document_path.name}"
            template_config["vars"]["name"] = self.document_path.name
            template_config["vars"]["project_folder"] = str(self.document_path)
            template_config["vars"]["documents_folder"] = str(self.document_path / "documents")
            template_config["vars"]["assets_folder"] = str(self.document_path / "assets")
            
            self.plans_config = template_config
            self._save_plans_config()
            
        except Exception as e:
            logger.error(f"Failed to create default plans: {e}")
    
    def _create_default_document_config(self):
        """Create default document configuration"""
        self.document_config = {
            "document_id": self.document_id,
            "created_at": str(Path().cwd()),  # Will be replaced with actual timestamp
            "title": self.document_path.name if self.document_path else "Untitled",
            "description": "",
            "tags": [],
            "processing_status": "new",
            "window_settings": {
                "size": [1200, 800],
                "position": [100, 100]
            },
            "recent_workflows": [],
            "bookmarks": []
        }
        self._save_document_config()
    
    def _save_plans_config(self):
        """Save plans configuration to file"""
        try:
            plans_file = self.document_path / "plans.yml"
            with open(plans_file, 'w', encoding='utf-8') as f:
                yaml.dump(self.plans_config, f, default_flow_style=False, allow_unicode=True, indent=2)
            logger.info(f"Saved plans config: {plans_file}")
        except Exception as e:
            logger.error(f"Failed to save plans config: {e}")
    
    def _save_document_config(self):
        """Save document configuration to file"""
        try:
            config_file = self.document_path / "document_config.yml"
            with open(config_file, 'w', encoding='utf-8') as f:
                yaml.dump(self.document_config, f, default_flow_style=False, allow_unicode=True, indent=2)
            logger.info(f"Saved document config: {config_file}")
        except Exception as e:
            logger.error(f"Failed to save document config: {e}")
    
    def create_window(self) -> toga.Window:
        """Create the main document window"""
        if self.window:
            return self.window
        
        title = self.document_config.get("title", "Untitled Document")
        if self.is_modified:
            title += " •"
        
        # Create a separate document window (not the main app window)
        self.window = toga.Window(
            title=title,
            size=tuple(self.document_config.get("window_settings", {}).get("size", [900, 700])),
            resizable=True
        )
        
        # Create main content
        main_box = toga.Box(style=Pack(direction=toga.constants.COLUMN, flex=1))
        
        # Document info header
        info_box = self._create_document_info_header()
        main_box.add(info_box)
        
        # Main content area
        content_box = toga.Box(
            style=Pack(
                direction=toga.constants.COLUMN,
                flex=1,
                margin=20,
                background_color="#FFFFFF"
            )
        )
        
        # Welcome content
        welcome_label = toga.Label(
            f"Document: {self.document_path.name}",
            style=Pack(
                text_align=toga.constants.CENTER,
                font_size=18,
                font_weight="bold",
                margin_bottom=20
            )
        )
        content_box.add(welcome_label)
        
        description_label = toga.Label(
            "This is a document window for managing and processing files.\n\n"
            "Use the buttons above to configure processing plans and document settings.\n"
            "Use the File menu to save your work or create additional documents.\n\n"
            "This window is separate from the main Fichero window.",
            style=Pack(
                text_align=toga.constants.CENTER,
                font_size=12,
                margin=30,
                color="#666666"
            )
        )
        content_box.add(description_label)
        
        # Document ID (for debugging)
        id_label = toga.Label(
            f"Document ID: {self.document_id}",
            style=Pack(
                text_align=toga.constants.CENTER,
                font_size=10,
                color="#AAAAAA",
                margin_top=40
            )
        )
        content_box.add(id_label)
        
        main_box.add(content_box)
        
        self.window.content = main_box
        return self.window
    
    def _create_document_info_header(self) -> toga.Box:
        """Create document information header"""
        header_box = toga.Box(
            style=Pack(
                direction=toga.constants.ROW,
                background_color="#f5f5f5",
                margin=15
            )
        )
        
        # Document title and status
        info_box = toga.Box(style=Pack(direction=toga.constants.COLUMN, flex=1))
        
        title_label = toga.Label(
            self.document_config.get("title", "Untitled"),
            style=Pack(font_size=16, font_weight="bold")
        )
        info_box.add(title_label)
        
        status_label = toga.Label(
            f"Status: {self.document_config.get('processing_status', 'new').title()}",
            style=Pack(font_size=12, color="#666666", margin_top=2)
        )
        info_box.add(status_label)
        
        path_label = toga.Label(
            f"Path: {self.document_path}",
            style=Pack(font_size=11, color="#888888", margin_top=2)
        )
        info_box.add(path_label)
        
        header_box.add(info_box)
        
        # Quick action buttons
        button_box = toga.Box(style=Pack(direction=toga.constants.ROW))
        
        edit_plans_btn = toga.Button(
            "Edit Plans",
            on_press=self._edit_plans,
            style=Pack(
                margin_right=10,
                font_size=12,
                height=32
            )
        )
        button_box.add(edit_plans_btn)
        

        
        header_box.add(button_box)
        
        return header_box
    
    def _edit_plans(self, widget):
        """Edit plans configuration for this document"""
        plans_file = self.document_path / "plans.yml"
        # Use the new specialized config windows
        from .windows.plans_editor_window import PlansEditorWindow
        plans_editor = PlansEditorWindow(self.app, plans_file)
        plans_editor.show()
    

    
    def save_document(self):
        """Save the document"""
        self._save_plans_config()
        self._save_document_config()
        self.is_modified = False
        self._update_window_title()
    
    def _update_window_title(self):
        """Update window title to reflect modified state"""
        if self.window:
            title = self.document_config.get("title", "Untitled Document")
            if self.is_modified:
                title += " •"
            self.window.title = title

class DocumentManager:
    """Manages all document windows and operations"""
    
    def __init__(self, app):
        self.app = app
        self.documents: List[DocumentWindow] = []
        self.active_document: Optional[DocumentWindow] = None
    
    def new_document(self) -> DocumentWindow:
        """Create a new document"""
        doc = DocumentWindow(self.app)
        self.documents.append(doc)
        self.active_document = doc
        return doc
    
    def open_document(self, document_path: Path) -> DocumentWindow:
        """Open an existing document"""
        # Check if document is already open
        for doc in self.documents:
            if doc.document_path == document_path:
                self.active_document = doc
                return doc
        
        # Create new document window
        doc = DocumentWindow(self.app, document_path)
        self.documents.append(doc)
        self.active_document = doc
        return doc
    
    def close_document(self, document: DocumentWindow) -> bool:
        """Close a document (returns False if cancelled)"""
        if document.is_modified:
            # TODO: Show save dialog
            pass
        
        if document in self.documents:
            self.documents.remove(document)
        
        if self.active_document == document:
            self.active_document = self.documents[0] if self.documents else None
        
        return True
    
    def save_document(self, document: Optional[DocumentWindow] = None):
        """Save a document"""
        doc = document or self.active_document
        if doc:
            doc.save_document()
    
    def save_document_as(self, document: Optional[DocumentWindow] = None, new_path: Path = None):
        """Save document with new path"""
        doc = document or self.active_document
        if doc and new_path:
            doc.document_path = new_path
            doc.save_document()
    
    def get_recent_documents(self) -> List[Path]:
        """Get list of recently opened documents"""
        # TODO: Implement recent documents tracking
        return []
    
    def get_recent_documents(self) -> List[Path]:
        """Get list of recently opened documents"""
        # TODO: Implement recent documents tracking
        return [] 