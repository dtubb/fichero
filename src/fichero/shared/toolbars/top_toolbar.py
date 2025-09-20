"""
Top Toolbar for Fichero

Toolbar for the top of views with:
- Title and navigation
- Back buttons (automatic on mobile)
- Primary actions
- Edit mode support
- Context information
"""

import toga
from toga.style import Pack
from toga.constants import ROW
import logging
from typing import Optional, Callable

from fichero.shared.toolbars.base_toolbar import BaseToolbar

logger = logging.getLogger(__name__)


class TopToolbar(BaseToolbar):
    """Top toolbar with edit mode support"""
    
    def __init__(self, app, title: str = "", auto_mobile_nav: bool = True, is_mobile: bool = None):
        """Initialize top toolbar
        
        Args:
            app: The Toga application
            title: Title to show (used for mobile back navigation)
            auto_mobile_nav: Whether to automatically add mobile back button + title
            is_mobile: Override mobile detection
        """
        self.title = title
        self.auto_mobile_nav = auto_mobile_nav
        
        # Use app.is_mobile if not provided
        if is_mobile is None:
            is_mobile = app.is_mobile
            
        super().__init__(app, is_mobile)
        
        # Top toolbar callbacks
        self.on_back: Optional[Callable] = None
        self.on_title_click: Optional[Callable] = None
        
        # Edit mode support
        self.is_edit_mode = False
        self.on_edit: Optional[Callable] = None
        self.edit_button: Optional[toga.Button] = None
        self.done_button: Optional[toga.Button] = None
        
        # Mobile navigation widgets
        self.back_button: Optional[toga.Button] = None

        
        # Create toolbar immediately
        self._create_toolbar()
    
    def _create_toolbar(self):
        """Create the top toolbar content with automatic mobile navigation"""
        try:
            # Clear any existing content
            if hasattr(self, 'left_content'):
                self.left_content.clear()
            if hasattr(self, 'center_content'):
                self.center_content.clear()
            if hasattr(self, 'right_content'):
                self.right_content.clear()
            
            # Automatic navigation pattern (mobile always, desktop when requested)
            if self.auto_mobile_nav:
                if self.is_mobile:
                    self._add_standard_mobile_navigation()
                else:
                    # Desktop also gets back button when auto_mobile_nav=True (e.g., collection views)
                    self._add_desktop_back_navigation()
            
            # Allow subclasses to add custom content
            self._add_custom_content()
            
            logger.info(f"Top toolbar created with auto mobile nav: {self.auto_mobile_nav}")
            
        except Exception as e:
            logger.error(f"Failed to create top toolbar: {e}")
    
    def _add_standard_mobile_navigation(self):
        """Add standard mobile back button + title pattern"""
        try:
            # Left: Back button (only if on_back is defined)
            if self.on_back:
                self.back_button = self._create_back_button()
                self.add_to_left(self.back_button)
            
            # Left: Title next to back button (iOS style)
            if self.title:
                # iOS HIG: 6 points distance from back button to title
                title_widget = self.add_title_left(
                    text=self.title,
                    margin_left=6,  # iOS HIG specification: 6pt from back button
                    on_click=self.on_back if self.on_back else None
                )
            
            logger.debug("Standard mobile navigation added")
            
        except Exception as e:
            logger.error(f"Failed to add mobile navigation: {e}")
    
    def _add_desktop_back_navigation(self):
        """Add desktop back button (for collection views, etc.)"""
        try:
            # Left: Back button for desktop collection views
            if self.on_back:
                self.back_button = self._create_back_button()
                self.add_to_left(self.back_button)
            
            # Center: Title
            if self.title:
                self.add_title_only(self.title)
            
            logger.debug("Desktop back navigation added")
            
        except Exception as e:
            logger.error(f"Failed to add desktop navigation: {e}")
    
    def _create_back_button(self) -> toga.Button:
        """Create a properly styled back button following iOS HIG specifications"""
        # iOS HIG specifications for back chevron:
        # - Chevron: 16x14 points
        # - Distance from left edge: 8 points
        # - Distance from bottom edge: 11 points  
        # - Minimum button height: 18 points
        # - Distance to title: 6 points
        
        if self.is_mobile:
            # iOS-compliant mobile button
            margin = (14, 8)  # (top, left) - 8pt from left edge per iOS HIG
            width = 32        # Minimum touch target (chevron 16pt + padding)
            height = 18       # Minimum height per iOS HIG
        else:
            # Desktop - similar proportions but adapted
            margin = (8, 8)   # Match title top margin
            width = 24        
            height = 18
        
        style_props = {
            'margin': margin,
            'width': width,
            'height': height
        }
        # Don't set color - use system default for better iOS appearance
        
        try:
            # Try to use the proper chevron icon (should be 16x14 points for iOS compliance)
            icon_path = self.app.paths.app / "resources/icons/toolbar/chevron.left@10x.png"
            back_button = toga.Button(
                icon=toga.Icon(icon_path),
                on_press=self._handle_back_press,
                style=Pack(**style_props)
            )
            logger.debug(f"Created iOS HIG-compliant back button with icon: {icon_path}")
            
        except Exception as e:
            logger.warning(f"Failed to load back chevron icon: {e}, using text fallback")
            # Fallback to text if icon fails
            button_text = "‹" if self.is_mobile else "‹ Back"
            back_button = toga.Button(
                button_text,
                on_press=self._handle_back_press,
                style=Pack(**style_props)
            )
            
        return back_button
    
    def _handle_back_press(self, widget):
        """Handle back button press"""
        if self.on_back:
            self.on_back()
    
    def add_edit_support(self, on_edit_callback: Callable):
        """Add edit mode support to the toolbar"""
        self.on_edit = on_edit_callback
        self._add_edit_button()
    
    def _add_edit_button(self):
        """Add edit button with proper alignment"""
        if not self.on_edit:
            return
            
        # Use same top margin as title for proper alignment
        if self.is_mobile:
            margin = (14, 12)  # Match title top margin (14px mobile)
        else:
            margin = (8, 12)  # Match title top margin (8px desktop)
        
        style_props = {'margin': margin}
        if self.TITLE_COLOR:  # Only set color on mobile
            style_props['color'] = self.TITLE_COLOR
            
        self.edit_button = toga.Button(
            "Edit",
            on_press=self._handle_edit_press,
            style=Pack(**style_props)
        )
        self.add_to_right(self.edit_button)
    
    def _handle_edit_press(self, widget):
        """Handle edit button press"""
        if self.on_edit:
            self.on_edit()
    
    def set_edit_mode(self, is_edit_mode: bool):
        """Set edit mode and update button layout (iOS style)"""
        try:
            self.is_edit_mode = is_edit_mode
            
            if is_edit_mode:
                # Edit mode: Hide back button, move "Done" to top left, hide edit button
                if self.back_button:
                    self.back_button.style.visibility = 'hidden'
                    
                if self.edit_button:
                    self.edit_button.style.visibility = 'hidden'
                
                # Create Done button on left side
                self._create_done_button()
                
            else:
                # Normal mode: Show back button, show edit button on right
                if self.back_button:
                    self.back_button.style.visibility = 'visible'
                    
                if self.edit_button:
                    self.edit_button.style.visibility = 'visible'
                
                # Remove Done button if it exists
                self._remove_done_button()
                    
            logger.debug(f"Edit mode set to: {is_edit_mode}")
            
        except Exception as e:
            logger.error(f"Failed to set edit mode: {e}")
    
    def _create_done_button(self):
        """Create Done button on the left side"""
        try:
            # Remove any existing done button first
            self._remove_done_button()
            
            # Use same top margin as title for proper alignment
            if self.is_mobile:
                margin = (14, 12)  # Match title top margin (14px mobile)
            else:
                margin = (8, 12)  # Match title top margin (8px desktop)
            
            style_props = {'margin': margin}
            if self.TITLE_COLOR:
                style_props['color'] = self.TITLE_COLOR
                
            self.done_button = toga.Button(
                "Done",
                on_press=self._handle_done_press,
                style=Pack(**style_props)
            )
            self.add_to_left(self.done_button)
            
        except Exception as e:
            logger.error(f"Failed to create done button: {e}")
    
    def _remove_done_button(self):
        """Remove Done button if it exists"""
        try:
            if hasattr(self, 'done_button') and self.done_button:
                if hasattr(self, 'left_content') and self.done_button in self.left_content.children:
                    self.left_content.remove(self.done_button)
                self.done_button = None
                
        except Exception as e:
            logger.error(f"Failed to remove done button: {e}")
    
    def _handle_done_press(self, widget):
        """Handle done button press"""
        if self.on_edit:
            self.on_edit()
    
    def clear_buttons(self):
        """Clear all buttons from toolbar"""
        try:
            if hasattr(self, 'left_content'):
                self.left_content.clear()
            if hasattr(self, 'center_content'):
                self.center_content.clear()
            if hasattr(self, 'right_content'):
                self.right_content.clear()
            
            # Reset button references
            self.back_button = None
            self.edit_button = None
            self.done_button = None
            
        except Exception as e:
            logger.error(f"Failed to clear buttons: {e}")
    
    def add_title_only(self, title: str):
        """Add just the title to center"""
        try:
            # Create title label with proper styling and positioning
            style_props = {
                'text_align': 'center', 
                'flex': 1,
                'margin_top': 14 if self.is_mobile else 8  # Better vertical centering
            }
            # Don't set color - use system default
            if self.TITLE_FONT_WEIGHT:
                style_props['font_weight'] = self.TITLE_FONT_WEIGHT
                
            title_label = toga.Label(
                title,
                style=Pack(**style_props)
            )
            self.add_to_center(title_label)
            
        except Exception as e:
            logger.error(f"Failed to add title: {e}")
    
    def register_edit_callback(self, on_edit: Callable):
        """Register edit callback and add edit button"""
        self.on_edit = on_edit
        self._add_edit_button()
    
    def _add_custom_content(self):
        """Override this in subclasses to add custom content"""
        pass
    
    def set_back_callback(self, callback: Callable):
        """Set the back button callback for mobile navigation"""
        self.on_back = callback
        # Recreate the toolbar to show the back button now that we have a callback
        self._create_toolbar()
        logger.debug("Back callback set on TopToolbar and toolbar recreated") 