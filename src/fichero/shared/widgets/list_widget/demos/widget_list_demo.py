#!/usr/bin/env python3
"""
Widget List Demo Application

Tests ALL widget list renderers with mock data BEFORE hooking up to backend.

Opens separate windows for each renderer type:
1. MacOS Sidebar Renderer (NSOutlineView) - Hierarchical, native macOS
2. Card Renderer - Visual cards in grid/list layout
3. HTML Renderer - WebView-based rendering
4. Native Renderer - Platform-native list widgets
5. Sidebar Renderer (Canvas) - Canvas-based sidebar
6. Canvas Renderer - Custom canvas rendering

Run with: briefcase dev -- demo-widgets

Purpose: Test UI functionality independently before library integration
"""

import sys
import os

# Add src to path so we can import fichero modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../../..'))

import toga
from toga.style import Pack
from toga.constants import COLUMN, ROW
import logging

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Import widget list renderers
from fichero.shared.widgets.list_widget.renderers.macos_sidebar import NSOutlineViewSidebar, RUBICON_AVAILABLE
from fichero.shared.widgets.list_widget.renderers.card import CardRenderer
from fichero.shared.widgets.list_widget.renderers.html import HTMLRenderer
from fichero.shared.widgets.list_widget.renderers.native import NativeRenderer
from fichero.shared.widgets.list_widget.renderers.sidebar import SidebarRenderer
from fichero.shared.widgets.list_widget.renderers.canvas_renderer import CanvasRenderer


class WidgetListDemo(toga.App):
    """Demo app testing all widget list renderers in separate windows."""

    def startup(self):
        """Open a window for each renderer type"""

        # Create mock data
        self.hierarchical_data = self._create_hierarchical_mock_data()
        self.flat_data = self._create_flat_mock_data()
        self.card_data = self._create_card_mock_data()

        # Create windows for each renderer type
        self._create_macos_sidebar_window()
        self._create_card_renderer_window()
        self._create_html_renderer_window()
        self._create_native_renderer_window()
        self._create_sidebar_renderer_window()
        self._create_canvas_renderer_window()

    def _create_macos_sidebar_window(self):
        """Create window for hierarchical macOS sidebar demo"""
        logger.info("Creating macOS hierarchical sidebar window")

        if RUBICON_AVAILABLE:
            # Create sidebar renderer
            sidebar = NSOutlineViewSidebar(
                headings=['text'],
                on_select=lambda item: logger.info(f"Sidebar selected: {item}")
            )
            sidebar.set_get_children_callback(self._get_children)
            sidebar.attach_source(self.hierarchical_data)

            # Create layout with sidebar and info
            demo_box = toga.Box(style=Pack(direction=ROW, flex=1))
            demo_box.add(sidebar.get_widget())
            demo_box.add(self._create_info_panel("macos_sidebar"))

            # Create window
            window = toga.Window(title="1. MacOS Sidebar (NSOutlineView)")
            window.content = demo_box
            window.show()
            self.windows.add(window)
        else:
            label = toga.Label("Rubicon-ObjC not available (macOS only)", style=Pack(padding=20))
            window = toga.Window(title="1. MacOS Sidebar - Not Available")
            window.content = label
            window.show()
            self.windows.add(window)

    def _create_card_renderer_window(self):
        """Create window for card renderer demo"""
        logger.info("Creating card renderer window")
        try:
            card_renderer = CardRenderer(
                headings=['name', 'type', 'size'],
                on_select=lambda item: logger.info(f"Card selected: {item}"),
                layout='grid', grid_columns=3, card_width=200, card_height=150
            )
            card_renderer.attach_source(self.card_data)
            demo_box = toga.Box(style=Pack(direction=ROW, flex=1))
            demo_box.add(card_renderer.get_widget())
            demo_box.add(self._create_info_panel("card"))
            window = toga.Window(title="2. Card Renderer")
            window.content = demo_box
            window.show()
            self.windows.add(window)
        except Exception as e:
            logger.error(f"Card renderer error: {e}", exc_info=True)
            self._create_error_window("2. Card Renderer", e)

    def _create_html_renderer_window(self):
        """Create window for HTML renderer demo"""
        logger.info("Creating HTML renderer window")
        try:
            html_renderer = HTMLRenderer(
                headings=['name', 'type', 'size'],
                on_select=lambda item: logger.info(f"HTML item: {item}"),
                style='gallery'
            )
            html_renderer.attach_source(self.flat_data)
            demo_box = toga.Box(style=Pack(direction=ROW, flex=1))
            demo_box.add(html_renderer.get_widget())
            demo_box.add(self._create_info_panel("html"))
            window = toga.Window(title="3. HTML Renderer (WebView)")
            window.content = demo_box
            window.show()
            self.windows.add(window)
        except Exception as e:
            logger.error(f"HTML renderer error: {e}", exc_info=True)
            self._create_error_window("3. HTML Renderer", e)

    def _create_native_renderer_window(self):
        """Create window for native renderer demo"""
        logger.info("Creating native renderer window")
        try:
            native_renderer = NativeRenderer(
                headings=['name', 'type', 'size'],
                on_select=lambda item: logger.info(f"Native item: {item}")
            )
            native_renderer.attach_source(self.flat_data)
            demo_box = toga.Box(style=Pack(direction=ROW, flex=1))
            demo_box.add(native_renderer.get_widget())
            demo_box.add(self._create_info_panel("native"))
            window = toga.Window(title="4. Native Renderer")
            window.content = demo_box
            window.show()
            self.windows.add(window)
        except Exception as e:
            logger.error(f"Native renderer error: {e}", exc_info=True)
            self._create_error_window("4. Native Renderer", e)

    def _create_sidebar_renderer_window(self):
        """Create window for canvas sidebar renderer demo"""
        logger.info("Creating sidebar (canvas) renderer window")
        try:
            sidebar_renderer = SidebarRenderer(
                headings=['name', 'type'],
                on_select=lambda item: logger.info(f"Sidebar item: {item}")
            )
            sidebar_renderer.attach_source(self.flat_data)
            demo_box = toga.Box(style=Pack(direction=ROW, flex=1))
            demo_box.add(sidebar_renderer.get_widget())
            demo_box.add(self._create_info_panel("sidebar"))
            window = toga.Window(title="5. Sidebar Renderer (Canvas)")
            window.content = demo_box
            window.show()
            self.windows.add(window)
        except Exception as e:
            logger.error(f"Sidebar renderer error: {e}", exc_info=True)
            self._create_error_window("5. Sidebar Renderer", e)

    def _create_canvas_renderer_window(self):
        """Create window for canvas renderer demo"""
        logger.info("Creating canvas renderer window")
        try:
            canvas_renderer = CanvasRenderer(
                headings=['name', 'type', 'size'],
                on_select=lambda item: logger.info(f"Canvas item: {item}")
            )
            canvas_renderer.attach_source(self.flat_data)
            demo_box = toga.Box(style=Pack(direction=ROW, flex=1))
            demo_box.add(canvas_renderer.get_widget())
            demo_box.add(self._create_info_panel("canvas"))
            window = toga.Window(title="6. Canvas Renderer")
            window.content = demo_box
            window.show()
            self.windows.add(window)
        except Exception as e:
            logger.error(f"Canvas renderer error: {e}", exc_info=True)
            self._create_error_window("6. Canvas Renderer", e)

    def _create_error_window(self, title, error):
        """Create error window"""
        info = toga.Label(f"{title} Error:\n{str(error)}", style=Pack(padding=20))
        window = toga.Window(title=f"{title} - Error")
        window.content = info
        window.show()
        self.windows.add(window)

    def _create_info_panel(self, renderer_type):
        """Create info panel for renderer"""
        info_text = {
            "macos_sidebar": """MACOS SIDEBAR (NSOutlineView)
✅ Fully Working

• 3-level hierarchy
• Section headers
• Expand/collapse
• Non-selectable headers
• SF Symbol icons
• Callback pattern
• Native macOS""",
            "card": """CARD RENDERER
✅ Working

• Grid layout (3 columns)
• Visual cards
• Icons + text
• Scrollable
• Touch-friendly""",
            "html": """HTML RENDERER
✅ Working

• WebView-based
• Gallery style
• Custom HTML/CSS
• Flexible styling
• Click selection""",
            "native": """NATIVE RENDERER
✅ Working

• Platform-native
• Toga.Table
• Column display
• Standard selection
• Cross-platform""",
            "sidebar": """SIDEBAR (Canvas)
✅ Working

• Canvas-based
• Custom drawing
• Sidebar layout
• Cross-platform
• No native deps""",
            "canvas": """CANVAS RENDERER
✅ Working

• Full control
• Custom layouts
• Animation ready
• Performance
• Platform-free"""
        }
        text = info_text.get(renderer_type, "Info not available")
        info = toga.MultilineTextInput(readonly=True, value=text, style=Pack(flex=1, padding=10, font_size=10))
        return toga.Box(children=[info], style=Pack(flex=1))

    def _create_hierarchical_mock_data(self):
        """Create hierarchical mock data"""
        return [
            {'_node_type': 'section', '_is_section_header': True, '_has_children': True,
             'text': 'Inbox', 'icon': 'archivebox',
             '_children': [{'_node_type': 'collection', '_has_children': False, 'text': 'Inbox', 'icon': 'tray', '_children': []}]},
            {'_node_type': 'section', '_is_section_header': True, '_has_children': True,
             'text': 'Library', 'icon': 'folder',
             '_children': [
                 {'_node_type': 'collection', '_has_children': True, 'text': 'Documents', 'icon': 'doc.text',
                  '_children': [
                      {'_node_type': 'folder', '_has_children': True, 'text': '2024', 'icon': 'folder',
                       '_children': [
                           {'_node_type': 'folder', '_has_children': False, 'text': 'January', 'icon': 'folder', '_children': []},
                           {'_node_type': 'folder', '_has_children': False, 'text': 'February', 'icon': 'folder', '_children': []}
                       ]},
                      {'_node_type': 'folder', '_has_children': False, 'text': 'Legal', 'icon': 'folder', '_children': []}
                  ]},
                 {'_node_type': 'collection', '_has_children': False, 'text': 'Photos', 'icon': 'photo', '_children': []}
             ]},
        ]

    def _create_flat_mock_data(self):
        """Create flat mock data"""
        return [
            {'name': 'Document 1.pdf', 'type': 'document', 'size': '2.5 MB', 'icon': 'doc.text'},
            {'name': 'Image 1.jpg', 'type': 'image', 'size': '1.2 MB', 'icon': 'photo'},
            {'name': 'Spreadsheet.xlsx', 'type': 'document', 'size': '500 KB', 'icon': 'tablecells'},
            {'name': 'Photo 2.jpg', 'type': 'image', 'size': '3.1 MB', 'icon': 'photo'},
            {'name': 'Video.mp4', 'type': 'video', 'size': '15.2 MB', 'icon': 'video'},
        ]

    def _create_card_mock_data(self):
        """Create card mock data"""
        return [
            {'name': 'Document 1.pdf', 'type': 'document', 'size': '2.5 MB', 'icon': 'doc.text', 'subtitle': 'PDF Document'},
            {'name': 'Image 1.jpg', 'type': 'image', 'size': '1.2 MB', 'icon': 'photo', 'subtitle': 'JPEG Image'},
            {'name': 'Spreadsheet.xlsx', 'type': 'document', 'size': '500 KB', 'icon': 'tablecells', 'subtitle': 'Excel Sheet'},
            {'name': 'Photo 2.jpg', 'type': 'image', 'size': '3.1 MB', 'icon': 'photo', 'subtitle': 'JPEG Image'},
            {'name': 'Video.mp4', 'type': 'video', 'size': '15.2 MB', 'icon': 'video', 'subtitle': 'MP4 Video'},
        ]

    def _get_children(self, item_data):
        """Callback for hierarchy"""
        if item_data is None:
            return None
        children = item_data.get('_children')
        if children and len(children) > 0:
            return children
        return None


def main():
    return WidgetListDemo('Widget List Demo', 'org.fichero.demo.widgetlist')


if __name__ == '__main__':
    main().main_loop()
