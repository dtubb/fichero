"""
AdjustView - Dynamic workflow tool controls

Shows collapsible sections for each processing tool in the order they've been run.
Each section shows:
- Completed tools: parameters used + Re-run button
- Available tools: parameter inputs + Run button

Replaces the old manual rotation/crop controls with a complete workflow interface.
"""
import logging
import asyncio
from typing import Optional, List, Dict, Any
from pathlib import Path

import toga
from toga.style import Pack
from toga.constants import COLUMN, ROW

from fichero.shared.views.base_view import BaseView
from fichero.library.services import ToolExecutionService
from ..shared.tool_registry import ToolRegistry

logger = logging.getLogger(__name__)


class ToolSection(toga.Box):
    """
    Collapsible section for a single tool.

    Shows either:
    - Completed: Parameters used + Re-run button
    - Available: Parameter inputs + Run button
    """

    def __init__(self, tool_name: str, is_completed: bool = False,
                 parameters: Dict[str, Any] = None, on_run=None):
        super().__init__(style=Pack(direction=COLUMN, margin=5))

        self.tool_name = tool_name
        self.is_completed = is_completed
        self.on_run = on_run
        self.is_expanded = False

        # Get tool definition from registry
        registry = ToolRegistry()
        self.tool_def = registry.get_tool(tool_name) or {}

        # Store parameter widgets for reading values
        self.param_widgets = {}

        # Build the section
        self._build_header()
        self._build_content(parameters)

    def _build_header(self):
        """Build collapsible header"""
        # Tool name
        name = self.tool_def.get('name', self.tool_name.replace('_', ' ').title())

        # Status indicator
        if self.is_completed:
            status = "✓ "
            icon = "▼" if self.is_expanded else "▶"
        else:
            status = ""
            icon = "▼" if self.is_expanded else "▶"

        # Create button text with icon, status, and name
        button_text = f"{icon} {status}{name}"

        # Make entire header a clickable button
        self.header_btn = toga.Button(
            button_text,
            on_press=self._toggle_expand,
            style=Pack(
                padding=5,
                flex=1,
                font_weight='bold' if self.is_completed else 'normal'
            )
        )

        self.add(self.header_btn)

        # Content container (hidden by default)
        self.content_box = toga.Box(
            style=Pack(direction=COLUMN, margin_left=25)
        )
        # Don't add to parent yet - will be added when expanded

    def _build_content(self, parameters: Dict[str, Any] = None):
        """Build expandable content area"""
        # Description
        desc = self.tool_def.get('description', '')
        if desc:
            desc_label = toga.Label(
                desc,
                style=Pack(margin_bottom=10, font_size=11, color='#666')
            )
            self.content_box.add(desc_label)

        if self.is_completed:
            # Show parameters that were used
            self._build_completed_view(parameters or {})
        else:
            # Show parameter inputs
            self._build_input_view()

    def _build_completed_view(self, parameters: Dict[str, Any]):
        """Show parameters that were used"""
        if not parameters:
            status_text = toga.Label(
                "Completed successfully",
                style=Pack(margin_bottom=10, color='#4CAF50')
            )
            self.content_box.add(status_text)
        else:
            # Show each parameter value
            for param_name, param_value in parameters.items():
                param_label = toga.Label(
                    f"{param_name}: {param_value}",
                    style=Pack(margin=2, font_size=11)
                )
                self.content_box.add(param_label)

        # Re-run button
        rerun_btn = toga.Button(
            "Re-run",
            on_press=self._on_run_clicked,
            style=Pack(margin_top=10)
        )
        self.content_box.add(rerun_btn)

    def _build_input_view(self):
        """Show parameter input widgets"""
        param_defs = self.tool_def.get('parameters', [])

        if not param_defs:
            # No parameters, just show Run button
            help_text = toga.Label(
                "Uses optimal defaults",
                style=Pack(margin_bottom=10, font_size=11, color='#666')
            )
            self.content_box.add(help_text)
        else:
            # Create input widget for each parameter
            for param_def in param_defs:
                param_box = self._create_parameter_widget(param_def)
                self.content_box.add(param_box)

        # Run button
        run_btn = toga.Button(
            f"Run {self.tool_def.get('name', 'Tool')}",
            on_press=self._on_run_clicked,
            style=Pack(margin_top=10, background_color='#2196F3', color='#FFFFFF')
        )
        self.content_box.add(run_btn)

    def _create_parameter_widget(self, param_def: Dict[str, Any]) -> toga.Box:
        """Create input widget for a parameter"""
        param_box = toga.Box(style=Pack(direction=COLUMN, margin=5))

        # Label
        label = toga.Label(
            param_def['label'],
            style=Pack(margin_bottom=5, font_size=11)
        )
        param_box.add(label)

        param_name = param_def['name']
        param_type = param_def['type']

        if param_type == 'select':
            # Dropdown
            options = [opt[1] for opt in param_def['options']]  # Display names
            widget = toga.Selection(
                items=options,
                style=Pack(width=200)
            )
            # Set default
            default = param_def.get('default')
            if default:
                # Find index of default in options
                option_values = [opt[0] for opt in param_def['options']]
                if default in option_values:
                    idx = option_values.index(default)
                    widget.value = options[idx]

            self.param_widgets[param_name] = {
                'widget': widget,
                'options': param_def['options'],  # To map back to values
                'type': 'select'
            }

        elif param_type == 'number':
            # Number input
            widget = toga.NumberInput(
                min=param_def.get('min', 0),
                max=param_def.get('max', 1000),
                value=param_def.get('default', 0),
                style=Pack(width=100)
            )
            self.param_widgets[param_name] = {
                'widget': widget,
                'type': 'number'
            }
        else:
            # Unsupported parameter type - create a label as placeholder
            widget = toga.Label(
                f"Unsupported type: {param_type}",
                style=Pack(margin=5)
            )

        param_box.add(widget)
        return param_box

    def _toggle_expand(self, widget):
        """Toggle section expansion"""
        self.is_expanded = not self.is_expanded

        # Update button text with new icon
        name = self.tool_def.get('name', self.tool_name.replace('_', ' ').title())
        status = "✓ " if self.is_completed else ""
        icon = "▼" if self.is_expanded else "▶"
        self.header_btn.text = f"{icon} {status}{name}"

        if self.is_expanded:
            self.add(self.content_box)
        else:
            self.remove(self.content_box)

    def _on_run_clicked(self, widget):
        """Handle Run/Re-run button click"""
        if self.on_run:
            # Gather parameter values
            params = self._get_parameter_values()
            self.on_run(self.tool_name, params)

    def _get_parameter_values(self) -> Dict[str, Any]:
        """Extract values from parameter widgets"""
        values = {}

        for param_name, param_info in self.param_widgets.items():
            widget = param_info['widget']
            param_type = param_info['type']

            if param_type == 'select':
                # Map display name back to value
                display_name = widget.value
                options = param_info['options']
                for val, display in options:
                    if display == display_name:
                        values[param_name] = val
                        break
            elif param_type == 'number':
                values[param_name] = widget.value

        return values


class AdjustView(BaseView):
    """
    Dynamic workflow tool controls.

    Shows collapsible sections for tools in workflow order.
    Updates dynamically based on completed steps.
    """

    def __init__(self, app, is_mobile: bool = False):
        """
        Initialize adjust view.

        Args:
            app: Application instance
            is_mobile: Whether running in mobile mode
        """
        logger.info("Initializing AdjustView (dynamic workflow version)")

        # Reference to preview view (set by main_window)
        self.preview_view = None

        # Track tool sections
        self.tool_sections: List[ToolSection] = []

        # Tool execution service (will be initialized when preview_view is set)
        self.tool_execution_service: Optional[ToolExecutionService] = None

        # Call parent init
        super().__init__(app, is_mobile)

        logger.info("AdjustView initialized")

    def _create_content(self):
        """Create dynamic tool sections"""
        # Container with scrolling
        self.tools_container = toga.ScrollContainer(
            style=Pack(flex=1)
        )

        self.tools_box = toga.Box(
            style=Pack(
                direction=COLUMN,
                padding=10
            )
        )

        # Title
        title = toga.Label(
            "Workflow Tools",
            style=Pack(
                margin_bottom=10,
                font_size=14,
                font_weight='bold'
            )
        )
        self.tools_box.add(title)

        # Placeholder - will be populated when item is loaded
        self.placeholder = toga.Label(
            "Select an item to begin processing",
            style=Pack(margin=20, color='#999')
        )
        self.tools_box.add(self.placeholder)

        self.tools_container.content = self.tools_box
        self.content_container.add(self.tools_container)

        logger.debug("Adjustment controls created (dynamic version)")

    def set_preview_view(self, preview_view):
        """
        Set the preview view reference.

        Args:
            preview_view: PreviewView instance with step_manager
        """
        self.preview_view = preview_view
        logger.debug("PreviewView reference set in AdjustView")

        # Initialize tool execution service
        if hasattr(preview_view, 'library_manager') and preview_view.library_manager:
            self.tool_execution_service = ToolExecutionService(
                library_manager=preview_view.library_manager
            )
            logger.debug("ToolExecutionService initialized")

        # Listen for step changes (using observer pattern)
        if hasattr(preview_view, 'step_manager') and preview_view.step_manager:
            preview_view.step_manager.add_state_change_listener(self._on_step_changed)

    def _on_step_changed(self, state):
        """Callback when step state changes - rebuild tool sections"""
        logger.info(f"Step changed - rebuilding tool sections (step {state.step_index}/{state.total_steps})")
        self.rebuild_tools()

    def rebuild_tools(self):
        """Rebuild tool sections based on current steps"""
        if not self.preview_view or not self.preview_view.step_manager:
            logger.debug("No preview_view/step_manager - cannot rebuild")
            return

        step_manager = self.preview_view.step_manager
        steps = step_manager.steps

        logger.info(f"Rebuilding tools - {len(steps)} steps exist")

        # Clear existing sections
        self.tools_box.clear()
        self.tool_sections = []

        # Re-add title
        title = toga.Label(
            "Workflow Tools",
            style=Pack(
                margin_bottom=10,
                font_size=14,
                font_weight='bold'
            )
        )
        self.tools_box.add(title)

        if not steps:
            self.tools_box.add(self.placeholder)
            return

        # Add section for each completed step
        for step in steps:
            tool_name = step.tool_name
            if tool_name == 'original':
                # Show original as read-only
                original_box = toga.Box(style=Pack(direction=COLUMN, margin=10))
                # Handle both Path and string for file_path
                from pathlib import Path
                file_path = step.file_path if isinstance(step.file_path, Path) else Path(step.file_path)
                original_label = toga.Label(
                    f"Original: {file_path.name}",
                    style=Pack(font_size=11, font_weight='bold')
                )
                original_box.add(original_label)
                self.tools_box.add(original_box)
            else:
                # Show completed tool
                section = ToolSection(
                    tool_name=tool_name,
                    is_completed=True,
                    parameters=step.parameters,
                    on_run=self._on_tool_run
                )
                self.tool_sections.append(section)
                self.tools_box.add(section)

        # Add next available tools
        registry = ToolRegistry()
        completed_tools = [s.tool_name for s in steps]
        workflow_order = registry.get_workflow_order()

        for tool_name in workflow_order:
            if tool_name not in completed_tools:
                # Show as available
                section = ToolSection(
                    tool_name=tool_name,
                    is_completed=False,
                    on_run=self._on_tool_run
                )
                self.tool_sections.append(section)
                self.tools_box.add(section)

    def _on_tool_run(self, tool_name: str, parameters: Dict[str, Any]):
        """Handle tool execution request"""
        logger.info(f"Tool run requested: {tool_name} with params {parameters}")

        if not self.tool_execution_service:
            logger.error("No tool_execution_service available")
            self.app.main_window.error_dialog(
                'Error',
                'Tool execution service not initialized'
            )
            return

        # Execute the tool asynchronously
        asyncio.create_task(self._execute_tool_async(tool_name, parameters))

    async def _execute_tool_async(self, tool_name: str, parameters: Dict[str, Any]):
        """Execute tool asynchronously with progress feedback"""
        logger.info(f"Executing {tool_name} asynchronously")

        try:
            # Get item_id from step_manager
            if not self.preview_view or not self.preview_view.step_manager:
                logger.error("No step_manager available")
                self.app.main_window.error_dialog(
                    'Error',
                    'Preview view not initialized'
                )
                return

            step_manager = self.preview_view.step_manager
            item_id = step_manager.current_item_id

            if not item_id:
                logger.error("No item selected")
                self.app.main_window.error_dialog(
                    'Error',
                    'No item selected'
                )
                return

            # Get last step as source
            steps = step_manager.steps
            if not steps:
                logger.error("No steps available")
                self.app.main_window.error_dialog(
                    'Error',
                    'No source step found'
                )
                return

            # Use last step's tool_name as source
            last_step = steps[-1]
            source_step_name = last_step.tool_name

            logger.info(f"Executing {tool_name} on item {item_id}, source: {source_step_name}")

            # TODO: Show progress dialog
            # For now, just execute and show result

            result = await self.tool_execution_service.execute_tool(
                item_id=item_id,
                tool_name=tool_name,
                source_step_name=source_step_name,
                parameters=parameters
            )

            if result.success:
                logger.info(f"✅ Tool {tool_name} completed successfully")

                # Explicitly refresh UI to show new step
                logger.info("🔄 Refreshing UI after tool completion")
                if self.preview_view and self.preview_view.step_manager:
                    # Reload the item to pick up the new processing result
                    await self.preview_view.step_manager.load_item(item_id)
                    logger.info("✅ UI refreshed - new step should now be visible")
            else:
                logger.error(f"❌ Tool {tool_name} failed: {result.error}")
                self.app.main_window.error_dialog(
                    f'{tool_name} Failed',
                    result.error or 'Unknown error'
                )

        except Exception as e:
            logger.error(f"Tool execution error: {e}", exc_info=True)
            self.app.main_window.error_dialog(
                'Execution Error',
                str(e)
            )
