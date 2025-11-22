"""
UniversalMetadataRenderer - Single renderer for all text/data content

Consolidates all text-based renderers (transcriptions, JSON, metadata, descriptions, etc.)
into one unified renderer that handles any textual output.

Provides syntax highlighting, copy functionality, and clean formatting.
"""
import logging
import json
from pathlib import Path
from typing import Dict, Any, Optional
from .base_renderer import BaseRenderer, RenderContext, RenderedOutput

logger = logging.getLogger(__name__)


class UniversalMetadataRenderer(BaseRenderer):
    """
    Universal renderer for all text/metadata content.

    Handles:
    - Transcriptions (from OCR/AI)
    - JSON outputs
    - Metadata extractions
    - Text descriptions
    - CSV/Excel data
    - Any other textual output
    """

    # Supported text file extensions
    TEXT_EXTENSIONS = {
        '.txt', '.json', '.jsonl', '.csv',
        '.md', '.xml', '.yaml', '.yml'
    }

    def can_render(self, context: RenderContext) -> bool:
        """
        Check if this renderer can handle the given context.

        Returns True for any text/data file or textual processing output.
        """
        # Check file extension
        if context.file_path:
            ext = context.file_path.suffix.lower()
            if ext in self.TEXT_EXTENSIONS:
                return True

        # Check file type metadata
        if context.file_type in ['text', 'json', 'transcription', 'metadata', 'csv']:
            return True

        # Check if this is a textual processing tool output
        text_tools = {
            'transcribe', 'describe', 'extract_metadata',
            'fuzzy_clean', 'json_to_word', 'json_to_excel',
            'analyze_groups', 'llm_process', 'convert_to_svg'
        }
        if context.tool_name in text_tools:
            return True

        return False

    def render_html(self, context: RenderContext) -> RenderedOutput:
        """
        Render text/metadata content as HTML with syntax highlighting.

        Returns RenderedOutput with HTML content.
        """
        # Get file path (handle both Path and string)
        if isinstance(context.file_path, Path):
            file_path = context.file_path
        else:
            file_path = Path(context.file_path) if context.file_path else None

        if not file_path or not file_path.exists():
            return RenderedOutput(
                html=self._render_error("File not found"),
                error="File not found"
            )

        # Read file content
        try:
            content = file_path.read_text(encoding='utf-8')
        except Exception as e:
            return RenderedOutput(
                html=self._render_error(f"Failed to read file: {e}"),
                error=f"Failed to read file: {e}"
            )

        # Determine content type
        ext = file_path.suffix.lower()

        if ext == '.json' or ext == '.jsonl':
            html = self._render_json(content, context)
        elif ext == '.csv':
            html = self._render_csv(content, context)
        else:
            html = self._render_text(content, context)

        return RenderedOutput(
            html=html,
            title=context.step_name
        )

    def _render_json(self, content: str, context: RenderContext) -> str:
        """Render JSON with syntax highlighting"""
        # Try to parse and pretty-print
        try:
            data = json.loads(content)
            formatted = json.dumps(data, indent=2, ensure_ascii=False)
        except json.JSONDecodeError:
            # If parsing fails, use raw content
            formatted = content

        # Escape HTML
        formatted = formatted.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

        tool_name = context.step_name or context.tool_name or "JSON"

        html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body {{
            margin: 0;
            padding: 20px;
            background: #1e1e1e;
            color: #d4d4d4;
            font-family: 'Menlo', 'Monaco', 'Courier New', monospace;
            font-size: 13px;
            line-height: 1.6;
        }}
        .header {{
            background: rgba(0, 0, 0, 0.5);
            padding: 10px 15px;
            margin: -20px -20px 20px -20px;
            border-bottom: 1px solid #444;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .title {{
            font-weight: bold;
            color: #ffffff;
        }}
        .copy-btn {{
            background: #007acc;
            color: white;
            border: none;
            padding: 5px 15px;
            border-radius: 3px;
            cursor: pointer;
            font-size: 12px;
        }}
        .copy-btn:hover {{
            background: #005a9e;
        }}
        pre {{
            margin: 0;
            white-space: pre-wrap;
            word-wrap: break-word;
        }}
        .json-key {{
            color: #9cdcfe;
        }}
        .json-string {{
            color: #ce9178;
        }}
        .json-number {{
            color: #b5cea8;
        }}
        .json-boolean {{
            color: #569cd6;
        }}
    </style>
</head>
<body>
    <div class="header">
        <div class="title">{tool_name}</div>
        <button class="copy-btn" onclick="copyContent()">Copy</button>
    </div>
    <pre id="content">{formatted}</pre>

    <script>
        function copyContent() {{
            const content = document.getElementById('content').textContent;
            navigator.clipboard.writeText(content).then(() => {{
                const btn = document.querySelector('.copy-btn');
                btn.textContent = 'Copied!';
                setTimeout(() => btn.textContent = 'Copy', 2000);
            }});
        }}

        // Send click events to Python
        document.addEventListener('click', function(e) {{
            window.webkit.messageHandlers.clickHandler.postMessage(JSON.stringify({{
                'metaKey': e.metaKey,
                'ctrlKey': e.ctrlKey,
                'shiftKey': e.shiftKey,
                'altKey': e.altKey
            }}));
        }});
    </script>
</body>
</html>
"""
        return html

    def _render_text(self, content: str, context: RenderContext) -> str:
        """Render plain text"""
        # Escape HTML
        escaped = content.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

        tool_name = context.step_name or context.tool_name or "Text"

        html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body {{
            margin: 0;
            padding: 20px;
            background: #ffffff;
            color: #000000;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            font-size: 14px;
            line-height: 1.8;
        }}
        .header {{
            background: #f5f5f5;
            padding: 10px 15px;
            margin: -20px -20px 20px -20px;
            border-bottom: 1px solid #ddd;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .title {{
            font-weight: bold;
            color: #000;
        }}
        .copy-btn {{
            background: #007acc;
            color: white;
            border: none;
            padding: 5px 15px;
            border-radius: 3px;
            cursor: pointer;
            font-size: 12px;
        }}
        .copy-btn:hover {{
            background: #005a9e;
        }}
        pre {{
            margin: 0;
            white-space: pre-wrap;
            word-wrap: break-word;
            font-family: inherit;
        }}
    </style>
</head>
<body>
    <div class="header">
        <div class="title">{tool_name}</div>
        <button class="copy-btn" onclick="copyContent()">Copy</button>
    </div>
    <pre id="content">{escaped}</pre>

    <script>
        function copyContent() {{
            const content = document.getElementById('content').textContent;
            navigator.clipboard.writeText(content).then(() => {{
                const btn = document.querySelector('.copy-btn');
                btn.textContent = 'Copied!';
                setTimeout(() => btn.textContent = 'Copy', 2000);
            }});
        }}

        // Send click events to Python
        document.addEventListener('click', function(e) {{
            window.webkit.messageHandlers.clickHandler.postMessage(JSON.stringify({{
                'metaKey': e.metaKey,
                'ctrlKey': e.ctrlKey,
                'shiftKey': e.shiftKey,
                'altKey': e.altKey
            }}));
        }});
    </script>
</body>
</html>
"""
        return html

    def _render_csv(self, content: str, context: RenderContext) -> str:
        """Render CSV as a table"""
        import csv
        from io import StringIO

        try:
            reader = csv.reader(StringIO(content))
            rows = list(reader)
        except Exception as e:
            return self._render_error(f"Failed to parse CSV: {e}")

        if not rows:
            return self._render_error("Empty CSV file")

        # Build HTML table
        table_html = "<table>"

        # Header row
        if rows:
            table_html += "<thead><tr>"
            for cell in rows[0]:
                table_html += f"<th>{cell}</th>"
            table_html += "</tr></thead>"

        # Data rows
        if len(rows) > 1:
            table_html += "<tbody>"
            for row in rows[1:]:
                table_html += "<tr>"
                for cell in row:
                    table_html += f"<td>{cell}</td>"
                table_html += "</tr>"
            table_html += "</tbody>"

        table_html += "</table>"

        tool_name = context.step_name or context.tool_name or "CSV"

        html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body {{
            margin: 0;
            padding: 20px;
            background: #ffffff;
            color: #000000;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            font-size: 13px;
        }}
        .header {{
            background: #f5f5f5;
            padding: 10px 15px;
            margin: -20px -20px 20px -20px;
            border-bottom: 1px solid #ddd;
            font-weight: bold;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
        }}
        th, td {{
            border: 1px solid #ddd;
            padding: 8px 12px;
            text-align: left;
        }}
        th {{
            background: #f5f5f5;
            font-weight: bold;
        }}
        tr:nth-child(even) {{
            background: #fafafa;
        }}
    </style>
</head>
<body>
    <div class="header">{tool_name}</div>
    {table_html}

    <script>
        // Send click events to Python
        document.addEventListener('click', function(e) {{
            window.webkit.messageHandlers.clickHandler.postMessage(JSON.stringify({{
                'metaKey': e.metaKey,
                'ctrlKey': e.ctrlKey,
                'shiftKey': e.shiftKey,
                'altKey': e.altKey
            }}));
        }});
    </script>
</body>
</html>
"""
        return html

    def _render_error(self, message: str) -> str:
        """Render error message"""
        return f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body {{
            margin: 0;
            padding: 20px;
            background: #1e1e1e;
            color: #ff6b6b;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            display: flex;
            align-items: center;
            justify-content: center;
            height: 100vh;
        }}
        .error {{
            text-align: center;
            font-size: 16px;
        }}
    </style>
</head>
<body>
    <div class="error">
        <strong>Error:</strong><br>
        {message}
    </div>
</body>
</html>
"""

    def get_editable_json(self, context: RenderContext) -> Optional[Dict[str, Any]]:
        """
        For JSON files, return the parsed content for editing.
        """
        if not context.file_path or context.file_path.suffix.lower() != '.json':
            return None

        try:
            content = context.file_path.read_text(encoding='utf-8')
            data = json.loads(content)
            return data
        except Exception as e:
            logger.error(f"Failed to load JSON for editing: {e}")
            return None

    def validate_json(self, data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """Validate edited JSON"""
        try:
            # Try to serialize to ensure it's valid JSON
            json.dumps(data)
            return True, None
        except Exception as e:
            return False, f"Invalid JSON: {e}"

    def apply_json_edits(self, context: RenderContext, data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """Save edited JSON back to file"""
        if not context.file_path:
            return False, "No file path specified"

        try:
            # Write pretty-printed JSON
            formatted = json.dumps(data, indent=2, ensure_ascii=False)
            context.file_path.write_text(formatted, encoding='utf-8')
            logger.info(f"Saved edited JSON to {context.file_path}")
            return True, None
        except Exception as e:
            return False, f"Failed to save: {e}"
