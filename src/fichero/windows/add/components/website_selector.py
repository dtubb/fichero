"""
Website Selector Component

UI component for browsing and selecting content from websites.
Uses Toga's WebView for interactive website browsing.
"""

import toga
from toga.style import Pack
from toga.constants import COLUMN, ROW
import logging
from typing import Optional, Callable, List

# Use builtin _ function installed by translation.install()

logger = logging.getLogger(__name__)


class WebsiteSelector:
    """Website selector component using Toga's WebView"""
    
    def __init__(self, app: toga.App):
        """Initialize website selector"""
        self.app = app
        self.on_content_selected: Optional[Callable] = None
        self.webview: Optional[toga.WebView] = None
        self.url_input: Optional[toga.TextInput] = None
        self.current_url: str = ""
    
    async def execute(self) -> Optional[str]:
        """
        Execute website browsing and content selection.
        
        Returns:
            Optional[str]: Selected content URL, None if cancelled
        """
        try:
            if self.webview and self.current_url:
                logger.info(f"Website content selected: {self.current_url}")
                
                # For now, return the current URL
                # In a more advanced implementation, this could return
                # specific content selected within the page
                if self.on_content_selected:
                    self.on_content_selected(self.current_url)
                
                return self.current_url
            else:
                logger.warning("No website loaded for content selection")
                return None
                
        except Exception as e:
            logger.error(f"Failed to select website content: {e}")
            return None
    
    def create(self):
        """Create the website selector UI"""
        container = toga.Box(
            style=Pack(
                direction=COLUMN,
                margin=(0, 0, 10, 0),
                flex=1
            )
        )
        
        # URL input and navigation
        nav_container = toga.Box(
            style=Pack(
                direction=ROW,
                margin=(0, 0, 10, 0)
            )
        )
        
        self.url_input = toga.TextInput(
            placeholder=_("Enter website URL (e.g., https://example.com)..."),
            value="https://",
            style=Pack(flex=1, margin=(0, 5, 0, 0))
        )
        nav_container.add(self.url_input)
        
        go_button = toga.Button(
            _("Go"),
            on_press=self._on_navigate,
            style=Pack(flex=0, margin=(0, 5, 0, 0))
        )
        nav_container.add(go_button)
        
        select_button = toga.Button(
            _("Select"),
            on_press=self._on_select_content,
            style=Pack(flex=0)
        )
        nav_container.add(select_button)
        
        container.add(nav_container)
        
        # WebView for browsing
        try:
            self.webview = toga.WebView(
                style=Pack(
                    flex=1,
                    height=400,
                    margin=(0, 0, 10, 0)
                )
            )
            container.add(self.webview)
            
            # Load default page
            self.webview.url = "https://www.example.com"
            self.current_url = "https://www.example.com"
            
        except Exception as e:
            logger.error(f"Failed to create WebView: {e}")
            # Fallback: show error message
            error_label = toga.Label(
                _("WebView not available on this platform"),
                style=Pack(
                    text_align="center",
                    margin=20,
                    color="#ff0000"
                )
            )
            container.add(error_label)
        
        # Instructions
        instructions = toga.Label(
            _("Navigate to a website and click 'Select' to add its content to your library."),
            style=Pack(
                text_align="center",
                margin=(10, 0, 0, 0),
                font_size=12,
                color="#666666"
            )
        )
        container.add(instructions)
        
        return container
    
    def _on_navigate(self, widget):
        """Handle navigation to a new URL"""
        try:
            url = self.url_input.value.strip()
            
            # Add https:// if no protocol specified
            if url and not url.startswith(('http://', 'https://')):
                url = 'https://' + url
            
            if url and self.webview:
                logger.info(f"Navigating to: {url}")
                self.webview.url = url
                self.current_url = url
            else:
                logger.warning("No URL provided or WebView not available")
                
        except Exception as e:
            logger.error(f"Failed to navigate to URL: {e}")
    
    async def _on_select_content(self, widget):
        """Handle content selection from current page"""
        selected_url = await self.execute()
        if selected_url:
            logger.info(f"Content selected from: {selected_url}")
    
    def register_callback(self, callback: Callable):
        """Register callback for when content is selected"""
        self.on_content_selected = callback


# Use builtin _ function installed by translation.install() 