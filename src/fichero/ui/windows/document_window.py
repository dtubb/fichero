"""
Document Window for Fichero - Thin Wrapper

Lightweight document window that delegates all business logic to director.py.
This ensures GUI and CLI share the same codebase for:
- Progress tracking with rich Toga progress bars via DocumentProgressDisplay
- Logging and error handling
- Status monitoring
- Task management

The UI focuses on display and user interaction, while director.py handles all processing.
"""

import toga
from toga.style import Pack
from toga.constants import COLUMN, ROW, CENTER, LEFT
from pathlib import Path
import asyncio
import webbrowser
import yaml
import os
import time
from typing import Optional, Any, Dict, List
import logging
import sys

from ..i18n import _, translator
from ...config.core.plan_manager import PlanManager
from ...config.core.settings import get_app_settings
from ...director import FicheroDirector
from ...director.monitoring.displays.gui_display import GUITaskDisplay
from ...director.monitoring.task_monitor import TaskMonitor
from ...utils.path_icons import render_path_with_icons, get_folder_icon_path

logger = logging.getLogger(__name__)


class FicheroDocumentWindow(toga.DocumentWindow):
    """
    Simplified document window for folder processing.
    
    Shows basic UI for folder/plan selection, then displays GUITaskDisplay
    only when processing starts. All business logic handled by director.py.
    """
    
    def __init__(self, doc):
        logger.info(f"Initializing document window for document {doc.document_id}")
        
        # Store references
        self._document = doc
        self._app = doc.app
        
        # Initialize state
        self.selected_folder = None
        self.current_plan = None
        self.current_workflow = None
        
        # GUI task display (created only when processing starts)
        self.task_display: Optional[GUITaskDisplay] = None
        self.current_task_ids = []
        
        # Create UI content
        content = self._create_content()
        
        super().__init__(doc=doc, content=content, resizable=False, size=(650, 350))
        
        # Set initial window title to just "Fichero"
        self.title = "Fichero"
        

        
        # Set up window handlers
        self._setup_window_handlers()
        
        # Initialize plan selection after window is created
        asyncio.create_task(self._initialize_after_show())
        
        logger.info("Document window initialized successfully")
    
    async def _initialize_after_show(self):
        """Initialize components after window is shown"""
        await asyncio.sleep(0.1)  # Let window fully render
        try:
            self._draw_folder_background()
            self._initialize_plan_workflow()
        except Exception as e:
            logger.error(f"Initialization error: {e}")
    
    def _create_content(self):
        """Create simplified document window UI"""
        # Create main sections
        self._create_folder_selection_section()
        self._create_content_section()
        self._create_footer()
        
        # Assemble layout - content section gets only the space it needs
        main_sections = toga.Box(style=Pack(direction=COLUMN, flex=1))
        main_sections.add(self.folder_section)
        main_sections.add(self.content_section)
        
        main_content = toga.Box(style=Pack(direction=COLUMN, background_color='#f7f2f1'))
        main_content.add(main_sections)
        main_content.add(self.footer_section)
        
        return main_content

    def _create_folder_icons(self):
        """Create different icons for different states"""
        # Question mark icon (default state)
        try:
            question_image = toga.Image("resources/icons/folder_with_question_mark.png")
            self.question_icon = toga.ImageView(
                question_image,
                style=Pack(width=62, height=62, margin=3)
            )
        except Exception as e:
            logger.warning(f"Could not load question folder icon: {e}")
            self.question_icon = toga.Label(
                "📁?",
                style=Pack(font_size=32, text_align=CENTER, margin=8)
            )
        
        # Processing icon (clean folder icon)
        self.processing_icon = self._create_folder_icon_widget()
    
    def _create_folder_icon_widget(self):
        """Create a clean folder icon widget for processing state"""
        # Try to get the actual folder icon from the selected folder
        if self.selected_folder:
            folder_icon = self._get_folder_icon(self.selected_folder)
            if folder_icon:
                return folder_icon
        
        # Fall back to user's custom folder.png icon
        try:
            folder_image = toga.Image("resources/icons/folder.png")
            return toga.ImageView(
                folder_image,
                style=Pack(width=62, height=62, margin=3)
            )
        except Exception as e:
            logger.debug(f"Could not load folder.png icon: {e}")
        
        # Fall back to simple folder emoji (clean, no gear)
        return toga.Label(
            "📁",
            style=Pack(font_size=32, text_align=CENTER, margin=8)
        )
    
    def _get_folder_icon(self, folder_path):
        """Get the actual icon for a specific folder"""
        try:

            # Use our new utility to get the icon path with larger size for top left icon
            icon_path = get_folder_icon_path(Path(folder_path), size=62)
            
            if icon_path and Path(icon_path).exists():
                try:
                    # Load the icon file
                    folder_image = toga.Image(icon_path)
                    return toga.ImageView(
                        folder_image,
                        style=Pack(width=62, height=62, margin=3)
                    )
                except Exception as e:
                    logger.debug(f"Could not load folder icon from {icon_path}: {e}")
            
            # Fall back to default folder icon
            return self._get_default_folder_icon()
            
        except Exception as e:
            logger.debug(f"Could not get folder icon for {folder_path}: {e}")
            return self._get_default_folder_icon()
    
    def _get_default_folder_icon(self):
        """Get the default folder icon"""
        try:
            # Try to load the custom folder.png icon
            folder_image = toga.Image("resources/icons/folder.png")
            return toga.ImageView(
                folder_image,
                style=Pack(width=62, height=62, margin=3)
            )
        except Exception as e:
            logger.debug(f"Could not load folder.png icon: {e}")
        
        # Fall back to simple folder emoji
        return toga.Label(
            "📁",
            style=Pack(font_size=32, text_align=CENTER, margin=8)
        )
    
    def _switch_to_processing_icon(self):
        """Switch to processing icon"""
        # Always recreate the processing icon to ensure it's the right size
        self.processing_icon = self._create_folder_icon_widget()
        self.icon_container.clear()
        self.icon_container.add(self.processing_icon)
        self.current_folder_icon = self.processing_icon
    
    def _switch_to_question_icon(self):
        """Switch to question mark icon"""
        self.icon_container.clear()
        self.icon_container.add(self.question_icon)
        self.current_folder_icon = self.question_icon
    


    def _create_folder_selection_section(self):
        """Create folder selection section with icon and background"""
        # Create different folder icons for different states
        self._create_folder_icons()
        
        # Start with question mark icon
        self.current_folder_icon = self.question_icon
        
        # Choose folder button
        self.choose_folder_btn = toga.Button(
            _("choose_folder"),
            on_press=self.choose_folder_handler,
            style=Pack(width=120)
        )
        
        # Processing label (initially hidden)
        self.processing_label = toga.Label(
            "",
            style=Pack(font_size=12, color='#333333', text_align=CENTER)
        )
        
        # Button container with centering
        self.button_row = toga.Box(
            children=[
                toga.Box(style=Pack(flex=1)),  # Left spacer
                self.choose_folder_btn,
                toga.Box(style=Pack(flex=1))   # Right spacer
            ],
            style=Pack(direction=ROW, align_items=CENTER)
        )
        
        # Canvas for rounded background
        self.folder_canvas = toga.Canvas(
            style=Pack(width=540, height=68),
            on_resize=self._draw_folder_background
        )
        
        # Overlay button on canvas
        self.path_container = toga.Box(
            children=[self.button_row],
            style=Pack(
                direction=COLUMN,
                justify_content=CENTER,
                width=540,
                height=68,
            )
        )
        
        # Stack canvas and button
        path_with_background = toga.Box(
            children=[self.folder_canvas],
            style=Pack(
                direction=COLUMN,
                margin_top=20,
                margin_right=20,
                margin_bottom=10,
                margin_left=10,
            )
        )
        
        overlaid_container = toga.Box(
            children=[self.path_container],
            style=Pack(
                direction=COLUMN,
                margin_top=-78,
                margin_right=20,
                margin_left=10,
            )
        )
        
        path_stack = toga.Box(
            children=[path_with_background, overlaid_container],
            style=Pack(direction=COLUMN)
        )
        
        # Icon container (store reference for icon swapping)
        self.icon_container = toga.Box(
            children=[self.current_folder_icon],
            style=Pack(
                direction=COLUMN,
                justify_content=CENTER,
                margin_top=20 + 34 - 34,
                margin_left=20
            )
        )
        
        # Main container
        self.folder_section = toga.Box(
            children=[self.icon_container, path_stack],
            style=Pack(direction=ROW, margin=(0, 0, 0, 0))
        )

    def _draw_folder_background(self, canvas=None, **kwargs):
        """Draw rounded gray background"""
        if canvas is None:
            canvas = self.folder_canvas
            
        canvas.context.clear()
        
        width = canvas.layout.content_width
        height = canvas.layout.content_height
        corner_radius = 6
        
        with canvas.context.Fill(color='rgb(226, 223, 222)') as background:
            background.begin_path()
            background.move_to(corner_radius, 0)
            background.line_to(width - corner_radius, 0)
            background.arc(width - corner_radius, corner_radius, corner_radius, -1.5708, 0)
            background.line_to(width, height - corner_radius)
            background.arc(width - corner_radius, height - corner_radius, corner_radius, 0, 1.5708)
            background.line_to(corner_radius, height)
            background.arc(corner_radius, height - corner_radius, corner_radius, 1.5708, 3.14159)
            background.line_to(0, corner_radius)
            background.arc(corner_radius, corner_radius, corner_radius, 3.14159, 4.71239)
            background.close_path()

    def _create_content_section(self):
        """Create content section with beautiful description view"""
        # Create simple container that will hold task display when processing starts
        self.content_section = toga.Box(
            style=Pack(direction=COLUMN, margin=(0, 0, 0, 0), flex=1)
        )
        
        # Create description canvas for beautiful markdown rendering
        self.description_canvas = toga.Canvas(
            style=Pack(
                margin_top=20,
                margin_right=20,
                margin_bottom=10,
                margin_left=20,
                height=200,  # Fixed height instead of flex=1
            ),
            on_resize=self._draw_content_text,
            on_press=self._handle_canvas_click
        )
        
        # Track link areas for click handling
        self.link_areas = []
        
        # Show description view initially
        self.content_section.add(self.description_canvas)
        
        # Draw content after a brief delay to ensure canvas is ready
        asyncio.create_task(self._delayed_draw_content())

    def _create_footer(self):
        """Create footer with controls"""
        # Left side: Help and plan selection
        left_section = toga.Box(style=Pack(direction=ROW))
        
        help_btn = toga.Button(
            _("help"),
            on_press=self.help_handler,
            style=Pack(font_size=12, font_weight='bold', width=24, height=24)
        )
        left_section.add(help_btn)
        
        # Plan selector
        self.plan_selector = toga.Selection(
            items=PlanManager.get_plan_dropdown_options(self._app),
            style=Pack(width=120, font_size=11, margin_left=5, height=24),
            on_change=self._on_plan_change
        )
        left_section.add(self.plan_selector)
        
        # Workflow selector
        self.workflow_selector = toga.Selection(
            items=["Select a plan first"],
            style=Pack(width=120, font_size=11, margin_left=5, height=24),
            on_change=self._on_workflow_change
        )
        left_section.add(self.workflow_selector)
        
        # Right side: Process controls
        right_section = toga.Box(style=Pack(direction=ROW))
        
        if sys.platform == "darwin":
            self.activity_indicator = toga.ActivityIndicator(
                style=Pack(margin_right=10)
            )
        else:
            self.activity_indicator = None  # Not supported on Windows/Linux
        
        # Reset button (comes first, hidden initially)
        self.reset_btn = toga.Button(
            "Reset",
            on_press=self.reset_handler,
            style=Pack(font_size=12, height=32)
        )
        
        self.process_btn = toga.Button(
            _("process"),
            on_press=self.process_handler,
            style=Pack(font_size=12, height=32, margin_left=10)
        )
        
        # Initially hide both buttons until folder is selected
        self.reset_btn.style.visibility = 'hidden'
        self.process_btn.style.visibility = 'hidden'
        
        if self.activity_indicator is not None:
            right_section.add(self.activity_indicator)
        right_section.add(self.reset_btn)
        right_section.add(self.process_btn)
        
        # Assemble footer
        spacer = toga.Box(style=Pack(flex=1))
        
        self.footer_section = toga.Box(
            style=Pack(
                direction=ROW,
                margin=(0, 20, 20, 20),
                align_items=CENTER
            )
        )
        
        self.footer_section.add(left_section)
        self.footer_section.add(spacer)
        self.footer_section.add(right_section)

    # Progress Management - Simple
    
    def _switch_to_processing_label(self):
        """Switch folder selection from button to processing label"""
        if self.selected_folder:
            # Show the folder path being processed
            folder_path = str(self.selected_folder)
            if len(folder_path) > 60:
                # Truncate long paths
                folder_path = "..." + folder_path[-57:]
            self.processing_label.text = f"Processing: {folder_path}"
            
            # Replace button with label
            self.path_container.clear()
            label_row = toga.Box(
                children=[
                    toga.Box(style=Pack(flex=1)),  # Left spacer
                    self.processing_label,
                    toga.Box(style=Pack(flex=1))   # Right spacer
                ],
                style=Pack(direction=ROW, align_items=CENTER)
            )
            self.path_container.add(label_row)
    
    def _switch_to_folder_path_label(self):
        """Switch folder selection from button to folder path canvas"""
        if self.selected_folder:
            # Show just the folder path (not processing)
            folder_path = str(self.selected_folder)
            
            # Create path display using ImageView + Label widgets
            self.path_display_container = toga.Box(
                style=Pack(
                    direction=ROW,
                    align_items=CENTER,
                    margin_left=10,
                    margin_top=20,
                    margin_bottom=20
                )
            )
            
            # Replace button with path display
            self.path_container.clear()
            path_row = toga.Box(
                children=[
                    self.path_display_container,
                    toga.Box(style=Pack(flex=1))   # Right spacer only
                ],
                style=Pack(direction=ROW, align_items=CENTER)
            )
            self.path_container.add(path_row)
            
            # Build the path with icons and labels
            self._build_path_display(folder_path)
            
            # Update content area to show "Ready to process..."
            self._show_ready_to_process()
    
    def _build_path_display(self, folder_path):
        """Build path display using ImageView + Label widgets with async icon loading"""
        from fichero.utils.path_icons import PathBuilder, get_fallback_folder_icon, load_image
        import logging
        logger = logging.getLogger(__name__)
        
        # Clear existing path display
        self.path_display_container.clear()
        
        # Get path components (this is fast, just path parsing)
        components = PathBuilder.build_path_with_icons(folder_path)
        
        # Build the display with icons loaded synchronously
        for i, component in enumerate(components):
            # Add icon (ImageView)
            icon_image = None
            
            # Try to use real macOS icon first
            if component.get("icon_path"):
                icon_image = load_image(component["icon_path"])
            
            # Fallback to generic folder icon
            if not icon_image:
                fallback_icon_path = get_fallback_folder_icon()
                if fallback_icon_path:
                    icon_image = load_image(fallback_icon_path)
            
            if icon_image:
                try:
                    icon_widget = toga.ImageView(
                        image=icon_image,
                        style=Pack(width=16, height=16, margin_right=2)
                    )
                    self.path_display_container.add(icon_widget)
                except Exception as e:
                    logger.debug(f"Could not create ImageView: {e}")
                    # Skip icon if it fails
            
            # Add folder name (Label) if not root
            if component["name"]:
                is_last_component = (i == len(components) - 1)
                
                name_label = toga.Label(
                    component["name"],
                    style=Pack(
                        font_family='SF Pro Text',
                        font_size=9,
                        font_weight='bold' if is_last_component else 'normal',
                        margin_right=4
                    )
                )
                self.path_display_container.add(name_label)
            
            # Add separator (except for last component)
            if i < len(components) - 1:
                separator_label = toga.Label(
                    "⟩",  # Narrow mathematical right angle bracket
                    style=Pack(
                        font_family='SF Pro Text',
                        font_size=9,
                        color='#808080',  # Dark grey
                        margin_left=4,
                        margin_right=4
                    )
                )
                self.path_display_container.add(separator_label)
    

    
    def _show_ready_to_process(self):
        """Show 'Ready to process...' message in content area"""
        # Clear the content section
        self.content_section.clear()
        
        # Create canvas that draws both background and text together
        self.ready_canvas = toga.Canvas(
            style=Pack(
                margin=(20, 20, 20, 20),  # 20px bottom margin
                height=200,  # Same height as description canvas
            ),
            on_resize=self._draw_ready_background_and_text
        )
        
        self.content_section.add(self.ready_canvas)
    
    def _draw_ready_background_and_text(self, canvas=None, **kwargs):
        """Draw rounded grey background and centered text for ready state"""
        if canvas is None:
            canvas = self.ready_canvas
            
        if not canvas or not hasattr(canvas, 'layout') or not canvas.layout:
            return
            
        canvas.context.clear()
        
        width = canvas.layout.content_width
        height = canvas.layout.content_height
        corner_radius = 6  # Same as top folder bar
        
        # Draw rounded grey rectangle (same color as top folder bar)
        with canvas.context.Fill(color='rgb(226, 223, 222)') as background:
            background.begin_path()
            background.move_to(corner_radius, 0)
            background.line_to(width - corner_radius, 0)
            background.arc(width - corner_radius, corner_radius, corner_radius, -1.5708, 0)
            background.line_to(width, height - corner_radius)
            background.arc(width - corner_radius, height - corner_radius, corner_radius, 0, 1.5708)
            background.line_to(corner_radius, height)
            background.arc(corner_radius, height - corner_radius, corner_radius, 1.5708, 3.14159)
            background.line_to(0, corner_radius)
            background.arc(corner_radius, corner_radius, corner_radius, 3.14159, 4.71239)
            background.close_path()
        
        # Thin light grey border (1px) around grey box
        with canvas.context.Stroke(color='rgb(213, 213, 213)', line_width=1) as border:
            border.begin_path()
            border.move_to(corner_radius, 0)
            border.line_to(width - corner_radius, 0)
            border.arc(width - corner_radius, corner_radius, corner_radius, -1.5708, 0)
            border.line_to(width, height - corner_radius)
            border.arc(width - corner_radius, height - corner_radius, corner_radius, 0, 1.5708)
            border.line_to(corner_radius, height)
            border.arc(corner_radius, height - corner_radius, corner_radius, 1.5708, 3.14159)
            border.line_to(0, corner_radius)
            border.arc(corner_radius, corner_radius, corner_radius, 3.14159, 4.71239)
            border.close_path()
        
        # Draw centered text
        try:
            # Create italic font for the text
            text_font = toga.Font(family=toga.fonts.SYSTEM, size=12, weight="normal", style="italic")
            
            # Calculate center position
            text = "Ready to process…"
            text_width, text_height = canvas.measure_text(text, text_font)
            center_x = width / 2 - text_width / 2
            center_y = height / 2 + text_height / 4  # Slight adjustment for visual centering
            
            # Draw the text
            with canvas.context.Fill(color='rgb(102, 102, 102)') as text_fill:  # #666666
                text_fill.write_text(text, center_x, center_y, text_font)
                
        except Exception as e:
            # Fallback if font styling fails
            text_font = toga.Font(family=toga.fonts.SYSTEM, size=14, weight="normal")
            with canvas.context.Fill(color='rgb(102, 102, 102)') as text_fill:
                text_fill.write_text("Ready to process…", width/2 - 50, height/2, text_font)

    def _update_folder_icon_for_selected_path(self, folder_path):
        """Update the left folder icon to match the selected folder"""
        from fichero.utils.path_icons import get_folder_icon_path, get_fallback_folder_icon, load_image
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            # Get the icon for the selected folder with larger size (62x62)
            icon_path = get_folder_icon_path(Path(folder_path), size=62)
            
            # Try to load the real icon for this folder
            icon_image = None
            if icon_path:
                icon_image = load_image(icon_path)
            
            # Fallback to generic folder icon
            if not icon_image:
                fallback_icon_path = get_fallback_folder_icon()
                if fallback_icon_path:
                    icon_image = load_image(fallback_icon_path)
            
            # Update the folder icon widget
            if icon_image and hasattr(self, 'current_folder_icon'):
                try:
                    # Create new icon widget
                    new_icon = toga.ImageView(
                        image=icon_image,
                        style=Pack(width=62, height=62, margin=3)
                    )
                    
                    # Replace the current icon
                    self.icon_container.clear()
                    self.icon_container.add(new_icon)
                    self.current_folder_icon = new_icon
                    
                except Exception as e:
                    logger.debug(f"Could not update folder icon: {e}")
                    
        except Exception as e:
            logger.debug(f"Error updating folder icon: {e}")
    


    def _format_path_with_separators(self, path_str):
        """Format path with platform-specific separators and icons"""
        return render_path_with_icons(path_str)
    
    def _switch_to_choose_button(self):
        """Switch folder selection from label back to button"""
        self.path_container.clear()
        self.path_container.add(self.button_row)
    
    def _reset_to_process_button(self):
        """Reset button back to process state"""
        if self.activity_indicator is not None:
            self.activity_indicator.stop()
        # Re-add footer section to show buttons again
        if hasattr(self, '_main_content') and self._main_content:
            self._main_content.add(self.footer_section)
        self.process_btn.enabled = bool(self.selected_folder and self.current_plan)
        self.process_btn.text = _("process")
        self.process_btn.on_press = self.process_handler
    
        # Clear task display if it exists
        if self.task_display:
            self.task_display.stop_monitoring()
            self.task_display = None
        
        # Reset folder selection to show choose button (keep folder icon)
        self._switch_to_choose_button()
        
        # Reset content section to welcome message
        self._reset_content_section()
    
    def _reset_content_section(self):
        """Reset content section to beautiful description view"""
        self.content_section.clear()
        self.content_section.add(self.description_canvas)
        # Redraw the content
        self._draw_content_text()
    
    # Beautiful Description View - Canvas-based text rendering
    
    async def _delayed_draw_content(self):
        """Draw content after a brief delay to ensure canvas is ready"""
        await asyncio.sleep(0.1)
        self._draw_content_text()
    
    def _draw_content_text(self, canvas=None, **kwargs):
        """Draw description content on canvas"""
        if canvas is None:
            canvas = self.description_canvas
        
        if not canvas or not hasattr(canvas, 'layout') or not canvas.layout:
            return
        
        # Clear and draw
        with canvas.context.Fill(color='rgb(255, 255, 255)') as clear_fill:
            clear_fill.rect(0, 0, canvas.layout.content_width, canvas.layout.content_height)
        
        self._draw_rounded_background(canvas)
        self._draw_description_content(canvas)
    
    def _draw_rounded_background(self, canvas):
        """Draw rounded white background with thin grey border"""
        width = canvas.layout.content_width
        height = canvas.layout.content_height
        corner_radius = 6
        
        # Light gray background to show rounded corners
        with canvas.context.Fill(color='rgb(240, 240, 240)') as full_background:
            full_background.rect(0, 0, width, height)
        
        # White rounded rectangle
        with canvas.context.Fill(color='rgb(255, 255, 255)') as background:
            background.begin_path()
            background.move_to(corner_radius, 0)
            background.line_to(width - corner_radius, 0)
            background.arc(width - corner_radius, corner_radius, corner_radius, -1.5708, 0)
            background.line_to(width, height - corner_radius)
            background.arc(width - corner_radius, height - corner_radius, corner_radius, 0, 1.5708)
            background.line_to(corner_radius, height)
            background.arc(corner_radius, height - corner_radius, corner_radius, 1.5708, 3.14159)
            background.line_to(0, corner_radius)
            background.arc(corner_radius, corner_radius, corner_radius, 3.14159, 4.71239)
            background.close_path()
        
        # Thin light grey border (1px)
        with canvas.context.Stroke(color='rgb(213, 213, 213)', line_width=1) as border:
            border.begin_path()
            border.move_to(corner_radius, 0)
            border.line_to(width - corner_radius, 0)
            border.arc(width - corner_radius, corner_radius, corner_radius, -1.5708, 0)
            border.line_to(width, height - corner_radius)
            border.arc(width - corner_radius, height - corner_radius, corner_radius, 0, 1.5708)
            border.line_to(corner_radius, height)
            border.arc(corner_radius, height - corner_radius, corner_radius, 1.5708, 3.14159)
            border.line_to(0, corner_radius)
            border.arc(corner_radius, corner_radius, corner_radius, 3.14159, 4.71239)
            border.close_path()
    
    def _draw_description_content(self, canvas):
        """Draw description text with markdown support"""
        self.link_areas = []
        
        regular_font = toga.Font(family=toga.fonts.SYSTEM, size=10, weight="light")
        bold_font = toga.Font(family=toga.fonts.SYSTEM, size=10, weight="bold")
        
        # Get description text from translations
        text = _("description")
        
        line_height_multiplier = 1.8
        left_margin = 15
        top_margin = 15
        right_margin = 10
        max_width = canvas.layout.content_width - left_margin - right_margin
        
        paragraphs = text.split('\n\n')
        current_y = top_margin
        
        for paragraph_idx, paragraph in enumerate(paragraphs):
            if paragraph_idx > 0:
                current_y += regular_font.size * line_height_multiplier * 0.8
            
            current_y = self._render_paragraph(canvas, paragraph, left_margin, current_y, 
                                             max_width, regular_font, bold_font, line_height_multiplier)
    
    def _render_paragraph(self, canvas, text, left_margin, start_y, max_width, 
                          regular_font, bold_font, line_height_multiplier):
        """Render paragraph with markdown formatting"""
        import re
        
        elements = []
        current_pos = 0
        
        # Parse markdown
        bold_pattern = r'\*([^*]+)\*'
        link_pattern = r'\[([^\]]+)\]\(([^)]+)\)'
        combined_pattern = f'({bold_pattern})|({link_pattern})'
        
        for match in re.finditer(combined_pattern, text):
            if match.start() > current_pos:
                elements.append({
                    'type': 'text',
                    'content': text[current_pos:match.start()],
                    'font': regular_font,
                    'color': 'black'
                })
            
            if match.group(2):  # Bold
                elements.append({
                    'type': 'text',
                    'content': match.group(2),
                    'font': bold_font,
                    'color': 'black'
                })
            elif match.group(4) and match.group(5):  # Link
                elements.append({
                    'type': 'link',
                    'content': match.group(4),
                    'url': match.group(5),
                    'font': regular_font,
                    'color': 'blue'
                })
            
            current_pos = match.end()
        
        if current_pos < len(text):
            elements.append({
                'type': 'text',
                'content': text[current_pos:],
                'font': regular_font,
                'color': 'black'
            })
        
        # Render with word wrapping
        current_y = start_y
        current_line_elements = []
        current_line_width = 0
        
        for element in elements:
            words = element['content'].split()
            
            for word_idx, word in enumerate(words):
                space_prefix = " " if word_idx > 0 or current_line_elements else ""
                test_word = space_prefix + word
                
                word_width, _ = canvas.measure_text(test_word, element['font'])
                
                if current_line_width + word_width <= max_width:
                    current_line_elements.append({
                        **element,
                        'content': test_word,
                        'width': word_width
                    })
                    current_line_width += word_width
                else:
                    if current_line_elements:
                        current_y = self._render_line(canvas, current_line_elements, 
                                                    left_margin, current_y, line_height_multiplier)
                    
                    current_line_elements = [{
                        **element,
                        'content': word,
                        'width': canvas.measure_text(word, element['font'])[0]
                    }]
                    current_line_width = current_line_elements[0]['width']
        
        if current_line_elements:
            current_y = self._render_line(canvas, current_line_elements, 
                                        left_margin, current_y, line_height_multiplier)
        
        return current_y
    
    def _render_line(self, canvas, elements, left_margin, y_position, line_height_multiplier):
        """Render a line of formatted text elements"""
        current_x = left_margin
        
        for element in elements:
            color = 'rgb(0, 100, 200)' if element['color'] == 'blue' else 'rgb(0, 0, 0)'
            
            with canvas.context.Fill(color=color) as fill_context:
                fill_context.write_text(
                    element['content'],
                    current_x,
                    y_position,
                    element['font'],
                    toga.constants.Baseline.TOP
                )
            
            # Track link areas
            if element['type'] == 'link':
                self.link_areas.append({
                    'x': current_x,
                    'y': y_position,
                    'width': element['width'],
                    'height': element['font'].size,
                    'url': element['url']
                })
            
            current_x += element['width']
        
        return y_position + elements[0]['font'].size * line_height_multiplier
    
    def _handle_canvas_click(self, widget, x, y, **kwargs):
        """Handle clicks on description canvas for links"""
        for link_area in self.link_areas:
            if (link_area['x'] <= x <= link_area['x'] + link_area['width'] and
                link_area['y'] <= y <= link_area['y'] + link_area['height']):
                webbrowser.open(link_area['url'])
                break
    
    def _create_task_display(self):
        """Create and show GUI task display for this document"""
        try:
            # Get director from app
            director = getattr(self._app, 'director', None)
            if director is None:
                components = getattr(self._app, 'components', {})
                director = components.get('director')
            
            if director is None:
                raise RuntimeError("Director not available")
            
            # Create task display filtered for this document
            task_monitor = TaskMonitor.get_instance(director)
            self.task_display = GUITaskDisplay(
                task_monitor, 
                filter_document_id=self._document.document_id
            )
            
            # Clear content section and add task display with margins
            self.content_section.clear()
            
            # Wrap task display in container with 20px margins and flex to fill available space
            task_display_wrapper = toga.Box(
                children=[self.task_display.container],
                style=Pack(
                    direction=COLUMN,
                    margin_top=20,
                    margin_left=20,
                    margin_right=20,
                    margin_bottom=0,  # No bottom margin to maximize height
                    flex=1,  # Fill available space like description canvas

                )
            )
            
            self.content_section.add(task_display_wrapper)
            
            logger.info(f"Created task display for document: {self._document.document_id}")
            
        except Exception as e:
            logger.error(f"Failed to create task display: {e}")
            raise
    
    def _show_stopped_message(self, output_path, completed_tasks, failed_tasks):
        """Show a custom stopped message with results and options"""
        # Clear content and create stopped message view
        self.content_section.clear()
        
        # Create main container
        stopped_container = toga.Box(
            style=Pack(
                direction=COLUMN,
                margin=(20, 20, 20, 20),
                align_items=CENTER
            )
        )
        
        # Title
        title_label = toga.Label(
            "🛑 Processing Stopped",
            style=Pack(
                font_size=16,
                font_weight='bold',
                color='#d32f2f',
                margin_bottom=15
            )
        )
        stopped_container.add(title_label)
        
        # Results summary
        total_tasks = completed_tasks + failed_tasks
        if total_tasks > 0:
            results_text = f"📊 Results: {completed_tasks} completed"
            if failed_tasks > 0:
                results_text += f", {failed_tasks} failed"
        else:
            results_text = "⏸️ Processing was interrupted before completion"
            
        results_label = toga.Label(
            results_text,
            style=Pack(
                font_size=12,
                margin_bottom=10,
                text_align=CENTER
            )
        )
        stopped_container.add(results_label)
        
        # Output location (if available)
        if output_path:
            output_label = toga.Label(
                f"📁 Output: {output_path}",
                style=Pack(
                    font_size=11,
                    color='#666666',
                    margin_bottom=20,
                    text_align=CENTER
                )
            )
            stopped_container.add(output_label)
        
        # Action buttons
        button_container = toga.Box(
            style=Pack(direction=ROW, margin_top=10)
        )
        
        # View Output button (if output exists)
        if output_path and Path(output_path).exists():
            view_output_btn = toga.Button(
                "📁 View Output",
                on_press=lambda w: self._open_output_folder(output_path),
                style=Pack(margin_right=10)
            )
            button_container.add(view_output_btn)
        
        # Activity Monitor button
        activity_btn = toga.Button(
            "📊 Activity Monitor",
            on_press=lambda w: self._open_activity_monitor(),
            style=Pack(margin_right=10)
        )
        button_container.add(activity_btn)
        
        # Back button
        back_btn = toga.Button(
            "↩️ Back",
            on_press=lambda w: self._reset_content_section(),
            style=Pack(background_color='#1976d2', color='white')
        )
        button_container.add(back_btn)
        
        stopped_container.add(button_container)
        
        # Add to content section
        self.content_section.add(stopped_container)
    
    def _open_output_folder(self, output_path):
        """Open the output folder in Finder/Explorer"""
        try:
            import subprocess
            import platform
            
            path = Path(output_path)
            if path.exists():
                if platform.system() == "Darwin":  # macOS
                    subprocess.run(["open", str(path)])
                elif platform.system() == "Windows":
                    subprocess.run(["explorer", str(path)])
                else:  # Linux
                    subprocess.run(["xdg-open", str(path)])
            else:
                logger.warning(f"Output path does not exist: {path}")
        except Exception as e:
            logger.error(f"Failed to open output folder: {e}")
    
    def _open_activity_monitor(self):
        """Open the activity monitor window"""
        try:
            # Use the app's activity monitor functionality
            if hasattr(self._app, 'show_activity_monitor'):
                self._app.show_activity_monitor()
            else:
                logger.warning("Activity monitor not available")
        except Exception as e:
            logger.error(f"Failed to open activity monitor: {e}")
    
    # Event Handlers - Thin Wrappers for Director
    
    async def choose_folder_handler(self, widget):
        """Handle folder selection"""
        try:
            folder_path = await self.dialog(toga.SelectFolderDialog(
                title=_("select_folder_title")
            ))
            
            if folder_path:
                self.selected_folder = Path(folder_path)
                folder_name = self.selected_folder.name
                
                # Update window title to include folder name
                self.title = f"Fichero: {folder_name}"
                
                # Update button text to "Choose Different Folder"
                self.choose_folder_btn.text = "Choose Different Folder"
                
                # Switch to clean folder icon immediately when folder is selected
                self._switch_to_processing_icon()
                
                # Update the path display immediately (just show the path, not "Processing")
                self._switch_to_folder_path_label()
                
                # Show both buttons when folder is selected
                self.reset_btn.style.visibility = 'visible'
                self.process_btn.style.visibility = 'visible'
                
                # Enable process button only if plan is selected
                self.process_btn.enabled = bool(self.current_plan)
                logger.info(f"Selected folder: {self.selected_folder}")
            
        except Exception as e:
            logger.error(f"Error selecting folder: {e}")
            await self.dialog(toga.ErrorDialog("Error", f"Failed to select folder: {e}"))

    def help_handler(self, widget):
        """Handle help button - open help website"""
        webbrowser.open("https://www.tubb.ca/fichero/")
    
    def reset_handler(self, widget):
        """Handle reset button - clear folder selection and return to initial state"""
        try:
            # Clear selected folder
            self.selected_folder = None
            
            # Reset window title back to just "Fichero"
            self.title = "Fichero"
            
            # Reset button text back to original
            self.choose_folder_btn.text = _("choose_folder")
            
            # Switch back to question mark icon
            self._switch_to_question_icon()
            
            # Switch back to choose button (removes path display)
            self._switch_to_choose_button()
            
            # Reset content section to show help text
            self._reset_content_section()
            
            # Hide both buttons again
            self.reset_btn.style.visibility = 'hidden'
            self.process_btn.style.visibility = 'hidden'
            
            logger.info("Reset to initial state")
            
        except Exception as e:
            logger.error(f"Error resetting: {e}")
    
    async def stop_handler(self, widget):
        """Handle stop button - cancel current processing and show results"""
        try:
            if not self.current_task_ids:
                return
            
            # Ask for confirmation
            confirm = await self.dialog(toga.ConfirmDialog(
                "Stop Processing",
                "Are you sure you want to stop the current processing?"
            ))
            
            if confirm:
                # Get task status before cancelling to show what was completed
                director = self._app.director
                completed_tasks = 0
                failed_tasks = 0
                output_path = None
                
                for task_id in self.current_task_ids:
                    try:
                        status = director.get_task_status(task_id)
                        if status and hasattr(status, 'value'):
                            if status.value == "SUCCESS":
                                completed_tasks += 1
                            elif status.value == "FAILED":
                                failed_tasks += 1
                        
                        # Get output path from task info
                        if not output_path:
                            task_info = director.get_task_info(task_id)
                            if task_info:
                                output_path = getattr(task_info, 'output_path', None)
                        
                        # Cancel the task
                        director.cancel_task(task_id)
                        logger.info(f"Cancelled task: {task_id}")
                    except Exception as e:
                        logger.warning(f"Could not cancel task {task_id}: {e}")
                
                # Store total tasks before clearing
                total_tasks = len(self.current_task_ids)
                
                # Reset UI state
                self._reset_to_process_button()
                self.current_task_ids = []
                
                # Stop task display monitoring
                if self.task_display:
                    self.task_display.stop_monitoring()
                
                # Show custom stopped message
                    self._show_stopped_message(output_path, completed_tasks, failed_tasks)
                
                # Show summary dialog
                message = f"Processing stopped.\n\nCompleted: {completed_tasks}/{total_tasks} tasks"
                if failed_tasks > 0:
                    message += f"\nFailed: {failed_tasks}"
                if output_path:
                    message += f"\n\nOutput location:\n{output_path}"
                
                await self.dialog(toga.InfoDialog("Processing Stopped", message))
                
        except Exception as e:
            logger.error(f"Error stopping processing: {e}")
            await self.dialog(toga.ErrorDialog("Error", f"Failed to stop processing: {e}"))

    async def process_handler(self, widget):
        """
        Handle process button - create GUI task display and delegate to director.py
        
        This creates a simple GUITaskDisplay for this document and starts processing.
        """
        if not self.selected_folder:
            await self.dialog(toga.ErrorDialog("Error", "Please select a folder to process"))
            return
        
        if not self.current_plan:
            await self.dialog(toga.ErrorDialog("Error", "Please select a plan"))
            return
        
        # Use default workflow if none selected
        workflow_to_use = self.current_workflow or "default"
        
        # Ask user where to save output - default to Desktop
        try:
            # Get desktop path cross-platform
            desktop_path = Path.home() / "Desktop"
            if not desktop_path.exists():
                # Fallback to home directory if Desktop doesn't exist
                desktop_path = Path.home()
            
            folder_name = self.selected_folder.name
            suggested_name = f"{folder_name}_processed"
            
            # Use SelectFolderDialog with desktop as initial directory
            parent_path = await self.dialog(toga.SelectFolderDialog(
                title="Choose where to save processed results...",
                initial_directory=desktop_path
            ))
            
            if not parent_path:
                return  # User cancelled
            
            # Create the output path with suggested name
            output_path = Path(parent_path) / suggested_name
            
            # Confirm continuing processing if folder already exists
            if output_path.exists():
                continue_processing = await self.dialog(toga.ConfirmDialog(
                    "Continue Processing?",
                    f'"{output_path.name}" already exists. Processing will continue where you left off.'
                ))
                if not continue_processing:
                    return
            
            logger.info(f"User chose save location: {output_path}")
            
        except Exception as e:
            logger.error(f"Error with save dialog: {e}")
            await self.dialog(toga.ErrorDialog("Error", f"Failed to select save location: {e}"))
            return
        
        # Start activity indicator and hide the footer buttons during processing
        if self.activity_indicator is not None:
            self.activity_indicator.start()
        # Store reference to footer and remove it from main content
        self._main_content = self.content
        self._main_content.remove(self.footer_section)
        
        # Keep the current path display and folder icon as they are during processing
        
        try:
            # Get director service (app should have initialized it)
            if not hasattr(self._app, 'director') or not self._app.director:
                raise Exception("Director service not available")
            
            director = self._app.director
            
            if not FicheroDirector.is_initialized():
                raise Exception("Director service not initialized")
            
            # Director handles folder detection internally
            detected_folders = [self.selected_folder]
            
            # Submit tasks using director's auto-detection - this handles everything!
            self.current_task_ids = director.process_with_auto_detection(
                input_path=self.selected_folder,
                output_path=output_path,
                plan_name=self.current_plan,
                workflow_name=workflow_to_use,
                document_context={
                    "document_window": self,
                    "document_id": self._document.document_id
                }
            )
            
            if not self.current_task_ids:
                raise Exception("No tasks were submitted")
            
            logger.info(f"Submitted {len(self.current_task_ids)} tasks for processing")
            
            # Create and show GUI task display for this document
            self._create_task_display()
            if self.task_display:
                self.task_display.start_monitoring()
            
            # Start monitoring task completion
            asyncio.create_task(self._monitor_task_completion())
            
        except Exception as e:
            logger.error(f"Processing failed: {e}")
            await self.dialog(toga.ErrorDialog("Error", f"Failed to start processing: {e}"))
            self._reset_to_process_button()
    
    async def _monitor_task_completion(self):
        """Monitor task completion in background - GUITaskDisplay handles UI updates"""
        if not self.current_task_ids:
            return
        
        director = self._app.director
        
        while True:
            try:
                # Check if all tasks completed
                statuses = []
                for task_id in self.current_task_ids:
                    status = director.get_task_status(task_id)
                    if status and hasattr(status, 'value'):
                        statuses.append(status.value)
                    else:
                        statuses.append('UNKNOWN')
                
                if all(s in ["SUCCESS", "FAILED", "CANCELLED"] for s in statuses):
                    # All tasks completed - reset button states
                    self._reset_to_process_button()
                    self.current_task_ids = []
                    break
                
                await asyncio.sleep(2)  # Check every 2 seconds
                
            except Exception as e:
                logger.error(f"Error monitoring tasks: {e}")
                # Reset button states on error
                self._reset_to_process_button()
                break

    # Plan Management - Simplified
    
    def _initialize_plan_workflow(self):
        """Initialize plan and workflow using unified helper"""
        try:
            from ...config.core.plan_workflow_ui_helper import PlanWorkflowUIHelper
            
            # Create unified helper
            self.ui_helper = PlanWorkflowUIHelper(self._app)
            
            # Initialize widgets with app defaults (document-specific mode)
            result = self.ui_helper.initialize_document_widgets(
                self.plan_selector, 
                self.workflow_selector
            )
            
            # Store current selections
            self.current_plan = result.get('plan')
            self.current_workflow = result.get('workflow')
            
            # Enable process button if folder selected
            self.process_btn.enabled = bool(self.selected_folder and self.current_plan)
            
        except Exception as e:
            logger.error(f"Error initializing plan/workflow: {e}")
    
    def _on_plan_change(self, widget):
        """Handle plan selection change using unified helper"""
        try:
            if not hasattr(self, 'ui_helper'):
                return
            
            # Use unified helper with save_as_default=False (document-specific)
            result = self.ui_helper.handle_plan_change(
                widget, 
                self.workflow_selector, 
                save_as_default=False
            )
            
            # Update current selections
            self.current_plan = result.get('plan')
            self.current_workflow = result.get('workflow')
            
            # Enable process button if folder selected and plan chosen
            self.process_btn.enabled = bool(self.selected_folder and self.current_plan)
            
            logger.info(f"Document plan changed: {result}")
            
        except Exception as e:
            logger.error(f"Error handling plan change: {e}")
    
    def _on_workflow_change(self, widget):
        """Handle workflow selection change using unified helper"""
        try:
            if not hasattr(self, 'ui_helper'):
                return
            
            # Use unified helper with save_as_default=False (document-specific)
            workflow_name = self.ui_helper.handle_workflow_change(
                widget, 
                save_as_default=False
            )
            
            # Update current selection
            self.current_workflow = workflow_name
            
            logger.info(f"Document workflow changed: {workflow_name}")
        
        except Exception as e:
            logger.error(f"Error handling workflow change: {e}")

    # Window Management
    
    def _setup_window_handlers(self):
        """Set up window event handlers"""
        try:
            def on_close_handler(widget, **kwargs):
                try:
                    return self._document.close()
                except Exception as e:
                    logger.warning(f"Error in close handler: {e}")
                    return True
            
            # Set close handler if available
            if hasattr(self, 'on_close'):
                self.on_close = on_close_handler
                
        except Exception as e:
            logger.warning(f"Failed to set up window handlers: {e}")
    

    
