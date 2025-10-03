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

from fichero.shared.views.base_view import BaseView
from fichero.shared.toolbars import ToolbarCoordinator, TopToolbar, BottomToolbar

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
        
        # Create toolbars after BaseView is initialized
        self._create_toolbars()

        # Register toolbar callbacks
        self._register_toolbar_callbacks()
        
        # Create content
        self._create_content()
        
        logger.info("Preview pane created with BaseView integration")
    
    def _create_toolbars(self):
        """Create top and bottom toolbars for preview pane"""
        try:
            # Create toolbar coordinator for edit mode management
            self.coordinator = ToolbarCoordinator(self.app, is_mobile=self.is_mobile)

            # Create top toolbar with new architecture (mobile only)
            if self.is_mobile:
                self.top_toolbar = TopToolbar(
                    app=self.app,
                    title="",  # Let NavigationController provide context-aware title
                    auto_mobile_nav=True,
                    is_mobile=self.is_mobile,
                    coordinator=self.coordinator
                )
                # Add iOS-standard preview navigation arrows (top-right, like Mail)
                self.top_toolbar.add_button_right(text="▲", on_press=self._on_previous_item, button_id="prev_item")
                self.top_toolbar.add_button_right(text="▼", on_press=self._on_next_item, button_id="next_item")
            else:
                self.top_toolbar = None

            # Create bottom toolbar with coordinator integration
            self.bottom_toolbar = BottomToolbar(
                app=self.app,
                is_mobile=self.is_mobile,
                coordinator=self.coordinator
            )

            # Add preview-specific buttons using composition
            self._add_preview_toolbar_buttons()

            # Set toolbars on the view
            self.set_top_toolbar(self.top_toolbar)
            self.set_bottom_toolbar(self.bottom_toolbar)

            logger.info("Preview pane toolbars created successfully")
        except Exception as e:
            logger.error(f"Failed to create preview toolbars: {e}")

    def _register_toolbar_callbacks(self):
        """Register callbacks for toolbar actions"""
        try:
            # Bottom toolbar callbacks - only register the working ones
            if hasattr(self.bottom_toolbar, 'register_callbacks'):
                self.bottom_toolbar.register_callbacks(
                    on_open_external=self._open_file_external
                )

            logger.debug("Preview pane toolbar callbacks registered")

        except Exception as e:
            logger.error(f"Failed to register toolbar callbacks: {e}")
            # Continue without callbacks - not critical for functionality
    
    def _open_file_external(self):
        """Open the current file with external system application"""
        if self.current_file_path:
            self._open_file(self.current_file_path)
        else:
            logger.warning("No file selected to open externally")
    
    def _open_file(self, file_path: str):
        """Open a file using the system default application"""
        try:
            import subprocess
            import sys
            from pathlib import Path
            
            path = Path(file_path)
            if not path.exists():
                logger.error(f"File not found: {file_path}")
                return
            
            # Use system default application to open the file
            if sys.platform == "darwin":  # macOS
                subprocess.run(["open", str(path)])
            elif sys.platform == "win32":  # Windows
                subprocess.run(["start", str(path)], shell=True)
            else:  # Linux and others
                subprocess.run(["xdg-open", str(path)])
                
            logger.info(f"Opened file externally: {file_path}")
            
        except Exception as e:
            logger.error(f"Failed to open file {file_path}: {e}")
    
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
            
            # Add filename as content title (like collection view does)
            filename = Path(file_path).name
            file_title = toga.Label(
                filename,
                style=Pack(
                    margin=(15, 20, 10, 20),
                    # Use default font size
                    font_weight="bold",
                    color=self.text_color
                )
            )
            self.content_container.add(file_title)
            
            # Create appropriate preview widget
            if self.current_file_type == "image":
                self._create_image_preview(file_path)
            elif self.current_file_type == "pdf":
                self._create_pdf_preview(file_path)
            elif self.current_file_type == "text":
                self._create_text_preview(file_path)
            elif self.current_file_type == "docx":
                self._create_document_preview(file_path)
            elif self.current_file_type == "url":
                self._create_url_preview(file_path)
            else:
                self._create_generic_preview(file_path)
            
            # Notify callbacks
            if self.on_file_changed:
                self.on_file_changed(file_path, self.current_file_type, self.current_stage)
            
            logger.info(f"Showing file preview: {file_path} ({self.current_file_type}, {self.current_stage})")
            
        except Exception as e:
            logger.error(f"Failed to show file: {e}")
            self._create_error_preview(str(e))

    def display_document(self, file_path: str, file_metadata: Dict[str, Any] = None):
        """
        Display a document in the preview pane (backward compatibility method)

        Args:
            file_path: Path to the file to preview
            file_metadata: Additional file metadata
        """
        # Call the main show_file method with proper parameter mapping
        self.show_file(file_path, file_metadata)
    
    def _detect_file_type(self, file_path: str) -> str:
        """Detect file type from extension or URL pattern"""
        if not file_path:
            return "none"

        # Check if it's a URL first
        if file_path.startswith(('http://', 'https://', 'ftp://')):
            return "url"

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
                        margin=(10, 10)
                        # No background color - transparent
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

    def _create_url_preview(self, url: str):
        """Create URL preview using Toga WebView"""
        try:
            logger.info(f"Creating WebView for URL: {url}")

            # Create WebView widget
            self.preview_widget = toga.WebView(
                url=url,
                style=Pack(
                    flex=1,
                    margin=(10, 10)
                ),
                on_webview_load=self._on_webview_load
            )

            if self.content_container:
                self.content_container.add(self.preview_widget)
                logger.info(f"✅ WebView preview created successfully for: {url}")

        except Exception as e:
            logger.error(f"Failed to create URL preview: {e}")
            # Fallback to showing URL info
            info_text = f"Web URL\n\nURL: {url}\n\nWebView Error: {e}\n\nThis would normally show the web page content using Toga WebView."

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

    def _on_webview_load(self, widget, **kwargs):
        """Handle WebView load events"""
        try:
            logger.debug(f"WebView loaded: {widget.url}")
        except Exception as e:
            logger.error(f"WebView load event error: {e}")
    
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

    def _on_previous_item(self, widget):
        """Handle previous item navigation (up chevron) - iOS style"""
        try:
            logger.info("Previous item navigation pressed (▲)")
            self._navigate_to_adjacent_item(-1)
        except Exception as e:
            logger.error(f"Failed to navigate to previous item: {e}")

    def _on_next_item(self, widget):
        """Handle next item navigation (down chevron) - iOS style"""
        try:
            logger.info("Next item navigation pressed (▼)")
            self._navigate_to_adjacent_item(1)
        except Exception as e:
            logger.error(f"Failed to navigate to next item: {e}")

    def _navigate_to_adjacent_item(self, direction: int):
        """Navigate to adjacent item in the current collection context

        Args:
            direction: -1 for previous, 1 for next
        """
        try:
            # Get NavigationController from app
            navigation_controller = self._get_navigation_controller()
            if not navigation_controller:
                logger.warning("No navigation controller available for preview navigation")
                return

            # Get current navigation state
            current_state = navigation_controller.get_current_state()
            logger.debug(f"Current navigation state: context={current_state.context.value}, collection_id={current_state.collection_id}")

            # Ensure we're in preview context with a collection
            if (current_state.context.value != 'preview' or
                not current_state.collection_id or
                not self.current_file_path):
                logger.warning(f"Invalid state for preview navigation: context={current_state.context.value}, collection_id={current_state.collection_id}, file_path={self.current_file_path}")
                return

            # Get collection items from library service
            collection_items = self._get_collection_items(current_state.collection_id, current_state.current_path or "")
            if not collection_items:
                logger.warning(f"No items found in collection {current_state.collection_id}")
                return

            logger.debug(f"Found {len(collection_items)} items in collection")

            # Find current file in the list
            current_index = self._find_current_file_index(collection_items)
            if current_index is None:
                logger.warning(f"Current file not found in collection items: {self.current_file_path}")
                return

            logger.debug(f"Current file index: {current_index} out of {len(collection_items)} items")

            # Calculate next index
            next_index = current_index + direction
            if next_index < 0 or next_index >= len(collection_items):
                logger.info(f"Navigation {direction}: No adjacent item available (index would be {next_index})")
                return

            # Get the target item
            target_item = collection_items[next_index]
            target_file_path = target_item.get('file_path') or target_item.get('local_path')

            if not target_file_path:
                logger.warning(f"Target item has no file path: {target_item}")
                return

            # Navigate to the target file
            logger.info(f"Navigating {'previous' if direction == -1 else 'next'} to: {target_file_path}")
            success = navigation_controller.navigate_to_preview(target_file_path, target_item)

            if success:
                logger.info(f"Successfully navigated to {'previous' if direction == -1 else 'next'} item")
            else:
                logger.error(f"Failed to navigate to {'previous' if direction == -1 else 'next'} item")

        except Exception as e:
            logger.error(f"Error in adjacent item navigation: {e}")
            import traceback
            logger.debug(f"Full traceback: {traceback.format_exc()}")

    def _get_navigation_controller(self):
        """Get navigation controller from app integration"""
        try:
            if hasattr(self.app, 'view_integration') and self.app.view_integration:
                return self.app.view_integration.get_navigation_controller()
            else:
                logger.warning("No view integration available in app")
                return None
        except Exception as e:
            logger.error(f"Failed to get navigation controller: {e}")
            return None

    def _get_collection_items(self, collection_id: str, current_path: str = ""):
        """Get items from the current collection and path"""
        try:
            # Get library service from app
            library_service = getattr(self.app, 'library_service', None)
            if not library_service:
                logger.error("No library service available")
                return []

            # For now, get all collection items (TODO: implement folder filtering when needed)
            import asyncio

            # Run async method in current event loop or create new one
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # We're in an async context - create a task
                    # For now, use run_until_complete which should work for most UI operations
                    items = loop.run_until_complete(library_service.get_collection_items_for_ui(collection_id))
                else:
                    items = asyncio.run(library_service.get_collection_items_for_ui(collection_id))
            except:
                # Fallback: create new event loop
                items = asyncio.run(library_service.get_collection_items_for_ui(collection_id))

            # Filter for files only (not folders) and sort by name for consistent navigation
            file_items = [item for item in items if item.get('type') != 'folder']
            file_items.sort(key=lambda x: x.get('name', ''))

            logger.debug(f"Retrieved {len(file_items)} file items from collection {collection_id}")
            return file_items

        except Exception as e:
            logger.error(f"Failed to get collection items: {e}")
            return []

    def _find_current_file_index(self, collection_items) -> Optional[int]:
        """Find the index of the current file in the collection items list"""
        try:
            if not self.current_file_path:
                return None

            # Try to match by exact file path first
            for i, item in enumerate(collection_items):
                item_path = item.get('file_path') or item.get('local_path')
                if item_path and item_path == self.current_file_path:
                    return i

            # Try to match by filename if exact path doesn't work
            current_filename = Path(self.current_file_path).name
            for i, item in enumerate(collection_items):
                item_path = item.get('file_path') or item.get('local_path')
                if item_path and Path(item_path).name == current_filename:
                    return i

            return None

        except Exception as e:
            logger.error(f"Failed to find current file index: {e}")
            return None
    
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

    def _add_preview_toolbar_buttons(self):
        """Add preview-specific buttons using composition"""
        try:
            # Add preview specific buttons if needed
            logger.debug("Preview toolbar buttons configured")

        except Exception as e:
            logger.error(f"Failed to add preview toolbar buttons: {e}") 