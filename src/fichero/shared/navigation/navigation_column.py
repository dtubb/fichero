"""
Navigation Column Component

Single-column drill-down navigation using Toga's DetailedList.
Works identically on desktop and mobile platforms.
"""

import toga
from toga.style import Pack
from toga.constants import COLUMN, ROW
import logging
from typing import Optional, List, Callable, Any, Dict

from fichero.shared.navigation.navigation_state import NavigationState, NavigationLevel, NavigationItem

logger = logging.getLogger(__name__)


class NavigationColumn:
    """
    Single-column navigation component using DetailedList.
    
    Features:
    - DetailedList for rich item display
    - Drill-down navigation
    - Back button
    - Breadcrumb path display
    - Action buttons at bottom
    """
    
    def __init__(self, navigation_state: NavigationState, is_mobile: bool = False):
        """Initialize navigation column"""
        self.navigation_state = navigation_state
        self.is_mobile = is_mobile
        
        # UI components
        self.container: Optional[toga.Box] = None
        self.header: Optional[toga.Box] = None
        self.back_button: Optional[toga.Button] = None
        self.breadcrumb_label: Optional[toga.Label] = None
        self.detailed_list: Optional[toga.DetailedList] = None
        self.actions_container: Optional[toga.Box] = None
        
        # Data
        self.list_data: List[Dict[str, Any]] = []
        
        # Callbacks
        self.on_item_drill_down: Optional[Callable[[NavigationItem], None]] = None
        self.on_item_select: Optional[Callable[[NavigationItem], None]] = None
        self.on_action: Optional[Callable[[str], None]] = None
        
        # Set up navigation state callbacks
        self._setup_navigation_callbacks()
        
    def create(self) -> toga.Box:
        """Create the navigation column UI"""
        # Main container
        self.container = toga.Box(
            style=Pack(
                direction=COLUMN,
                flex=1
            )
        )
        
        # Create header with back button and breadcrumb
        self._create_header()
        
        # Create detailed list
        self._create_detailed_list()
        
        # Create action buttons
        self._create_actions()
        
        # Add components to container
        self.container.add(self.header)
        self.container.add(self.detailed_list)
        self.container.add(self.actions_container)
        
        # Load initial data
        self._refresh_list()
        
        return self.container
    
    def _create_header(self):
        """Create header with back button and breadcrumb"""
        self.header = toga.Box(
            style=Pack(
                direction=COLUMN,
                margin_bottom=10
            )
        )
        
        # Back button container
        back_container = toga.Box(
            style=Pack(
                direction=ROW,
                margin_bottom=5
            )
        )
        
        # Back button
        self.back_button = toga.Button(
            text="← Back",
            on_press=self._on_back_pressed,
            style=Pack(
                margin_right=10
            ),
            enabled=self.navigation_state.can_go_back()
        )
        back_container.add(self.back_button)
        
        # Breadcrumb label
        self.breadcrumb_label = toga.Label(
            text=self.navigation_state.get_current_path_string(),
            style=Pack(
                font_size=12,
                color="#666666",
                flex=1
            )
        )
        back_container.add(self.breadcrumb_label)
        
        self.header.add(back_container)
        
        # Level title
        level_title = self._get_level_title()
        level_label = toga.Label(
            text=level_title,
            style=Pack(
                font_size=16,
                font_weight="bold",
                margin_bottom=5
            )
        )
        self.header.add(level_label)
    
    def _create_detailed_list(self):
        """Create the detailed list for navigation items"""
        self.detailed_list = toga.DetailedList(
            data=self.list_data,
            style=Pack(
                flex=1,
                margin_bottom=10
            ),
            on_select=self._on_list_select
        )
    
    def _create_actions(self):
        """Create action buttons at bottom"""
        self.actions_container = toga.Box(
            style=Pack(
                direction=ROW,
                justify_content="center",
                margin_top=10
            )
        )
        
        # Actions based on current level
        current_level = self.navigation_state.get_current_level()
        
        if current_level == NavigationLevel.COLLECTIONS:
            # Add collection action
            add_button = toga.Button(
                text="+ Add Collection",
                on_press=lambda w: self._trigger_action("add_collection"),
                style=Pack(margin_right=5)
            )
            self.actions_container.add(add_button)
            
            # Import action
            import_button = toga.Button(
                text="📁 Import",
                on_press=lambda w: self._trigger_action("import"),
                style=Pack(margin_left=5)
            )
            self.actions_container.add(import_button)
            
        elif current_level == NavigationLevel.FOLDERS:
            # Add folder action
            add_folder_button = toga.Button(
                text="+ Add Folder",
                on_press=lambda w: self._trigger_action("add_folder"),
                style=Pack(margin_right=5)
            )
            self.actions_container.add(add_folder_button)
            
            # Process action
            process_button = toga.Button(
                text="⚙️ Process",
                on_press=lambda w: self._trigger_action("process"),
                style=Pack(margin_left=5)
            )
            self.actions_container.add(process_button)
            
        elif current_level == NavigationLevel.DOCUMENTS:
            # Add document action
            add_doc_button = toga.Button(
                text="+ Add Document",
                on_press=lambda w: self._trigger_action("add_document"),
                style=Pack(margin_right=5)
            )
            self.actions_container.add(add_doc_button)
            
            # Batch process action
            batch_button = toga.Button(
                text="📋 Batch Process",
                on_press=lambda w: self._trigger_action("batch_process"),
                style=Pack(margin_left=5)
            )
            self.actions_container.add(batch_button)
            
        elif current_level == NavigationLevel.PAGES:
            # View all pages action
            view_all_button = toga.Button(
                text="👁️ View All",
                on_press=lambda w: self._trigger_action("view_all"),
                style=Pack(margin_right=5)
            )
            self.actions_container.add(view_all_button)
            
            # Export action
            export_button = toga.Button(
                text="💾 Export",
                on_press=lambda w: self._trigger_action("export"),
                style=Pack(margin_left=5)
            )
            self.actions_container.add(export_button)
    
    def _setup_navigation_callbacks(self):
        """Set up callbacks from navigation state"""
        self.navigation_state.on_level_change = self._on_level_changed
        self.navigation_state.on_selection_change = self._on_selection_changed
    
    def _on_level_changed(self, level: NavigationLevel, items: List[NavigationItem]):
        """Handle navigation level change"""
        logger.info(f"Navigation level changed to: {level.value}")
        self._refresh_list()
        self._update_header()
        self._update_actions()
    
    def _on_selection_changed(self, item: Optional[NavigationItem]):
        """Handle item selection change"""
        if item:
            logger.info(f"Selection changed to: {item.name}")
            
            # Notify external callback
            if self.on_item_select:
                self.on_item_select(item)
    
    def _refresh_list(self):
        """Refresh the detailed list with current items"""
        try:
            items = self.navigation_state.get_current_items()
            
            # Convert navigation items to DetailedList data format
            self.list_data = []
            for item in items:
                # Create detailed list item
                list_item = {
                    'title': item.name,
                    'subtitle': self._get_item_subtitle(item),
                    'icon': self._get_item_icon(item),
                    '_navigation_item': item  # Store reference to original item
                }
                self.list_data.append(list_item)
            
            # Always clear and recreate the detailed list to reset selection state
            if self.detailed_list:
                try:
                    # Remove from container if it exists
                    if self.container and self.detailed_list in self.container.children:
                        self.container.remove(self.detailed_list)
                    logger.debug("Cleared existing navigation DetailedList to reset selection")
                except Exception as e:
                    logger.debug(f"Note: Could not remove existing navigation DetailedList: {e}")
            
            # Create new DetailedList with fresh data
            self.detailed_list = toga.DetailedList(
                data=self.list_data,
                style=Pack(
                    flex=1,
                    margin_bottom=10
                ),
                on_select=self._on_list_select
            )
            
            # Add it back to the container
            if self.container:
                # Insert it in the correct position (after header, before actions)
                if hasattr(self, 'actions_container') and self.actions_container in self.container.children:
                    # Insert before actions container
                    actions_index = self.container.children.index(self.actions_container)
                    self.container.insert(actions_index, self.detailed_list)
                else:
                    # Add at the end
                    self.container.add(self.detailed_list)
                
            logger.info(f"Refreshed list with {len(self.list_data)} items")
            
        except Exception as e:
            logger.error(f"Failed to refresh list: {e}")
    
    def _get_item_subtitle(self, item: NavigationItem) -> str:
        """Get subtitle for navigation item"""
        if item.level == NavigationLevel.COLLECTIONS:
            count = item.metadata.get('folder_count', 0)
            return f"{count} folders"
        elif item.level == NavigationLevel.FOLDERS:
            count = item.metadata.get('document_count', 0)
            return f"{count} documents"
        elif item.level == NavigationLevel.DOCUMENTS:
            count = item.metadata.get('page_count', 0)
            return f"{count} pages"
        elif item.level == NavigationLevel.PAGES:
            size = item.metadata.get('file_size', '')
            return f"Size: {size}" if size else "Page"
        
        return ""
    
    def _get_item_icon(self, item: NavigationItem) -> Optional[str]:
        """Get icon for navigation item"""
        # Note: Toga's DetailedList icon support may be limited
        # This is a placeholder for future icon implementation
        level_icons = {
            NavigationLevel.COLLECTIONS: "📚",
            NavigationLevel.FOLDERS: "📁", 
            NavigationLevel.DOCUMENTS: "📄",
            NavigationLevel.PAGES: "🖼️"
        }
        return level_icons.get(item.level)
    
    def _get_level_title(self) -> str:
        """Get title for current level"""
        level_titles = {
            NavigationLevel.COLLECTIONS: "Collections",
            NavigationLevel.FOLDERS: "Folders",
            NavigationLevel.DOCUMENTS: "Documents", 
            NavigationLevel.PAGES: "Pages"
        }
        return level_titles.get(self.navigation_state.get_current_level(), "Library")
    
    def _update_header(self):
        """Update header elements"""
        if self.back_button:
            self.back_button.enabled = self.navigation_state.can_go_back()
            
        if self.breadcrumb_label:
            self.breadcrumb_label.text = self.navigation_state.get_current_path_string()
    
    def _update_actions(self):
        """Update action buttons for current level"""
        # Clear existing actions
        if self.actions_container:
            self.actions_container.clear()
            
        # Recreate actions for current level
        self._create_actions()
    
    def _on_list_select(self, widget):
        """Handle detailed list selection"""
        try:
            if widget.selection:
                selected_data = widget.selection
                navigation_item = selected_data.get('_navigation_item')
                
                if navigation_item:
                    # Update navigation state selection
                    self.navigation_state.select_item(navigation_item)
                    
                    # Check if this item can be drilled down
                    if navigation_item.has_children:
                        # Double-tap or enter to drill down
                        # For now, auto drill-down on select
                        self._drill_down_item(navigation_item)
                        
        except Exception as e:
            logger.error(f"Failed to handle list selection: {e}")
    
    def _drill_down_item(self, item: NavigationItem):
        """Drill down into selected item"""
        try:
            self.navigation_state.drill_down(item)
            
            # Notify external callback
            if self.on_item_drill_down:
                self.on_item_drill_down(item)
                
        except Exception as e:
            logger.error(f"Failed to drill down into {item.name}: {e}")
    
    def _on_back_pressed(self, widget):
        """Handle back button press"""
        self.navigation_state.go_back()
    
    def _trigger_action(self, action_name: str):
        """Trigger an action callback"""
        if self.on_action:
            self.on_action(action_name)
        else:
            logger.info(f"Action triggered: {action_name}")
    
    # Public interface
    
    def refresh(self):
        """Refresh the navigation column"""
        self.navigation_state.refresh_current_level()
    
    def set_drill_down_callback(self, callback: Callable[[NavigationItem], None]):
        """Set callback for item drill-down"""
        self.on_item_drill_down = callback
    
    def set_select_callback(self, callback: Callable[[NavigationItem], None]):
        """Set callback for item selection"""
        self.on_item_select = callback
    
    def set_action_callback(self, callback: Callable[[str], None]):
        """Set callback for action buttons"""
        self.on_action = callback 