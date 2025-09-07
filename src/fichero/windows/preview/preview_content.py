"""
Preview Content - Shared Component

Shared preview content component used by both desktop window and mobile view.
Handles file preview and editing capabilities for multiple file types.
"""

import logging
import subprocess
import platform
from typing import Optional
import toga
from toga.style import Pack
from toga.constants import COLUMN, ROW
from pathlib import Path

logger = logging.getLogger(__name__)


class PreviewContent:
    """Shared preview content component"""
    
    def __init__(self, app, file_path=None, **kwargs):
        """Initialize the preview content"""
        self.app = app
        self.file_path = file_path
        self.kwargs = kwargs
        
        # Preview widgets
        self.main_container = None
        self.content_area = None
        self.file_info_label = None
        
        logger.info(f"PreviewContent initialized for: {file_path or 'no file'}")
    
    def create(self):
        """Create the preview content widget"""
        try:
            # Main container
            self.main_container = toga.Box(
                style=Pack(
                    direction=COLUMN,
                    flex=1,
                    margin=10
                )
            )
            
            # Header with file info and actions
            header = self._create_header()
            self.main_container.add(header)
            
            # Content area
            self.content_area = toga.Box(
                style=Pack(
                    direction=COLUMN,
                    flex=1,
                    margin=(10, 0)
                )
            )
            self.main_container.add(self.content_area)
            
            # Load initial content
            self._load_content()
            
            logger.info("Preview content created")
            return self.main_container
            
        except Exception as e:
            logger.error(f"Failed to create preview content: {e}")
            return self._create_error_content(str(e))
    
    def _create_header(self):
        """Create the header with file info and actions"""
        header = toga.Box(
            style=Pack(
                direction=ROW,
                margin=(0, 0, 10, 0)
            )
        )
        
        # File info
        if self.file_path:
            file_name = Path(self.file_path).name
            file_size = self._get_file_size()
            info_text = f"📄 {file_name} ({file_size})"
        else:
            info_text = "📄 No file selected"
        
        self.file_info_label = toga.Label(
            info_text,
            style=Pack(
                flex=1,
                font_size=14,
                font_weight='bold',
                margin=(0, 10, 0, 0)
            )
        )
        header.add(self.file_info_label)
        
        # Action buttons
        if self.file_path:
            # Open in system app button
            open_button = toga.Button(
                "Open with System App",
                on_press=self._on_open_system,
                style=Pack(margin=(0, 5, 0, 0))
            )
            header.add(open_button)
            
            # Edit button (for text files)
            if self._is_text_file():
                edit_button = toga.Button(
                    "Edit",
                    on_press=self._on_edit,
                    style=Pack(margin=(0, 5, 0, 0))
                )
                header.add(edit_button)
        
        return header
    
    def _load_content(self):
        """Load and display file content"""
        try:
            # Clear existing content
            self.content_area.clear()
            
            if not self.file_path:
                self._show_no_file_message()
                return
            
            file_path = Path(self.file_path)
            
            if not file_path.exists():
                self._show_error_message(f"File not found: {self.file_path}")
                return
            
            # Handle different file types
            if self._is_image_file():
                self._load_image_content()
            elif self._is_text_file():
                self._load_text_content()
            else:
                self._show_file_info()
                
        except Exception as e:
            logger.error(f"Failed to load content: {e}")
            self._show_error_message(f"Failed to load file: {e}")
    
    def _is_image_file(self) -> bool:
        """Check if file is an image"""
        if not self.file_path:
            return False
        
        image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp'}
        return Path(self.file_path).suffix.lower() in image_extensions
    
    def _is_text_file(self) -> bool:
        """Check if file is text-based"""
        if not self.file_path:
            return False
        
        text_extensions = {'.txt', '.md', '.py', '.js', '.html', '.css', '.json', '.xml', '.yml', '.yaml'}
        return Path(self.file_path).suffix.lower() in text_extensions
    
    def _load_image_content(self):
        """Load and display image content"""
        try:
            # For now, show image info - Toga doesn't have built-in image display
            # In a real implementation, you might use a WebView or platform-specific component
            info_box = toga.Box(
                style=Pack(
                    direction=COLUMN,
                    margin=20,
                    alignment='center'
                )
            )
            
            # Image icon
            icon_label = toga.Label(
                "🖼️",
                style=Pack(
                    font_size=48,
                    text_align='center',
                    margin=(0, 0, 10, 0)
                )
            )
            info_box.add(icon_label)
            
            # Image info
            file_path = Path(self.file_path)
            info_label = toga.Label(
                f"Image File\n{file_path.name}\n\nUse 'Open with System App' to view the image",
                style=Pack(
                    text_align='center',
                    margin=10
                )
            )
            info_box.add(info_label)
            
            self.content_area.add(info_box)
            
        except Exception as e:
            logger.error(f"Failed to load image content: {e}")
            self._show_error_message(f"Failed to load image: {e}")
    
    def _load_text_content(self):
        """Load and display text content"""
        try:
            file_path = Path(self.file_path)
            
            # Read file content
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
            except UnicodeDecodeError:
                # Try with different encoding
                with open(file_path, 'r', encoding='latin-1') as f:
                    content = f.read()
            
            # Limit content size for display
            if len(content) > 10000:
                content = content[:10000] + "\n\n... (content truncated)"
            
            # Create text area
            text_area = toga.MultilineTextInput(
                value=content,
                readonly=True,
                style=Pack(
                    flex=1,
                    margin=5
                )
            )
            
            self.content_area.add(text_area)
            
        except Exception as e:
            logger.error(f"Failed to load text content: {e}")
            self._show_error_message(f"Failed to load text file: {e}")
    
    def _show_file_info(self):
        """Show general file information"""
        try:
            file_path = Path(self.file_path)
            
            info_box = toga.Box(
                style=Pack(
                    direction=COLUMN,
                    margin=20,
                    alignment='center'
                )
            )
            
            # File icon based on type
            file_type = self._get_file_type_icon()
            icon_label = toga.Label(
                file_type,
                style=Pack(
                    font_size=48,
                    text_align='center',
                    margin=(0, 0, 10, 0)
                )
            )
            info_box.add(icon_label)
            
            # File details
            file_size = self._get_file_size()
            file_type_text = file_path.suffix.upper()[1:] if file_path.suffix else "Unknown"
            
            details = f"""File: {file_path.name}
Type: {file_type_text} File
Size: {file_size}
Location: {file_path.parent}

Use 'Open with System App' to view this file."""
            
            details_label = toga.Label(
                details,
                style=Pack(
                    text_align='center',
                    margin=10
                )
            )
            info_box.add(details_label)
            
            self.content_area.add(info_box)
            
        except Exception as e:
            logger.error(f"Failed to show file info: {e}")
            self._show_error_message(f"Failed to show file info: {e}")
    
    def _get_file_type_icon(self) -> str:
        """Get appropriate icon for file type"""
        if not self.file_path:
            return "📄"
        
        suffix = Path(self.file_path).suffix.lower()
        
        # Icon mapping
        icon_map = {
            '.jpg': '🖼️', '.jpeg': '🖼️', '.png': '🖼️', '.gif': '🖼️',
            '.txt': '📄', '.md': '📝', '.py': '🐍', '.js': '📜',
            '.pdf': '📕', '.doc': '📘', '.docx': '📘',
            '.mp3': '🎵', '.wav': '🎵', '.mp4': '🎬', '.mov': '🎬',
            '.zip': '🗜️', '.rar': '🗜️', '.tar': '🗜️'
        }
        
        return icon_map.get(suffix, '📄')
    
    def _get_file_size(self) -> str:
        """Get human-readable file size"""
        try:
            if not self.file_path:
                return "Unknown"
            
            size = Path(self.file_path).stat().st_size
            
            for unit in ['B', 'KB', 'MB', 'GB']:
                if size < 1024:
                    return f"{size:.1f} {unit}"
                size /= 1024
            
            return f"{size:.1f} TB"
            
        except Exception:
            return "Unknown"
    
    def _show_no_file_message(self):
        """Show message when no file is selected"""
        message_box = toga.Box(
            style=Pack(
                direction=COLUMN,
                margin=50,
                alignment='center'
            )
        )
        
        icon_label = toga.Label(
            "📂",
            style=Pack(
                font_size=64,
                text_align='center',
                margin=(0, 0, 20, 0)
            )
        )
        message_box.add(icon_label)
        
        message_label = toga.Label(
            "No file selected for preview.\n\nSelect a file from the collection to preview it here.",
            style=Pack(
                text_align='center',
                font_size=16,
                margin=20
            )
        )
        message_box.add(message_label)
        
        self.content_area.add(message_box)
    
    def _show_error_message(self, message: str):
        """Show error message"""
        error_box = toga.Box(
            style=Pack(
                direction=COLUMN,
                margin=20,
                alignment='center'
            )
        )
        
        icon_label = toga.Label(
            "⚠️",
            style=Pack(
                font_size=48,
                text_align='center',
                margin=(0, 0, 10, 0)
            )
        )
        error_box.add(icon_label)
        
        error_label = toga.Label(
            message,
            style=Pack(
                text_align='center',
                margin=10
            )
        )
        error_box.add(error_label)
        
        self.content_area.add(error_box)
    
    def _create_error_content(self, error_message: str):
        """Create error content widget"""
        error_container = toga.Box(
            style=Pack(direction=COLUMN, margin=20)
        )
        
        error_label = toga.Label(
            f"Error creating preview: {error_message}",
            style=Pack(margin=10, text_align='center')
        )
        error_container.add(error_label)
        
        return error_container
    
    def _on_open_system(self, widget):
        """Open file with system default application"""
        try:
            if not self.file_path:
                return
            
            file_path = Path(self.file_path)
            if not file_path.exists():
                logger.error(f"File not found: {self.file_path}")
                return
            
            # Platform-specific file opening
            system = platform.system()
            if system == "Darwin":  # macOS
                subprocess.run(["open", str(file_path)])
            elif system == "Windows":
                subprocess.run(["start", str(file_path)], shell=True)
            else:  # Linux
                subprocess.run(["xdg-open", str(file_path)])
            
            logger.info(f"Opened file with system app: {self.file_path}")
            
        except Exception as e:
            logger.error(f"Failed to open file with system app: {e}")
    
    def _on_edit(self, widget):
        """Open file for editing"""
        try:
            if not self.file_path:
                return
            
            # For now, just open with system app
            # In the future, could integrate a text editor
            self._on_open_system(widget)
            
            logger.info(f"Edit requested for: {self.file_path}")
            
        except Exception as e:
            logger.error(f"Failed to edit file: {e}")
    
    def update_file(self, file_path):
        """Update the preview to show a different file"""
        try:
            self.file_path = file_path
            
            # Update header
            if self.file_info_label:
                if file_path:
                    file_name = Path(file_path).name
                    file_size = self._get_file_size()
                    self.file_info_label.text = f"📄 {file_name} ({file_size})"
                else:
                    self.file_info_label.text = "📄 No file selected"
            
            # Reload content
            self._load_content()
            
            logger.info(f"Preview updated for: {file_path}")
            
        except Exception as e:
            logger.error(f"Failed to update preview: {e}")
    
    def show(self):
        """Show callback"""
        pass
    
    def cleanup(self):
        """Cleanup resources"""
        pass 