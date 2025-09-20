"""
Preview Bottom Toolbar for Fichero

Bottom toolbar for preview view with file type controls, zoom, and actions.
Supports different preview modes for Fichero's workflow stages.
"""

import toga
from toga.style import Pack
from toga.constants import ROW
import logging
from typing import Optional, Callable, Dict, Any

from fichero.shared.toolbars.bottom_toolbar import BottomToolbar

logger = logging.getLogger(__name__)


class PreviewPaneBottomToolbar(BottomToolbar):
    """
    Bottom toolbar for preview pane in main window with comprehensive file controls
    
    Supports:
    - Input files (JPG, PDF, TIFF)
    - Intermediate files (cropped, enhanced, split)  
    - Output files (transcribed text, Word docs)
    """
    
    def __init__(self, app, is_mobile: bool = None):
        """Initialize preview bottom toolbar"""
        super().__init__(app, is_mobile)
        
        # Current file context
        self.current_file_path: Optional[str] = None
        self.current_file_type: str = "unknown"  # image, pdf, text, docx
        self.current_stage: str = "input"  # input, intermediate, output
        
        # Preview state
        self.zoom_level: float = 1.0
        self.view_mode: str = "fit"  # fit, actual, custom
        
        # Preview-specific callbacks
        self.on_zoom_in: Optional[Callable] = None
        self.on_zoom_out: Optional[Callable] = None
        self.on_zoom_fit: Optional[Callable] = None
        self.on_zoom_actual: Optional[Callable] = None
        self.on_rotate_left: Optional[Callable] = None
        self.on_rotate_right: Optional[Callable] = None
        self.on_edit_file: Optional[Callable] = None
        self.on_open_external: Optional[Callable] = None
        self.on_show_metadata: Optional[Callable] = None
        self.on_compare_versions: Optional[Callable] = None
        self.on_export_file: Optional[Callable] = None
        
        # UI components
        self.file_type_label: Optional[toga.Label] = None
        self.zoom_label: Optional[toga.Label] = None
        
        # Create the toolbar content
        self._create_toolbar()
    
    def _create_toolbar(self):
        """Create the preview bottom toolbar with file controls"""
        try:
            # Call parent to set up basic structure
            super()._create_toolbar()
            
            # Left side: File info and type
            self._create_file_info_section()
            
            # Right side: Only the working button
            self._create_file_actions()
            
            logger.info("Preview bottom toolbar created successfully with working controls only")
            
        except Exception as e:
            logger.error(f"Failed to create preview bottom toolbar: {e}")
    
    def _create_file_info_section(self):
        """Create file type and stage information section"""
        try:
            # Don't add any file info to left side - keep it clean
            pass
            
        except Exception as e:
            logger.error(f"Failed to create file info section: {e}")
    
    def _create_file_actions(self):
        """Create file action buttons - empty for now to maintain toolbar height"""
        # Use the improved spacer method for consistent height
        self.add_spacer(height=30, flex=True)
    
    def update_file_context(self, file_path: str, file_type: str = None, stage: str = "input"):
        """
        Update the toolbar based on current file context
        
        Args:
            file_path: Path to the current file
            file_type: Type of file (image, pdf, text, docx)
            stage: Workflow stage (input, intermediate, output)
        """
        try:
            self.current_file_path = file_path
            self.current_stage = stage
            
            # Detect file type if not provided
            if file_type is None:
                file_type = self._detect_file_type(file_path)
            self.current_file_type = file_type
            
            # No UI labels to update - we removed them for cleaner design
            
            # Update button visibility based on file type
            self._update_button_visibility()
            
            logger.debug(f"Updated file context: {file_type} ({stage}) - {file_path}")
            
        except Exception as e:
            logger.error(f"Failed to update file context: {e}")
    
    def _detect_file_type(self, file_path: str) -> str:
        """Detect file type from extension"""
        if not file_path:
            return "unknown"
            
        ext = file_path.lower().split('.')[-1] if '.' in file_path else ""
        
        if ext in ['jpg', 'jpeg', 'png', 'tiff', 'tif', 'heic', 'jxl']:
            return "image"
        elif ext == 'pdf':
            return "pdf"
        elif ext in ['txt', 'md', 'text']:
            return "text"
        elif ext in ['docx', 'doc']:
            return "docx"
        else:
            return "unknown"
    
    def _update_button_visibility(self):
        """Update button visibility based on file type"""
        try:
            # Show/hide rotate buttons based on file type
            show_rotate = self.current_file_type in ["image", "pdf"]
            if hasattr(self, 'rotate_left_btn'):
                self.rotate_left_btn.enabled = show_rotate
            if hasattr(self, 'rotate_right_btn'):
                self.rotate_right_btn.enabled = show_rotate
            
            # Update edit button tooltip based on file type
            if hasattr(self, 'edit_btn'):
                if self.current_file_type == "image":
                    self.edit_btn.tooltip = "Edit Image"
                elif self.current_file_type == "text":
                    self.edit_btn.tooltip = "Edit Text"
                elif self.current_file_type == "docx":
                    self.edit_btn.tooltip = "Edit Document"
                else:
                    self.edit_btn.tooltip = "Edit File"
            
        except Exception as e:
            logger.error(f"Failed to update button visibility: {e}")
    
    def update_zoom_level(self, zoom_level: float):
        """Update the zoom level display"""
        try:
            self.zoom_level = zoom_level
            if self.zoom_label:
                self.zoom_label.text = f"{int(zoom_level * 100)}%"
        except Exception as e:
            logger.error(f"Failed to update zoom level: {e}")
    
    def set_view_mode(self, mode: str):
        """Set the current view mode"""
        self.view_mode = mode
        logger.debug(f"View mode set to: {mode}")
    
    # Event handlers
    def _on_zoom_in_clicked(self, widget):
        """Handle zoom in button click"""
        logger.debug("Zoom in clicked")
        if self.on_zoom_in:
            self.on_zoom_in()
    
    def _on_zoom_out_clicked(self, widget):
        """Handle zoom out button click"""
        logger.debug("Zoom out clicked")
        if self.on_zoom_out:
            self.on_zoom_out()
    
    def _on_zoom_fit_clicked(self, widget):
        """Handle fit to window button click"""
        logger.debug("Zoom fit clicked")
        if self.on_zoom_fit:
            self.on_zoom_fit()
    
    def _on_zoom_actual_clicked(self, widget):
        """Handle actual size button click"""
        logger.debug("Zoom actual clicked")
        if self.on_zoom_actual:
            self.on_zoom_actual()
    
    def _on_rotate_left_clicked(self, widget):
        """Handle rotate left button click"""
        logger.debug("Rotate left clicked")
        if self.on_rotate_left:
            self.on_rotate_left()
    
    def _on_rotate_right_clicked(self, widget):
        """Handle rotate right button click"""
        logger.debug("Rotate right clicked")
        if self.on_rotate_right:
            self.on_rotate_right()
    
    def _on_edit_file_clicked(self, widget):
        """Handle edit file button click"""
        logger.debug("Edit file clicked")
        if self.on_edit_file:
            self.on_edit_file()
    
    def _on_open_external_clicked(self, widget):
        """Handle open external button click"""
        logger.debug("Open external clicked")
        if self.on_open_external:
            self.on_open_external()
    
    def _on_show_metadata_clicked(self, widget):
        """Handle show metadata button click"""
        logger.debug("Show metadata clicked")
        if self.on_show_metadata:
            self.on_show_metadata()
    
    def _on_preview_clicked(self, widget):
        """Handle preview button click - simple implementation"""
        logger.info("Preview button clicked")
    
    def register_callbacks(self, 
                         on_settings: Optional[Callable] = None,
                         on_about: Optional[Callable] = None,
                         on_help: Optional[Callable] = None,
                         # Zoom callbacks
                         on_zoom_in: Optional[Callable] = None,
                         on_zoom_out: Optional[Callable] = None,
                         on_zoom_fit: Optional[Callable] = None,
                         on_zoom_actual: Optional[Callable] = None,
                         # Image callbacks
                         on_rotate_left: Optional[Callable] = None,
                         on_rotate_right: Optional[Callable] = None,
                         # File callbacks
                         on_edit_file: Optional[Callable] = None,
                         on_open_external: Optional[Callable] = None,
                         on_show_metadata: Optional[Callable] = None,
                         on_compare_versions: Optional[Callable] = None,
                         on_export_file: Optional[Callable] = None):
        """Register callbacks for preview bottom toolbar actions"""
        super().register_callbacks(on_settings, on_about, on_help)
        
        # Zoom callbacks
        self.on_zoom_in = on_zoom_in
        self.on_zoom_out = on_zoom_out
        self.on_zoom_fit = on_zoom_fit
        self.on_zoom_actual = on_zoom_actual
        
        # Image callbacks
        self.on_rotate_left = on_rotate_left
        self.on_rotate_right = on_rotate_right
        
        # File callbacks
        self.on_edit_file = on_edit_file
        self.on_open_external = on_open_external
        self.on_show_metadata = on_show_metadata
        self.on_compare_versions = on_compare_versions
        self.on_export_file = on_export_file
        
        logger.debug("Preview bottom toolbar callbacks registered")