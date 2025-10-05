"""
Acknowledgments Manager

Handles the acknowledgments text and HTML generation for the about dialog.
"""

import gettext

# Use the global _ function for translations
try:
    _ = gettext.gettext
except:
    def _(text): return text


class AcknowledgmentsManager:
    """Manages acknowledgments content and HTML generation"""

    def __init__(self, is_mobile=False):
        """Initialize the acknowledgments manager"""
        self.is_mobile = is_mobile
    
    def get_acknowledgments_text(self):
        """Get the acknowledgments text from i18n system"""
        # Try to get from translation system first
        acknowledgments = _("about_acknowledgments")
        if acknowledgments and acknowledgments != "about_acknowledgments":
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
    
    def generate_html(self):
        """Generate HTML content for the acknowledgments section"""
        acknowledgments_text = self.get_acknowledgments_text()

        # Convert markdown-style text to HTML
        acknowledgments_html = self._markdown_to_html(acknowledgments_text)

        # Use larger font size for mobile (16pt) vs desktop (8pt)
        font_size = '16pt' if self.is_mobile else '8pt'
        line_height = '1.4' if self.is_mobile else '1.1'

        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Helvetica Neue', Arial, sans-serif;
                    margin: 0;
                    padding: 15px;
                    background-color: white;
                    line-height: {line_height};
                    font-size: {font_size};
                    color: #000;
                    text-align: center;
                }}
                h1, h2, h3, h4, p {{
                    margin: 0;
                    padding: 0;
                    font-size: {font_size};
                    line-height: {line_height};
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