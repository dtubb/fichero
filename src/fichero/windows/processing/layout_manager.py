"""
Processing Layout Manager

Handles UI layout and assembly for the processing window.
Separates layout concerns from business logic.
"""

import toga
from toga.style import Pack
from toga.constants import COLUMN, ROW, CENTER
import logging
from typing import Optional, Callable
import gettext

# Delayed translation function - calls gettext at runtime
def _translate(text):
    """Get translation at runtime when UI is created"""
    try:
        return gettext.gettext(text)
    except:
        return text

logger = logging.getLogger(__name__)


class ProcessingLayoutManager:
    """Manages processing window layout and UI assembly"""
    
    def __init__(self, app, show_back_button: bool = False):
        """Initialize layout manager"""
        self.app = app
        self.show_back_button = show_back_button
        
        # UI containers (will be created)
        self.main_container: Optional[toga.Box] = None
        self.content_container: Optional[toga.Box] = None
        self.footer_container: Optional[toga.Box] = None
        self.back_button_container: Optional[toga.Box] = None
        
        # Control elements
        self.reset_btn: Optional[toga.Button] = None
        self.process_btn: Optional[toga.Button] = None
        self.activity_indicator: Optional[toga.ActivityIndicator] = None
        self.back_button: Optional[toga.Button] = None
    
    def create_main_layout(self, 
                          folder_selector_widget,
                          plan_selector_widget, 
                          initial_content_widget,
                          on_reset: Callable,
                          on_process: Callable,
                          on_back: Optional[Callable] = None) -> toga.Box:
        """Create the main layout with all components"""
        
        # Main container
        self.main_container = toga.Box(
            style=Pack(direction=COLUMN, flex=1, margin=10)
        )
        
        # Add back button if needed
        if self.show_back_button and on_back:
            self._create_back_button(on_back)
            self.main_container.add(self.back_button_container)
        
        # Folder selection section
        self.main_container.add(folder_selector_widget)
        
        # Content section (description view or progress display)
        self.content_container = toga.Box(
            style=Pack(direction=COLUMN, flex=1)
        )
        self.content_container.add(initial_content_widget)
        self.main_container.add(self.content_container)
        
        # Footer section
        self._create_footer(plan_selector_widget, on_reset, on_process)
        self.main_container.add(self.footer_container)
        
        return self.main_container
    
    def _create_back_button(self, on_back: Callable):
        """Create back button for mobile navigation"""
        self.back_button_container = toga.Box(
            style=Pack(direction=ROW, alignment=CENTER, margin_bottom=10)
        )
        
        self.back_button = toga.Button(
            "← Back",
            on_press=lambda widget: on_back() if on_back else None,
            style=Pack(font_size=14, margin_bottom=5)
        )
        
        self.back_button_container.add(self.back_button)
    
    def _create_footer(self, plan_selector_widget, on_reset: Callable, on_process: Callable):
        """Create footer with plan selector and control buttons"""
        
        # Footer container
        self.footer_container = toga.Box(
            style=Pack(direction=COLUMN, margin_top=10)
        )
        
        # Plan selector section
        self.footer_container.add(plan_selector_widget)
        
        # Control buttons section
        controls_container = toga.Box(
            style=Pack(direction=ROW, alignment=CENTER, margin_top=10)
        )
        
        # Reset button (hidden initially)
        self.reset_btn = toga.Button(
            _translate("cancel"),
            on_press=lambda widget: on_reset(),
            style=Pack(font_size=12, height=32, visibility='hidden')
        )
        controls_container.add(self.reset_btn)
        
        # Activity indicator (hidden initially)
        self.activity_indicator = toga.ActivityIndicator(
            style=Pack(margin_left=10, visibility='hidden')
        )
        controls_container.add(self.activity_indicator)
        
        # Process button (hidden initially)
        self.process_btn = toga.Button(
            _translate("process"), 
            on_press=lambda widget: on_process(),
            style=Pack(font_size=12, height=32, margin_left=10, visibility='hidden')
        )
        controls_container.add(self.process_btn)
        
        self.footer_container.add(controls_container)
    
    def switch_content(self, new_content_widget):
        """Switch the main content area to a new widget"""
        if self.content_container:
            # Clear existing content
            self.content_container.clear()
            # Add new content
            self.content_container.add(new_content_widget)
            logger.info("Switched content area")
    
    def show_control_buttons(self):
        """Show the control buttons (Cancel/Process)"""
        if self.reset_btn:
            self.reset_btn.style.visibility = 'visible'
        if self.process_btn:
            self.process_btn.style.visibility = 'visible'
        logger.info("Control buttons shown")
    
    def hide_control_buttons(self):
        """Hide the control buttons"""
        if self.reset_btn:
            self.reset_btn.style.visibility = 'hidden'
        if self.process_btn:
            self.process_btn.style.visibility = 'hidden'
        logger.info("Control buttons hidden")
    
    def show_activity_indicator(self):
        """Show the activity indicator"""
        if self.activity_indicator:
            self.activity_indicator.style.visibility = 'visible'
            self.activity_indicator.start()
        logger.info("Activity indicator started")
    
    def hide_activity_indicator(self):
        """Hide the activity indicator"""
        if self.activity_indicator:
            self.activity_indicator.stop()
            self.activity_indicator.style.visibility = 'hidden'
        logger.info("Activity indicator stopped")
    
    def update_button_states(self, can_process: bool, is_processing: bool):
        """Update button states based on processing state"""
        if self.process_btn:
            self.process_btn.enabled = can_process and not is_processing
        
        if self.reset_btn:
            # Always allow cancel/reset
            self.reset_btn.enabled = True
            
        logger.info(f"Button states updated: can_process={can_process}, is_processing={is_processing}")
    
    def get_main_container(self) -> Optional[toga.Box]:
        """Get the main container"""
        return self.main_container 