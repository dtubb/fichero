"""
Description View Component

Handles beautiful markdown rendering for welcome text and plan descriptions.
Uses canvas-based text rendering with rounded backgrounds and link handling.
"""

import toga
from toga.style import Pack
from toga.constants import COLUMN
import webbrowser
import asyncio
import logging
from typing import Optional, List, Dict

# Use the builtin _ function installed by translation.install()
# No need to import gettext or override _ - it's in builtins after app startup

logger = logging.getLogger(__name__)


class DescriptionView:
    """Description view component with markdown rendering"""
    
    def __init__(self, app):
        """Initialize description view"""
        self.app = app
        
        # UI components
        self.container: Optional[toga.Box] = None
        self.canvas: Optional[toga.Canvas] = None
        
        # State
        self.current_mode = "welcome"  # "welcome", "plan_description", "ready_to_process"
        self.current_plan = None
        self.current_plan_filename = None
        self.current_workflow = None
        
        # Link tracking for click handling
        self.link_areas: List[Dict] = []
    
    def create(self) -> toga.Box:
        """Create the description view UI"""
        # Create canvas for markdown rendering
        self.canvas = toga.Canvas(
            style=Pack(
                margin_top=5,
                margin_right=20,
                margin_bottom=10,
                margin_left=20,
                flex=1
            ),
            on_resize=self._draw_content,
            on_press=self._handle_canvas_click
        )
        
        # Container
        self.container = toga.Box(
            children=[self.canvas],
            style=Pack(direction=COLUMN, flex=1)
        )
        
        # Draw content after a brief delay
        asyncio.create_task(self._delayed_draw_content())
        
        return self.container
    
    async def _delayed_draw_content(self):
        """Draw content after a brief delay to ensure canvas is ready"""
        await asyncio.sleep(0.1)
        try:
            self._draw_content()
        except Exception as e:
            logger.error(f"Error in delayed draw content: {e}")
    
    def show_welcome_text(self):
        """Show welcome/description text"""
        self.current_mode = "welcome"
        self._draw_content()
    
    def show_plan_description(self, plan_name: str, plan_filename: str, workflow: str):
        """Show plan description when folder is selected"""
        self.current_mode = "plan_description"
        self.current_plan = plan_name
        self.current_plan_filename = plan_filename
        self.current_workflow = workflow
        self._draw_content()
    
    def show_ready_to_process(self, plan_name: str, plan_filename: str, workflow: str):
        """Show ready to process message"""
        self.current_mode = "ready_to_process"
        self.current_plan = plan_name
        self.current_plan_filename = plan_filename
        self.current_workflow = workflow
        self._draw_content()
    
    def _draw_content(self, canvas=None, **kwargs):
        """Draw content on canvas"""
        try:
            if canvas is None:
                canvas = self.canvas
            
            if not canvas or not hasattr(canvas, 'layout') or not canvas.layout:
                return
            
            # Clear and draw background
            with canvas.context.Fill(color='#FFFFFF') as clear_fill:
                clear_fill.rect(0, 0, canvas.layout.content_width, canvas.layout.content_height)
            
            self._draw_rounded_background(canvas)
            
            # Draw content based on current mode
            if self.current_mode == "welcome":
                self._draw_welcome_content(canvas)
            elif self.current_mode == "plan_description":
                self._draw_plan_description_content(canvas)
            elif self.current_mode == "ready_to_process":
                self._draw_ready_to_process_content(canvas)
                
        except Exception as e:
            logger.error(f"Error drawing content: {e}")
    
    def _draw_rounded_background(self, canvas):
        """Draw rounded white background with thin grey border"""
        width = canvas.layout.content_width
        height = canvas.layout.content_height
        corner_radius = 6
        
        # Light gray background for rounded corners
        with canvas.context.Fill(color='#F0F0F0') as full_background:
            full_background.rect(0, 0, width, height)
        
        # White rounded rectangle
        with canvas.context.Fill(color='#FFFFFF') as background:
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
        
        # Thin light grey border
        with canvas.context.Stroke(color='#D5D5D5', line_width=1) as border:
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
    
    def _draw_welcome_content(self, canvas):
        """Draw welcome/description text with markdown support"""
        self.link_areas = []
        
        # Fonts
        try:
            regular_font = toga.Font(family=toga.fonts.SYSTEM, size=10, weight="light")
            bold_font = toga.Font(family=toga.fonts.SYSTEM, size=10, weight="bold")
        except Exception as e:
            logger.warning(f"Could not create custom fonts, using defaults: {e}")
            regular_font = toga.Font(family=toga.fonts.SYSTEM, size=10)
            bold_font = toga.Font(family=toga.fonts.SYSTEM, size=10)
        
        # Get description text from translations
        text = _("description")
        logger.info(f"DEBUG: Translation result for 'description': {text[:100]}...")
        
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
    
    def _draw_plan_description_content(self, canvas):
        """Draw plan description content"""
        # Fonts
        try:
            regular_font = toga.Font(family=toga.fonts.SYSTEM, size=10, weight="light")
            bold_font = toga.Font(family=toga.fonts.SYSTEM, size=10, weight="bold")
        except Exception as e:
            logger.warning(f"Could not create custom fonts, using defaults: {e}")
            regular_font = toga.Font(family=toga.fonts.SYSTEM, size=10)
            bold_font = toga.Font(family=toga.fonts.SYSTEM, size=10)
        
        # Get plan description
        description = self._get_plan_description()
        
        # Margins
        line_height_multiplier = 1.8
        left_margin = 15
        top_margin = 15
        right_margin = 10
        max_width = canvas.layout.content_width - left_margin - right_margin
        
        # Start with title
        title = f"*Plan:* {self.current_plan}" if self.current_plan else "*No Plan Selected*"
        current_y = top_margin
        
        # Render title
        current_y = self._render_paragraph(canvas, title, left_margin, current_y, 
                                         max_width, regular_font, bold_font, line_height_multiplier)
        
        # Add space after title
        current_y += regular_font.size * line_height_multiplier * 0.8
        
        # Render description
        current_y = self._render_paragraph(canvas, description, left_margin, current_y, 
                                         max_width, regular_font, bold_font, line_height_multiplier)
    
    def _draw_ready_to_process_content(self, canvas):
        """Draw ready to process content"""
        # Fonts
        try:
            regular_font = toga.Font(family=toga.fonts.SYSTEM, size=10, weight="light")
            bold_font = toga.Font(family=toga.fonts.SYSTEM, size=10, weight="bold")
        except Exception as e:
            logger.warning(f"Could not create custom fonts, using defaults: {e}")
            regular_font = toga.Font(family=toga.fonts.SYSTEM, size=10)
            bold_font = toga.Font(family=toga.fonts.SYSTEM, size=10)
        
        # Get plan description
        description = self._get_plan_description()
        
        # Margins
        line_height_multiplier = 1.8
        left_margin = 15
        top_margin = 15
        right_margin = 10
        max_width = canvas.layout.content_width - left_margin - right_margin
        
        # Start with title
        title = f"*Plan:* {self.current_plan}" if self.current_plan else "*No Plan Selected*"
        current_y = top_margin
        
        # Render title
        current_y = self._render_paragraph(canvas, title, left_margin, current_y, 
                                         max_width, regular_font, bold_font, line_height_multiplier)
        
        # Add space after title
        current_y += regular_font.size * line_height_multiplier * 0.8
        
        # Render description
        current_y = self._render_paragraph(canvas, description, left_margin, current_y, 
                                         max_width, regular_font, bold_font, line_height_multiplier)
        
        # Draw workflow steps if available
        if self.current_plan_filename and self.current_workflow:
            try:
                from fichero.config.core.plan_manager import PlanManager
                plan_data = PlanManager._load_plan_file(self.current_plan_filename, self.app)
                if plan_data and 'workflows' in plan_data and self.current_workflow in plan_data['workflows']:
                    steps = plan_data['workflows'][self.current_workflow]
                    if isinstance(steps, list):
                        # Add space before steps
                        current_y += regular_font.size * line_height_multiplier * 0.8
                        
                        # Render steps
                        steps_text = "*Steps:* " + ", ".join(steps)
                        current_y = self._render_paragraph(canvas, steps_text, left_margin, current_y, 
                                                         max_width, regular_font, bold_font, line_height_multiplier)
            except Exception as e:
                logger.debug(f"Could not load workflow steps: {e}")
        
        # Add space before "Ready to process..."
        current_y += regular_font.size * line_height_multiplier * 0.8
        
        # Draw 'Ready to process...' centered, italics
        ready_text = "Ready to process..."
        try:
            ready_font = toga.Font(family=toga.fonts.SYSTEM, size=10, weight="normal", style="italic")
        except Exception as e:
            logger.warning(f"Could not create italic font, using regular: {e}")
            ready_font = toga.Font(family=toga.fonts.SYSTEM, size=10)
        
        try:
            ready_width, ready_height = canvas.measure_text(ready_text, ready_font)
            ready_x = (canvas.layout.content_width - ready_width) // 2
            ready_y = current_y + (regular_font.size * line_height_multiplier * 0.8)
        except Exception as e:
            logger.warning(f"Could not measure ready text, using fallback: {e}")
            ready_x = 20
            ready_y = current_y + (regular_font.size * line_height_multiplier * 0.8)
        
        with canvas.context.Fill(color='#000000') as ready_fill:
            ready_fill.write_text(ready_text, ready_x, ready_y, ready_font)
    
    def _get_plan_description(self) -> str:
        """Get the description of the currently selected plan"""
        try:
            if not self.current_plan_filename:
                return "Please select a plan to see its description."
            
            from fichero.config.core.plan_manager import PlanManager
            plan_data = PlanManager._load_plan_file(self.current_plan_filename, self.app)
            
            if plan_data and 'description' in plan_data:
                return plan_data['description']
            else:
                return f"Plan: {self.current_plan}"
                
        except Exception as e:
            logger.debug(f"Could not load plan description: {e}")
            return f"Plan: {self.current_plan}"
    
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
                
                try:
                    word_width, _ = canvas.measure_text(test_word, element['font'])
                except Exception as e:
                    logger.warning(f"Could not measure word width: {e}")
                    word_width = len(test_word) * 6  # Fallback
                
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
                    
                    try:
                        word_width = canvas.measure_text(word, element['font'])[0]
                    except Exception as e:
                        logger.warning(f"Could not measure word width for new line: {e}")
                        word_width = len(word) * 6
                    
                    current_line_elements = [{
                        **element,
                        'content': word,
                        'width': word_width
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
            color = '#0064C8' if element['color'] == 'blue' else '#000000'
            
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
        """Handle clicks on canvas for links"""
        for link_area in self.link_areas:
            if (link_area['x'] <= x <= link_area['x'] + link_area['width'] and
                link_area['y'] <= y <= link_area['y'] + link_area['height']):
                webbrowser.open(link_area['url'])
                break 