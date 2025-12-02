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

Run with: python3 widget_list_demo.py

Purpose: Test UI functionality independently before library integration
"""

import sys
import os

# Add src to path so we can import fichero modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

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
        # Skip canvas renderer - it's abstract

        # Set main window (first window created)
        for window in self.windows:
            self.main_window = window
            break

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

            # Set up file drop callback
            sidebar.set_import_callback(self._handle_file_import)
            sidebar.set_import_to_collection_callback(self._handle_file_import_to_collection)

            # Set up contextual menu callback
            sidebar.set_context_menu_callback(self._handle_context_menu)

            # Create sidebar widget directly (no control buttons)
            sidebar_widget = sidebar.create_widget()

            # Attach data AFTER widget is created
            sidebar.attach_source(self.hierarchical_data)

            # Create a split container to allow resizing
            split_container = toga.SplitContainer(
                content=[
                    sidebar_widget,
                    self._create_info_panel("macos_sidebar")
                ],
                style=Pack(flex=1)
            )

            # Create window
            window = toga.Window(title="1. MacOS Sidebar (NSOutlineView)")
            window.content = split_container
            window.show()
            self.windows.add(window)

            # Store sidebar reference for testing
            self.sidebar = sidebar
        else:
            label = toga.Label("Rubicon-ObjC not available (macOS only)", style=Pack(margin=20))
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
            demo_box = toga.Box(style=Pack(direction=ROW, flex=1))
            demo_box.add(card_renderer.create_widget())
            card_renderer.attach_source(self.card_data)
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
            demo_box = toga.Box(style=Pack(direction=ROW, flex=1))
            demo_box.add(html_renderer.create_widget())
            html_renderer.attach_source(self.flat_data)
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
                on_select=lambda item: logger.info(f"Native item: {item}"),
                widget_type='table'
            )
            demo_box = toga.Box(style=Pack(direction=ROW, flex=1))
            demo_box.add(native_renderer.create_widget())
            native_renderer.attach_source(self.flat_data)
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
            demo_box = toga.Box(style=Pack(direction=ROW, flex=1))
            demo_box.add(sidebar_renderer.create_widget())
            sidebar_renderer.attach_source(self.flat_data)
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
            demo_box.add(canvas_renderer.create_widget())
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
        info = toga.Label(f"{title} Error:\n{str(error)}", style=Pack(margin=20))
        window = toga.Window(title=f"{title} - Error")
        window.content = info
        window.show()
        self.windows.add(window)

    def _create_info_panel(self, renderer_type):
        """Create info panel for renderer"""
        info_text = {
            "macos_sidebar": """MACOS SIDEBAR (NSOutlineView)
✅ Enhanced API

• 3-level hierarchy
• Section headers
• User expand/collapse
• Programmatic expand/collapse (NEW!)
• expand_all() / collapse_all() (NEW!)
• is_item_expanded() query (NEW!)
• Non-selectable headers
• SF Symbol icons
• Badge counts
• Trailing status icons
• Native macOS

Try the buttons above!""",
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
        info = toga.MultilineTextInput(readonly=True, value=text, style=Pack(flex=1, margin=10, font_size=10))
        return toga.Box(children=[info], style=Pack(flex=1))

    def _create_hierarchical_mock_data(self):
        """Create hierarchical mock data with badges, trailing icons, font styling, and drag & drop flags"""
        return [
            {'_node_type': 'section', '_is_section_header': True, '_has_children': True,
             'text': 'Favorites', 'icon': 'star',
             '_draggable': False, '_can_accept_drops': True, '_drop_types': ['collection', 'folder', 'file'],
             '_children': [
                 {'_node_type': 'collection', '_has_children': False, 'text': 'Inbox', 'icon': 'tray',
                  'badge_text': '15', 'trailing_icon': 'exclamationmark.circle',
                  'font_weight': 'bold',
                  '_draggable': False, '_can_accept_drops': False, '_drop_types': [],
                  '_children': []},  # Inbox is not draggable and doesn't accept drops
                 {'_node_type': 'collection', '_has_children': False, 'text': 'Flagged', 'icon': 'flag',
                  'badge_text': '8', 'trailing_icon': 'star.fill',
                  '_draggable': True, '_can_accept_drops': True, '_drop_types': ['collection', 'folder', 'file'], '_can_accept_collections': True,
                  '_children': []},
                 {'_node_type': 'collection', '_has_children': False, 'text': 'Important', 'icon': 'exclamationmark.triangle',
                  'badge_text': '203', 'trailing_icon': 'sparkles',
                  '_draggable': True, '_can_accept_drops': True, '_drop_types': ['collection', 'folder', 'file'], '_can_accept_collections': True,
                  '_children': []},
             ]},
            {'_node_type': 'section', '_is_section_header': True, '_has_children': True,
             'text': 'Library', 'icon': 'folder',
             '_draggable': False, '_can_accept_drops': True, '_drop_types': ['collection', 'folder', 'file'],
             '_children': [
                 {'_node_type': 'collection', '_has_children': True, 'text': 'Documents', 'icon': 'doc.text',
                  'badge_text': '1,234', 'trailing_icon': 'checkmark.circle.fill',
                  '_draggable': True, '_can_accept_drops': True, '_drop_types': ['collection', 'folder', 'file'], '_can_accept_collections': True,
                  '_children': [
                      {'_node_type': 'folder', '_has_children': True, 'text': '2024', 'icon': 'folder',
                       'badge_text': '567', 'trailing_icon': 'calendar', 'font_weight': 'semibold',
                       '_draggable': True, '_can_accept_drops': True, '_drop_types': ['folder', 'file'],
                       '_children': [
                           {'_node_type': 'folder', '_has_children': True, 'text': 'January', 'icon': 'folder',
                            'badge_text': '89', 'trailing_icon': 'snowflake', 'font_style': 'italic',
                            '_draggable': True, '_can_accept_drops': True, '_drop_types': ['folder', 'file'],
                            '_children': [
                                {'_node_type': 'folder', '_has_children': False, 'text': 'Week 1', 'icon': 'folder',
                                 'badge_text': '23', 'trailing_icon': 'number',
                                 '_draggable': True, '_can_accept_drops': True, '_drop_types': ['file'],
                                 '_children': []},
                                {'_node_type': 'folder', '_has_children': False, 'text': 'Week 2', 'icon': 'folder',
                                 'badge_text': '45', 'trailing_icon': 'star.circle', 'font_weight': 'bold', 'font_style': 'italic',
                                 '_draggable': True, '_can_accept_drops': True, '_drop_types': ['file'],
                                 '_children': []}
                            ]},
                           {'_node_type': 'folder', '_has_children': False, 'text': 'February', 'icon': 'folder',
                            'badge_text': '178', 'trailing_icon': 'heart.fill',
                            '_draggable': True, '_can_accept_drops': True, '_drop_types': ['file'],
                            '_children': []},
                           {'_node_type': 'folder', '_has_children': False, 'text': 'March', 'icon': 'folder',
                            'badge_text': '234', 'trailing_icon': 'sun.max',
                            '_draggable': True, '_can_accept_drops': True, '_drop_types': ['file'],
                            '_children': []}
                       ]},
                      {'_node_type': 'folder', '_has_children': False, 'text': 'Legal', 'icon': 'folder',
                       'badge_text': '3,890', 'trailing_icon': 'briefcase',
                       '_draggable': True, '_can_accept_drops': True, '_drop_types': ['file'],
                       '_children': []},
                      {'_node_type': 'folder', '_has_children': False, 'text': 'Contracts', 'icon': 'folder',
                       'badge_text': '9', 'trailing_icon': 'doc.text.fill',
                       '_draggable': True, '_can_accept_drops': True, '_drop_types': ['file'],
                       '_children': []}
                  ]},
                 {'_node_type': 'collection', '_has_children': False, 'text': 'Photos', 'icon': 'photo',
                  'badge_text': '12,456', 'trailing_icon': 'icloud',
                  '_draggable': True, '_can_accept_drops': True, '_drop_types': ['collection', 'folder', 'file'], '_can_accept_collections': True,
                  '_children': []},
                 {'_node_type': 'collection', '_has_children': False, 'text': 'Videos', 'icon': 'video',
                  'badge_text': '678', 'trailing_icon': 'play.circle',
                  '_draggable': True, '_can_accept_drops': True, '_drop_types': ['collection', 'folder', 'file'], '_can_accept_collections': True,
                  '_children': []},
                 {'_node_type': 'collection', '_has_children': False, 'text': 'Music', 'icon': 'music.note',
                  'badge_text': '4,567', 'trailing_icon': 'speaker.wave.3',
                  '_draggable': True, '_can_accept_drops': True, '_drop_types': ['collection', 'folder', 'file'], '_can_accept_collections': True,
                  '_children': []}
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

    def _handle_file_import(self, file_paths):
        """Handle files dropped on sidebar (generic import)"""
        logger.info(f"FILE IMPORT: {len(file_paths)} files dropped")
        for path in file_paths:
            logger.info(f"  - {path}")

    def _handle_file_import_to_collection(self, file_paths, collection_id):
        """Handle files dropped on a specific collection"""
        logger.info(f"FILE IMPORT TO COLLECTION: {len(file_paths)} files to collection '{collection_id}'")
        for path in file_paths:
            logger.info(f"  - {path}")

    def _handle_context_menu(self, action, item_data):
        """Handle contextual menu actions"""
        item_name = item_data.get('text', 'unknown') if item_data else 'unknown'
        logger.info(f"CONTEXT MENU: action='{action}' on item='{item_name}'")
        logger.info(f"  Full item data: {item_data}")


def main():
    return WidgetListDemo('Widget List Demo', 'org.fichero.demo.widgetlist')


if __name__ == '__main__':
    main().main_loop()
