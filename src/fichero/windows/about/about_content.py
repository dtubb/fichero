"""
About content component for displaying application information.
Handles both desktop and mobile layouts.
"""

import toga
from toga.style import Pack
from toga.constants import COLUMN, CENTER, ROW

# Use builtin _ function installed by translation.install()

import logging

logger = logging.getLogger(__name__)


class AboutContent:
    """About content component that can be used in windows or as content replacement"""
    
    def __init__(self, app):
        """Initialize the about content"""
        self.app = app
        self.acknowledgments_webview = None
        
        # Import specialized components
        from fichero.windows.about.acknowledgments import AcknowledgmentsManager
        from fichero.windows.about.version_info import VersionManager
        
        self.acknowledgments_manager = AcknowledgmentsManager()
        self.version_manager = VersionManager(app)
    
    def create(self):
        """Create the about content UI"""
        # Main container with margin
        main_container = toga.Box(
            style=Pack(
                direction=COLUMN,
                flex=1,
                margin=0
            )
        )
        
        # Top section with icon and app info
        top_section = self._create_top_section()
        main_container.add(top_section)
        
        # Acknowledgments WebView (scrollable HTML content)
        acknowledgments_webview = self._create_acknowledgments_webview()
        main_container.add(acknowledgments_webview)
        
        # Website link at bottom
        website_link = self._create_website_link()
        main_container.add(website_link)
        
        return main_container
    

    
    def _create_top_section(self):
        """Create the top section with icon and app info"""
        top_section = toga.Box(
            style=Pack(
                direction=COLUMN,
                align_items=CENTER,
                margin=(10, 0, 20, 0)
            )
        )
        
        # App icon (clickable to open website)
        icon = self._create_app_icon()
        top_section.add(icon)
        
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
        top_section.add(app_name)
        
        # Version
        version = self.version_manager.get_version()
        version_label = toga.Label(
            f"version {version}",
            style=Pack(
                font_size=9,
                text_align=CENTER,
                margin=(0, 0, 5, 0)
            )
        )
        top_section.add(version_label)
        
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
        top_section.add(copyright_label)
        
        return top_section
    
    def _create_app_icon(self):
        """Create the app icon (clickable)"""
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
            return icon
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
            return icon
    
    def _create_acknowledgments_webview(self):
        """Create the acknowledgments webview"""
        self.acknowledgments_webview = toga.WebView(
            on_webview_load=self._on_webview_load,
            style=Pack(
                flex=1,
                margin=(0, 0, 0, 0)
            )
        )
        
        # Generate and set acknowledgments HTML content
        acknowledgments_html = self.acknowledgments_manager.generate_html()
        self.acknowledgments_webview.set_content("about:blank", acknowledgments_html)
        
        return self.acknowledgments_webview
    
    def _create_website_link(self):
        """Create the website link at the bottom"""
        website_link = toga.Label(
            "https://www.tubb.ca/fichero/",
            style=Pack(
                font_size=8,
                text_align=CENTER,
                color='#007bff',
                margin=(4, 0, 4, 0)
            )
        )
        # Make website link clickable
        website_link.on_press = self._on_website_click
        return website_link
    
    def _on_webview_load(self, widget, **kwargs):
        """Handle webview load - inject JavaScript to handle link clicks"""
        # Import the link handler
        from fichero.windows.about.link_handler import LinkHandler
        
        link_handler = LinkHandler(self.acknowledgments_webview)
        link_handler.setup_link_monitoring()
    
    def _on_website_click(self, widget, **kwargs):
        """Handle website button click"""
        webbrowser.open("https://www.tubb.ca/fichero/") 