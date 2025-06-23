"""
About window for Fichero application
"""

import toga
from toga.style import Pack
from toga.constants import COLUMN, ROW, CENTER
from ..i18n import _
import webbrowser


class AboutWindow:
    """About window showing app information"""
    
    def __init__(self, app):
        """Initialize the about window"""
        self.app = app
        self.window = toga.Window(
            title="About Fichero",
            size=(306, 470),
            resizable=False
        )
        
        # Create the UI
        self._create_ui()
        
        # Center the window
        self._center_window()
    
    def _create_ui(self):
        """Create the about UI"""
        # Main container with margin
        main_container = toga.Box(
            style=Pack(
                direction=COLUMN,
                flex=1,
                margin=0
            )
        )
        
        # Top section with icon and app info
        top_section = toga.Box(
            style=Pack(
                direction=COLUMN,
                align_items=CENTER,
                margin=(10, 0, 20, 0)
            )
        )
        
        # App icon (clickable to open website)
        try:
            app_image = toga.Image("resources/icons/fichero.png")
            icon = toga.ImageView(
                app_image,
                style=Pack(
                    width=96,
                    height=96,
                    margin=(10, 0, 20, 0)
                )
            )
            # Make icon clickable
            icon.on_press = self._on_website_click
        except Exception:
            # Fallback to text
            icon = toga.Label(
                "📁",
                style=Pack(
                    font_size=48,
                    text_align=CENTER,
                    margin=(0, 0, 5, 0)
                )
            )
        
        # App name
        app_name = toga.Label(
            "Fichero",
            style=Pack(
                font_size=10,
                font_weight='bold',
                text_align=CENTER,
                margin=(0, 0, 5, 0)
            )
        )
        
        # Version (read from changelog)
        version = self._get_version()
        version_label = toga.Label(
            f"version {version}",
            style=Pack(
                font_size=9,
                text_align=CENTER,
                margin=(0, 0, 5, 0)
            )
        )
        
        # Copyright
        copyright_label = toga.Label(
            "© 2025 Daniel Tubb",
            style=Pack(
                font_size=9,
                text_align=CENTER,
                color='#666666',
                margin=(0, 0, 0, 0)
            )
        )
        
        # Add to top section
        top_section.add(icon)
        top_section.add(app_name)
        top_section.add(version_label)
        top_section.add(copyright_label)
        
        # Acknowledgments WebView (scrollable HTML content)
        self.acknowledgments_webview = toga.WebView(
            on_webview_load=self._on_webview_load,
            style=Pack(
                flex=1,
                margin=(0, 0, 0, 0)
            )
        )
        

        
        # Generate and set acknowledgments HTML content
        acknowledgments_html = self._generate_acknowledgments_html()
        self.acknowledgments_webview.set_content("about:blank", acknowledgments_html)
        
        # Website link at bottom
        website_link = toga.Label(
            "https://www.tubb.ca/fichero/",
            style=Pack(
                font_size=8,
                text_align=CENTER,
                color='#007bff',
                margin=(4, 0, 4,  0)
            )
        )
        # Make website link clickable
        website_link.on_press = self._on_website_click
        
        # Add all sections to main container
        main_container.add(top_section)
        main_container.add(self.acknowledgments_webview)
        main_container.add(website_link)
        
        # Set window content
        self.window.content = main_container
    
    def _generate_acknowledgments_html(self):
        """Generate HTML content for the acknowledgments section"""
        acknowledgments_text = self._get_acknowledgments_text()
        
        # Convert markdown-style text to HTML
        acknowledgments_html = self._markdown_to_html(acknowledgments_text)
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{
                    font-family: 'Lucida Grande', 'Lucida Sans Unicode', 'Lucida Sans', Geneva, Verdana, sans-serif;
                    margin: 0;
                    padding: 15px;
                    background-color: white;
                    line-height: 1.1;
                    font-size: 8pt;
                    color: #000;
                    text-align: center;
                }}
                h1, h2, h3, h4, p {{
                    margin: 0;
                    padding: 0;
                    font-size: 8pt;
                    line-height: 1.1;
                    text-align: center;
                }}
                h1, h2 {{
                    font-weight: bold;
                }}
                h3, h4 {{
                    font-weight: normal;
                    font-style: italic;
                }}
                a {{
                    color: #007bff;
                    text-decoration: none;
                }}
                a:hover {{
                    text-decoration: underline;
                }}
                strong {{
                    font-weight: bold;
                }}
                em {{
                    font-style: italic;
                }}
            </style>
        </head>
        <body>
            {acknowledgments_html}
        </body>
        </html>
        """
        
        return html
    
    def _markdown_to_html(self, text):
        """Convert simple markdown to HTML"""
        import re
        
        # Convert [text](url) to <a href="url" target="_blank">text</a> first
        text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2" target="_blank">\1</a>', text)
        
        # Convert **bold** to <strong>
        text = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', text)
        
        # Convert *italic* to <em> (simple approach)
        text = re.sub(r'\*([^*\n]+?)\*', r'<em>\1</em>', text)
        
        # Process lines for headers
        lines = text.split('\n')
        html_lines = []
        
        for line in lines:
            line = line.strip()
            if not line:
                html_lines.append('<br>')
            elif line.startswith('### '):
                # H3 header
                heading_text = line[4:].strip()
                html_lines.append(f'<h3>{heading_text}</h3>')
            elif line.startswith('## '):
                # H2 header
                heading_text = line[3:].strip()
                html_lines.append(f'<h2>{heading_text}</h2>')
            elif line.startswith('# '):
                # H1 header
                heading_text = line[2:].strip()
                html_lines.append(f'<h1>{heading_text}</h1>')
            else:
                html_lines.append(f'<p>{line}</p>')
        
        return '\n'.join(html_lines)
    
    def _get_version(self):
        """Get version from CHANGELOG file"""
        try:
            import os
            changelog_path = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'CHANGELOG')
            with open(changelog_path, 'r') as f:
                content = f.read()
                # Extract first version number (format: ## X.X.X)
                import re
                match = re.search(r'##\s+(\d+\.\d+\.\d+)', content)
                if match:
                    return match.group(1)
        except Exception:
            pass
        return "0.0.1"  # Default version
    
    def _get_acknowledgments_text(self):
        """Get the acknowledgments text from i18n system"""
        # Try to get from translation system first
        acknowledgments = _("about_acknowledgments", None)
        if acknowledgments:
            return acknowledgments
        
        # Fallback text with updated content
        return """[Fichero](http://www.tubb.ca/fichero/) transcribes and auto-catalogues historical archives using vision large language models and artificial intelligence, running locally or in the cloud.

## support and questions
**email** daniel@tubb.ca
**website** [https://www.tubb.ca/fichero/](https://www.tubb.ca/fichero/)

## coding
Daniel Tubb
Andrew Janco

*Daniel coded with [Cursor, the AI Code editor](https://www.cursor.com), with help from [Claude Sonnet](https://www.anthropic.com/claude/sonnet). Andy knows what he's doing.*

## testers and contributors
Ann Farnsworth-Alvear
Kelly López Roldán
Javier R. Ardila

## libraries and dependencies
[Python Software Foundation](https://python.org) 
[Toga GUI Toolkit](https://github.com/beeware/toga)
[Briefcase](https://github.com/beeware/briefcase) 

## user interface inspiration
[John Siracusa](https://hypercritical.co) for Hyperspace interface inspiration
[Bare Bones Software](https://barebones.com) for BBEdit's about dialog design

## license
This software is released under an open source license.

Source code available at: [https://github.com/dtubb/fichero](https://github.com/dtubb/fichero)

Report bugs and contribute at:
[https://github.com/dtubb/fichero/issues](https://github.com/dtubb/fichero/issues)

© 2025 Daniel Tubb
All rights reserved."""
    
    def _center_window(self):
        """Center the window on screen"""
        try:
            # Get the primary screen dimensions
            screen = self.app.screens[0]  # Primary screen
            screen_width = screen.size.width
            screen_height = screen.size.height
            
            # Calculate center position
            window_width = self.window.size.width
            window_height = self.window.size.height
            
            center_x = (screen_width - window_width) // 2
            center_y = (screen_height - window_height) // 2
            
            # Set the position
            self.window.position = (center_x, center_y)
        except Exception:
            # If centering fails, just use default position
            pass
    
    def _on_webview_load(self, widget, **kwargs):
        """Handle webview load - inject JavaScript to handle link clicks"""
        # JavaScript to intercept link clicks and store URL for Python to access
        js_code = """
        window.pendingUrl = null;
        document.addEventListener('click', function(e) {
            if (e.target.tagName === 'A') {
                e.preventDefault();
                // Store the URL so Python can access it
                window.pendingUrl = e.target.href;
                // Trigger a small change to notify Python
                document.title = 'LINK_CLICKED:' + Date.now();
            }
        });
        """
        try:
            self.acknowledgments_webview.evaluate_javascript(js_code)
            # Start checking for link clicks
            self._start_link_monitoring()
        except Exception:
            pass  # Ignore if JavaScript evaluation fails
    
    def _start_link_monitoring(self):
        """Start monitoring for link clicks"""
        import asyncio
        
        async def check_for_links():
            while True:
                try:
                    # Check if there's a pending URL to open
                    result = await self.acknowledgments_webview.evaluate_javascript("window.pendingUrl")
                    if result and result != "null":
                        # Open the URL in browser
                        webbrowser.open(result)
                        # Clear the pending URL
                        await self.acknowledgments_webview.evaluate_javascript("window.pendingUrl = null")
                except Exception:
                    pass
                # Wait a bit before checking again
                await asyncio.sleep(0.5)
        
        # Start the monitoring task
        try:
            asyncio.create_task(check_for_links())
        except Exception:
            pass
    
    def _on_website_click(self, widget, **kwargs):
        """Handle website button click"""
        webbrowser.open("https://www.tubb.ca/fichero/")
    
    def show(self):
        """Show the window"""
        self.window.show()
    
    def hide(self):
        """Hide the window"""  
        self.window.hide() 