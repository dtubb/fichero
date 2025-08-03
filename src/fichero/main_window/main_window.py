"""
Main Window for Fichero - Collection Library View

Shows a detailed list of processed collections and their transcriptions.
Uses modular components for maintainability and separation of concerns.
Keeps all existing functionality intact - this is an addition, not replacement.
"""

import toga
from toga.style import Pack
from toga.constants import ROW, COLUMN
import asyncio
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any

# Import platform detection
import toga.platform

from fichero.main_window.components.collection_list import CollectionListComponent
from fichero.main_window.command_manager import CommandManager

logger = logging.getLogger(__name__)

# Use the global _ function installed by gettext.install() in app.py


class MainWindow:
    """
    Main window showing collection library with detailed list of processed collections.
    
    Features:
    - Modular components for maintainability
    - DetailedList showing processed collections with transcriptions
    - Quick access to collection transcriptions
    - Integration with existing director service
    - Cross-platform command support (desktop menus, Android toolbars)
    - iOS-specific top toolbar (since iOS doesn't support commands yet)
    - Mac-like interface with no title bar, header, or status bar
    - Collection browser with image viewer and swipe navigation
    """
    
    def __init__(self, app):
        """Initialize main window"""
        self.app = app
        self.window: Optional[toga.MainWindow] = None
        self.is_visible = False
        
        # Platform detection - iOS needs custom handling since it doesn't support commands yet
        current_platform = toga.platform.current_platform
        self.is_ios = current_platform == 'iOS'
        self.is_android = current_platform == 'android'
        self.is_mobile = self.is_ios or self.is_android
        
        # iOS demo mode disabled - use native macOS UI
        
        # UI components
        self.collection_list: Optional[CollectionListComponent] = None
        self.image_display: Optional[toga.ImageView] = None
        self.prev_button: Optional[toga.Button] = None
        self.next_button: Optional[toga.Button] = None
        self.process_button: Optional[toga.Button] = None
        self.process_all_button: Optional[toga.Button] = None
        self.catalogue_button: Optional[toga.Button] = None
        
        # iOS-specific components
        self.ios_top_toolbar: Optional[toga.Box] = None
        self.ios_content_container: Optional[toga.Box] = None
        self.main_content: Optional[toga.Widget] = None
        
        # Data
        self.current_collection: Optional[Dict[str, Any]] = None
        self.current_images: List[str] = []
        self.current_image_index = 0
        
        # Director service
        self.director = None
        
        # Initialize services
        from fichero.main_window.services import LibraryManager, CollectionScanner
        from fichero.main_window.data import WindowState
        self.library_manager = LibraryManager(app)
        self.scanner = CollectionScanner()
        self.state = WindowState()
        
        logger.info(f"Main window initialized for platform: {toga.platform.current_platform}")
    
    def show(self):
        """Show the main window"""
        if self.window is None:
            self._create_window()
        
        if not self.is_visible:
            # Add commands to toolbar for all platforms except iOS (iOS uses custom top toolbar)
            if not self.is_ios and hasattr(self.app, 'command_manager'):
                self.app.command_manager.add_to_toolbar(self.window)
            
            self.window.show()
            self.is_visible = True
            
            # Load collection data
            asyncio.create_task(self._load_collection_data())
            
            logger.info("Main window shown")
    
    def hide(self):
        """Hide the main window"""
        if self.window and self.is_visible:
            self.window.hide()
            self.is_visible = False
            logger.info("Main window hidden")
    
    def close(self):
        """Close the main window"""
        if self.window:
            self.window.close()
            self.window = None
            self.is_visible = False
    
    def _create_window(self):
        """Create the main window with detailed list"""
        try:
            # Get director from app
            self.director = getattr(self.app, 'director', None)
            if self.director is None:
                components = getattr(self.app, 'components', {})
                self.director = components.get('director')
            
            # Create main window with appropriate sizing
            window_size = self._get_window_size()
            
            # Use empty title for iOS to remove redundant title bar
            window_title = "" if self.is_ios else _("app_title")
            
            self.window = toga.MainWindow(
                title=_("app_title"),
                size=window_size,
                resizable=True,
                minimizable=True
            )
            
            # Set minimum window size
            self.window.min_size = (1200, 800)
            
            # Create the UI content
            self._create_ui()
            
            # Set up window close handler
            self.window.on_close = self._on_close
            
            logger.info("Main window created successfully")
            
        except Exception as e:
            logger.error(f"Failed to create main window: {e}")
            raise
    
    def _get_window_size(self) -> tuple:
        """Get appropriate window size based on platform"""
        if self.is_mobile:
            # Mobile: use typical mobile screen dimensions
            if self.is_ios:
                # iPhone dimensions - iPhone 12 mini: 375x812
                return (375, 812)  # iPhone 12 mini portrait
            elif self.is_android:
                # Android dimensions (Pixel 7: 412x915) - Portrait
                return (412, 915)
            else:
                # Generic mobile
                return (400, 800)
        elif self.is_ios:
            # iOS testing on macOS: use portrait orientation
            return (375, 812)  # iPhone 12 mini portrait
        else:
            # Desktop: use reasonable default
            return (1400, 900)
    
    def _create_ui(self):
        """Create the main window UI using modular components"""
        if self.is_ios:
            self._create_ios_ui()
        else:
            self._create_desktop_ui()
    
    def _create_desktop_ui(self):
        """Create desktop UI with traditional layout"""
        # Create main container with split layout
        main_container = toga.Box(
            style=Pack(
                direction=ROW,
                flex=1
            )
        )
        
        # Create collection list component with callbacks
        self.collection_list = CollectionListComponent(
            on_select=self._on_collection_select,
            on_primary_action=self._on_collection_open,
            on_secondary_action=self._on_collection_show_info
        )
        
        # Create right side container for image viewer and controls
        right_side = toga.Box(
            style=Pack(
                direction=COLUMN,
                flex=1,
                margin=20
            )
        )
        
        # Create image viewer
        self._create_image_viewer(right_side)
        
        # Create processing controls
        self._create_processing_controls(right_side)
        
        # Add components to main container
        main_container.add(self.collection_list.create())
        main_container.add(right_side)
        
        # Set the content
        self.window.content = main_container
    
    def _create_ios_ui(self):
        """Create iOS-specific UI with top toolbar (since iOS doesn't support commands yet)"""
        # Main container - vertical layout for iOS
        main_container = toga.Box(
            style=Pack(
                direction=COLUMN,
                flex=1
            )
        )
        
        # Create iOS top toolbar
        self._create_ios_top_toolbar()
        
        # Create overlay container for iOS modals/overlays
        self.ios_content_container = toga.Box(
            style=Pack(
                direction=COLUMN,
                flex=1
            )
        )
        
        # Create main content (collection view)
        content_area = toga.Box(
            style=Pack(
                direction=ROW,
                flex=1
            )
        )
        
        # Create collection list component
        self.collection_list = CollectionListComponent(
            on_select=self._on_collection_select,
            on_primary_action=self._on_collection_open,
            on_secondary_action=self._on_collection_show_info
        )
        
        # Create right side for image viewer
        right_side = toga.Box(
            style=Pack(
                direction=COLUMN,
                flex=1,
                margin=10
            )
        )
        
        # Create image viewer
        self._create_image_viewer(right_side)
        
        # Add components to content area
        content_area.add(self.collection_list.create())
        content_area.add(right_side)
        
        # Set main content
        self.main_content = content_area
        self.ios_content_container.add(content_area)
        
        # Add toolbar and content container to main container
        main_container.add(self.ios_top_toolbar)
        main_container.add(self.ios_content_container)
        
        # Set the content
        self.window.content = main_container
    
    def _create_ios_top_toolbar(self):
        """Create iOS top toolbar with essential actions"""
        self.ios_top_toolbar = toga.Box(
            style=Pack(
                direction=ROW,
                justify_content="center",
                margin=10,
                background_color="#f8f8f8"
            )
        )
        
        # Settings button
        settings_button = toga.Button(
            text="Settings",
            on_press=self._on_ios_settings
        )
        
        # Process button
        process_button = toga.Button(
            text="Process",
            on_press=self._on_ios_process
        )
        
        # Add button
        add_button = toga.Button(
            text="Add",
            on_press=self._on_ios_add
        )
        
        # Delete button
        delete_button = toga.Button(
            text="Delete",
            on_press=self._on_ios_delete
        )
        
        # About button
        about_button = toga.Button(
            text="About",
            on_press=self._on_ios_about
        )
        
        self.ios_top_toolbar.add(settings_button)
        self.ios_top_toolbar.add(process_button)
        self.ios_top_toolbar.add(add_button)
        self.ios_top_toolbar.add(delete_button)
        self.ios_top_toolbar.add(about_button)
    
    def _create_image_viewer(self, parent_container):
        """Create image viewer with swipe navigation"""
        # Image viewer container
        self.image_viewer = toga.Box(
            style=Pack(
                direction=COLUMN,
                flex=1,
                margin=10
            )
        )
        
        # Image display
        self.image_display = toga.ImageView(
            style=Pack(
                flex=1,
                background_color='#f0f0f0'
            )
        )
        
        # Navigation controls
        nav_container = toga.Box(
            style=Pack(
                direction=ROW,
                justify_content="center",
                margin=10
            )
        )
        
        # Previous button
        self.prev_button = toga.Button(
            text="← Previous",
            on_press=self._previous_image,
            style=Pack(margin_right=10)
        )
        
        # Image counter
        self.image_counter = toga.Label(
            text="0 / 0",
            style=Pack(
                font_size=12,
                margin=10
            )
        )
        
        # Next button
        self.next_button = toga.Button(
            text="Next →",
            on_press=self._next_image,
            style=Pack(margin_left=10)
        )
        
        nav_container.add(self.prev_button)
        nav_container.add(self.image_counter)
        nav_container.add(self.next_button)
        
        # Add to image viewer
        self.image_viewer.add(self.image_display)
        self.image_viewer.add(nav_container)
        
        # Add to parent
        parent_container.add(self.image_viewer)
        
        # Initially hide the image viewer
        self.image_viewer.style.visibility = 'hidden'
    
    def _create_processing_controls(self, parent_container):
        """Create processing controls"""
        self.processing_controls = toga.Box(
            style=Pack(
                direction=COLUMN,
                margin=10
            )
        )
        
        # Collection info
        self.collection_info = toga.Label(
            text="",
            style=Pack(
                font_size=14,
                font_weight="bold",
                margin_bottom=10
            )
        )
        
        # Processing buttons
        button_container = toga.Box(
            style=Pack(
                direction=ROW,
                margin=10
            )
        )
        
        # Process current image
        self.process_current_btn = toga.Button(
            text="Process Current Image",
            on_press=self._process_current_image,
            style=Pack(margin_right=10)
        )
        
        # Process all images
        self.process_all_btn = toga.Button(
            text="Process All Images",
            on_press=self._process_all_images,
            style=Pack(margin_right=10)
        )
        
        # Catalogue collection
        self.catalogue_btn = toga.Button(
            text="Catalogue Collection",
            on_press=self._catalogue_collection,
            style=Pack(margin_right=10)
        )
        
        button_container.add(self.process_current_btn)
        button_container.add(self.process_all_btn)
        button_container.add(self.catalogue_btn)
        
        # Add to processing controls
        self.processing_controls.add(self.collection_info)
        self.processing_controls.add(button_container)
        
        # Add to parent
        parent_container.add(self.processing_controls)
        
        # Initially hide the processing controls
        self.processing_controls.style.visibility = 'hidden'
    
    async def _load_collection_data(self):
        """Load collection data from the library location"""
        try:
            # Initialize library first
            await self.library_manager.initialize_library()
            
            # Get library location from settings
            library_path = self.library_manager.get_library_path()
            
            if not library_path.exists():
                logger.warning(f"Library path not found: {library_path}")
                return
            
            # Scan for collection manifests
            collections = await self.scanner.scan_collections(library_path)
            
            # If no collections found, create dummy collections
            if not collections:
                logger.info("No collections found, creating dummy collections")
                await self.library_manager.create_dummy_collections()
                collections = await self.scanner.scan_collections(library_path)
            
            # Update state
            self.state.set_collections(collections)
            
            # Update UI using Toga data source
            self.collection_list.set_data(self.state.get_list_data())
            
            logger.info(f"Loaded {self.state.collection_count} collections")
            
        except Exception as e:
            logger.error(f"Failed to load collection data: {e}")
    
    def _get_library_path(self) -> Path:
        """Get the library path from settings or use Toga default"""
        return self.library_manager.get_library_path()
    
    def _on_collection_select(self, widget, row):
        """Handle collection selection"""
        if row and row.data:
            collection_info = row.data
            logger.debug(f"Selected collection: {collection_info.title}")
            self._load_collection_images(collection_info)
    
    def _on_collection_open(self, widget, row):
        """Handle collection open action"""
        if row and row.data:
            collection_info = row.data
            self._open_collection(collection_info)
    
    def _on_collection_show_info(self, widget, row):
        """Handle collection info action"""
        if row and row.data:
            collection_info = row.data
            self._show_collection_info(collection_info)
    
    def _load_collection_images(self, collection_info):
        """Load images for the selected collection"""
        try:
            self.current_collection = collection_info
            
            # Get the collection folder path
            library_path = self.library_manager.get_library_path()
            collection_folder = library_path / "collections" / collection_info.title
            
            if collection_folder.exists():
                # Find all image files
                image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff']
                self.current_images = []
                
                for ext in image_extensions:
                    self.current_images.extend(collection_folder.glob(f"*{ext}"))
                    self.current_images.extend(collection_folder.glob(f"*{ext.upper()}"))
                
                # Sort images naturally
                self.current_images.sort(key=lambda x: self._natural_sort_key(x.name))
                
                # Show image viewer and processing controls
                self.image_viewer.style.visibility = 'visible'
                self.processing_controls.style.visibility = 'visible'
                
                # Update collection info
                self.collection_info.text = f"Collection: {collection_info.title}\nImages: {len(self.current_images)}"
                
                # Show first image if available
                if self.current_images:
                    self.current_image_index = 0
                    self._show_current_image()
                else:
                    self.image_display.image = None
                    self.image_counter.text = "No images found"
                
                logger.info(f"Loaded {len(self.current_images)} images for collection: {collection_info.title}")
            else:
                logger.warning(f"Collection folder not found: {collection_folder}")
                
        except Exception as e:
            logger.error(f"Failed to load collection images: {e}")
    
    def _show_current_image(self):
        """Show the current image in the viewer"""
        if not self.current_images or self.current_image_index >= len(self.current_images):
            return
        
        try:
            image_path = self.current_images[self.current_image_index]
            
            # Load and display the image
            image = toga.Image(str(image_path))
            self.image_display.image = image
            
            # Update counter
            self.image_counter.text = f"{self.current_image_index + 1} / {len(self.current_images)}"
            
            # Update navigation buttons
            self.prev_button.enabled = self.current_image_index > 0
            self.next_button.enabled = self.current_image_index < len(self.current_images) - 1
            
        except Exception as e:
            logger.error(f"Failed to show image: {e}")
    
    def _previous_image(self, widget):
        """Show previous image"""
        if self.current_image_index > 0:
            self.current_image_index -= 1
            self._show_current_image()
    
    def _next_image(self, widget):
        """Show next image"""
        if self.current_image_index < len(self.current_images) - 1:
            self.current_image_index += 1
            self._show_current_image()
    
    def _natural_sort_key(self, s: str) -> list:
        """Natural sort key for sorting filenames with numbers"""
        import re
        return [int(text) if text.isdigit() else text.lower()
                for text in re.split('([0-9]+)', s)]
    
    def _process_current_image(self, widget):
        """Process the current image"""
        if not self.current_images or self.current_image_index >= len(self.current_images):
            return
        
        current_image = self.current_images[self.current_image_index]
        logger.info(f"Processing current image: {current_image}")
        # TODO: Implement image processing
    
    def _process_all_images(self, widget):
        """Process all images in the collection"""
        if not self.current_images:
            return
        
        logger.info(f"Processing all {len(self.current_images)} images in collection: {self.current_collection.title}")
        # TODO: Implement batch processing
    
    def _catalogue_collection(self, widget):
        """Catalogue the current collection"""
        if not self.current_collection:
            return
        
        logger.info(f"Catalogue collection: {self.current_collection.title}")
        # TODO: Implement catalogue functionality
    
    def _open_collection(self, collection_info):
        """Open a collection for viewing"""
        try:
            # For now, just show a message
            # TODO: Implement collection viewer
            logger.info(f"Opening collection: {collection_info.title}")
            
        except Exception as e:
            logger.error(f"Failed to open collection: {e}")
    
    def _show_collection_info(self, collection_info):
        """Show detailed collection information"""
        try:
            # For now, just log the info
            info = f"Collection: {collection_info.title}, Entries: {collection_info.entry_count}, Status: {collection_info.status}"
            logger.info(f"Collection info: {info}")
            
        except Exception as e:
            logger.error(f"Failed to show collection info: {e}")
    
    def _on_close(self, widget):
        """Handle window close event"""
        self.hide()  # Hide instead of close
        return True  # Prevent window from actually closing
    
    @property
    def closed(self):
        """Check if the main window is closed"""
        return self.window is None 
    
    def _on_ios_add(self, widget):
        """Handle Add button press on iOS"""
        if hasattr(self.app, 'command_manager'):
            # For iOS: show add content as overlay
            self._show_ios_overlay(self._create_add_overlay())
    
    def _on_ios_process(self, widget):
        """Handle Process button press on iOS"""
        if hasattr(self.app, 'command_manager'):
            # For iOS: show process content as overlay
            self._show_ios_overlay(self._create_process_overlay())
    
    def _on_ios_settings(self, widget):
        """Handle Settings button press on iOS"""
        if hasattr(self.app, 'command_manager'):
            # For iOS: show settings content as overlay
            self._show_ios_overlay(self._create_settings_overlay())
    
    def _on_ios_delete(self, widget):
        """Handle Delete button press on iOS"""
        if hasattr(self.app, 'command_manager'):
            # For iOS: show delete content as overlay
            self._show_ios_overlay(self._create_delete_overlay())
    
    def _on_ios_about(self, widget):
        """Handle About button press on iOS"""
        if hasattr(self.app, 'command_manager'):
            # For iOS: show about content as overlay instead of separate window
            self._show_ios_overlay(self._create_about_overlay())
    
    def _show_ios_overlay(self, overlay_widget):
        """Replace main window content with new content (iOS alternative to secondary windows)"""
        if not self.ios_content_container:
            return
        
        # Remove current content
        if self.main_content:
            self.ios_content_container.remove(self.main_content)
        
        # Show new content
        self.main_content = overlay_widget
        self.ios_content_container.add(overlay_widget)
        self.ios_content_container.refresh()
    
    def _hide_ios_overlay(self):
        """Return to main content"""
        if not self.ios_content_container:
            return
        
        # Remove current content
        if self.main_content:
            self.ios_content_container.remove(self.main_content)
        
        # Recreate and show main content
        content_area = toga.Box(
            style=Pack(
                direction=ROW,
                flex=1
            )
        )
        
        # Create collection list component
        self.collection_list = CollectionListComponent(
            on_select=self._on_collection_select,
            on_primary_action=self._on_collection_open,
            on_secondary_action=self._on_collection_show_info
        )
        
        # Create right side for image viewer
        right_side = toga.Box(
            style=Pack(
                direction=COLUMN,
                flex=1,
                margin=10
            )
        )
        
        # Create image viewer
        self._create_image_viewer(right_side)
        
        # Add components to content area
        content_area.add(self.collection_list.create())
        content_area.add(right_side)
        
        # Set main content
        self.main_content = content_area
        self.ios_content_container.add(content_area)
        self.ios_content_container.refresh()
    
    def _create_about_overlay(self):
        """Create about content as an overlay widget"""
        # Use the shared AboutContent component with back button
        from fichero.ui.windows.about_window import AboutContent
        about_content = AboutContent(
            self.app, 
            show_back_button=True, 
            on_back=lambda widget: self._hide_ios_overlay()
        )
        return about_content.create()
    
    def _create_settings_overlay(self):
        """Create settings content as an overlay widget"""
        # Use the shared SettingsContent component with back button
        from fichero.config.ui.windows.settings import SettingsContent
        settings_content = SettingsContent(
            self.app, 
            show_back_button=True, 
            on_back=lambda widget: self._hide_ios_overlay()
        )
        return settings_content.create()
    
    def _create_process_overlay(self):
        """Create process content as an overlay widget"""
        # Use the shared ProcessingContent component with back button
        from fichero.ui.windows.processing_window import ProcessingContent
        processing_content = ProcessingContent(
            self.app, 
            show_back_button=True, 
            on_back=lambda widget: self._hide_ios_overlay()
        )
        return processing_content.create()
    
    def _create_add_overlay(self):
        """Create add content as an overlay widget"""
        overlay = toga.Box(
            style=Pack(
                direction=COLUMN,
                margin=20,
                background_color="#ffffff"
            )
        )
        
        close_button = toga.Button(
            text="✕",
            on_press=lambda widget: self._hide_ios_overlay()
        )
        
        title = toga.Label(
            "Add",
            style=Pack(font_size=24, font_weight="bold", margin_bottom=10)
        )
        
        content = toga.Label(
            "Add content coming soon...",
            style=Pack(font_size=16)
        )
        
        overlay.add(close_button)
        overlay.add(title)
        overlay.add(content)
        
        return overlay
    
    def _create_delete_overlay(self):
        """Create delete content as an overlay widget"""
        overlay = toga.Box(
            style=Pack(
                direction=COLUMN,
                margin=20,
                background_color="#ffffff"
            )
        )
        
        close_button = toga.Button(
            text="✕",
            on_press=lambda widget: self._hide_ios_overlay()
        )
        
        title = toga.Label(
            "Delete",
            style=Pack(font_size=24, font_weight="bold", margin_bottom=10)
        )
        
        content = toga.Label(
            "Delete content coming soon...",
            style=Pack(font_size=16)
        )
        
        overlay.add(close_button)
        overlay.add(title)
        overlay.add(content)
        
        return overlay 