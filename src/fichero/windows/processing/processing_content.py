"""
Processing Content - Refactored Clean Implementation

Clean, modular processing content that delegates responsibilities to specialized managers:
- StateManager: Handles state transitions and data
- LayoutManager: Handles UI layout and assembly  
- ProcessingController: Handles business logic and processing workflow
- Components: Handle specific UI elements (folder, plan, progress, description)

This results in a much cleaner, more maintainable ProcessingContent class.
"""

import toga
import asyncio
import logging
from typing import Optional, Callable
import gettext

# Use the global _ function for translations
try:
    _ = gettext.gettext
except:
    def _(text): return text

# Import the new managers
from fichero.windows.processing.state_manager import ProcessingStateManager, ProcessingState
from fichero.windows.processing.layout_manager import ProcessingLayoutManager
from fichero.windows.processing.processing_controller import ProcessingController

# Import components
from fichero.windows.processing.components import (
    FolderSelector, PlanSelector, ProgressDisplay, DescriptionView
)

logger = logging.getLogger(__name__)


class ProcessingContent:
    """Clean processing content using modular managers and components"""
    
    def __init__(self, app):
        """Initialize processing content with modular architecture"""
        self.app = app
        
        # Compatibility attribute for window manager
        self.on_back = None  # Not used in processing, but expected by window manager
        
        # Initialize managers
        self.state_manager = ProcessingStateManager()
        self.layout_manager = ProcessingLayoutManager(app, show_back_button=False)
        self.processing_controller = ProcessingController(app)
        
        # Initialize components (created in create())
        self.folder_selector: Optional[FolderSelector] = None
        self.plan_selector: Optional[PlanSelector] = None
        self.progress_display: Optional[ProgressDisplay] = None
        self.description_view: Optional[DescriptionView] = None
        
        # Setup event listeners
        self._setup_event_listeners()
    
    def _setup_event_listeners(self):
        """Setup event listeners between managers and components"""
        
        # State change listener
        self.state_manager.add_state_change_listener(self._on_state_changed)
        
        # Processing controller listeners
        self.processing_controller.add_processing_complete_listener(self._on_processing_complete)
        self.processing_controller.add_processing_stopped_listener(self._on_processing_stopped)
    
    def create(self) -> toga.Box:
        """Create the processing content UI"""
        logger.info("Creating refactored processing content")
        
        # Initialize components
        self._initialize_components()
        
        # Create layout using layout manager
        layout = self.layout_manager.create_main_layout(
            folder_selector_widget=self.folder_selector.create(),
            plan_selector_widget=self.plan_selector.create(),
            initial_content_widget=self.description_view.create(),
            on_reset=self._on_reset,
            on_process=self._on_process,
            on_back=self.on_back
        )
        
        logger.info("Refactored processing content created successfully")
        return layout
    
    def _initialize_components(self):
        """Initialize all UI components"""
        
        # Folder selector
        self.folder_selector = FolderSelector(
            app=self.app,
            on_folder_selected=self._on_folder_selected
        )
        
        # Plan selector
        self.plan_selector = PlanSelector(
            app=self.app,
            on_plan_changed=self._on_plan_changed
        )
        
        # Progress display
        self.progress_display = ProgressDisplay(
            app=self.app,
            on_processing_complete=self.processing_controller.on_processing_complete,
            on_processing_stopped=self.processing_controller.on_processing_stopped
        )
        
        # Description view
        self.description_view = DescriptionView(app=self.app)
    
    def _on_state_changed(self, new_state: ProcessingState):
        """Handle state changes from state manager"""
        logger.info(f"State changed to: {new_state}")
        
        if new_state == ProcessingState.FOLDER_SELECTION:
            # Show description, hide buttons
            self.layout_manager.switch_content(self.description_view.create())
            self.layout_manager.hide_control_buttons()
            self.layout_manager.hide_activity_indicator()
            
        elif new_state == ProcessingState.READY_TO_PROCESS:
            # Show description, show buttons
            self.layout_manager.switch_content(self.description_view.create())
            self.layout_manager.show_control_buttons()
            self.layout_manager.hide_activity_indicator()
            
        elif new_state == ProcessingState.PROCESSING:
            # Show progress, show activity indicator
            self.layout_manager.switch_content(self.progress_display.create())
            self.layout_manager.show_control_buttons()
            self.layout_manager.show_activity_indicator()
            
        elif new_state == ProcessingState.COMPLETED:
            # Keep progress display, hide activity indicator
            self.layout_manager.hide_activity_indicator()
        
        # Update button states
        state_info = self.state_manager.get_state_info()
        self.layout_manager.update_button_states(
            can_process=state_info['can_process'],
            is_processing=self.state_manager.is_processing()
        )
    
    def _on_folder_selected(self, folder_path):
        """Handle folder selection from folder selector"""
        logger.info(f"Folder selected: {folder_path}")
        self.state_manager.set_folder(folder_path)
    
    def _on_plan_changed(self, plan_name, plan_filename=None, workflow=None):
        """Handle plan change from plan selector"""
        logger.info(f"Plan changed: {plan_name}")
        self.state_manager.set_plan(plan_name, plan_filename, workflow)
    
    async def _on_process(self):
        """Handle process button click"""
        logger.info("Process button clicked")
        
        # Validate inputs
        state_info = self.state_manager.get_state_info()
        is_valid, error_msg = self.processing_controller.validate_processing_inputs(
            self.state_manager.selected_folder, 
            self.state_manager.current_plan
        )
        
        if not is_valid:
            await self.app.dialog(toga.ErrorDialog("Error", error_msg))
            return
        
        # Get output location
        output_path = await self.processing_controller.get_output_location(
            self.state_manager.selected_folder
        )
        if not output_path:
            return  # User cancelled
        
        # Start processing
        self.state_manager.start_processing(output_path)
        
        # Start the actual processing
        success = await self.processing_controller.start_processing(
            self.progress_display,
            self.state_manager.selected_folder,
            self.state_manager.output_path,
            self.state_manager.current_plan,
            self.state_manager.current_workflow or "default"
        )
        
        if not success:
            # Reset state if processing failed to start
            self.state_manager.reset()
    
    async def _on_reset(self):
        """Handle reset/cancel button click"""
        logger.info("Reset button clicked")
        
        if self.state_manager.is_processing():
            # Stop processing
            stopped = await self.processing_controller.stop_processing(self.progress_display)
            if stopped:
                self.state_manager.reset()
        else:
            # Just reset state
            self.state_manager.reset()
    
    def _on_processing_complete(self):
        """Handle processing completion"""
        logger.info("Processing completed")
        self.state_manager.complete_processing()
        
        # Show completion dialog
        asyncio.create_task(self._show_completion_dialog())
    
    def _on_processing_stopped(self):
        """Handle processing stopped"""
        logger.info("Processing stopped")
        self.state_manager.reset()
    
    async def _show_completion_dialog(self):
        """Show processing completion dialog"""
        if self.progress_display:
            # Get completion info from progress display
            # This would need to be implemented in ProgressDisplay
            await self.processing_controller.show_completion_dialog(0, 0)
    
    def get_state_info(self) -> dict:
        """Get current state information for debugging"""
        return self.state_manager.get_state_info() 