"""
Website Add View

BaseView for browsing and adding website content.
"""

import toga
from toga.style import Pack
from toga.constants import COLUMN, ROW, CENTER
import logging
from typing import Optional, Callable

from fichero.shared.views.base_view import BaseView
from fichero.shared.toolbars import TopToolbar, BottomToolbar

# Use builtin _ function installed by translation.install()

logger = logging.getLogger(__name__)


class WebsiteAddView(BaseView):
    """View for adding website content to the library"""
    
    def __init__(self, app: toga.App, on_content_added: Optional[Callable] = None):
        """Initialize website add view"""
        self.on_content_added = on_content_added
        self.current_url: str = ""

        # Initialize BaseView first
        super().__init__(app, is_mobile=app.is_mobile)
        
        # Create toolbars after BaseView is initialized
        self._create_toolbars()
        
        logger.info("Website Add View initialized")
    
    def _create_toolbars(self):
        """Create top and bottom toolbars for website add view"""
        try:
            # Create top toolbar without coordinator (no edit mode for modal views)
            self.top_toolbar = TopToolbar(
                app=self.app,
                title="Add Website",
                auto_mobile_nav=True,
                is_mobile=self.is_mobile
            )

            # NavigationController integration is handled automatically by TopToolbar

            # Add centered title for desktop (preserving button alignment)
            if not self.is_mobile:
                self.top_toolbar.add_centered_title_only(
                    title_text="Add Website",
                    on_title_click=None
                )

            # Create bottom toolbar without coordinator (no edit mode for modal views)
            self.bottom_toolbar = BottomToolbar(
                app=self.app,
                is_mobile=self.is_mobile
            )

            # Set toolbars on the view
            self.set_top_toolbar(self.top_toolbar)
            self.set_bottom_toolbar(self.bottom_toolbar)

            logger.info("Website add view toolbars created successfully")
        except Exception as e:
            logger.error(f"Failed to create website add toolbars: {e}")
    
    def _create_content(self):
        """Create the view content"""
        # Title
        title = toga.Label(
            _("Add Website Content"),
            style=Pack(
                font_size=20,
                font_weight="bold",
                text_align=CENTER,
                margin=20,
                color="#1a1a1a"
            )
        )
        self.content_container.add(title)
        
        # Description
        description = toga.Label(
            _("Browse websites and select content to add to your library."),
            style=Pack(
                font_size=14,
                text_align=CENTER,
                margin=20,
                color="#666666"
            )
        )
        self.content_container.add(description)
        
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
            _("Add to Library"),
            on_press=self._on_select_content,
            style=Pack(flex=0)
        )
        nav_container.add(select_button)
        
        self.content_container.add(nav_container)
        
        # WebView for browsing
        try:
            self.webview = toga.WebView(
                style=Pack(
                    flex=1,
                    height=400,
                    margin=(0, 0, 10, 0)
                )
            )
            self.content_container.add(self.webview)
            
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
            self.content_container.add(error_label)
        
        # Instructions
        instructions = toga.Label(
            _("Navigate to a website and click 'Add to Library' to add its content to your library."),
            style=Pack(
                text_align="center",
                margin=(10, 0, 0, 0),
                font_size=12,
                color="#666666"
            )
        )
        self.content_container.add(instructions)
        
        # Status label
        self.status_label = toga.Label(
            _("Ready to browse websites"),
            style=Pack(margin=10)
        )
        self.content_container.add(self.status_label)
    
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
                self.status_label.text = _("Loading website...")
            else:
                logger.warning("No URL provided or WebView not available")
                self.status_label.text = _("Please enter a valid URL")
                
        except Exception as e:
            logger.error(f"Failed to navigate to URL: {e}")
            self.status_label.text = _("Error loading website")
    
    async def _on_select_content(self, widget):
        """Handle content selection from current page"""
        try:
            if not self.current_url:
                self.status_label.text = _("Please navigate to a website first")
                return
            
            self.status_label.text = _("Adding website to library...")
            
            # Call the callback with the current URL
            if self.on_content_added:
                self.on_content_added({'option_id': 'website', 'url': self.current_url, 'action': 'added'})
                self.status_label.text = _("Website added successfully!")
                logger.info(f"Added website to library: {self.current_url}")
            
        except Exception as e:
            logger.error(f"Failed to add website: {e}")
            self.status_label.text = _("Error adding website. Please try again.") 