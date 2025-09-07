"""
Preview Pane for Fichero

Full-width preview pane for the right side of the main window.
Supports different file types and integrates with toolbar controls.
"""

import toga
from toga.style import Pack
from toga.constants import COLUMN, ROW
import logging
from pathlib import Path
from typing import Optional, Callable, Dict, Any

from fichero.windows.main.views.base_view import BaseView
from fichero.windows.main.toolbars.preview_top_toolbar import PreviewTopToolbar
from fichero.windows.main.toolbars.preview_bottom_toolbar import PreviewBottomToolbar

logger = logging.getLogger(__name__)


class PreviewPane(BaseView):
    """
    Preview pane using the BaseView system for proper toolbar integration
    
    Supports Fichero's file types:
    - Input files (JPG, PDF, TIFF, HEIC, JXL)
    - Intermediate files (processed images)
    - Output files (transcribed text, Word docs)
    """
    
    def __init__(self, app, is_mobile: bool = False):
        """Initialize preview pane with BaseView system"""
        super().__init__(app, is_mobile)
        
        # Current file context
        self.current_file_path: Optional[str] = None
        self.current_file_type: str = "none"
        self.current_stage: str = "input"
        
        # Preview state
        self.zoom_level: float = 1.0
        self.view_mode: str = "fit"
        
        # Callbacks
        self.on_file_changed: Optional[Callable] = None
        
        # UI components (content area provided by BaseView)
        self.preview_widget: Optional[toga.Widget] = None
        self.placeholder_label: Optional[toga.Label] = None
        
        # Create toolbars
        self.top_toolbar = PreviewTopToolbar(app, is_mobile)
        self.bottom_toolbar = PreviewBottomToolbar(app, is_mobile)
        
        # Set both toolbars using BaseView system
        self.set_toolbars(self.top_toolbar, self.bottom_toolbar)
        
        # Create content
        self._create_content()
        
        logger.info("Preview pane created with BaseView integration")
    
    def _create_content(self):
        """Create the preview content using BaseView system"""
        try:
            # Create placeholder content
            self._create_placeholder()
            
            logger.debug("Preview pane content created successfully")
            
        except Exception as e:
            logger.error(f"Failed to create preview content: {e}")
    
    def _create_placeholder(self):
        """Create placeholder for when no file is selected"""
        try:
            # Clear existing content from the content container
            if self.content_container:
                for child in list(self.content_container.children):
                    self.content_container.remove(child)
            
            # Placeholder message
            self.placeholder_label = toga.Label(
                "Select a file to preview",
                style=Pack(
                    margin=(50, 20),
                    text_align="center",
                    font_size=16,
                    color="#999999"
                )
            )
            
            if self.content_container:
                self.content_container.add(self.placeholder_label)
            self.preview_widget = None
            
        except Exception as e:
            logger.error(f"Failed to create placeholder: {e}")
    
    def show_file(self, file_path: str, file_data: Dict[str, Any] = None):
        """
        Show a file in the preview pane
        
        Args:
            file_path: Path to the file to preview
            file_data: Additional file metadata
        """
        try:
            if not file_path:
                self._create_placeholder()
                return
            
            self.current_file_path = file_path
            
            # Detect file type and stage
            self.current_file_type = self._detect_file_type(file_path)
            self.current_stage = self._detect_workflow_stage(file_path, file_data)
            
            # Clear existing content
            if self.content_container:
                for child in list(self.content_container.children):
                    self.content_container.remove(child)
            
            # Create appropriate preview widget
            if self.current_file_type == "image":
                self._create_image_preview(file_path)
            elif self.current_file_type == "pdf":
                self._create_pdf_preview(file_path)
            elif self.current_file_type == "text":
                self._create_text_preview(file_path)
            elif self.current_file_type == "docx":
                self._create_document_preview(file_path)
            else:
                self._create_generic_preview(file_path)
            
            # Notify callbacks
            if self.on_file_changed:
                self.on_file_changed(file_path, self.current_file_type, self.current_stage)
            
            logger.info(f"Showing file preview: {file_path} ({self.current_file_type}, {self.current_stage})")
            
        except Exception as e:
            logger.error(f"Failed to show file: {e}")
            self._create_error_preview(str(e))
    
    def _detect_file_type(self, file_path: str) -> str:
        """Detect file type from extension"""
        if not file_path:
            return "none"
            
        ext = Path(file_path).suffix.lower()
        
        if ext in ['.jpg', '.jpeg', '.png', '.tiff', '.tif', '.heic', '.jxl']:
            return "image"
        elif ext == '.pdf':
            return "pdf"
        elif ext in ['.txt', '.md', '.text']:
            return "text"
        elif ext in ['.docx', '.doc']:
            return "docx"
        else:
            return "unknown"
    
    def _detect_workflow_stage(self, file_path: str, file_data: Dict = None) -> str:
        """
        Detect workflow stage based on file path patterns
        
        Fichero workflow stages:
        - input: Original scanned documents
        - intermediate: Processed (cropped, enhanced, split)
        - output: Final transcribed documents
        """
        if not file_path:
            return "input"
        
        path_lower = file_path.lower()
        
        # Check for intermediate processing indicators
        if any(keyword in path_lower for keyword in ['cropped', 'enhanced', 'split', 'processed', 'temp']):
            return "intermediate"
        
        # Check for output indicators
        if any(keyword in path_lower for keyword in ['output', 'transcribed', 'final', 'result']):
            return "output"
        
        # Default to input for original files
        return "input"
    
    def _create_image_preview(self, file_path: str):
        """Create image preview widget"""
        try:
            # For now, create a simple image view
            # TODO: Implement full image viewer with zoom, pan, rotate
            
            if Path(file_path).exists():
                logger.debug(f"Loading image preview for: {file_path}")
                
                # Create image widget with better styling
                self.preview_widget = toga.ImageView(
                    image=toga.Image(file_path),
                    style=Pack(
                        flex=1,
                        margin=(10, 10),
                        background_color="#F0F0F0"  # Light background to make image visible
                    )
                )
                if self.content_container:
                    self.content_container.add(self.preview_widget)
                logger.info(f"✅ Image preview created successfully: {Path(file_path).name}")
            else:
                logger.error(f"Image file not found: {file_path}")
                self._create_error_preview(f"Image file not found: {file_path}")
            
        except Exception as e:
            logger.error(f"Failed to create image preview: {e}")
            self._create_error_preview(f"Error loading image: {e}")
    
    def _create_pdf_preview(self, file_path: str):
        """Create PDF preview widget"""
        try:
            # For now, show PDF info
            # TODO: Implement PDF viewer or conversion to images
            
            info_text = f"PDF Document\n\nFile: {Path(file_path).name}\nPath: {file_path}\n\nPDF preview coming soon..."
            
            self.preview_widget = toga.MultilineTextInput(
                value=info_text,
                readonly=True,
                style=Pack(
                    flex=1,
                    margin=(10, 10),
                    font_family="monospace"
                )
            )
            if self.content_container:
                self.content_container.add(self.preview_widget)
            
        except Exception as e:
            logger.error(f"Failed to create PDF preview: {e}")
            self._create_error_preview(f"Error loading PDF: {e}")
    
    def _create_text_preview(self, file_path: str):
        """Create text file preview widget"""
        try:
            # Read and display text content
            if Path(file_path).exists():
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                except UnicodeDecodeError:
                    # Try with different encoding
                    with open(file_path, 'r', encoding='latin-1') as f:
                        content = f.read()
                
                self.preview_widget = toga.MultilineTextInput(
                    value=content,
                    readonly=True,
                    style=Pack(
                        flex=1,
                        margin=(10, 10),
                        font_family="monospace"
                    )
                )
                if self.content_container:
                    self.content_container.add(self.preview_widget)
            else:
                self._create_error_preview(f"Text file not found: {file_path}")
            
        except Exception as e:
            logger.error(f"Failed to create text preview: {e}")
            self._create_error_preview(f"Error loading text: {e}")
    
    def _create_document_preview(self, file_path: str):
        """Create Word document preview widget"""
        try:
            # For now, show document info
            # TODO: Implement document preview or conversion
            
            info_text = f"Word Document\n\nFile: {Path(file_path).name}\nPath: {file_path}\n\nDocument preview coming soon...\n\nThis would show:\n- Document text content\n- Images/tables\n- Formatting preview"
            
            self.preview_widget = toga.MultilineTextInput(
                value=info_text,
                readonly=True,
                style=Pack(
                    flex=1,
                    margin=(10, 10),
                    font_family="monospace"
                )
            )
            if self.content_container:
                self.content_container.add(self.preview_widget)
            
        except Exception as e:
            logger.error(f"Failed to create document preview: {e}")
            self._create_error_preview(f"Error loading document: {e}")
    
    def _create_generic_preview(self, file_path: str):
        """Create generic file preview"""
        try:
            file_info = f"File: {Path(file_path).name}\nType: {self.current_file_type}\nStage: {self.current_stage}\nPath: {file_path}\n\nUnsupported file type for preview."
            
            self.preview_widget = toga.MultilineTextInput(
                value=file_info,
                readonly=True,
                style=Pack(
                    flex=1,
                    margin=(10, 10),
                    font_family="monospace"
                )
            )
            if self.content_container:
                self.content_container.add(self.preview_widget)
            
        except Exception as e:
            logger.error(f"Failed to create generic preview: {e}")
    
    def _create_error_preview(self, error_message: str):
        """Create error preview widget"""
        try:
            error_text = f"Preview Error\n\n{error_message}"
            
            self.preview_widget = toga.Label(
                error_text,
                style=Pack(
                    margin=(20, 20),
                    text_align="center",
                    color="#cc0000"
                )
            )
            if self.content_container:
                self.content_container.add(self.preview_widget)
            
        except Exception as e:
            logger.error(f"Failed to create error preview: {e}")
    
    def clear_preview(self):
        """Clear the current preview"""
        self.current_file_path = None
        self.current_file_type = "none"
        self.current_stage = "input"
        self._create_placeholder()
    
    def get_container(self) -> toga.Box:
        """Get the preview pane container"""
        return self.container
    
    def get_current_file_info(self) -> Dict[str, Any]:
        """Get information about the currently previewed file"""
        return {
            "file_path": self.current_file_path,
            "file_type": self.current_file_type,
            "stage": self.current_stage,
            "zoom_level": self.zoom_level,
            "view_mode": self.view_mode
        }
    
    def set_zoom_level(self, zoom_level: float):
        """Set the zoom level for the preview"""
        self.zoom_level = zoom_level
        # TODO: Update preview widget zoom
        logger.debug(f"Zoom level set to: {zoom_level}")
    
    def set_view_mode(self, mode: str):
        """Set the view mode (fit, actual, custom)"""
        self.view_mode = mode
        # TODO: Update preview widget view mode
        logger.debug(f"View mode set to: {mode}")
    
    def register_file_change_callback(self, callback: Callable):
        """Register callback for when file changes"""
        self.on_file_changed = callback 