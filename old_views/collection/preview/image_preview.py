"""
Image Preview Component

Full-size image preview with zoom and navigation support.
Uses WebView for better image handling and zoom capabilities.
"""

import toga
from toga.style import Pack
from toga.constants import COLUMN, ROW
import logging
from typing import Optional, List, Callable
from pathlib import Path
import base64
import mimetypes

logger = logging.getLogger(__name__)


class ImagePreview:
    """Full-size image preview with zoom and navigation"""
    
    def __init__(self, presenter, width=300, is_mobile=False):
        self.presenter = presenter
        self.width = width
        self.is_mobile = is_mobile
        
        # Image state
        self.current_image_path: Optional[Path] = None
        self.image_list: List[Path] = []
        self.current_image_index = 0
        
        # UI components
        self.container = None
        self.webview = None
        self.nav_controls = None
        self.prev_button = None
        self.next_button = None
        self.image_counter = None
        
        # Callbacks
        self.on_image_change: Optional[Callable[[Path], None]] = None
        
        self._create_ui()
    
    def _create_ui(self):
        """Create image preview UI with WebView"""
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
        
        # Image display area (WebView for zoom support)
        self.webview = toga.WebView(
            style=Pack(flex=1, margin_bottom=10)
        )
        self.container.add(self.webview)
        
        # Navigation controls
        self.nav_controls = toga.Box(style=Pack(direction=ROW, margin_top=5))
        
        self.prev_button = toga.Button(
            "◀ Previous",
            on_press=self._show_previous_image,
            style=Pack(margin_right=10)
        )
        self.nav_controls.add(self.prev_button)
        
        # Image counter
        self.image_counter = toga.Label(
            "",
            style=Pack(flex=1, text_align="center", margin_top=5)
        )
        self.nav_controls.add(self.image_counter)
        
        self.next_button = toga.Button(
            "Next ▶",
            on_press=self._show_next_image,
            style=Pack(margin_left=10)
        )
        self.nav_controls.add(self.next_button)
        
        # Initially hide navigation
        self.nav_controls.style.visibility = "hidden"
        self.container.add(self.nav_controls)
        
        # Show placeholder
        self._show_placeholder()
    
    def _show_placeholder(self):
        """Show placeholder content"""
        placeholder_html = """
        <html>
        <head>
            <style>
                body { 
                    font-family: -apple-system, BlinkMacSystemFont, sans-serif;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    height: 100vh;
                    margin: 0;
                    background: #f5f5f5;
                    color: #666;
                }
                .placeholder {
                    text-align: center;
                    padding: 20px;
                }
            </style>
        </head>
        <body>
            <div class="placeholder">
                <h3>Image Preview</h3>
                <p>Select an image to preview</p>
            </div>
        </body>
        </html>
        """
        self.webview.set_content("", placeholder_html)
    
    def show_image(self, image_path: Path, image_list: Optional[List[Path]] = None):
        """Show image with full-size preview and zoom support"""
        try:
            self.current_image_path = image_path
            
            # Build or use provided image list
            if image_list:
                self.image_list = image_list
            else:
                self._build_image_list(image_path)
            
            # Find current image index
            self.current_image_index = 0
            for i, img_path in enumerate(self.image_list):
                if img_path == image_path:
                    self.current_image_index = i
                    break
            
            # Display the image
            self._display_current_image()
            
            # Notify callback
            if self.on_image_change:
                self.on_image_change(image_path)
            
            logger.info(f"Showing image preview: {image_path.name}")
            
        except Exception as e:
            logger.error(f"Failed to show image: {e}")
            self._show_error(f"Failed to load image: {image_path.name}")
    
    def _build_image_list(self, current_image_path: Path):
        """Build list of all images in the current folder"""
        try:
            folder_path = current_image_path.parent
            self.image_list = []
            
            # Get all image files in the folder
            for file_path in folder_path.iterdir():
                if file_path.is_file() and self._is_image_file(file_path):
                    self.image_list.append(file_path)
            
            # Sort by name for consistent order
            self.image_list.sort(key=lambda p: p.name.lower())
            
            logger.info(f"Found {len(self.image_list)} images in folder")
            
        except Exception as e:
            logger.error(f"Failed to build image list: {e}")
            self.image_list = [current_image_path]  # Fallback
    
    def _is_image_file(self, file_path: Path) -> bool:
        """Check if file is a supported image type"""
        image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tif', '.tiff', '.webp'}
        return file_path.suffix.lower() in image_extensions
    
    def _display_current_image(self):
        """Display current image with zoom support"""
        try:
            if not self.image_list or self.current_image_index >= len(self.image_list):
                return
            
            current_path = self.image_list[self.current_image_index]
            
            # Create HTML with zoom support
            html_content = self._create_image_html(current_path)
            self.webview.set_content("", html_content)
            
            # Update navigation controls
            self._update_navigation_controls()
            
        except Exception as e:
            logger.error(f"Failed to display image: {e}")
            self._show_error(f"Failed to display image")
    
    def _create_image_html(self, image_path: Path) -> str:
        """Create HTML content for image with zoom support"""
        try:
            # Read image as base64
            with open(image_path, 'rb') as f:
                image_data = f.read()
                image_base64 = base64.b64encode(image_data).decode('utf-8')
            
            # Determine MIME type
            mime_type, _ = mimetypes.guess_type(str(image_path))
            if not mime_type:
                mime_type = 'image/jpeg'  # Default
            
            # Create responsive HTML with zoom support
            html = f"""
            <html>
            <head>
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <style>
                    body {{
                        margin: 0;
                        padding: 10px;
                        background: #1a1a1a;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        min-height: 100vh;
                        font-family: -apple-system, BlinkMacSystemFont, sans-serif;
                    }}
                    .image-container {{
                        max-width: 100%;
                        max-height: 100vh;
                        text-align: center;
                        position: relative;
                    }}
                    .image {{
                        max-width: 100%;
                        max-height: 80vh;
                        object-fit: contain;
                        border-radius: 8px;
                        box-shadow: 0 4px 20px rgba(0,0,0,0.3);
                        cursor: zoom-in;
                        transition: transform 0.2s ease;
                    }}
                    .image:hover {{
                        transform: scale(1.02);
                    }}
                    .image.zoomed {{
                        cursor: zoom-out;
                        transform: scale(2.5);
                    }}
                    .image.zoomed-more {{
                        cursor: zoom-out;
                        transform: scale(4);
                    }}
                    .image.zoomed-max {{
                        cursor: zoom-out;
                        transform: scale(6);
                    }}
                </style>
                <script>
                    let zoomLevel = 0;
                    const maxZoomLevel = 3;
                    
                    function cycleZoom() {{
                        const img = document.querySelector('.image');
                        
                        // Remove all zoom classes
                        img.classList.remove('zoomed', 'zoomed-more', 'zoomed-max');
                        
                        // Cycle through zoom levels
                        zoomLevel = (zoomLevel + 1) % (maxZoomLevel + 1);
                        
                        if (zoomLevel === 1) {{
                            img.classList.add('zoomed');
                        }} else if (zoomLevel === 2) {{
                            img.classList.add('zoomed-more');
                        }} else if (zoomLevel === 3) {{
                            img.classList.add('zoomed-max');
                        }}
                    }}
                    
                    // Keyboard navigation
                    document.addEventListener('keydown', function(e) {{
                        if (e.key === 'ArrowLeft') {{
                            window.webkit.messageHandlers.previousImage.postMessage('previous');
                        }} else if (e.key === 'ArrowRight') {{
                            window.webkit.messageHandlers.nextImage.postMessage('next');
                        }} else if (e.key === 'Escape') {{
                            window.webkit.messageHandlers.closePreview.postMessage('close');
                        }} else if (e.key === 'z' || e.key === 'Z') {{
                            cycleZoom();
                        }}
                    }});
                    
                    // Click to cycle zoom
                    document.addEventListener('click', function(e) {{
                        if (e.target.classList.contains('image')) {{
                            cycleZoom();
                        }}
                    }});
                </script>
            </head>
            <body>
                <div class="image-container">
                    <img src="data:{mime_type};base64,{image_base64}" 
                         alt="{image_path.name}" 
                         class="image"
                         title="Click to cycle zoom • Z key to zoom • Arrow keys to navigate">
                </div>
            </body>
            </html>
            """
            
            return html
            
        except Exception as e:
            logger.error(f"Failed to create image HTML: {e}")
            return self._create_error_html(f"Failed to load image: {image_path.name}")
    
    def _format_file_size(self, file_path: Path) -> str:
        """Format file size for display"""
        try:
            size_bytes = file_path.stat().st_size
            if size_bytes < 1024:
                return f"{size_bytes} B"
            elif size_bytes < 1024 * 1024:
                return f"{size_bytes / 1024:.1f} KB"
            else:
                return f"{size_bytes / (1024 * 1024):.1f} MB"
        except:
            return "Unknown size"
    
    def _create_error_html(self, message: str) -> str:
        """Create error HTML"""
        return f"""
        <html>
        <head>
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, sans-serif;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    height: 100vh;
                    margin: 0;
                    background: #1a1a1a;
                    color: #ff6b6b;
                }}
                .error {{
                    text-align: center;
                    padding: 20px;
                }}
            </style>
        </head>
        <body>
            <div class="error">
                <h3>Error</h3>
                <p>{message}</p>
            </div>
        </body>
        </html>
        """
    
    def _show_error(self, message: str):
        """Show error message"""
        error_html = self._create_error_html(message)
        self.webview.set_content("", error_html)
    
    def _update_navigation_controls(self):
        """Update navigation controls visibility and state"""
        try:
            if len(self.image_list) > 1:
                # Show navigation controls
                self.nav_controls.style.visibility = "visible"
                
                # Update counter
                self.image_counter.text = f"{self.current_image_index + 1} of {len(self.image_list)}"
                
                # Enable/disable buttons
                self.prev_button.enabled = self.current_image_index > 0
                self.next_button.enabled = self.current_image_index < len(self.image_list) - 1
            else:
                # Hide navigation if only one image
                self.nav_controls.style.visibility = "hidden"
                
        except Exception as e:
            logger.error(f"Failed to update navigation controls: {e}")
    
    def _show_previous_image(self, widget):
        """Show previous image"""
        if self.current_image_index > 0:
            self.current_image_index -= 1
            self._display_current_image()
            logger.info(f"Previous image: {self.current_image_index + 1} of {len(self.image_list)}")
    
    def _show_next_image(self, widget):
        """Show next image"""
        if self.current_image_index < len(self.image_list) - 1:
            self.current_image_index += 1
            self._display_current_image()
            logger.info(f"Next image: {self.current_image_index + 1} of {len(self.image_list)}")
    
    # Keyboard navigation support
    def handle_key_left(self):
        """Handle left arrow key"""
        if self.current_image_path and len(self.image_list) > 1:
            self._show_previous_image(None)
    
    def handle_key_right(self):
        """Handle right arrow key"""
        if self.current_image_path and len(self.image_list) > 1:
            self._show_next_image(None)
    
    def handle_key_escape(self):
        """Handle escape key"""
        # Could trigger close or back navigation
        pass
    
    # Public interface
    def clear(self):
        """Clear the preview"""
        self.current_image_path = None
        self.image_list = []
        self.current_image_index = 0
        self.nav_controls.style.visibility = "hidden"
        self._show_placeholder()
    
    def get_current_image(self) -> Optional[Path]:
        """Get current image path"""
        return self.current_image_path
    
    def get_image_count(self) -> int:
        """Get total number of images"""
        return len(self.image_list) 