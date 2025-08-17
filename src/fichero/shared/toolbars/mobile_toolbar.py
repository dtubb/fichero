"""
Mobile Toolbar Manager

Manages toolbar functionality for mobile platforms (iOS, Android).
Creates custom button-based footer toolbars for consistent bottom navigation.

- iOS: Bottom footer toolbar for consistent mobile UX
- Android: Bottom footer toolbar following Material Design patterns
"""

import toga
from toga.style import Pack
from toga.constants import ROW, COLUMN
import logging
from typing import Optional, Dict, Callable, Any, List

logger = logging.getLogger(__name__)


class MobileToolbar:
    """
    Mobile footer toolbar manager for consistent bottom navigation.
    
    - iOS: Creates bottom footer with essential actions
    - Android: Creates bottom footer following Material Design
    """
    
    def __init__(self, app, view_manager, is_ios: bool = False):
        """Initialize mobile footer toolbar"""
        self.app = app
        self.view_manager = view_manager
        self.is_ios = is_ios
        self.is_android = not is_ios
        
        # Toolbar components
        self.toolbar_container: Optional[toga.Box] = None
        self.buttons: Dict[str, toga.Button] = {}
        
        # Action callbacks
        self.action_callbacks: Dict[str, Callable] = {}
        
    def create_toolbar(self) -> toga.Box:
        """
        Create the mobile footer toolbar
        
        Returns:
            toga.Box: The footer toolbar container
        """
        if self.is_ios:
            return self._create_ios_footer()
        else:
            return self._create_android_footer()
    
    def _create_ios_footer(self) -> toga.Box:
        """Create iOS-style bottom footer toolbar"""
        self.toolbar_container = toga.Box(
            style=Pack(
                direction=ROW,
                margin=(10, 15, 15, 15),  # Margin for footer spacing
                background_color="#f8f8f8"
            )
        )
        
        # Essential action buttons for iOS footer navigation
        buttons_config = [
            ("collection", "Library", self._on_collection),
            ("add", "Add", self._on_add),
            ("process", "Process", self._on_process),
            ("activity", "Activity", self._on_activity),
            # ("plans", "Plans", self._on_plans),  # HIDDEN
            # ("prompts", "Prompts", self._on_prompts),  # HIDDEN
            ("settings", "Settings", self._on_settings)
        ]
        
        for btn_id, text, callback in buttons_config:
            btn = self._create_button(btn_id, text, callback)
            self.toolbar_container.add(btn)
        
        logger.info("Created iOS bottom footer toolbar")
        return self.toolbar_container
    
    def _create_android_footer(self) -> toga.Box:
        """Create Android-style bottom footer toolbar"""
        self.toolbar_container = toga.Box(
            style=Pack(
                direction=ROW,
                margin=(10, 5, 15, 5),  # Margin for footer spacing
                background_color="#2196F3"  # Material Design primary color
            )
        )
        
        # Essential action buttons for bottom navigation
        buttons_config = [
            ("collection", "Library", self._on_collection),
            ("add", "Add", self._on_add),
            ("process", "Process", self._on_process),
            ("activity", "Activity", self._on_activity),
            # ("plans", "Plans", self._on_plans),  # HIDDEN
            # ("prompts", "Prompts", self._on_prompts),  # HIDDEN
            ("settings", "Settings", self._on_settings)
        ]
        
        for btn_id, text, callback in buttons_config:
            btn = self._create_button(btn_id, text, callback)
            btn.style.background_color = "transparent"
            btn.style.color = "white"
            self.toolbar_container.add(btn)
        
        logger.info("Created Android bottom footer toolbar")
        return self.toolbar_container
    
    def _create_button(self, button_id: str, text: str, callback: Callable) -> toga.Button:
        """Create a toolbar button with icon support"""
        # Icon mapping for different button types
        icon_map = {
            "collection": "resources/icons/list_bullet_32.png",
            "add": "resources/icons/plus_32.png", 
            "process": "resources/icons/process/process.png",
            "activity": "resources/icons/activity_32.png",
            "plans": "resources/icons/plan/plan.png",
            "prompts": "resources/icons/prompt/prompt.png",
            "settings": "resources/icons/gear_32.png"
        }
        
        # Try to create button with icon, fallback to text
        icon_path = icon_map.get(button_id)
        if icon_path:
            try:
                icon = toga.Icon(icon_path)
                button = toga.Button(
                    icon=icon,
                    on_press=callback,
                    style=Pack(margin=5, width=44, height=44)  # Fixed size for mobile icons
                )
            except Exception as e:
                logger.warning(f"Failed to load icon {icon_path}: {e}, using text fallback")
                button = toga.Button(
                    text=text,
                    on_press=callback,
                    style=Pack(margin=5)
                )
        else:
            button = toga.Button(
                text=text,
                on_press=callback,
                style=Pack(margin=5)
            )
        
        self.buttons[button_id] = button
        return button
    
    def register_action_callback(self, action_name: str, callback: Callable):
        """Register a callback for a specific action"""
        self.action_callbacks[action_name] = callback
        logger.info(f"Registered callback for action: {action_name}")
    
    def update_button_state(self, button_id: str, enabled: bool = True, text: Optional[str] = None):
        """
        Update the state of a toolbar button
        
        Args:
            button_id: ID of the button
            enabled: Whether the button is enabled
            text: New text for the button (optional)
        """
        if button_id in self.buttons:
            button = self.buttons[button_id]
            button.enabled = enabled
            
            if text:
                button.text = text
                
            logger.info(f"Updated button {button_id}: enabled={enabled}")
    
    def show(self):
        """Show the mobile toolbar"""
        if self.toolbar_container:
            self.toolbar_container.style.visibility = "visible"
    
    def hide(self):
        """Hide the mobile toolbar"""
        if self.toolbar_container:
            self.toolbar_container.style.visibility = "hidden"
    
    # Default action handlers - these call registered callbacks
    
    def _on_back(self, widget):
        """Handle back button press"""
        if self.view_manager:
            self.view_manager.go_back()
    
    def _on_collection(self, widget):
        """Handle collection button press"""
        self._call_action_callback("collection")
    
    def _on_add(self, widget):
        """Handle add button press"""
        self._call_action_callback("add")
    
    def _on_process(self, widget):
        """Handle process button press"""
        self._call_action_callback("process")
    
    def _on_settings(self, widget):
        """Handle settings button press"""
        self._call_action_callback("settings")
    
    def _on_activity(self, widget):
        """Handle activity button press"""
        self._call_action_callback("activity")
    
    # def _on_plans(self, widget):  # HIDDEN
    #     """Handle plans button press"""
    #     self._call_action_callback("plans")
    
    # def _on_prompts(self, widget):  # HIDDEN
    #     """Handle prompts button press"""
    #     self._call_action_callback("prompts")
    
    def _on_about(self, widget):
        """Handle about button press"""
        self._call_action_callback("about")
    
    def _call_action_callback(self, action_name: str):
        """Call a registered action callback"""
        if action_name in self.action_callbacks:
            try:
                self.action_callbacks[action_name]()
            except Exception as e:
                logger.error(f"Error calling action callback {action_name}: {e}")
        else:
            logger.warning(f"No callback registered for action: {action_name}") 