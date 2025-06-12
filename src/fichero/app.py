"""
Fichero - Document Processing and Transcription GUI
Internationalized version with clean, modern layout
"""

import toga
from toga.style import Pack
from toga.constants import COLUMN, ROW, CENTER, LEFT
from .i18n import _, translator
import webbrowser
import asyncio
import sys
import os
from pathlib import Path
from . import director


class FicheroApp(toga.App):
    def startup(self):
        """Initialize the app with the new internationalized layout."""
        print("🚀 App starting up...")
        
        # Store selected folder path
        self.selected_folder = None
        
        # Create all UI elements (no header - title is in window title bar)
        self._create_folder_selection_section()
        self._create_description_section()
        self._create_footer()
        
        # Assemble main layout - pin footer to bottom
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
        
        print("🖼️ Creating main window...")
        # Create main window
        self.main_window = toga.MainWindow(
            title=_("app_title"), 
            size=(650, 406),  # Retina-adjusted window size (1300x812 / 2)
            resizable=False
        )
        self.main_window.content = main_content
        
        print("✨ Showing window...")
        self.main_window.show()
        
        # Draw initial description text
        self._draw_description_text()
        
        # Draw initial folder background
        self._draw_folder_background()
        
        print("🎉 Window should now be visible!")

    def finalize(self):
        """Clean up when app closes"""
        try:
            print("🧹 Cleaning up Redis and Celery workers...")
            director.stop_workers()
            print("✓ Cleanup completed")
        except Exception as e:
            print(f"Warning: Error during cleanup: {e}")

    def _create_folder_selection_section(self):
        """Create the folder selection section with icon and rounded gray canvas background"""
        # Fichero logo image (left side)
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
        
        # Spacers to center the button horizontally (original approach)
        left_spacer = toga.Box(style=Pack(flex=1))
        right_spacer = toga.Box(style=Pack(flex=1))
        
        # Horizontal row to center button
        button_row = toga.Box(
            children=[left_spacer, self.choose_folder_btn, right_spacer],
            style=Pack(direction=ROW, align_items=CENTER)
        )
        
        # Create canvas for rounded gray background (no margins - container handles positioning)
        self.folder_canvas = toga.Canvas(
            style=Pack(
                width=540,
                height=68,
                # No margins - handled by container
            ),
            on_resize=self._draw_folder_background
        )
        
        # Transparent container for the button (no margins - positioning handled by overlaid_container)
        path_container = toga.Box(
            children=[button_row],
            style=Pack(
                direction=COLUMN,
                justify_content=CENTER,
                width=540,
                height=68,
                # No margins - positioning handled by overlaid_container
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
                margin_left=10,  # Add left margin to create space between icon and canvas
            )
        )
        
        # Use a negative margin on the container to overlay it on the canvas
        overlaid_container = toga.Box(
            children=[path_container],
            style=Pack(
                direction=COLUMN,
                margin_top=-78,  # Move up by canvas height + container top margin: -(68 + 20)
                margin_right=20,  # Same right positioning as canvas container
                margin_left=10,  # Match left positioning with canvas container
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
                margin_top=20 + 34 - 34,  # 20 (path top) + 34 (path center) - 34 (icon half-height including margin)
                margin_left=20  # Back to 20px from left edge
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

    def _create_description_section(self):
        """Create the description section with transparent background for rounded corners"""
        description_canvas = toga.Canvas(
            style=Pack(
                margin_top=20,  # Increased from 10px to 20px
                margin_right=20,  # Same right margin as path_container
                margin_bottom=10,
                margin_left=20,
                flex=1,
                height=200,  # Fixed height for description area
                # Remove background_color to allow custom rounded shape
            ),
            on_resize=self._draw_description_text,
            on_press=self._handle_canvas_click
        )
        
        # Store reference for drawing
        self.description_canvas = description_canvas
        
        # Container for description to match top row structure
        self.description_section = toga.Box(
            children=[description_canvas],
            style=Pack(
                direction=COLUMN,
                margin=(0, 0, 0, 0)  # No margins - let the canvas handle positioning
            )
        )

    def _draw_description_text(self, canvas=None, **kwargs):
        """Draw the description text on canvas with markdown support (bold and links)"""
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
            weight="light"  # Use lighter weight to reduce text density
        )
        bold_font = toga.Font(
            family=toga.fonts.SYSTEM,
            size=10,
            weight="bold"
        )
        
        # Get description text
        from .i18n import _
        text = _("description")
        
        # Define spacing and positioning
        line_height_multiplier = 1.8  # 1.8x line spacing for better readability
        left_padding = 15  # Increased to better align with top container content
        top_padding = 15  # Reduced from 20px to 3px
        right_padding = 10
        max_width = canvas.layout.content_width - left_padding - right_padding
        
        # Split text by double newlines to handle paragraphs
        paragraphs = text.split('\n\n')
        
        current_y = top_padding
        
        for paragraph_idx, paragraph in enumerate(paragraphs):
            if paragraph_idx > 0:
                # Add paragraph spacing - moderate gap between paragraphs
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
        current_x = left_padding
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
        
        return y_position + elements[0]['font'].size * line_height_multiplier

    def _handle_canvas_click(self, widget, x, y, **kwargs):
        """Handle clicks on the description canvas to detect link clicks"""
        import webbrowser
        
        # Check if click coordinates intersect with any link areas
        for link_area in getattr(self, 'link_areas', []):
            if (link_area['x'] <= x <= link_area['x'] + link_area['width'] and
                link_area['y'] <= y <= link_area['y'] + link_area['height']):
                print(f"🔗 Opening link: {link_area['url']}")
                webbrowser.open(link_area['url'])
                return

    def _create_footer(self):
        """Create the footer with help and process buttons"""
        # Help button (left) - circular with bold text
        help_btn = toga.Button(
            _("help"),
            on_press=self.help_handler,
            style=Pack(
                font_size=12,  # Larger text, not bold
                font_weight='bold',
                width=24,
                height=24
                # Using default system button colors
            )
        )
        
        # Process button (right)
        self.process_btn = toga.Button(
            _("process"),
            on_press=self.process_handler,
            enabled=False,  # Disabled until folder is selected
            style=Pack(
                font_size=12,  # Larger text, not bold
                margin_right=20,
                height=32
            )
        )
        
        # Activity indicator for processing status
        self.activity_indicator = toga.ActivityIndicator(
            style=Pack(
                margin_right=20
            )
        )
        
        # Spacer to push buttons to edges
        spacer = toga.Box(style=Pack(flex=1))
        
        self.footer_section = toga.Box(
            children=[help_btn, 
            spacer, self.activity_indicator, self.process_btn, ],
            style=Pack(
                direction=ROW,
                margin=(10, 0, 20, 20)  # 10px from description (total 20px gap), 0 right (handled by elements), 20px bottom, 20px left
            )
        )

    async def choose_folder_handler(self, widget):
        """Handle folder selection"""
        try:
            # Open folder selection dialog
            selected_path = await self.main_window.select_folder_dialog(
                title=_("choose_folder")
            )
            
            if selected_path:
                self.selected_folder = selected_path
                # Update button text to show selected folder name
                folder_name = selected_path.name
                self.choose_folder_btn.text = f"📁 {folder_name}"
                
                # Enable process button
                self.process_btn.enabled = True
                
                print(f"Selected folder: {selected_path}")
            
        except Exception as e:
            print(f"Error selecting folder: {e}")

    def help_handler(self, widget):
        """Handle help button click - open Fichero website"""
        print("🔘 Help button clicked - opening website")
        webbrowser.open("https://www.tubb.ca/fichero/")

    async def process_handler(self, widget):
        """Handle process button click - open log window and run director.py"""
        if self.selected_folder:
            print(f"🔘 Processing folder: {self.selected_folder}")
            
            # Start activity indicator and disable process button
            self.activity_indicator.start()
            self.process_btn.enabled = False
            self.process_btn.text = _("processing") + "..."
            
            # Open log window and start processing (completely non-blocking)
            try:
                await self._open_log_window_and_process()
            except Exception as e:
                print(f"Error in process_handler: {e}")
                # Reset button state on error
                self.activity_indicator.stop()
                self.process_btn.enabled = True
                self.process_btn.text = _("process")
        else:
            print("No folder selected for processing")

    async def _open_log_window_and_process(self):
        """Open a log window and start processing with director.py"""
        # Create log window
        self.log_window = toga.Window(
            title="Fichero Processing Log",
            size=(800, 600)
        )
        
        # Create log text area
        self.log_text = toga.MultilineTextInput(
            readonly=True,
            style=Pack(
                flex=1,
                margin=10,
                font_family="monospace",
                font_size=10
            )
        )
        
        # Add initial log message  
        desktop = Path.home() / "Desktop"
        folder_name = self.selected_folder.name
        output_folder = desktop / f"Fichero_Output_{folder_name}"
        self.log_text.value = f"Starting Fichero processing...\nInput folder: {self.selected_folder}\nOutput folder: {output_folder}\n\n"
        
        # Create log window content
        log_content = toga.Box(
            children=[self.log_text],
            style=Pack(direction=COLUMN, flex=1)
        )
        
        self.log_window.content = log_content
        self.log_window.show()
        
        # Small delay to ensure window is visible
        await asyncio.sleep(0.1)
        
        # Start background processing
        asyncio.create_task(self._start_director_process_async())
    
    async def _start_director_process_async(self):
        """Start the director processing as a subprocess using the CLI entry point"""
        try:
            # Add processing info to log window
            self.log_text.value += f"Starting background processing...\n\n"
            
            # Create output folder path
            desktop = Path.home() / "Desktop"
            folder_name = self.selected_folder.name
            output_folder = desktop / f"Fichero_Output_{folder_name}"
            
            # Find the config file path
            config_path = Path(__file__).parent / "resources" / "plans" / "plans.yml"
            
            self.log_text.value += f"Output folder: {output_folder}\n"
            self.log_text.value += f"Config file: {config_path}\n"
            self.log_text.value += f"Input folder: {self.selected_folder}\n\n"
            
            # Build the CLI command - this is the exact same command that works in CLI mode
            cmd = [
                sys.executable,
                '-m', 'fichero',  # Use the CLI entry point that works
                'process-folders',
                str(output_folder),
                str(config_path),
                'archive-to-catalogue-qwen-max-segmented', 
                '--input-folder', str(self.selected_folder),
                '--no-use-weasel'
            ]
            
            self.log_text.value += f"Running command: {' '.join(cmd)}\n\n"
            
            # Start the subprocess using the CLI entry point
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT
            )
            
            # Read output line by line and update log window
            while True:
                line = await process.stdout.readline()
                if not line:
                    break
                line_text = line.decode('utf-8')
                self.log_text.value += line_text
                self.log_text.scroll_to_bottom()
                
            # Wait for process to complete
            await process.wait()
            
            if process.returncode == 0:
                self.log_text.value += f"\n✅ Processing completed successfully!\n"
                print("✅ Document processing completed successfully!")
            else:
                self.log_text.value += f"\n❌ Processing failed with exit code: {process.returncode}\n"
                print(f"❌ Processing failed with exit code: {process.returncode}")
                
        except Exception as e:
            error_msg = f"❌ Error: {str(e)}"
            self.log_text.value += error_msg + "\n"
            print(f"❌ Processing error: {e}")
        finally:
            # Always stop spinner and re-enable button when done
            self.activity_indicator.stop()
            self.process_btn.enabled = True
            self.process_btn.text = _("process")
    
    def set_language(self, language_code: str):
        """Change the app language and refresh UI"""
        translator.set_language(language_code)
        # TODO: Refresh all UI text (would need to recreate widgets)
        print(f"Language changed to: {language_code}")


def main():
    """Main entry point for the app."""
    return FicheroApp("Fichero", "ca.tubb.fichero")


if __name__ == "__main__":
    app = main()
    app.main_loop() 