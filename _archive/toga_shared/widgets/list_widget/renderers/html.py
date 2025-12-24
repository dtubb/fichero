"""
HTML renderer - displays items using web-based rendering in a WebView.

This renderer creates an HTML-based view where items are rendered using
custom HTML/CSS. This provides maximum flexibility for styling and layout,
similar to web-based file browsers like macOS Finder's gallery view.
"""

import logging
from typing import List, Dict, Any, Optional
import html

import toga
from toga.style.pack import Pack
from . import Renderer


logger = logging.getLogger(__name__)


class HTMLRenderer(Renderer):
    """Renderer that displays items as HTML in a WebView."""

    def __init__(
        self,
        headings: List[str],
        on_select: Optional[callable] = None,
        style: str = 'default',
        platform: Optional[str] = None,
        toga_style: Optional[toga.style.pack.Pack] = None,
        template: Optional[str] = None,
        css: Optional[str] = None,
        on_navigate_back: Optional[callable] = None,
    ):
        """
        Initialize HTML renderer.

        Args:
            headings: Column headings (used for data mapping)
            on_select: Selection callback
            style: Rendering style ('default', 'compact', 'detailed', 'gallery')
            platform: Platform string (for debugging)
            toga_style: Toga Pack style for the container
            template: Custom HTML template (if None, uses default)
            css: Custom CSS (if None, uses default)
        """
        super().__init__(headings, on_select, style)
        self.uses_native_source = False  # HTMLRenderer handles raw data, not ListSource
        self.platform = platform
        self.toga_style = toga_style
        self.template = template or self._get_default_template()
        self.css = css or self._get_default_css()
        self.widget = None
        self.items = []  # List of item data
        self.selected_item_id = None
        self._last_checked_selection = None
        self._selection_check_interval = 500  # Check every 500ms
        self.current_path = ""  # Current folder path for header display
        self.on_navigate_back = on_navigate_back  # Callback for back button

    def _get_item_value(self, item: Any, key: str, default: Any = None) -> Any:
        """
        Safely get a value from an item (dict or Toga Row object).

        Args:
            item: Item (dict or Row object)
            key: Key to retrieve
            default: Default value if key not found

        Returns:
            Value for the key, or default if not found
        """
        try:
            if isinstance(item, dict):
                return item.get(key, default)
            else:
                # Try to access as attribute (for Toga Row objects)
                return getattr(item, key, default)
        except AttributeError:
            return default

    def _icon_to_base64(self, icon) -> Optional[str]:
        """
        Convert a Toga Image to base64 data URL.

        Args:
            icon: Toga Image object or None

        Returns:
            Base64 data URL string, or None if conversion fails
        """
        if icon is None:
            return None

        try:
            import base64
            from io import BytesIO
            from PIL import Image as PILImage

            # Get the path from the Toga Image
            if hasattr(icon, 'path') and icon.path:
                # Load image using PIL
                pil_image = PILImage.open(str(icon.path))

                # Convert to PNG in memory
                buffer = BytesIO()
                pil_image.save(buffer, format='PNG')
                buffer.seek(0)

                # Encode to base64
                img_base64 = base64.b64encode(buffer.read()).decode('utf-8')

                return f"data:image/png;base64,{img_base64}"
            else:
                logger.warning("Icon object has no path attribute")
                return None
        except Exception as e:
            logger.error(f"Failed to convert icon to base64: {e}", exc_info=True)
            return None

    def _get_default_css(self) -> str:
        """Return default CSS for HTML rendering."""
        if self.style == 'card' or self.style == 'default':
            # Card style matching CardRenderer appearance
            return """
                body {
                    margin: 0;
                    padding: 0;
                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                    background-color: #ffffff;
                    overflow-x: hidden;
                    min-height: 100vh;
                }
                .container {
                    display: flex;
                    flex-direction: column;
                    width: 100%;
                    min-height: 100vh;
                }
                .folder-header {
                    padding: 8px 10px;
                    background-color: #f8f8f8;
                    border-bottom: 1px solid #e0e0e0;
                    font-size: 10pt;
                    font-weight: 500;
                    color: #333333;
                    position: sticky;
                    top: 0;
                    z-index: 100;
                    display: flex;
                    align-items: flex-start;
                    user-select: none;
                    cursor: pointer;
                    transition: background-color 0.15s;
                }
                .folder-header:hover {
                    background-color: #eeeeee;
                }
                .folder-header.selected {
                    background-color: #E3F2FD;
                }
                .folder-header .back-button {
                    cursor: pointer;
                    padding: 4px 8px;
                    margin-right: 8px;
                    border-radius: 4px;
                    font-size: 14pt;
                    line-height: 1;
                    transition: background-color 0.15s;
                    color: #007AFF;
                    flex-shrink: 0;
                }
                .folder-header .back-button:hover {
                    background-color: #e8e8e8;
                }
                .folder-header .back-button:active {
                    background-color: #d8d8d8;
                }
                .folder-header .folder-name {
                    flex: 1;
                    word-wrap: break-word;
                    overflow-wrap: break-word;
                    word-break: break-word;
                    min-width: 0;
                }
                .item {
                    padding: 10px;
                    cursor: pointer;
                    display: flex;
                    align-items: flex-start;
                    transition: background-color 0.15s;
                    word-wrap: break-word;
                    overflow-wrap: break-word;
                    word-break: break-word;
                }
                .item:hover {
                    background-color: #f5f5f5;
                }
                .item.selected {
                    background-color: #E3F2FD;
                }
                .item-icon {
                    width: 32px;
                    height: 32px;
                    margin-right: 8px;
                    flex-shrink: 0;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                }
                .item-icon img {
                    width: 100%;
                    height: 100%;
                    object-fit: cover;
                }
                .item-content {
                    flex: 1;
                    min-width: 0;
                    overflow-wrap: break-word;
                }
                .item-title {
                    font-weight: normal;
                    font-size: 10pt;
                    margin: 0 0 2px 0;
                    word-wrap: break-word;
                    overflow-wrap: break-word;
                }
                .item-title.folder {
                    font-weight: 500;
                }
                .item-subtitle {
                    font-size: 9pt;
                    color: #666666;
                    margin: 0;
                    word-wrap: break-word;
                    overflow-wrap: break-word;
                }
            """
        elif self.style == 'gallery':
            return """
                body {
                    margin: 0;
                    padding: 20px;
                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                    background-color: #f5f5f5;
                }
                .container {
                    display: grid;
                    grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
                    gap: 20px;
                }
                .item {
                    background: white;
                    border-radius: 8px;
                    padding: 15px;
                    cursor: pointer;
                    transition: all 0.2s;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                }
                .item:hover {
                    transform: translateY(-2px);
                    box-shadow: 0 4px 8px rgba(0,0,0,0.15);
                }
                .item.selected {
                    border: 2px solid #007AFF;
                    background-color: #E3F2FD;
                }
                .item-icon {
                    width: 64px;
                    height: 64px;
                    margin: 0 auto 10px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    font-size: 32px;
                }
                .item-title {
                    font-weight: 600;
                    font-size: 14px;
                    margin-bottom: 5px;
                    text-align: center;
                }
                .item-subtitle {
                    font-size: 12px;
                    color: #666;
                    text-align: center;
                }
            """
        elif self.style == 'list':
            return """
                body {
                    margin: 0;
                    padding: 0;
                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                    background-color: white;
                }
                .container {
                    display: flex;
                    flex-direction: column;
                }
                .item {
                    padding: 12px 20px;
                    border-bottom: 1px solid #e0e0e0;
                    cursor: pointer;
                    display: flex;
                    align-items: center;
                    transition: background-color 0.15s;
                }
                .item:hover {
                    background-color: #f5f5f5;
                }
                .item.selected {
                    background-color: #007AFF;
                    color: white;
                }
                .item-icon {
                    width: 40px;
                    height: 40px;
                    margin-right: 15px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    font-size: 20px;
                }
                .item-content {
                    flex: 1;
                }
                .item-title {
                    font-weight: 500;
                    font-size: 14px;
                    margin-bottom: 2px;
                }
                .item-subtitle {
                    font-size: 12px;
                    color: #666;
                }
                .item.selected .item-subtitle {
                    color: rgba(255, 255, 255, 0.8);
                }
            """
        else:  # default
            return """
                body {
                    margin: 0;
                    padding: 10px;
                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                    background-color: white;
                }
                .container {
                    display: flex;
                    flex-direction: column;
                    gap: 10px;
                }
                .item {
                    background: white;
                    border: 1px solid #e0e0e0;
                    border-radius: 4px;
                    padding: 10px;
                    cursor: pointer;
                    transition: all 0.15s;
                }
                .item:hover {
                    border-color: #007AFF;
                    background-color: #f8f8f8;
                }
                .item.selected {
                    border-color: #007AFF;
                    background-color: #E3F2FD;
                }
                .item-title {
                    font-weight: 500;
                    font-size: 14px;
                    margin-bottom: 4px;
                }
                .item-subtitle {
                    font-size: 12px;
                    color: #666;
                }
            """

    def _get_default_template(self) -> str:
        """Return default HTML template."""
        return """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        {css}
    </style>
    <script>
        // Store the currently selected item ID
        var currentSelection = null;

        function selectItem(itemId, event) {{
            // Stop propagation to prevent container click
            if (event) {{
                event.stopPropagation();
            }}

            // Remove previous selection from items AND header
            const selected = document.querySelector('.item.selected');
            if (selected) {{
                selected.classList.remove('selected');
            }}
            const selectedHeader = document.querySelector('.folder-header.selected');
            if (selectedHeader) {{
                selectedHeader.classList.remove('selected');
            }}

            // Add selection to clicked item
            const item = document.getElementById('item-' + itemId);
            if (item) {{
                item.classList.add('selected');
                currentSelection = itemId;
            }}

            console.log('Selected item:', itemId);
        }}

        function deselectAll() {{
            const selected = document.querySelector('.item.selected');
            if (selected) {{
                selected.classList.remove('selected');
            }}
            const selectedHeader = document.querySelector('.folder-header.selected');
            if (selectedHeader) {{
                selectedHeader.classList.remove('selected');
            }}
            currentSelection = null;
            console.log('Deselected all');
        }}

        // Click on container background deselects
        document.addEventListener('DOMContentLoaded', function() {{
            const container = document.querySelector('.container');
            if (container) {{
                container.addEventListener('click', function(e) {{
                    // Only deselect if clicking directly on container, not on items
                    if (e.target === container) {{
                        deselectAll();
                    }}
                }});
            }}
        }});

        // Function Python can call to get current selection
        // Return empty string instead of null to avoid WebKit serialization issues
        function getSelection() {{
            return currentSelection === null ? '' : String(currentSelection);
        }}

        // Navigation function - signals Python to navigate back
        function navigateBack(event) {{
            console.log('Navigate back clicked');
            // Stop propagation so header doesn't get selected
            if (event) {{
                event.stopPropagation();
            }}
            // Python will poll for this or we can use a callback mechanism
            window.location.hash = '#navigate-back';
        }}

        // Select current folder header
        function selectHeader(itemId, event) {{
            console.log('Header selected:', itemId);
            // Stop propagation
            if (event) {{
                event.stopPropagation();
            }}
            // Remove previous selection from items
            const selected = document.querySelector('.item.selected');
            if (selected) {{
                selected.classList.remove('selected');
            }}
            // Remove previous header selection
            const prevHeader = document.querySelector('.folder-header.selected');
            if (prevHeader) {{
                prevHeader.classList.remove('selected');
            }}
            // Select header
            const header = document.querySelector('.folder-header');
            if (header) {{
                header.classList.add('selected');
                currentSelection = itemId;
            }}
        }}

        // Restore selection state after any updates
        function restoreSelection() {{
            if (currentSelection) {{
                // Check if it's a header selection
                const header = document.querySelector('.folder-header');
                if (header && header.onclick && header.onclick.toString().includes(currentSelection)) {{
                    header.classList.add('selected');
                }} else {{
                    // Regular item
                    const item = document.getElementById('item-' + currentSelection);
                    if (item) {{
                        item.classList.add('selected');
                    }}
                }}
            }}
        }}

        // Call restore on load
        document.addEventListener('DOMContentLoaded', restoreSelection);
    </script>
</head>
<body>
    <div class="container">
        {items}
    </div>
</body>
</html>
"""

    def _render_item_html(self, item: Any, index: int) -> str:
        """Render a single item as HTML."""
        item_id = self._get_item_value(item, '_item_id', f'item_{index}')
        title_text = self._get_item_value(item, 'text', self._get_item_value(item, 'title', 'Untitled'))
        title = html.escape(str(title_text))

        # Check if this is a folder
        is_folder = self._get_item_value(item, 'is_folder', False)
        folder_class = ' folder' if is_folder else ''

        # Only show subtitle for folders, hide for files (cleaner look)
        subtitle_text = self._get_item_value(item, 'subtitle', '') if is_folder else ''
        subtitle = html.escape(str(subtitle_text)) if subtitle_text else ''

        # Get icon - try image first, fall back to emoji
        icon_obj = self._get_item_value(item, 'icon', None)
        icon_data_url = self._icon_to_base64(icon_obj)

        if icon_data_url:
            # Use actual image
            icon_html = f'<img src="{icon_data_url}" alt="icon" />'
        else:
            # Fall back to emoji or icon_text
            icon_text = self._get_item_value(item, 'icon_text', '📄')
            icon_html = html.escape(str(icon_text))

        if self.style == 'card' or self.style == 'default':
            # Card style matching CardRenderer with icon support
            return f"""
                <div class="item" id="item-{item_id}" onclick="selectItem('{item_id}', event)">
                    <div class="item-icon">{icon_html}</div>
                    <div class="item-content">
                        <div class="item-title{folder_class}">{title}</div>
                        {f'<div class="item-subtitle">{subtitle}</div>' if subtitle else ''}
                    </div>
                </div>
            """
        elif self.style == 'gallery':
            return f"""
                <div class="item" id="item-{item_id}" onclick="selectItem('{item_id}', event)">
                    <div class="item-icon">{icon_html}</div>
                    <div class="item-title">{title}</div>
                    {f'<div class="item-subtitle">{subtitle}</div>' if subtitle else ''}
                </div>
            """
        elif self.style == 'list':
            return f"""
                <div class="item" id="item-{item_id}" onclick="selectItem('{item_id}', event)">
                    <div class="item-icon">{icon_html}</div>
                    <div class="item-content">
                        <div class="item-title">{title}</div>
                        {f'<div class="item-subtitle">{subtitle}</div>' if subtitle else ''}
                    </div>
                </div>
            """

    def _generate_html(self) -> str:
        """Generate complete HTML for all items."""
        # Add folder header if we're in a subfolder
        header_html = ""
        header_icon = None

        # Determine which items to display
        items_to_render = self.items

        if self.current_path:
            # Find the current folder item to get its icon and ID
            current_folder_item = None
            folder_item_id = 'folder-current'
            for item in self.items:
                item_path = self._get_item_value(item, 'path', '')
                if item_path == self.current_path:
                    current_folder_item = item
                    folder_item_id = self._get_item_value(item, '_item_id', 'folder-current')
                    break

            # Get icon for header
            if current_folder_item:
                icon_obj = self._get_item_value(current_folder_item, 'icon', None)
                icon_data_url = self._icon_to_base64(icon_obj)
                if icon_data_url:
                    header_icon = f'<img src="{icon_data_url}" alt="folder" style="width: 20px; height: 20px; margin-right: 8px; vertical-align: middle;" />'

            # Show the current folder name with back button and icon
            # Make header clickable to select the folder (use special ID to prevent navigation)
            folder_name = html.escape(self.current_path.split('/')[-1] if '/' in self.current_path else self.current_path)
            # Use a special ID that doesn't match any real item to prevent accidental navigation
            header_selection_id = f'_header_{folder_item_id}'
            header_html = f'''
                <div class="folder-header" id="header-current" onclick="selectHeader('{header_selection_id}', event)">
                    <span class="back-button" onclick="navigateBack(event)">‹</span>
                    {header_icon if header_icon else ''}
                    <span class="folder-name">{folder_name}</span>
                </div>
            '''

            # Filter out the current folder from items (don't show it in the list)
            items_to_render = [
                item for item in self.items
                if self._get_item_value(item, 'path', '') != self.current_path
            ]
            logger.debug(f"Filtered {len(self.items)} items to {len(items_to_render)} (removed current folder)")

        items_html = '\n'.join(
            self._render_item_html(item, i)
            for i, item in enumerate(items_to_render)
        )

        html_output = self.template.format(
            css=self.css,
            items=header_html + items_html
        )

        logger.debug(f"Generated HTML with {len(items_to_render)} items, header={'yes' if header_html else 'no'}")
        return html_output

    def create_widget(self) -> toga.Widget:
        """
        Create the HTML renderer widget.

        Returns:
            WebView widget displaying HTML content
        """
        logger.debug(f"Creating HTML renderer container (style={self.style})")

        # Create WebView widget
        self.widget = toga.WebView(
            style=self.toga_style or Pack(flex=1),
            on_webview_load=self._on_webview_load,
        )

        # Set initial empty HTML
        self.widget.set_content("", "<html><body>Loading...</body></html>")

        return self.widget

    def _on_webview_load(self, widget):
        """Handle WebView load event."""
        logger.debug("HTML renderer WebView loaded")
        # Start polling for selection changes
        self._start_selection_polling()

    async def _check_selection(self):
        """Check if selection has changed in the WebView."""
        if not self.widget:
            return

        try:
            # Check for navigation back request (via hash change)
            try:
                url = await self.widget.evaluate_javascript("window.location.hash")
                if url == '#navigate-back':
                    logger.debug("Back navigation detected in HTML renderer")
                    # Clear the hash
                    await self.widget.evaluate_javascript("window.location.hash = ''")
                    # Call the navigation callback
                    if self.on_navigate_back:
                        self.on_navigate_back()
            except:
                pass  # Hash check can fail, that's okay

            # Get current selection from JavaScript (empty string means no selection)
            result = await self.widget.evaluate_javascript("getSelection()")

            # Convert empty string to None
            if result == '' or result is None:
                result = None

            if result != self._last_checked_selection:
                self._last_checked_selection = result

                if self.on_select:
                    if result is None:
                        # Deselected - notify with None (don't log, too noisy)
                        self.on_select(None)
                    else:
                        # Check if this is a header selection (starts with _header_)
                        if str(result).startswith('_header_'):
                            # Extract the real folder ID and find the folder item
                            real_id = str(result)[8:]  # Remove '_header_' prefix
                            for item in self.items:
                                item_id = self._get_item_value(item, '_item_id', None)
                                if str(item_id) == real_id:
                                    logger.debug(f"Header selected, found folder item: {item_id}")
                                    self.on_select(item)
                                    break
                        else:
                            # Find the selected item in our data (don't log, too noisy)
                            for item in self.items:
                                item_id = self._get_item_value(item, '_item_id', None)
                                if str(item_id) == str(result):
                                    self.on_select(item)
                                    break
        except RuntimeError as e:
            # Silently ignore WebKit errors during polling
            # These happen occasionally during page transitions
            pass
        except Exception as e:
            # Only log unexpected errors
            logger.error(f"Unexpected error checking selection: {e}", exc_info=True)

    def _start_selection_polling(self):
        """Start periodic polling for selection changes."""
        import asyncio

        async def poll():
            while self.widget is not None:
                await self._check_selection()
                await asyncio.sleep(self._selection_check_interval / 1000.0)

        # Start the polling task
        try:
            import toga
            # Use Toga's event loop to schedule the polling
            asyncio.create_task(poll())
        except Exception as e:
            logger.error(f"Failed to start selection polling: {e}", exc_info=True)

    def get_accessors(self, headings: List[str]) -> List[str]:
        """
        Return accessor names.

        For HTML rendering, we use standard accessors.

        Args:
            headings: The column headings (ignored for HTML)

        Returns:
            List of accessor strings
        """
        return ['text', 'title', 'subtitle', 'icon', 'icon_text', '_collection_data', '_item_id']

    def convert_to_source_format(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Convert app data to HTML-compatible format.

        For HTML, we keep the data as-is since we're not using a Toga source.

        Args:
            data: Application data

        Returns:
            Data in HTML format (same as input)
        """
        logger.debug(f"Converting {len(data)} items to HTML format")
        return data

    def attach_source(self, source):
        """
        Attach data to HTML renderer.

        Unlike native widgets, HTML renderer directly renders data as HTML.

        Args:
            source: Data (list of dicts) to display as HTML
        """
        if not self.widget:
            logger.warning("Cannot attach source - widget not created yet")
            return

        # Store items
        if isinstance(source, list):
            self.items = source
        else:
            # If source is a ListSource or TreeSource, convert to list
            self.items = list(source)

        # Generate and set HTML
        html_content = self._generate_html()
        self.widget.set_content("", html_content)

        logger.debug(f"Rendered {len(self.items)} items as HTML")

    def set_style(self, style: str):
        """
        Change rendering style and refresh display.

        Args:
            style: New style ('default', 'compact', 'detailed', 'gallery', 'list')
        """
        self.style = style
        self.css = self._get_default_css()

        # Refresh display if we have data
        if self.widget and self.items:
            logger.debug(f"Updating HTML style to '{style}'")
            self.attach_source(self.items)


__all__ = ['HTMLRenderer']
