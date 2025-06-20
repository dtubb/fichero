"""
Document Window for Fichero
Contains the document processing UI
"""

import toga
from toga.style import Pack
from toga.constants import COLUMN, ROW, CENTER, LEFT
from pathlib import Path
import asyncio
import webbrowser
import yaml
import os
from typing import Optional, Any
import logging

from ...utils import _, translator
from ...utils.plan_manager import PlanManager
from ...utils.app_settings import get_app_settings


class FicheroDocumentWindow(toga.DocumentWindow):
    """Document window for Fichero documents"""
    
    def __init__(self, doc):
        print(f"🪟 Initializing FicheroDocumentWindow for document {doc.document_id}")
        
        # Store doc reference and get app reference
        self._document = doc
        self._app = doc.app  # Get app from document
        
        # Initialize properties
        self.selected_folder = None
        self.link_areas = []
        self.current_plan = None
        self.current_workflow = None
        
        print("🎨 Creating window content...")
        # Create the beautiful content like the original app
        content = self._create_content()
        print("✅ Window content created successfully")
        
        print("🏗️ Initializing DocumentWindow...")
        # Initialize the DocumentWindow with the content (like official example)
        super().__init__(
            doc=doc,
            content=content
        )
        print("✅ FicheroDocumentWindow initialized successfully")
    
    def _create_content(self):
        """Create document window content"""
        # Create all UI sections like the original app
        self._create_folder_selection_section()
        self._create_description_section()
        self._create_footer()
        
        # Assemble main layout - pin footer to bottom (exactly like original)
        main_content = toga.Box(
            children=[
                toga.Box(
                    children=[
                        self.folder_section,
                        self.description_section,
                    ],
                    style=Pack(direction=COLUMN, flex=1)
                ),
                self.footer_section
            ],
            style=Pack(direction=COLUMN, flex=1)
        )
        
        # Schedule drawing after widget creation
        self._schedule_drawing()
        
        return main_content
    
    def _schedule_drawing(self):
        """Schedule the canvas drawing and initialization for after the window is shown"""
        async def draw_after_show():
            # Small delay to ensure window is fully created
            await asyncio.sleep(0.1)
            try:
                self._draw_description_text()
                self._draw_folder_background()
                # Initialize plan/workflow dropdown after widgets are created
                self._initialize_plan_workflow()
            except Exception as e:
                print(f"Drawing/initialization error: {e}")
        
        # Schedule the drawing and initialization
        asyncio.create_task(draw_after_show())

    def _create_folder_selection_section(self):
        """Create the folder selection section with icon and rounded gray canvas background"""
        # Fichero logo image (left side) - exactly like original
        try:
            fichero_image = toga.Image("resources/icons/folder_with_question_mark.png")
            folder_icon = toga.ImageView(
                fichero_image,
                style=Pack(
                    width=62,
                    height=62,
                    margin=3
                )
            )
        except Exception as e:
            print(f"Could not load folder_with_question_mark.png: {e}")
            # Fallback to text label
            folder_icon = toga.Label(
                _("folder_icon_label") + _("help"),
                style=Pack(
                    font_size=32,
                    text_align=CENTER,
                    margin=8
                )
            )
        
        # Choose folder button
        self.choose_folder_btn = toga.Button(
            _("choose_folder"),
            on_press=self.choose_folder_handler,
            style=Pack(
                width=120
            )
        )
        
        # Spacers to center the button horizontally
        left_spacer = toga.Box(style=Pack(flex=1))
        right_spacer = toga.Box(style=Pack(flex=1))
        
        # Horizontal row to center button
        button_row = toga.Box(
            children=[left_spacer, self.choose_folder_btn, right_spacer],
            style=Pack(direction=ROW, align_items=CENTER)
        )
        
        # Create canvas for rounded gray background
        self.folder_canvas = toga.Canvas(
            style=Pack(
                width=540,
                height=68,
            ),
            on_resize=self._draw_folder_background
        )
        
        # Transparent container for the button
        path_container = toga.Box(
            children=[button_row],
            style=Pack(
                direction=COLUMN,
                justify_content=CENTER,
                width=540,
                height=68,
            )
        )
        
        # Put canvas with proper margins at container level
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
        
        # Use a negative margin on the container to overlay it on the canvas
        overlaid_container = toga.Box(
            children=[path_container],
            style=Pack(
                direction=COLUMN,
                margin_top=-78,
                margin_right=20,
                margin_left=10,
            )
        )
        
        # Final path stack
        path_stack = toga.Box(
            children=[path_with_background, overlaid_container],
            style=Pack(direction=COLUMN)
        )
        
        # Container to position icon vertically centered with path_container
        icon_container = toga.Box(
            children=[folder_icon],
            style=Pack(
                direction=COLUMN,
                justify_content=CENTER,
                margin_top=20 + 34 - 34,
                margin_left=20
            )
        )
        
        # Main container holding both positioned elements
        self.folder_section = toga.Box(
            children=[icon_container, path_stack],
            style=Pack(
                direction=ROW,
                margin=(0, 0, 0, 0)
            )
        )

    def _draw_folder_background(self, canvas=None, **kwargs):
        """Draw the rounded gray background for the folder selection area"""
        if canvas is None:
            canvas = self.folder_canvas
            
        # Clear canvas
        canvas.context.clear()
        
        # Draw rounded gray rectangle
        width = canvas.layout.content_width
        height = canvas.layout.content_height
        corner_radius = 6  # Reduced from 8px for a subtler rounded look
        
        with canvas.context.Fill(color='rgb(217, 217, 217)') as background:  # #D9D9D9
            # Create rounded rectangle path
            background.begin_path()
            background.move_to(corner_radius, 0)
            
            # Top edge
            background.line_to(width - corner_radius, 0)
            
            # Top-right corner
            background.arc(width - corner_radius, corner_radius, corner_radius, 
                          -1.5708, 0)
            
            # Right edge  
            background.line_to(width, height - corner_radius)
            
            # Bottom-right corner
            background.arc(width - corner_radius, height - corner_radius, corner_radius,
                          0, 1.5708)
            
            # Bottom edge
            background.line_to(corner_radius, height)
            
            # Bottom-left corner
            background.arc(corner_radius, height - corner_radius, corner_radius,
                          1.5708, 3.14159)
            
            # Left edge
            background.line_to(0, corner_radius)
            
            # Top-left corner
            background.arc(corner_radius, corner_radius, corner_radius,
                          3.14159, 4.71239)
            
            # Close the path
            background.close_path()

    def _create_description_section(self):
        """Create the description section with canvas and rounded background"""
        description_canvas = toga.Canvas(
            style=Pack(
                margin_top=20,
                margin_right=20,
                margin_bottom=10,
                margin_left=20,
                flex=1,
                height=200,
            ),
            on_resize=self._draw_description_text,
            on_press=self._handle_canvas_click
        )
        
        # Store reference for drawing
        self.description_canvas = description_canvas
        
        # Container for description
        self.description_section = toga.Box(
            children=[description_canvas],
            style=Pack(
                direction=COLUMN,
                margin=(0, 0, 0, 0)
            )
        )

    def _draw_description_text(self, canvas=None, **kwargs):
        """Draw the description text on canvas with markdown support"""
        if canvas is None:
            canvas = self.description_canvas
            
        # Clear canvas
        canvas.context.clear()
        
        # Draw rounded rectangle background
        self._draw_rounded_background(canvas)
        
        # Store clickable link areas for mouse handling
        self.link_areas = []
        
        # Create fonts
        regular_font = toga.Font(
            family=toga.fonts.SYSTEM,
            size=10,
            weight="light"
        )
        bold_font = toga.Font(
            family=toga.fonts.SYSTEM,
            size=10,
            weight="bold"
        )
        
        # Get description text - use internationalized version like app_old.py
        text = _("description")
        
        # Define spacing and positioning
        line_height_multiplier = 1.8
        left_padding = 15  # Increased to better align with top container content
        top_padding = 15  # Reduced from 20px to 15px
        right_padding = 10
        max_width = canvas.layout.content_width - left_padding - right_padding
        
        # Split text by double newlines to handle paragraphs
        paragraphs = text.split('\n\n')
        
        current_y = top_padding
        
        for paragraph_idx, paragraph in enumerate(paragraphs):
            if paragraph_idx > 0:
                # Add paragraph spacing
                current_y += regular_font.size * line_height_multiplier * 0.8
            
            # Parse and render this paragraph
            current_y = self._render_paragraph(canvas, paragraph, left_padding, current_y, 
                                             max_width, regular_font, bold_font, line_height_multiplier)

    def _draw_rounded_background(self, canvas):
        """Draw a rounded rectangle background for the canvas"""
        width = canvas.layout.content_width
        height = canvas.layout.content_height
        corner_radius = 6  # Reduced from 8px for a subtler rounded look
        
        # First fill the entire canvas with light gray to make rounded corners visible
        with canvas.context.Fill(color='rgb(240, 240, 240)') as full_background:
            full_background.rect(0, 0, width, height)
        
        # Then draw the white rounded rectangle on top
        with canvas.context.Fill(color='rgb(255, 255, 255)') as background:
            # Create rounded rectangle path
            background.begin_path()
            background.move_to(corner_radius, 0)
            
            # Top edge
            background.line_to(width - corner_radius, 0)
            
            # Top-right corner
            background.arc(width - corner_radius, corner_radius, corner_radius, 
                          -1.5708, 0)  # -90° to 0°
            
            # Right edge  
            background.line_to(width, height - corner_radius)
            
            # Bottom-right corner
            background.arc(width - corner_radius, height - corner_radius, corner_radius,
                          0, 1.5708)  # 0° to 90°
            
            # Bottom edge
            background.line_to(corner_radius, height)
            
            # Bottom-left corner
            background.arc(corner_radius, height - corner_radius, corner_radius,
                          1.5708, 3.14159)  # 90° to 180°
            
            # Left edge
            background.line_to(0, corner_radius)
            
            # Top-left corner
            background.arc(corner_radius, corner_radius, corner_radius,
                          3.14159, 4.71239)  # 180° to 270°
            
            # Close the path
            background.close_path()

    def _render_paragraph(self, canvas, text, left_padding, start_y, max_width, 
                          regular_font, bold_font, line_height_multiplier):
        """Render a paragraph with markdown formatting"""
        import re
        
        # Parse text for markdown elements
        elements = []
        current_pos = 0
        
        # Find all markdown elements (bold and links)
        bold_pattern = r'\*([^*]+)\*'
        link_pattern = r'\[([^\]]+)\]\(([^)]+)\)'
        
        # Combine patterns and find all matches
        combined_pattern = f'({bold_pattern})|({link_pattern})'
        
        for match in re.finditer(combined_pattern, text):
            # Add text before the match
            if match.start() > current_pos:
                elements.append({
                    'type': 'text',
                    'content': text[current_pos:match.start()],
                    'font': regular_font,
                    'color': 'black'
                })
            
            if match.group(2):  # Bold text (*text*)
                elements.append({
                    'type': 'text',
                    'content': match.group(2),
                    'font': bold_font,
                    'color': 'black'
                })
            elif match.group(4) and match.group(5):  # Link [text](url)
                elements.append({
                    'type': 'link',
                    'content': match.group(4),
                    'url': match.group(5),
                    'font': regular_font,
                    'color': 'blue'
                })
            
            current_pos = match.end()
        
        # Add remaining text
        if current_pos < len(text):
            elements.append({
                'type': 'text',
                'content': text[current_pos:],
                'font': regular_font,
                'color': 'black'
            })
        
        # Now render elements with word wrapping
        current_y = start_y
        current_line_elements = []
        current_line_width = 0
        
        for element in elements:
            words = element['content'].split()
            
            for word_idx, word in enumerate(words):
                # Add space before word (except first word of element)
                space_prefix = " " if word_idx > 0 or current_line_elements else ""
                test_word = space_prefix + word
                
                word_width, _ = canvas.measure_text(test_word, element['font'])
                
                # Check if word fits on current line
                if current_line_width + word_width <= max_width:
                    # Add to current line
                    current_line_elements.append({
                        **element,
                        'content': test_word,
                        'width': word_width
                    })
                    current_line_width += word_width
                else:
                    # Render current line and start new line
                    if current_line_elements:
                        current_y = self._render_line(canvas, current_line_elements, 
                                                    left_padding, current_y, line_height_multiplier)
                    
                    # Start new line with current word
                    current_line_elements = [{
                        **element,
                        'content': word,
                        'width': canvas.measure_text(word, element['font'])[0]
                    }]
                    current_line_width = current_line_elements[0]['width']
        
        # Render final line
        if current_line_elements:
            current_y = self._render_line(canvas, current_line_elements, 
                                        left_padding, current_y, line_height_multiplier)
        
        return current_y

    def _render_line(self, canvas, elements, left_padding, y_position, line_height_multiplier):
        """Render a line of formatted text elements"""
        current_x = left_padding
        
        for element in elements:
            # Use Toga Fill context for proper text coloring
            if element['color'] == 'blue':
                with canvas.context.Fill(color='rgb(0, 100, 200)') as fill_context:
                    fill_context.write_text(
                        element['content'],
                        current_x,
                        y_position,
                        element['font'],
                        toga.constants.Baseline.TOP
                    )
            else:
                with canvas.context.Fill(color='rgb(0, 0, 0)') as fill_context:
                    fill_context.write_text(
                        element['content'],
                        current_x,
                        y_position,
                        element['font'],
                        toga.constants.Baseline.TOP
                    )
            
            # Track link areas for click handling
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
        """Handle clicks on the description canvas to detect link clicks"""
        for link_area in self.link_areas:
            if (link_area['x'] <= x <= link_area['x'] + link_area['width'] and
                link_area['y'] <= y <= link_area['y'] + link_area['height']):
                # Open the link
                webbrowser.open(link_area['url'])
                break

    def _create_footer(self):
        """Create the footer with help button, gear menu, and process controls"""
        # Left side: Help button
        left_section = toga.Box(style=Pack(direction=ROW))
        
        # Help button
        help_btn = toga.Button(
            _("help"),
            on_press=self.help_handler,
            style=Pack(
                font_size=12,
                font_weight='bold',
                width=24,
                height=24
            )
        )
        
        left_section.add(help_btn)
        
        # Plan selector dropdown (5px from help button)
        self.plan_selector = toga.Selection(
            items=PlanManager.get_plan_dropdown_options(self._app),
            style=Pack(
                width=120,
                font_size=11,
                margin_left=5,
                height=24
            ),
            on_change=self._on_plan_change
        )
        
        # Workflow selector dropdown (5px from plan selector)
        self.workflow_selector = toga.Selection(
            items=["Select a plan first"],
            style=Pack(
                width=120,
                font_size=11,
                margin_left=5,
                height=24
            ),
            on_change=self._on_workflow_change
        )
        
        left_section.add(self.plan_selector)
        left_section.add(self.workflow_selector)
        
        # Right side: Process controls
        right_section = toga.Box(style=Pack(direction=ROW))
        
        # Activity indicator for processing status
        self.activity_indicator = toga.ActivityIndicator(
            style=Pack(
                margin_right=10
            )
        )
        
        # Process button
        self.process_btn = toga.Button(
            _("process"),
            on_press=self.process_handler,
            enabled=False,
            style=Pack(
                font_size=12,
                height=32
            )
        )
        
        right_section.add(self.activity_indicator)
        right_section.add(self.process_btn)
        
        # Spacer to push right section to the right
        spacer = toga.Box(style=Pack(flex=1))
        
        self.footer_section = toga.Box(
            children=[left_section, spacer, right_section],
            style=Pack(
                direction=ROW,
                margin=(10, 20, 20, 20),
                align_items=CENTER
            )
        )

    # Plan Management Methods
    
    def _initialize_plan_workflow(self):
        """Initialize default plan and workflow selection"""
        try:
            # First, try to get the active plan from AppSettings
            app_settings = get_app_settings(self._app)
            active_plan_path = app_settings.get_shared_setting("active_plans")
            
            # Get all available plan options
            plan_options = PlanManager.get_plan_dropdown_options(self._app)
            
            # Try to find the active plan name from the file path
            active_plan_name = None
            if active_plan_path:
                try:
                    active_plan_file = Path(active_plan_path)
                    if active_plan_file.exists():
                        # Extract plan name (could be filename without extension or loaded from file)
                        active_plan_name = active_plan_file.stem
                        # Check if this plan name is in the available options
                        if active_plan_name not in plan_options:
                            active_plan_name = None
                except Exception as e:
                    print(f"⚠️ Could not load active plan from {active_plan_path}: {e}")
            
            # Use active plan if found, otherwise use first available plan
            if active_plan_name and active_plan_name in plan_options:
                selected_plan = active_plan_name
                print(f"📋 Using active plan from settings: {selected_plan}")
            elif plan_options and plan_options[0] not in ["No plans found", "Error loading plans", "Manage Plans..."]:
                selected_plan = plan_options[0]
                print(f"📋 Using first available plan: {selected_plan}")
            else:
                print("⚠️ No plans available")
                return
            
            # Set the plan in the dropdown
            if hasattr(self, 'plan_selector'):
                self.plan_selector.value = selected_plan
                self.current_plan = selected_plan
                
                # Update workflow options for the selected plan
                workflow_options = PlanManager.get_workflow_dropdown_options(selected_plan, self._app)
                self.workflow_selector.items = workflow_options
                
                # Set first workflow as default
                if workflow_options and workflow_options[0] not in ["Select a plan first", "No workflows in plan", "Error loading workflows"]:
                    default_workflow = workflow_options[0]
                    self.workflow_selector.value = default_workflow
                    self.current_workflow = default_workflow
                    print(f"📋 Initialized with plan: {self.current_plan}, workflow: {self.current_workflow}")
                else:
                    print("⚠️ No workflows available in selected plan")
            else:
                print("⚠️ Plan selector not available")
                
        except Exception as e:
            print(f"❌ Error initializing plan/workflow: {e}")
    
    def _on_plan_change(self, widget):
        """Handle plan selection change"""
        try:
            selection = widget.value
            if not selection:
                return
            
            # Handle special options
            if selection == "Manage Plans...":
                self._open_plans_manager()
                # Reset to previous selection
                if hasattr(self, 'current_plan') and self.current_plan:
                    widget.value = self.current_plan
                return
            elif selection in ["No plans found", "Error loading plans"]:
                return
            
            # Update current plan
            self.current_plan = selection
            self.current_workflow = None  # Reset workflow selection
            
            # Set this plan as active in AppSettings
            try:
                app_settings = get_app_settings(self._app)
                # Find the file path for this plan name
                # This is a simplified approach - we could enhance PlanManager to provide file paths
                user_plans_dir = self._app.paths.data / "plans"
                default_plans_dir = self._app.paths.app / "resources" / "plans"
                
                # Try user directory first, then default directory
                plan_file = None
                for plans_dir in [user_plans_dir, default_plans_dir]:
                    if plans_dir.exists():
                        for ext in ['.yml', '.yaml', '.json']:
                            potential_file = plans_dir / f"{selection}{ext}"
                            if potential_file.exists():
                                plan_file = potential_file
                                break
                    if plan_file:
                        break
                
                if plan_file:
                    app_settings.set_shared_setting("active_plans", str(plan_file), immediate_save=True)
                    print(f"✅ Set active plan: {plan_file.name}")
                else:
                    print(f"⚠️ Could not find file for plan: {selection}")
                    
            except Exception as e:
                print(f"⚠️ Failed to set active plan: {e}")
            
            # Update workflow dropdown with workflows for this plan
            workflow_options = PlanManager.get_workflow_dropdown_options(selection, self._app)
            self.workflow_selector.items = workflow_options
            
            # Auto-select first workflow if available
            if workflow_options and workflow_options[0] not in ["Select a plan first", "No workflows in plan", "Error loading workflows"]:
                first_workflow = workflow_options[0]
                self.workflow_selector.value = first_workflow
                self.current_workflow = first_workflow
                print(f"📋 Selected plan: {self.current_plan}, auto-selected workflow: {self.current_workflow}")
            else:
                self.workflow_selector.value = workflow_options[0] if workflow_options else "No workflows"
                print(f"📋 Selected plan: {self.current_plan}, no workflows available")
            
        except Exception as e:
            print(f"❌ Error handling plan change: {e}")
    
    def _on_workflow_change(self, widget):
        """Handle workflow selection change"""
        try:
            selection = widget.value
            if not selection or selection in ["Select a plan first", "No workflows in plan", "Error loading workflows"]:
                return
            
            # Update current workflow
            self.current_workflow = selection
            print(f"📋 Selected workflow: {self.current_workflow} (plan: {self.current_plan})")
                
        except Exception as e:
            print(f"❌ Error handling workflow change: {e}")
    
    def _open_plans_manager(self):
        """Open the plans management window"""
        try:
            from .config_windows import create_plans_editor_window
            
            # If we have a current plan, try to open it for editing
            plan_file = None
            if hasattr(self, 'current_plan') and self.current_plan:
                # Get plan file path using PlanManager if method exists
                if hasattr(PlanManager, 'get_plan_file_path'):
                    plan_file = PlanManager.get_plan_file_path(self.current_plan, self._app)
            
            plans_editor = create_plans_editor_window(self._app, plan_file)
            plans_editor.show()
            print(f"📝 Opening plans manager{f' for plan: {self.current_plan}' if self.current_plan else ''}")
            
            # Refresh dropdowns after plans manager closes (in case plans were modified)
            # Note: This would ideally be done with a callback when the plans manager closes
                
        except Exception as e:
            print(f"❌ Failed to open plans manager: {e}")

    # Event Handlers
    
    async def choose_folder_handler(self, widget):
        """Handle folder selection"""
        try:
            folder_path = await self.select_folder_dialog(
                title=_("select_folder_title")
            )
            
            if folder_path:
                self.selected_folder = Path(folder_path)
                folder_name = self.selected_folder.name
                self.choose_folder_btn.text = f"📁 {folder_name}"
                self.process_btn.enabled = True
                print(f"📁 Selected folder: {self.selected_folder}")
            
        except Exception as e:
            print(f"❌ Error selecting folder: {e}")

    def help_handler(self, widget):
        """Handle help button click"""
        print("🔘 Help button clicked - opening website")
        webbrowser.open("https://www.tubb.ca/fichero/")

    async def process_handler(self, widget):
        """Handle process button click"""
        if not self.selected_folder:
            print("❌ No folder selected")
            return
        
        print(f"🚀 Starting processing for folder: {self.selected_folder}")
        
        # Start activity indicator and disable process button
        self.activity_indicator.start()
        self.process_btn.enabled = False
        self.process_btn.text = _("processing") + "..."
        
        try:
            print(f"🔄 Processing folder {self.selected_folder} for document {self._document.document_id}")
            # Simulate processing
            await asyncio.sleep(2)
            print("✅ Processing completed!")
        except Exception as e:
            print(f"❌ Error processing: {e}")
        finally:
            # Re-enable process button
            self.activity_indicator.stop()
            self.process_btn.enabled = True
            self.process_btn.text = _("process")