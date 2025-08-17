"""
Preview Manager

Coordinates all preview components and automatically selects the appropriate preview
based on file type. Manages switching between different preview types.
"""

import toga
from toga.style import Pack
from toga.constants import COLUMN, ROW
import logging
from typing import Optional, Dict, Any, Callable
from pathlib import Path

from .image_preview import ImagePreview
from .text_preview import TextPreview
from .document_preview import DocumentPreview
from .fiche_preview import FichePreview
from .translation_preview import TranslationPreview

logger = logging.getLogger(__name__)


class PreviewManager:
    """Manages different preview components based on file type"""
    
    def __init__(self, presenter, width=300, is_mobile=False):
        self.presenter = presenter
        self.width = width
        self.is_mobile = is_mobile
        
        # Current state
        self.current_file_path: Optional[Path] = None
        self.current_preview_type: str = ""
        
        # Preview components
        self.image_preview: Optional[ImagePreview] = None
        self.text_preview: Optional[TextPreview] = None
        self.document_preview: Optional[DocumentPreview] = None
        self.fiche_preview: Optional[FichePreview] = None
        self.translation_preview: Optional[TranslationPreview] = None
        
        # Current active preview
        self.active_preview = None
        
        # UI components
        self.container = None
        self.header = None
        self.content_container = None
        
        # Callbacks
        self.on_preview_change: Optional[Callable[[str, Path], None]] = None
        
        self._create_ui()
        self._initialize_previews()
    
    def _create_ui(self):
        """Create preview manager UI"""
        # Main container
        style = Pack(direction=COLUMN, margin=10)
        if self.is_mobile:
            # Mobile: use specified width or full width
            if self.width is not None:
                style.width = self.width
            else:
                style.flex = 1  # Full width for mobile
        else:
            # Desktop: always use full width
            style.flex = 1
        self.container = toga.Box(style=style)
        
        # Header
        self.header = toga.Label(
            "Preview",
            style=Pack(font_size=12, font_weight="bold", margin_bottom=5)
        )
        self.container.add(self.header)
        
        # Content container (will hold the active preview)
        self.content_container = toga.Box(style=Pack(flex=1))
        self.container.add(self.content_container)
        
        # Show placeholder
        self._show_placeholder()
    
    def _initialize_previews(self):
        """Initialize all preview components"""
        try:
            # Create preview components (lazy initialization)
            self.image_preview = ImagePreview(self.presenter, self.width, self.is_mobile)
            self.text_preview = TextPreview(self.presenter, self.width, self.is_mobile)
            self.document_preview = DocumentPreview(self.presenter, self.width, self.is_mobile)
            self.fiche_preview = FichePreview(self.presenter, self.width, self.is_mobile)
            self.translation_preview = TranslationPreview(self.presenter, self.width, self.is_mobile)
            
            logger.info("All preview components initialized")
            
        except Exception as e:
            logger.error(f"Failed to initialize preview components: {e}")
    
    def _show_placeholder(self):
        """Show placeholder content"""
        self.header.text = "Preview"
        self.content_container.clear()
        self.content_container.add(toga.Label("Select an item to preview"))
        self.current_file_path = None
        self.current_preview_type = ""
        self.active_preview = None
    
    def preview_file(self, file_path: Path):
        """Preview a file using the appropriate preview component"""
        try:
            self.current_file_path = file_path
            
            # Determine preview type
            preview_type = self._determine_preview_type(file_path)
            self.current_preview_type = preview_type
            
            # Update header
            self.header.text = f"Preview: {file_path.name}"
            
            # Switch to appropriate preview
            self._switch_to_preview(preview_type, file_path)
            
            # Notify callback
            if self.on_preview_change:
                self.on_preview_change(preview_type, file_path)
            
            logger.info(f"Previewing file: {file_path.name} (type: {preview_type})")
            
        except Exception as e:
            logger.error(f"Failed to preview file: {e}")
            self._show_error(f"Failed to preview: {file_path.name}")
    
    def _determine_preview_type(self, file_path: Path) -> str:
        """Determine the appropriate preview type for a file"""
        try:
            extension = file_path.suffix.lower()
            filename_lower = file_path.name.lower()
            
            # Image files
            if extension in {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tif', '.tiff', '.webp'}:
                return "image"
            
            # Text files
            elif extension in {'.txt', '.md', '.rtf', '.log'}:
                return "text"
            
            # Document files
            elif extension in {'.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx'}:
                return "document"
            
            # Translation files (check filename patterns first)
            elif any(keyword in filename_lower for keyword in ['translation', 'translated', 'translate']):
                return "translation"
            elif extension in {'.trans', '.translation', '.json'} and self._is_translation_file(file_path):
                return "translation"
            
            # Fiche files (check filename patterns first)
            elif any(keyword in filename_lower for keyword in ['fiche', 'processed', 'metadata']):
                return "fiche"
            elif extension in {'.fiche', '.json'} and self._is_fiche_file(file_path):
                return "fiche"
            
            # Transcription files
            elif any(keyword in filename_lower for keyword in ['transcription', 'transcribe', 'ocr', 'text']):
                return "text"  # Use text preview for transcriptions
            
            # Default to text for unknown types
            else:
                return "text"
                
        except Exception as e:
            logger.error(f"Failed to determine preview type: {e}")
            return "text"  # Default fallback
    
    def _is_translation_file(self, file_path: Path) -> bool:
        """Check if file is a translation file"""
        try:
            if file_path.suffix.lower() == '.json':
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = f.read(1000)  # Read first 1000 chars
                    return '"original"' in data and '"translated"' in data
            return False
        except:
            return False
    
    def _is_fiche_file(self, file_path: Path) -> bool:
        """Check if file is a fiche data file"""
        try:
            if file_path.suffix.lower() == '.json':
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = f.read(1000)  # Read first 1000 chars
                    return '"transcription"' in data or '"processing_status"' in data
            return False
        except:
            return False
    
    def _is_transcription_file(self, file_path: Path) -> bool:
        """Check if file is a transcription file"""
        try:
            # Check filename patterns
            name_lower = file_path.name.lower()
            transcription_keywords = ['transcription', 'transcribe', 'ocr', 'text']
            return any(keyword in name_lower for keyword in transcription_keywords)
        except:
            return False
    
    def _switch_to_preview(self, preview_type: str, file_path: Path):
        """Switch to the appropriate preview component"""
        try:
            # Clear current content
            self.content_container.clear()
            
            # Deactivate current preview
            if self.active_preview:
                self.active_preview.clear()
            
            # Switch to new preview
            if preview_type == "image":
                self.active_preview = self.image_preview
                self.image_preview.show_image(file_path)
                self.content_container.add(self.image_preview.container)
                
            elif preview_type == "text":
                self.active_preview = self.text_preview
                self.text_preview.show_text_file(file_path, editable=True)
                self.content_container.add(self.text_preview.container)
                
            elif preview_type == "document":
                self.active_preview = self.document_preview
                self.document_preview.show_document(file_path)
                self.content_container.add(self.document_preview.container)
                
            elif preview_type == "fiche":
                self.active_preview = self.fiche_preview
                self.fiche_preview.show_fiche(file_path)
                self.content_container.add(self.fiche_preview.container)
                
            elif preview_type == "translation":
                self.active_preview = self.translation_preview
                self.translation_preview.show_translation(file_path, editable=True)
                self.content_container.add(self.translation_preview.container)
                
            else:
                # Fallback to text preview
                self.active_preview = self.text_preview
                self.text_preview.show_text_file(file_path, editable=False)
                self.content_container.add(self.text_preview.container)
            
            logger.info(f"Switched to {preview_type} preview")
            
        except Exception as e:
            logger.error(f"Failed to switch to {preview_type} preview: {e}")
            self._show_error(f"Failed to load {preview_type} preview")
    
    def _show_error(self, message: str):
        """Show error message"""
        self.header.text = "Error"
        self.content_container.clear()
        self.content_container.add(toga.Label(message))
        self.active_preview = None
    
    def clear(self):
        """Clear the preview"""
        if self.active_preview:
            self.active_preview.clear()
        
        self.current_file_path = None
        self.current_preview_type = ""
        self.active_preview = None
        self._show_placeholder()
    
    def refresh(self):
        """Refresh the current preview"""
        try:
            if self.current_file_path and self.active_preview:
                # Re-preview the current file
                self.preview_file(self.current_file_path)
                logger.info("Preview refreshed")
            else:
                logger.warning("No preview to refresh")
                
        except Exception as e:
            logger.error(f"Failed to refresh preview: {e}")
    
    def get_current_file(self) -> Optional[Path]:
        """Get current file path"""
        return self.current_file_path
    
    def get_current_preview_type(self) -> str:
        """Get current preview type"""
        return self.current_preview_type
    
    def get_active_preview(self):
        """Get the currently active preview component"""
        return self.active_preview
    
    # Keyboard navigation support (delegates to active preview)
    def handle_key_left(self):
        """Handle left arrow key"""
        if self.active_preview and hasattr(self.active_preview, 'handle_key_left'):
            self.active_preview.handle_key_left()
    
    def handle_key_right(self):
        """Handle right arrow key"""
        if self.active_preview and hasattr(self.active_preview, 'handle_key_right'):
            self.active_preview.handle_key_right()
    
    def handle_key_escape(self):
        """Handle escape key"""
        if self.active_preview and hasattr(self.active_preview, 'handle_key_escape'):
            self.active_preview.handle_key_escape()
    
    # Preview-specific methods (delegates to active preview)
    def save_current_content(self):
        """Save current content if supported"""
        if self.active_preview and hasattr(self.active_preview, '_save_content'):
            self.active_preview._save_content(None)
    
    def copy_current_content(self):
        """Copy current content if supported"""
        if self.active_preview and hasattr(self.active_preview, '_copy_content'):
            self.active_preview._copy_content(None)
    
    def make_current_editable(self, editable: bool = True):
        """Make current preview editable if supported"""
        if self.active_preview and hasattr(self.active_preview, 'make_editable'):
            self.active_preview.make_editable(editable)
    
    def is_current_modified(self) -> bool:
        """Check if current preview is modified"""
        if self.active_preview and hasattr(self.active_preview, 'is_content_modified'):
            return self.active_preview.is_content_modified()
        elif self.active_preview and hasattr(self.active_preview, 'is_translation_modified'):
            return self.active_preview.is_translation_modified()
        return False 