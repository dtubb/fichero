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

from fichero.windows.main.toolbars.bottom_toolbar import BottomToolbar

logger = logging.getLogger(__name__)


class PreviewBottomToolbar(BottomToolbar):
    """
    Bottom toolbar for preview view with comprehensive file controls
    
    Supports:
    - Input files (JPG, PDF, TIFF)
    - Intermediate files (cropped, enhanced, split)  
    - Output files (transcribed text, Word docs)
    """
    
    def __init__(self, app, is_mobile: bool = False):
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
            # Left side: File info and type
            self._create_file_info_section()
            
            # Center: Zoom and view controls
            self._create_zoom_controls()
            
            # Right side: File actions
            self._create_file_actions()
            
            logger.info("Preview bottom toolbar created successfully with file controls")
            
        except Exception as e:
            logger.error(f"Failed to create preview bottom toolbar: {e}")
    
    def _create_file_info_section(self):
        """Create file type and stage information section"""
        try:
            # File type indicator
            self.file_type_label = toga.Label(
                "No file",
                style=Pack(
                    margin=(4, 8),
                    font_size=12,
                    color="#666666"
                )
            )
            self.add_to_left(self.file_type_label)
            
            # Stage indicator (for Fichero workflow)
            self.stage_label = toga.Label(
                "",
                style=Pack(
                    margin=(4, 8),
                    font_size=11,
                    color="#888888"
                )
            )
            self.add_to_left(self.stage_label)
            
        except Exception as e:
            logger.error(f"Failed to create file info section: {e}")
    
    def _create_zoom_controls(self):
        """Create zoom and view controls"""
        try:
            # Zoom out button
            zoom_out_btn = self.create_icon_button(
                button_id="zoom_out",
                icon="minus",
                on_press=self._on_zoom_out_clicked,
                tooltip="Zoom Out"
            )
            self.add_to_center(zoom_out_btn)
            
            # Zoom level display
            self.zoom_label = toga.Label(
                "100%",
                style=Pack(
                    margin=(4, 12),
                    font_size=12,
                    color="#333333"
                )
            )
            self.add_to_center(self.zoom_label)
            
            # Zoom in button
            zoom_in_btn = self.create_icon_button(
                button_id="zoom_in",
                icon="plus",
                on_press=self._on_zoom_in_clicked,
                tooltip="Zoom In"
            )
            self.add_to_center(zoom_in_btn)
            
            # Fit to window button
            fit_btn = self.create_icon_button(
                button_id="zoom_fit",
                icon="fit_window",
                on_press=self._on_zoom_fit_clicked,
                tooltip="Fit to Window"
            )
            self.add_to_center(fit_btn)
            
            # Actual size button
            actual_btn = self.create_icon_button(
                button_id="zoom_actual",
                icon="actual_size",
                on_press=self._on_zoom_actual_clicked,
                tooltip="Actual Size"
            )
            self.add_to_center(actual_btn)
            
        except Exception as e:
            logger.error(f"Failed to create zoom controls: {e}")
    
    def _create_file_actions(self):
        """Create file action buttons (context-sensitive)"""
        try:
            # Rotate buttons (for images)
            self.rotate_left_btn = self.create_icon_button(
                button_id="rotate_left",
                icon="rotate_left",
                on_press=self._on_rotate_left_clicked,
                tooltip="Rotate Left"
            )
            self.add_to_right(self.rotate_left_btn)
            
            self.rotate_right_btn = self.create_icon_button(
                button_id="rotate_right", 
                icon="rotate_right",
                on_press=self._on_rotate_right_clicked,
                tooltip="Rotate Right"
            )
            self.add_to_right(self.rotate_right_btn)
            
            # Edit button (context-sensitive)
            self.edit_btn = self.create_icon_button(
                button_id="edit_file",
                icon="edit",
                on_press=self._on_edit_file_clicked,
                tooltip="Edit File"
            )
            self.add_to_right(self.edit_btn)
            
            # Open external button
            self.external_btn = self.create_icon_button(
                button_id="open_external",
                icon="external_link",
                on_press=self._on_open_external_clicked,
                tooltip="Open in External App"
            )
            self.add_to_right(self.external_btn)
            
            # Metadata/info button
            self.info_btn = self.create_icon_button(
                button_id="show_metadata",
                icon="info",
                on_press=self._on_show_metadata_clicked,
                tooltip="Show File Info"
            )
            self.add_to_right(self.info_btn)
            
        except Exception as e:
            logger.error(f"Failed to create file actions: {e}")
    
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
            
            # Update file type display
            if self.file_type_label:
                type_text = f"{file_type.upper()}"
                self.file_type_label.text = type_text
            
            # Update stage display
            if hasattr(self, 'stage_label') and self.stage_label:
                stage_text = f"({stage.title()})"
                self.stage_label.text = stage_text
            
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