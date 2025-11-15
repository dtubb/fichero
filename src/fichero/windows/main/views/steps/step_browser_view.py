"""
StepBrowserView - Standalone view wrapper for StepBrowser component

Shows the list of processing steps (Original, transcribe, enhance, etc.)
This is Column 3 in the 5-column layout.
"""
import logging
from typing import Optional, List

import toga
from toga.style import Pack
from toga.constants import COLUMN

from fichero.shared.views.base_view import BaseView
from fichero.windows.main.views.preview.step_browser import StepBrowser
from fichero.windows.main.views.preview.step_manager import Step

logger = logging.getLogger(__name__)


class StepBrowserView(BaseView):
    """
    Standalone view for browsing processing steps.

    Wraps the existing StepBrowser component in a BaseView for consistency
    with the 5-column architecture. This view only shows the list of steps
    and doesn't contain the preview canvas or adjustment controls.
    """

    def __init__(self, app, is_mobile: bool = False, library_manager=None):
        """
        Initialize step browser view.

        Args:
            app: Application instance
            is_mobile: Whether running in mobile mode
            library_manager: LibraryManager instance for loading step data
        """
        logger.info("Initializing StepBrowserView")

        self.library_manager = library_manager

        # Create StepBrowser component
        # Callback will be wired up later via set_on_step_selected
        self.step_browser = StepBrowser(on_step_selected=self._on_step_selected)

        # Call parent init
        super().__init__(app, is_mobile)

        logger.info("StepBrowserView initialized")

    def _create_content(self):
        """Create step browser content"""
        # The StepBrowser component already has its own container with proper styling
        # Just add it directly to our content container
        self.content_container.add(self.step_browser.as_box())
        logger.debug("StepBrowser component added to view")

    def _on_step_selected(self, step_index: int):
        """
        Handle step selection from StepBrowser component.

        This callback is called when the user clicks on a step in the list.
        We need to notify the PreviewView (in column 4) to update.

        Args:
            step_index: Index of the selected step
        """
        logger.info(f"Step {step_index} selected in StepBrowserView")

        # TODO: Wire this up to NavigationController or directly to PreviewView
        # For now, just log it
        # The PreviewView will need to listen for these events and update accordingly

    def load_steps(self, steps: List[Step], current_index: int = 0):
        """
        Load steps into the browser.

        Args:
            steps: List of Step objects to display
            current_index: Index of currently selected step
        """
        logger.info(f"Loading {len(steps)} steps into StepBrowserView (current={current_index})")
        self.step_browser.load_steps(steps, current_index)

    def set_current_index(self, index: int):
        """
        Update the selected step by index.

        Args:
            index: Index to select
        """
        self.step_browser.set_current_index(index)

    def clear(self):
        """Clear the step browser"""
        self.step_browser.clear()

    def set_on_step_selected(self, callback):
        """
        Set callback for step selection events.

        This allows main_window or navigation controller to wire up
        the step selection to update the PreviewView.

        Args:
            callback: Function to call when step is selected (receives step_index)
        """
        self.step_browser.on_step_selected = callback
        logger.debug("Step selection callback updated")
