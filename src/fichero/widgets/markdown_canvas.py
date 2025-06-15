"""
Reusable markdown canvas widget for rendering text with markdown support.

This widget extracts and encapsulates the working markdown rendering logic
from app.py to make it reusable across the application.

Supports:
- Bold text: **bold**
- Italic text: *italic*  
- Clickable links: [text](url)
- Word wrapping
- Centered or left-aligned text
"""

import toga
from toga.style import Pack
import webbrowser
import re


class MarkdownCanvas:
    """
    A canvas-based widget that renders text with markdown formatting.
    
    This class handles all the complex logic of parsing markdown text,
    measuring text dimensions, word wrapping, and click detection for links.
    """
    
    def __init__(self, text="", font_size=10, line_height_multiplier=1.8, 
                 left_padding=15, top_padding=15, right_padding=10, 
                 canvas_style=None):
        """
        Initialize the markdown canvas.
        
        Args:
            text: The markdown text to render
            font_size: Font size for regular text
            line_height_multiplier: Line spacing (1.0 = single spacing, 1.8 = generous spacing)
            left_padding: Left margin in pixels
            top_padding: Top margin in pixels  
            right_padding: Right margin in pixels
            canvas_style: Optional toga.Pack style for the canvas
        """
        self.text = text
        self.font_size = font_size
        self.line_height_multiplier = line_height_multiplier
        self.left_padding = left_padding
        self.top_padding = top_padding
        self.right_padding = right_padding
        
        # Store clickable link areas for click detection
        self.link_areas = []
        
        # Create canvas with event handlers
        default_style = Pack(flex=1, margin=10)
        self.canvas = toga.Canvas(
            style=canvas_style or default_style,
            on_resize=self._draw_text,
            on_press=self._handle_click
        )
        
        # Create font objects for different styles
        self.regular_font = toga.Font(
            family=toga.fonts.SYSTEM,
            size=font_size,
            weight="light"  # Light weight for better readability
        )
        self.bold_font = toga.Font(
            family=toga.fonts.SYSTEM,
            size=font_size,
            weight="bold"
        )
        try:
            # Try to create italic font (may not be supported on all platforms)
            self.italic_font = toga.Font(
                family=toga.fonts.SYSTEM,
                size=font_size,
                style=toga.Font.Style.ITALIC
            )
        except:
            # Fallback to regular font if italic not supported
            self.italic_font = self.regular_font
    
    def set_text(self, text):
        """Update the text content and redraw the canvas."""
        self.text = text
        self._draw_text()
    
    def _draw_text(self, canvas=None, **kwargs):
        """
        Main drawing method that renders all the markdown text.
        Called automatically when canvas is resized or text is updated.
        """
        if canvas is None:
            canvas = self.canvas
            
        # Clear canvas and reset link areas
        canvas.context.clear()
        self.link_areas = []
        
        # Calculate available width for text
        max_width = canvas.layout.content_width - self.left_padding - self.right_padding
        
        # If canvas not ready yet, skip drawing
        if max_width <= 0:
            return
        
        # Split text into paragraphs (separated by double newlines)
        paragraphs = self.text.split('\n\n')
        
        current_y = self.top_padding
        
        # Render each paragraph
        for paragraph_idx, paragraph in enumerate(paragraphs):
            if paragraph_idx > 0:
                # Add spacing between paragraphs
                current_y += self.regular_font.size * self.line_height_multiplier * 0.8
            
            # Parse and render this paragraph
            current_y = self._render_paragraph(canvas, paragraph, current_y, max_width)
    
    def _render_paragraph(self, canvas, text, start_y, max_width):
        """
        Parse markdown in a paragraph and render it with proper formatting.
        
        Returns:
            The Y position after rendering this paragraph
        """
        # Parse markdown elements using regex
        elements = self._parse_markdown(text)
        
        # Render elements with word wrapping
        current_y = start_y
        current_line_elements = []
        current_line_width = 0
        
        for element in elements:
            words = element['content'].split()
            
            for word_idx, word in enumerate(words):
                # Add space before word (except first word of element)
                space_prefix = " " if word_idx > 0 or current_line_elements else ""
                test_word = space_prefix + word
                
                # Measure word width
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
                        current_y = self._render_line(canvas, current_line_elements, current_y, max_width)
                    
                    # Start new line with current word
                    word_width = canvas.measure_text(word, element['font'])[0]
                    current_line_elements = [{
                        **element,
                        'content': word,
                        'width': word_width
                    }]
                    current_line_width = word_width
        
        # Render final line
        if current_line_elements:
            current_y = self._render_line(canvas, current_line_elements, current_y, max_width)
        
        return current_y
    
    def _parse_markdown(self, text):
        """
        Parse markdown syntax and return list of formatted elements.
        
        Returns:
            List of dict elements with 'type', 'content', 'font', 'color', and optionally 'url'
        """
        elements = []
        current_pos = 0
        
        # Define markdown patterns
        bold_pattern = r'\*\*([^*]+)\*\*'  # **bold**
        italic_pattern = r'(?<!\*)\*([^*]+)\*(?!\*)'  # *italic* (not part of **bold**)
        link_pattern = r'\[([^\]]+)\]\(([^)]+)\)'  # [text](url)
        
        # Combine patterns to find all matches in order
        combined_pattern = f'({bold_pattern})|({italic_pattern})|({link_pattern})'
        
        for match in re.finditer(combined_pattern, text):
            # Add regular text before the match
            if match.start() > current_pos:
                elements.append({
                    'type': 'text',
                    'content': text[current_pos:match.start()],
                    'font': self.regular_font,
                    'color': 'black'
                })
            
            # Add the formatted element
            if match.group(2):  # Bold text (**text**)
                elements.append({
                    'type': 'text',
                    'content': match.group(2),
                    'font': self.bold_font,
                    'color': 'black'
                })
            elif match.group(4):  # Italic text (*text*)
                elements.append({
                    'type': 'text',
                    'content': match.group(4),
                    'font': self.italic_font,
                    'color': 'black'
                })
            elif match.group(6) and match.group(7):  # Link [text](url)
                elements.append({
                    'type': 'link',
                    'content': match.group(6),
                    'url': match.group(7),
                    'font': self.regular_font,
                    'color': 'blue'
                })
            
            current_pos = match.end()
        
        # Add remaining regular text
        if current_pos < len(text):
            elements.append({
                'type': 'text',
                'content': text[current_pos:],
                'font': self.regular_font,
                'color': 'black'
            })
        
        return elements
    
    def _render_line(self, canvas, elements, y_position, max_width):
        """
        Render a line of formatted text elements.
        Override this method in subclasses to change alignment (e.g., centered).
        
        Returns:
            The Y position for the next line
        """
        current_x = self.left_padding
        
        for element in elements:
            # Draw text with appropriate color
            color = 'rgb(0, 100, 200)' if element['color'] == 'blue' else 'rgb(0, 0, 0)'
            
            with canvas.context.Fill(color=color) as fill_context:
                fill_context.write_text(
                    element['content'],
                    current_x,
                    y_position,
                    element['font'],
                    toga.constants.Baseline.TOP
                )
            
            # Store link area for click detection
            if element['type'] == 'link':
                self.link_areas.append({
                    'url': element['url'],
                    'x': current_x,
                    'y': y_position,
                    'width': element['width'],
                    'height': element['font'].size
                })
            
            current_x += element['width']
        
        return y_position + elements[0]['font'].size * self.line_height_multiplier
    
    def _handle_click(self, widget, x, y, **kwargs):
        """Handle clicks on the canvas to detect and open links."""
        for link_area in self.link_areas:
            if (link_area['x'] <= x <= link_area['x'] + link_area['width'] and
                link_area['y'] <= y <= link_area['y'] + link_area['height']):
                print(f"🔗 Opening link: {link_area['url']}")
                webbrowser.open(link_area['url'])
                return


class CenteredMarkdownCanvas(MarkdownCanvas):
    """
    A markdown canvas that centers each line of text.
    Inherits all functionality from MarkdownCanvas but overrides line rendering for centering.
    """
    
    def _render_line(self, canvas, elements, y_position, max_width):
        """
        Render a line of formatted text elements, centered horizontally.
        """
        # Calculate total width of all elements in this line
        total_line_width = sum(element['width'] for element in elements)
        
        # Calculate starting X position to center the line
        start_x = self.left_padding + (max_width - total_line_width) / 2
        
        current_x = start_x
        
        for element in elements:
            # Draw text with appropriate color
            color = 'rgb(0, 100, 200)' if element['color'] == 'blue' else 'rgb(0, 0, 0)'
            
            with canvas.context.Fill(color=color) as fill_context:
                fill_context.write_text(
                    element['content'],
                    current_x,
                    y_position,
                    element['font'],
                    toga.constants.Baseline.TOP
                )
            
            # Store link area for click detection
            if element['type'] == 'link':
                self.link_areas.append({
                    'url': element['url'],
                    'x': current_x,
                    'y': y_position,
                    'width': element['width'],
                    'height': element['font'].size
                })
            
            current_x += element['width']
        
        return y_position + elements[0]['font'].size * self.line_height_multiplier 