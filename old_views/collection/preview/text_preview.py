"""
Text Preview Component

Text content preview with syntax highlighting and editing support.
Handles transcriptions, text files, and other text content.
"""

import toga
from toga.style import Pack
from toga.constants import COLUMN, ROW
import logging
from typing import Optional, Callable
from pathlib import Path
import mimetypes

logger = logging.getLogger(__name__)


class TextPreview:
    """Text content preview with syntax highlighting and editing"""
    
    def __init__(self, presenter, width=300, is_mobile=False):
        self.presenter = presenter
        self.width = width
        self.is_mobile = is_mobile
        
        # Text state
        self.current_file_path: Optional[Path] = None
        self.current_content: str = ""
        self.is_editable: bool = False
        self.is_modified: bool = False
        
        # UI components
        self.container = None
        self.header = None
        self.text_editor = None
        self.toolbar = None
        self.save_button = None
        self.copy_button = None
        
        # Callbacks
        self.on_content_change: Optional[Callable[[str], None]] = None
        self.on_save: Optional[Callable[[Path, str], None]] = None
        
        self._create_ui()
    
    def _create_ui(self):
        """Create text preview UI"""
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
        
        # Header with file info
        self.header = toga.Label(
            "Text Preview",
            style=Pack(font_size=12, font_weight="bold", margin_bottom=5)
        )
        self.container.add(self.header)
        
        # Toolbar for actions
        self.toolbar = toga.Box(style=Pack(direction=ROW, margin_bottom=5))
        
        self.copy_button = toga.Button(
            "Copy",
            on_press=self._copy_content,
            style=Pack(margin_right=5)
        )
        self.toolbar.add(self.copy_button)
        
        self.save_button = toga.Button(
            "Save",
            on_press=self._save_content,
            style=Pack(margin_right=5)
        )
        self.save_button.enabled = False  # Initially disabled
        self.toolbar.add(self.save_button)
        
        self.container.add(self.toolbar)
        
        # Text editor (read-only initially)
        self.text_editor = toga.MultilineTextInput(
            readonly=True,  # Start as read-only
            style=Pack(flex=1, font_family="monospace", font_size=11)
        )
        self.container.add(self.text_editor)
        
        # Show placeholder
        self._show_placeholder()
    
    def _show_placeholder(self):
        """Show placeholder content"""
        self.header.text = "Text Preview"
        self.text_editor.value = "Select a text file or transcription to preview"
        self.text_editor.readonly = True
        self.save_button.enabled = False
        self.copy_button.enabled = False
    
    def show_text_file(self, file_path: Path, editable: bool = False):
        """Show text file content"""
        try:
            self.current_file_path = file_path
            self.is_editable = editable
            
            # Read file content
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            self.current_content = content
            self.is_modified = False
            
            # Update UI
            self.header.text = f"Text: {file_path.name}"
            self.text_editor.value = content
            self.text_editor.readonly = not editable
            self.save_button.enabled = False
            self.copy_button.enabled = True
            
            # Set up change handler if editable
            if editable:
                self.text_editor.on_change = self._on_text_change
            
            logger.info(f"Showing text file: {file_path.name}")
            
        except Exception as e:
            logger.error(f"Failed to show text file: {e}")
            self._show_error(f"Failed to load text file: {file_path.name}")
    
    def show_transcription(self, transcription_path: Path, editable: bool = True):
        """Show transcription content (usually editable)"""
        try:
            self.current_file_path = transcription_path
            self.is_editable = editable
            
            # Read transcription content
            with open(transcription_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            self.current_content = content
            self.is_modified = False
            
            # Update UI
            self.header.text = f"Transcription: {transcription_path.name}"
            self.text_editor.value = content
            self.text_editor.readonly = not editable
            self.save_button.enabled = False
            self.copy_button.enabled = True
            
            # Set up change handler if editable
            if editable:
                self.text_editor.on_change = self._on_text_change
            
            logger.info(f"Showing transcription: {transcription_path.name}")
            
        except Exception as e:
            logger.error(f"Failed to show transcription: {e}")
            self._show_error(f"Failed to load transcription: {transcription_path.name}")
    
    def show_text_content(self, content: str, title: str = "Text Content", editable: bool = False):
        """Show arbitrary text content"""
        try:
            self.current_file_path = None
            self.current_content = content
            self.is_editable = editable
            self.is_modified = False
            
            # Update UI
            self.header.text = title
            self.text_editor.value = content
            self.text_editor.readonly = not editable
            self.save_button.enabled = False
            self.copy_button.enabled = True
            
            # Set up change handler if editable
            if editable:
                self.text_editor.on_change = self._on_text_change
            
            logger.info(f"Showing text content: {title}")
            
        except Exception as e:
            logger.error(f"Failed to show text content: {e}")
            self._show_error("Failed to display text content")
    
    def _on_text_change(self, widget):
        """Handle text content changes"""
        try:
            new_content = self.text_editor.value
            if new_content != self.current_content:
                self.is_modified = True
                self.save_button.enabled = True
                
                # Notify callback
                if self.on_content_change:
                    self.on_content_change(new_content)
                
                logger.debug("Text content modified")
            
        except Exception as e:
            logger.error(f"Failed to handle text change: {e}")
    
    def _copy_content(self, widget):
        """Copy content to clipboard"""
        try:
            content = self.text_editor.value
            if content:
                # Toga clipboard support
                app = toga.App.app
                if app and hasattr(app, 'clipboard'):
                    app.clipboard.set_text(content)
                    logger.info("Content copied to clipboard")
                else:
                    logger.warning("Clipboard not available")
            
        except Exception as e:
            logger.error(f"Failed to copy content: {e}")
    
    def _save_content(self, widget):
        """Save modified content"""
        try:
            if not self.is_modified:
                return
            
            new_content = self.text_editor.value
            
            # Save to file if we have a file path
            if self.current_file_path:
                with open(self.current_file_path, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                
                self.current_content = new_content
                self.is_modified = False
                self.save_button.enabled = False
                
                logger.info(f"Content saved to: {self.current_file_path}")
                
                # Notify callback
                if self.on_save:
                    self.on_save(self.current_file_path, new_content)
            else:
                logger.warning("No file path available for saving")
            
        except Exception as e:
            logger.error(f"Failed to save content: {e}")
            self._show_error("Failed to save content")
    
    def _show_error(self, message: str):
        """Show error message"""
        self.header.text = "Error"
        self.text_editor.value = message
        self.text_editor.readonly = True
        self.save_button.enabled = False
        self.copy_button.enabled = False
    
    def set_syntax_highlighting(self, language: str):
        """Set syntax highlighting for the text editor"""
        # Note: Toga doesn't have built-in syntax highlighting yet
        # This is a placeholder for future implementation
        logger.info(f"Syntax highlighting requested for: {language}")
    
    def get_content(self) -> str:
        """Get current text content"""
        return self.text_editor.value
    
    def is_content_modified(self) -> bool:
        """Check if content has been modified"""
        return self.is_modified
    
    def clear(self):
        """Clear the preview"""
        self.current_file_path = None
        self.current_content = ""
        self.is_editable = False
        self.is_modified = False
        self._show_placeholder()
    
    def make_editable(self, editable: bool = True):
        """Make the text editor editable or read-only"""
        self.is_editable = editable
        self.text_editor.readonly = not editable
        
        if editable:
            self.text_editor.on_change = self._on_text_change
        else:
            self.text_editor.on_change = None
            self.save_button.enabled = False 