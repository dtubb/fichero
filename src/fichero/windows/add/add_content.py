"""
Add Content Component

Shared component for adding items to the library using BaseView pattern.
Uses DetailedList for add options like LibraryView does for collections.
"""

import toga
from toga.style import Pack
from toga.constants import COLUMN
import logging
from typing import Optional, Callable, Dict, Any, List

from fichero.shared.views.base_view import BaseView
from fichero.windows.add.platform_features import detect_platform_features, get_available_add_options

# Use builtin _ function installed by translation.install()

logger = logging.getLogger(__name__)


class AddContentView(BaseView):
    """Add content view using DetailedList like LibraryView"""
    
    def __init__(self, app, on_content_added: Optional[Callable] = None, option_id: Optional[str] = None):
        """Initialize add content view using BaseView pattern"""
        self.on_content_added = on_content_added
        self.initial_option_id = option_id
        self.add_options: List[Dict[str, Any]] = []
        
        # Platform features MUST be set before calling super().__init__
        # because BaseView.__init__ calls _create_content()
        self.platform_features = detect_platform_features(app)
        
        # Initialize BaseView after platform_features is set
        super().__init__(app, is_mobile=app.is_mobile)
        
        # Create toolbars after BaseView is initialized
        self._create_toolbars()
        
        logger.info("AddContentView initialized")
    
    def _create_toolbars(self):
        """Create top and bottom toolbars for add content view"""
        try:
            from fichero.windows.add.add_top_toolbar import AddTopToolbar
            from fichero.windows.add.add_bottom_toolbar import AddBottomToolbar
            
            # Create add-specific toolbars like LibraryView does
            self.top_toolbar = AddTopToolbar(self.app, self.is_mobile)
            self.bottom_toolbar = AddBottomToolbar(self.app, self.is_mobile)
            
            # Set toolbars on the view
            self.set_toolbars(self.top_toolbar, self.bottom_toolbar)
            
            logger.info("Add content view toolbars created")
            
        except Exception as e:
            logger.error(f"Failed to create add content toolbars: {e}")
    
    def _create_content(self):
        """Create the add content using DetailedList like LibraryView"""
        try:
            # Get available options based on platform
            available_options = get_available_add_options(self.platform_features)
            self.add_options = [opt for opt in available_options if opt.get("available", True)]
            
            logger.info(f"Platform features: {self.platform_features}")
            logger.info(f"Available add options: {len(available_options)} total, {len(self.add_options)} filtered")
            for opt in self.add_options:
                logger.info(f"  - {opt['id']}: {opt['title']} (available: {opt['available']})")
            
            # Create the add options display
            self._create_add_options_display()
            
            logger.info("Add content created successfully")
            
        except Exception as e:
            logger.error(f"Failed to create add content: {e}")
            import traceback
            traceback.print_exc()
            raise  # Don't hide the error
    
    def _create_add_options_display(self):
        """Create display for add options using DetailedList"""
        try:
            # Clear any existing content
            if self.content_container:
                self.content_container.clear()
            
            if self.add_options:
                logger.info(f"Creating DetailedList with {len(self.add_options)} options")
                self._create_add_options_detailed_list()
            else:
                logger.warning("No add options available, creating placeholder")
                self._create_placeholder_content()
            
            logger.debug(f"Created display for {len(self.add_options)} add options")
            
        except Exception as e:
            logger.error(f"Failed to create add options display: {e}")
            import traceback
            traceback.print_exc()
            raise  # Don't hide the error
    
    def _create_add_options_detailed_list(self):
        """Create a detailed list view for add options using correct Toga format"""
        try:
            logger.info("Creating DetailedList for add options...")
            
            # Format add options for Toga DetailedList - correct format from manual
            option_data = []
            for option in self.add_options:
                # Use correct Toga DetailedList format: title, subtitle, icon
                item = {
                    'title': option.get('title', option.get('id', '').title()),
                    'subtitle': option.get('description', ''),
                    'icon': None,  # No icon for now - keep it simple
                    'option_id': option.get('id', '')  # Store option_id for callbacks
                }
                option_data.append(item)
                logger.info(f"  Formatted option: {item['title']}")
            
            logger.info(f"Creating DetailedList with {len(option_data)} formatted items")
            
            # Create detailed list using correct Toga format
            self.options_list = toga.DetailedList(
                data=option_data,
                on_select=self._on_option_selected,
                style=Pack(flex=1)
            )
            
            logger.info("DetailedList created successfully")
            
            if self.content_container:
                self.content_container.add(self.options_list)
                logger.info("DetailedList added to content container")
            else:
                logger.error("No content container available!")
                raise Exception("content_container is None")
                
            logger.debug(f"Created DetailedList with {len(option_data)} add options")
            
        except Exception as e:
            logger.error(f"Failed to create add options detailed list: {e}")
            import traceback
            traceback.print_exc()
            raise  # Don't hide the error
    
    def _create_placeholder_content(self):
        """Create placeholder content when no options available"""
        try:
            title = toga.Label(
                "Add to Library",
                style=Pack(
                    font_weight="bold",
                    margin=(20, 20, 15, 20),
                    color=self.text_color
                )
            )
            if self.content_container:
                self.content_container.add(title)
            
            empty_message = toga.Label(
                "No add options available on this platform",
                style=Pack(
                    font_size=14,
                    color="#8E8E93",
                    margin=(20, 20, 0, 20),
                    text_align="center"
                )
            )
            if self.content_container:
                self.content_container.add(empty_message)
                
            logger.debug("Created placeholder add content")
            
        except Exception as e:
            logger.error(f"Failed to create placeholder content: {e}")
            raise  # Don't hide errors
    
    def _on_option_selected(self, widget):
        """Handle option selection from detailed list"""
        try:
            if widget.selection:
                # Get the selected row data
                selected_row = widget.selection
                option_id = getattr(selected_row, 'option_id', None)
                option_title = getattr(selected_row, 'title', 'Unknown')
                
                logger.info(f"Add option selected: {option_title} (id: {option_id})")
                
                # Navigate to specific add option view
                if self.on_content_added and option_id:
                    self.on_content_added({'option_id': option_id, 'action': 'selected'})
                    
        except Exception as e:
            logger.error(f"Failed to handle option selection: {e}")
            import traceback
            traceback.print_exc()


class AddContent:
    """Legacy wrapper for backward compatibility"""
    
    def __init__(self, app, on_content_added: Optional[Callable] = None, option_id: Optional[str] = None):
        """Initialize legacy add content wrapper"""
        self.view = AddContentView(app, on_content_added, option_id)
    
    def create(self):
        """Create the add content UI"""
        return self.view.get_container()
