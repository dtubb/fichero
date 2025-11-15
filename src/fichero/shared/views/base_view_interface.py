"""
Base View Interface - Standard interface all views must implement.

This interface establishes the contract for all views in the Fichero navigation system,
enabling uniform view management, focus tracking, state persistence, and window management.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import toga

from .view_types import ViewType


class BaseViewInterface(ABC):
    """
    Interface that all views must implement for the universal navigation system.

    This interface enables:
    - Uniform view management across the application
    - Focus tracking and visual indicators
    - State persistence (save/restore complete app state)
    - Window management (views can be windowed or embedded)
    - Navigation controller integration

    Example:
        class MyView(BaseViewInterface):
            def __init__(self, app, is_mobile):
                self._view_id = f"myview_{id(self)}"
                self._view_type = ViewType.CUSTOM
                self._is_focused = False
                self.container = toga.Box()
                # ... implement rest of interface
    """

    # ========================================
    # Required Properties
    # ========================================

    @property
    @abstractmethod
    def view_id(self) -> str:
        """
        Unique identifier for this view instance.

        Returns:
            Unique string identifier (e.g., "library_1", "preview_main")

        Note:
            This ID is used by NavigationController and WindowManager to track views.
            Should be stable across app restarts if view is persistent.
        """
        pass

    @property
    @abstractmethod
    def view_type(self) -> ViewType:
        """
        Type of view (LIBRARY, COLLECTION, STEP, etc.)

        Returns:
            ViewType enum value

        Note:
            Used for view organization, menu commands, and state management.
        """
        pass

    @property
    @abstractmethod
    def container(self) -> toga.Box:
        """
        The root container widget for this view.

        Returns:
            Toga Box containing all view content

        Note:
            This is what gets added to layouts or windows.
            Should include toolbar if view has one.
        """
        pass

    @property
    def toolbar(self) -> Optional[toga.Box]:
        """
        Toolbar for this view (if any).

        Returns:
            Toga Box with toolbar widgets, or None if view has no toolbar

        Note:
            Optional - return None if view doesn't have a toolbar.
            Top-level toolbars are typically managed by MainWindow.
        """
        return None

    @property
    @abstractmethod
    def is_focused(self) -> bool:
        """
        Whether this view currently has focus.

        Returns:
            True if view is focused, False otherwise

        Note:
            Focus is managed by FocusTracker in NavigationController.
            Visual focus indicator should reflect this state.
        """
        pass

    # ========================================
    # Required Methods
    # ========================================

    @abstractmethod
    def set_focused(self, focused: bool):
        """
        Update focus state and visual indicator.

        Args:
            focused: True to focus view, False to unfocus

        Note:
            Should update internal state and visual focus border/highlight.
            Called by NavigationController when focus changes.

        Example:
            def set_focused(self, focused: bool):
                self._is_focused = focused
                if focused:
                    self.container.style.background_color = rgb(0, 122, 204)
                else:
                    if hasattr(self.container.style, 'background_color'):
                        del self.container.style.background_color
        """
        pass

    @abstractmethod
    def get_state(self) -> Dict[str, Any]:
        """
        Return current state for persistence.

        Returns:
            Dictionary containing all state needed to restore this view

        Note:
            Used by WorkspaceManager to save complete app state.
            Should include enough information to recreate view in same state.

        Example:
            def get_state(self) -> Dict[str, Any]:
                return {
                    'view_id': self.view_id,
                    'view_type': self.view_type.value,
                    'selected_item': self.current_selection,
                    'scroll_position': self.scroll_pos,
                    # ... other view-specific state
                }
        """
        pass

    @abstractmethod
    def restore_state(self, state: Dict[str, Any]):
        """
        Restore view from saved state.

        Args:
            state: Dictionary returned by get_state()

        Note:
            Used by WorkspaceManager to restore app state on startup or workspace load.
            Should handle missing keys gracefully (for backward compatibility).

        Example:
            def restore_state(self, state: Dict[str, Any]):
                if 'selected_item' in state:
                    self.select_item(state['selected_item'])
                if 'scroll_position' in state:
                    self.scroll_to(state['scroll_position'])
        """
        pass

    def can_close(self) -> bool:
        """
        Whether view can be closed (check for unsaved changes).

        Returns:
            True if view can close safely, False if user needs to save/cancel first

        Note:
            Called by WindowManager before closing a view or window.
            Should prompt user if there are unsaved changes.

        Example:
            def can_close(self) -> bool:
                if self.has_unsaved_changes:
                    return self._prompt_save()  # Show dialog
                return True
        """
        return True  # Default: always allow close

    def on_close(self):
        """
        Cleanup when view is closed.

        Note:
            Called by WindowManager after view is removed from layout/window.
            Use for resource cleanup (close files, stop timers, etc.)

        Example:
            def on_close(self):
                if self.file_handle:
                    self.file_handle.close()
                if self.timer:
                    self.timer.cancel()
        """
        pass  # Default: no cleanup needed

    # ========================================
    # Optional Helper Methods
    # ========================================

    def get_title(self) -> str:
        """
        Get display title for this view.

        Returns:
            Human-readable title for window title bar or tab

        Note:
            Optional - override to provide dynamic titles.

        Example:
            def get_title(self) -> str:
                if self.current_file:
                    return f"{self.current_file.name} - Preview"
                return "Preview"
        """
        return self.view_type.value.capitalize()

    def get_menu_commands(self) -> list:
        """
        Get view-specific menu commands.

        Returns:
            List of Command objects for this view's menu items

        Note:
            Optional - override to add view-specific commands to app menu.

        Example:
            def get_menu_commands(self) -> list:
                return [
                    Command('view.refresh', 'Refresh', self._on_refresh, shortcut='cmd+r'),
                    Command('view.export', 'Export...', self._on_export),
                ]
        """
        return []


__all__ = ['BaseViewInterface']
