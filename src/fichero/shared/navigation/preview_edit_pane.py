"""
Preview/Edit Pane Component

Large content preview and editing area for the desktop layout.
Shows images, transcriptions, metadata, and provides editing capabilities.
"""

import toga
from toga.style import Pack
from toga.constants import COLUMN, ROW
import logging
from typing import Optional, Callable, Any, Dict
from pathlib import Path

from fichero.shared.navigation.navigation_state import NavigationItem, NavigationLevel

logger = logging.getLogger(__name__)


class PreviewEditPane:
    """
    Preview/Edit pane for content viewing and editing.
    
    Features:
    - Tabbed interface (Image | Text | Metadata)
    - Image viewer with zoom/pan
    - Text editor for transcriptions
    - Metadata forms
    - Save/export actions
    """
    
    def __init__(self, is_mobile: bool = False):
        """Initialize preview/edit pane"""
        self.is_mobile = is_mobile
        
        # UI components
        self.container: Optional[toga.Box] = None
        self.header: Optional[toga.Box] = None
        self.title_label: Optional[toga.Label] = None
        self.tab_container: Optional[toga.Box] = None
        self.content_container: Optional[toga.Box] = None
        self.actions_container: Optional[toga.Box] = None
        
        # Tab components
        self.image_tab: Optional[toga.Button] = None
        self.text_tab: Optional[toga.Button] = None
        self.metadata_tab: Optional[toga.Button] = None
        
        # Content components
        self.image_view: Optional[toga.ImageView] = None
        self.text_editor: Optional[toga.MultilineTextInput] = None
        self.metadata_scroll: Optional[toga.ScrollContainer] = None
        
        # State
        self.current_item: Optional[NavigationItem] = None
        self.current_tab: str = "image"
        self.content_data: Dict[str, Any] = {}
        
        # Callbacks
        self.on_save: Optional[Callable[[str, Any], None]] = None
        self.on_export: Optional[Callable[[str], None]] = None
        
    def create(self) -> toga.Box:
        """Create the preview/edit pane UI"""
        # Main container
        self.container = toga.Box(
            style=Pack(
                direction=COLUMN,
                flex=1,
                margin=10
            )
        )
        
        # Create header
        self._create_header()
        
        # Create tab navigation (desktop only)
        if not self.is_mobile:
            self._create_tabs()
        
        # Create content area
        self._create_content_area()
        
        # Create action buttons
        self._create_actions()
        
        # Add components
        self.container.add(self.header)
        if not self.is_mobile:
            self.container.add(self.tab_container)
        self.container.add(self.content_container)
        self.container.add(self.actions_container)
        
        # Show default empty state
        self._show_empty_state()
        
        return self.container
    
    def _create_header(self):
        """Create header with title"""
        self.header = toga.Box(
            style=Pack(
                direction=ROW,
                margin_bottom=10
            )
        )
        
        # Title label
        self.title_label = toga.Label(
            text="Select an item to preview",
            style=Pack(
                font_size=18,
                font_weight="bold",
                flex=1
            )
        )
        self.header.add(self.title_label)
    
    def _create_tabs(self):
        """Create tab navigation for desktop"""
        self.tab_container = toga.Box(
            style=Pack(
                direction=ROW,
                margin_bottom=10
            )
        )
        
        # Image tab
        self.image_tab = toga.Button(
            text="🖼️ Image",
            on_press=lambda w: self._switch_tab("image"),
            style=Pack(margin_right=5)
        )
        
        # Text tab
        self.text_tab = toga.Button(
            text="📝 Text",
            on_press=lambda w: self._switch_tab("text"),
            style=Pack(margin_right=5)
        )
        
        # Metadata tab
        self.metadata_tab = toga.Button(
            text="📋 Metadata",
            on_press=lambda w: self._switch_tab("metadata"),
            style=Pack(margin_right=5)
        )
        
        self.tab_container.add(self.image_tab)
        self.tab_container.add(self.text_tab)
        self.tab_container.add(self.metadata_tab)
        
        # Set initial tab state
        self._update_tab_styles()
    
    def _create_content_area(self):
        """Create content display area"""
        self.content_container = toga.Box(
            style=Pack(
                direction=COLUMN,
                flex=1,
                margin_bottom=10
            )
        )
        
        # Create image view
        self.image_view = toga.ImageView(
            style=Pack(
                flex=1,
                background_color="#f0f0f0"
            )
        )
        
        # Create text editor
        self.text_editor = toga.MultilineTextInput(
            placeholder="Transcription text will appear here...",
            style=Pack(
                flex=1,
                font_family="monospace"
            )
        )
        
        # Create metadata scroll container
        self.metadata_scroll = toga.ScrollContainer(
            style=Pack(
                flex=1
            )
        )
        
        # Initially show image view
        self.content_container.add(self.image_view)
    
    def _create_actions(self):
        """Create action buttons"""
        self.actions_container = toga.Box(
            style=Pack(
                direction=ROW,
                justify_content="center",
                margin_top=10
            )
        )
        
        # Save button
        save_button = toga.Button(
            text="💾 Save",
            on_press=self._on_save_pressed,
            style=Pack(margin_right=10),
            enabled=False  # Disabled initially
        )
        
        # Export button
        export_button = toga.Button(
            text="📤 Export",
            on_press=self._on_export_pressed,
            style=Pack(margin_right=10),
            enabled=False  # Disabled initially
        )
        
        # Previous/Next buttons for navigation
        prev_button = toga.Button(
            text="← Previous",
            on_press=self._on_previous_pressed,
            style=Pack(margin_right=5),
            enabled=False
        )
        
        next_button = toga.Button(
            text="Next →",
            on_press=self._on_next_pressed,
            style=Pack(margin_left=5),
            enabled=False
        )
        
        self.actions_container.add(save_button)
        self.actions_container.add(export_button)
        self.actions_container.add(prev_button)
        self.actions_container.add(next_button)
        
        # Store references for enabling/disabling
        self.save_button = save_button
        self.export_button = export_button
        self.prev_button = prev_button
        self.next_button = next_button
    
    def _switch_tab(self, tab_name: str):
        """Switch to a different tab"""
        if tab_name == self.current_tab:
            return
            
        self.current_tab = tab_name
        
        # Clear content container
        self.content_container.clear()
        
        # Add appropriate content
        if tab_name == "image":
            self.content_container.add(self.image_view)
        elif tab_name == "text":
            self.content_container.add(self.text_editor)
        elif tab_name == "metadata":
            self.content_container.add(self.metadata_scroll)
        
        # Update tab styles
        self._update_tab_styles()
        
        logger.info(f"Switched to tab: {tab_name}")
    
    def _update_tab_styles(self):
        """Update tab button styles to show active tab"""
        if not self.is_mobile:
            # Reset all tab styles
            tabs = [
                (self.image_tab, "image"),
                (self.text_tab, "text"), 
                (self.metadata_tab, "metadata")
            ]
            
            for tab_button, tab_name in tabs:
                if tab_button:
                    if tab_name == self.current_tab:
                        # Active tab style
                        tab_button.style.background_color = "#007AFF"
                        tab_button.style.color = "white"
                    else:
                        # Inactive tab style
                        tab_button.style.background_color = "#f0f0f0"
                        tab_button.style.color = "black"
    
    def show_item(self, item: NavigationItem):
        """Show content for a navigation item"""
        try:
            self.current_item = item
            
            # Update title
            self.title_label.text = f"{item.name} ({item.level.value})"
            
            # Load content based on item type
            self._load_item_content(item)
            
            # Enable action buttons
            self.save_button.enabled = True
            self.export_button.enabled = True
            
            logger.info(f"Showing content for: {item.name}")
            
        except Exception as e:
            logger.error(f"Failed to show item {item.name}: {e}")
            self._show_error_state(str(e))
    
    def _load_item_content(self, item: NavigationItem):
        """Load content for the item"""
        try:
            # Load based on item level and type
            if item.level == NavigationLevel.PAGES:
                self._load_page_content(item)
            elif item.level == NavigationLevel.DOCUMENTS:
                self._load_document_content(item)
            else:
                self._load_summary_content(item)
                
        except Exception as e:
            logger.error(f"Failed to load content for {item.name}: {e}")
            self._show_error_state(f"Failed to load content: {e}")
    
    def _load_page_content(self, item: NavigationItem):
        """Load content for a page item"""
        # Load image if available
        image_path = Path(item.path)
        if image_path.exists() and image_path.suffix.lower() in ['.jpg', '.jpeg', '.png', '.tiff', '.tif']:
            try:
                self.image_view.image = toga.Image(str(image_path))
            except Exception as e:
                logger.error(f"Failed to load image {image_path}: {e}")
        
        # Load transcription text
        transcription = item.metadata.get('transcription', 'No transcription available')
        self.text_editor.value = transcription
        
        # Load metadata
        self._load_metadata_content(item.metadata)
    
    def _load_document_content(self, item: NavigationItem):
        """Load content for a document item"""
        # Show document summary in text area
        summary = f"Document: {item.name}\n"
        summary += f"Path: {item.path}\n"
        summary += f"Pages: {item.metadata.get('page_count', 0)}\n"
        summary += f"Status: {item.metadata.get('status', 'Unknown')}\n"
        
        self.text_editor.value = summary
        
        # Load metadata
        self._load_metadata_content(item.metadata)
        
        # Switch to text tab for documents
        if not self.is_mobile:
            self._switch_tab("text")
    
    def _load_summary_content(self, item: NavigationItem):
        """Load summary content for collections/folders"""
        # Show summary in text area
        summary = f"{item.level.value.title()}: {item.name}\n"
        summary += f"Path: {item.path}\n"
        
        if item.level == NavigationLevel.COLLECTIONS:
            summary += f"Folders: {item.metadata.get('folder_count', 0)}\n"
        elif item.level == NavigationLevel.FOLDERS:
            summary += f"Documents: {item.metadata.get('document_count', 0)}\n"
            
        summary += f"Created: {item.metadata.get('created_date', 'Unknown')}\n"
        summary += f"Modified: {item.metadata.get('modified_date', 'Unknown')}\n"
        
        self.text_editor.value = summary
        
        # Load metadata
        self._load_metadata_content(item.metadata)
        
        # Switch to text tab for summaries
        if not self.is_mobile:
            self._switch_tab("text")
    
    def _load_metadata_content(self, metadata: Dict[str, Any]):
        """Load metadata into the metadata tab"""
        # Create metadata form
        metadata_box = toga.Box(
            style=Pack(
                direction=COLUMN,
                margin=10
            )
        )
        
        # Add metadata fields
        for key, value in metadata.items():
            if key.startswith('_'):  # Skip internal metadata
                continue
                
            field_container = toga.Box(
                style=Pack(
                    direction=COLUMN,
                    margin_bottom=10
                )
            )
            
            # Field label
            label = toga.Label(
                text=f"{key.replace('_', ' ').title()}:",
                style=Pack(
                    font_weight="bold",
                    margin_bottom=5
                )
            )
            
            # Field value (editable)
            if isinstance(value, bool):
                field_widget = toga.Switch(value=value)
            elif isinstance(value, (int, float)):
                field_widget = toga.NumberInput(value=value)
            else:
                field_widget = toga.TextInput(value=str(value))
            
            field_container.add(label)
            field_container.add(field_widget)
            metadata_box.add(field_container)
        
        # Update metadata scroll content
        self.metadata_scroll.content = metadata_box
    
    def _show_empty_state(self):
        """Show empty state when no item is selected"""
        self.title_label.text = "Select an item to preview"
        self.text_editor.value = "No content selected"
        self.image_view.image = None
        
        # Disable action buttons
        if hasattr(self, 'save_button'):
            self.save_button.enabled = False
            self.export_button.enabled = False
    
    def _show_error_state(self, error_message: str):
        """Show error state"""
        self.title_label.text = "Error loading content"
        self.text_editor.value = f"Error: {error_message}"
        self.image_view.image = None
    
    # Event handlers
    
    def _on_save_pressed(self, widget):
        """Handle save button press"""
        if self.current_item and self.on_save:
            # Get current content based on active tab
            if self.current_tab == "text":
                content = self.text_editor.value
                self.on_save("text", content)
            elif self.current_tab == "metadata":
                # TODO: Extract metadata from form
                self.on_save("metadata", {})
        
        logger.info("Save action triggered")
    
    def _on_export_pressed(self, widget):
        """Handle export button press"""
        if self.current_item and self.on_export:
            self.on_export(self.current_item.path)
        
        logger.info("Export action triggered")
    
    def _on_previous_pressed(self, widget):
        """Handle previous button press"""
        logger.info("Previous action triggered")
    
    def _on_next_pressed(self, widget):
        """Handle next button press"""
        logger.info("Next action triggered")
    
    # Public interface
    
    def clear(self):
        """Clear the preview pane"""
        self.current_item = None
        self._show_empty_state()
    
    def set_save_callback(self, callback: Callable[[str, Any], None]):
        """Set callback for save action"""
        self.on_save = callback
    
    def set_export_callback(self, callback: Callable[[str], None]):
        """Set callback for export action"""
        self.on_export = callback 