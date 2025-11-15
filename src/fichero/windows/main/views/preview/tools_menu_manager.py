"""
ToolsMenuManager - Manages the Tools menu for OutputView

Provides three submenus using Toga's Command system:
- Adjust: Open inspector to edit tool parameters
- Go To: Navigate to different processing step outputs
- Process: Run tools on current item
"""

import logging
from typing import Optional, List
import toga

logger = logging.getLogger(__name__)


class ToolsMenuManager:
    """Manages the Tools menu for OutputView using Toga Command system"""

    def __init__(self, output_view, renderer_registry):
        """
        Initialize ToolsMenuManager.

        Args:
            output_view: OutputView instance
            renderer_registry: RendererRegistry instance
        """
        self.output_view = output_view
        self.renderer_registry = renderer_registry

        # Track commands for state updates
        self.adjust_commands = []
        self.goto_commands = []
        self.process_commands = []

        logger.info("ToolsMenuManager initialized")

    def build_menu(self):
        """
        Build the complete Tools menu using Toga Commands.

        This adds commands to the app's command set which automatically
        creates menu items.

        Returns:
            None (commands are added to app.commands)
        """
        logger.info("Building Tools menu commands")

        # Get app instance
        app = self.output_view.app

        # Create custom Tools group
        tools_group = toga.Group("Tools", order=50)

        # Build all three submenus
        self._build_adjust_commands(app, tools_group)
        self._build_goto_commands(app, tools_group)
        self._build_process_commands(app, tools_group)

        logger.info("Tools menu commands built successfully")

    def _build_adjust_commands(self, app, tools_group):
        """
        Build Adjust command - single command to toggle inspector for current tool.

        Opens/closes inspector panel showing JSON editor for current step's tool.
        """
        logger.debug("Building Adjust command")

        # Single "Adjust Current Tool..." command
        cmd = toga.Command(
            action=lambda widget: self._on_adjust_current(),
            text='Adjust Current Tool...',
            tooltip='Show/hide inspector for current tool parameters',
            shortcut=toga.Key.MOD_1 + toga.Key.SHIFT + 'i',
            group=tools_group,
            section=0,  # Section 0: Adjust command
            order=0
        )
        app.commands.add(cmd)
        self.adjust_commands.append(cmd)
        logger.debug("Added Adjust Current Tool command")

    def _build_goto_commands(self, app, tools_group):
        """
        Build Go To submenu commands.

        Built from current item's processing steps.
        Navigates to specific step output.
        """
        logger.debug("Building Go To commands")

        # Always add "Go To Original Image" command
        cmd = toga.Command(
            action=lambda widget: self._goto_original(),
            text='Go To Original Image',
            tooltip='Navigate to original image',
            group=tools_group,
            section=1,  # Section 1: Go To commands
            order=0
        )
        app.commands.add(cmd)
        self.goto_commands.append(cmd)
        logger.debug("Added Go To Original command")

        # TODO: Add commands for each step dynamically
        # This would need to be rebuilt when item changes

    def _build_process_commands(self, app, tools_group):
        """
        Build Process submenu commands.

        All available tools organized by category.
        Runs tool on current item.
        """
        logger.debug("Building Process commands")

        # For now, just add Rotate as a test
        # TODO: Add all tools organized by category
        cmd = toga.Command(
            action=lambda widget: self._process_rotate(),
            text='Rotate Image...',
            tooltip='Process current item with rotate tool',
            group=tools_group,
            section=2,  # Section 2: Process commands
            order=0
        )
        app.commands.add(cmd)
        self.process_commands.append(cmd)
        logger.debug("Added Process Rotate command")

    # ----------------------------------------------------------------
    # Action Handlers - Adjust Menu
    # ----------------------------------------------------------------

    def _on_adjust_current(self):
        """
        Toggle inspector panel for current tool.

        Shows/hides the inspector panel on the right with JSON editor
        for the current step's tool parameters.
        """
        logger.info("Adjust Current Tool requested")

        # Toggle the inspector
        if hasattr(self.output_view, '_toggle_inspector'):
            self.output_view._toggle_inspector()
        else:
            logger.warning("OutputView does not have _toggle_inspector method")

    # ----------------------------------------------------------------
    # Action Handlers - Go To Menu
    # ----------------------------------------------------------------

    def _goto_step(self, step):
        """
        Navigate to a specific processing step.

        Args:
            step: Step object to navigate to
        """
        logger.info(f"Go To step: {step.step_name if hasattr(step, 'step_name') else step.step_index}")

        # Set current step
        if hasattr(self.output_view, 'step_manager') and self.output_view.step_manager:
            self.output_view.step_manager.set_current_step(step.step_index)

            # Update step browser selection if available
            if hasattr(self.output_view, 'step_browser') and self.output_view.step_browser:
                self.output_view.step_browser.select_step(step.step_index)
                # TODO: Add scroll_to_step when implemented
        else:
            logger.warning("No step manager available for navigation")

    def _goto_original(self):
        """Navigate to original image (step 0)"""
        logger.info("Go To original image")

        if hasattr(self.output_view, 'step_manager') and self.output_view.step_manager:
            self.output_view.step_manager.set_current_step(0)

            # Update step browser selection if available
            if hasattr(self.output_view, 'step_browser') and self.output_view.step_browser:
                self.output_view.step_browser.select_step(0)
        else:
            logger.warning("No step manager available for navigation")

    # ----------------------------------------------------------------
    # Action Handlers - Process Menu
    # ----------------------------------------------------------------

    def _process_rotate(self):
        """
        Open dialog to process current item with rotate tool.
        """
        logger.info("Process Rotate requested")

        # Get current item
        if not hasattr(self.output_view, 'step_manager') or not self.output_view.step_manager:
            logger.warning("No step manager available")
            self.output_view.app.main_window.info_dialog(
                'No Item Selected',
                'Please select an item to process.'
            )
            return

        state = self.output_view.step_manager.get_state()

        if not state.item_id:
            self.output_view.app.main_window.info_dialog(
                'No Item Selected',
                'Please select an item to process.'
            )
            return

        # TODO: Show process dialog for rotate
        # For now, just show info dialog
        logger.info(f"Would process item {state.item_id} with rotate tool")
        self.output_view.app.main_window.info_dialog(
            'Process Rotate',
            f'Would process item: {state.item_id}\n\n(Process dialog not yet implemented)'
        )

    # ----------------------------------------------------------------
    # Menu State Management
    # ----------------------------------------------------------------

    def update_menu_states(self):
        """
        Update enabled/disabled state of all commands.

        Should be called when:
        - Item changes
        - Step changes
        - Processing completes
        """
        logger.debug("Updating menu states")

        self.update_adjust_menu_states()
        self.update_goto_menu_states()
        self.update_process_menu_states()

    def update_adjust_menu_states(self):
        """
        Update enabled/disabled state of Adjust command.

        Enabled: When viewing a tool step (not original)
        Disabled: When viewing original or no item selected
        """
        if not hasattr(self.output_view, 'step_manager') or not self.output_view.step_manager:
            # No step manager, disable
            for cmd in self.adjust_commands:
                cmd.enabled = False
            return

        # Get current step
        current_step = self.output_view.step_manager.get_current_step()

        # Enable if current step has a tool (not original)
        has_tool = (current_step and
                   hasattr(current_step, 'tool_name') and
                   current_step.tool_name and
                   current_step.tool_name != 'original')

        logger.debug(f"Current step has tool: {has_tool}")

        # Update command state
        for cmd in self.adjust_commands:
            cmd.enabled = has_tool
            logger.debug(f"Adjust Current Tool enabled: {cmd.enabled}")

    def update_goto_menu_states(self):
        """
        Update state on Go To commands.

        All items always enabled (if steps exist).
        """
        if not hasattr(self.output_view, 'step_manager') or not self.output_view.step_manager:
            return

        state = self.output_view.step_manager.get_state()
        current_index = state.step_index if state else 0

        logger.debug(f"Current step index: {current_index}")

        # All Go To commands are always enabled
        # TODO: Could add visual indication of current step if Toga supports it

    def update_process_menu_states(self):
        """
        Update enabled/disabled state of Process commands.

        Enabled: When an item is selected
        Disabled: When no item selected
        """
        if not hasattr(self.output_view, 'step_manager') or not self.output_view.step_manager:
            # No step manager, disable all
            for cmd in self.process_commands:
                cmd.enabled = False
            return

        state = self.output_view.step_manager.get_state()
        has_item = bool(state.item_id if state else None)

        logger.debug(f"Has item selected: {has_item}")

        for cmd in self.process_commands:
            cmd.enabled = has_item

    # ----------------------------------------------------------------
    # Dynamic Menu Rebuilding
    # ----------------------------------------------------------------

    def rebuild_menus(self):
        """
        Rebuild dynamic menus based on current state.

        Called when:
        - Item changes
        - Step changes
        - Processing completes
        - Renderer registry updates
        """
        logger.info("Rebuilding menus")

        # TODO: Remove old commands before rebuilding
        # For now, we'll just rebuild which may create duplicates

        # Clear tracked commands
        self.adjust_commands = []
        self.goto_commands = []
        self.process_commands = []

        # Rebuild the entire Tools menu
        self.build_menu()

        # Update menu states
        self.update_menu_states()

        logger.info("Menus rebuilt successfully")
