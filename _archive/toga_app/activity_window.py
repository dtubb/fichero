"""
Activity Monitor Window for Fichero application.

Shows real-time task progress and status.
"""

import logging
from typing import Optional

import toga

from fichero.director.monitoring.displays.gui_display import GUITaskDisplay
from fichero.director.monitoring.task_monitor import TaskMonitor

logger = logging.getLogger(__name__)


class ActivityMonitorWindow:
    """Activity monitor window showing task progress."""

    def __init__(self, app):
        self.app = app
        self.window: Optional[toga.Window] = None
        self._display: Optional[GUITaskDisplay] = None
        self._is_visible = False
        logger.info("ActivityMonitorWindow initialized")

    def show(self):
        """Show the activity monitor window."""
        if self.window is None:
            self._create_window()

        if not self._is_visible:
            self.window.show()
            self._is_visible = True
            if self._display:
                self._display.start_monitoring()
            logger.info("Activity monitor window shown")

    def hide(self):
        """Hide the activity monitor window."""
        if self.window and self._is_visible:
            self.window.hide()
            self._is_visible = False
            if self._display:
                self._display.stop_monitoring()
            logger.info("Activity monitor window hidden")

    def close(self):
        """Close the activity monitor window."""
        if self.window:
            if hasattr(self.app, 'window_state_tracker') and self.app.window_state_tracker:
                self.app.window_state_tracker.save_window_state("activity")

            if self._display:
                self._display.stop_monitoring()

            self.window.close()
            self.window = None
            self._display = None
            self._is_visible = False
            logger.info("Activity monitor window closed")

    def _create_window(self):
        """Create the activity monitor window."""
        try:
            # Get director from app
            director = getattr(self.app, 'director', None)
            if director is None:
                components = getattr(self.app, 'components', {})
                director = components.get('director')

            if director is None:
                raise RuntimeError("Director not available")

            # Create task display
            task_monitor = TaskMonitor.get_instance(director)
            self._display = GUITaskDisplay(task_monitor, app=self.app, filter_document_id=None)

            # Create window
            self.window = toga.Window(
                title="Fichero Activity Monitor",
                size=(1000, 500),
                resizable=True,
                content=self._display.container
            )

            self._center_window()

            # Register for state persistence
            if hasattr(self.app, 'window_state_tracker') and self.app.window_state_tracker:
                self.app.window_state_tracker.register_window("activity", self.window, restore=True)

            logger.info("Activity monitor window created")

        except Exception as e:
            logger.error(f"Failed to create activity monitor window: {e}")
            raise

    def _center_window(self):
        """Center window on screen."""
        try:
            screen = self.app.screens[0]
            x = (screen.size.width - self.window.size.width) // 2
            y = (screen.size.height - self.window.size.height) // 2
            self.window.position = (x, y)
        except Exception:
            pass

    def start_monitoring(self):
        """Start monitoring tasks."""
        if self._display:
            self._display.start_monitoring()

    def stop_monitoring(self):
        """Stop monitoring tasks."""
        if self._display:
            self._display.stop_monitoring()
