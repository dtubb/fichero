"""
URL Add View

BaseView for adding URLs to the library.
Supports single URLs and bulk URL input.
"""

import toga
from toga.style import Pack
from toga.constants import COLUMN, ROW
import logging
from typing import Optional, Callable, List
import re

from fichero.shared.views.base_view import BaseView
from fichero.shared.toolbars.simple_top_toolbar import SimpleTopToolbar

# Use builtin _ function installed by translation.install()

logger = logging.getLogger(__name__)


class URLAddView(BaseView):
    """View for adding URLs to the library"""
    
    def __init__(self, app: toga.App, on_back: Callable, on_content_added: Callable):
        """Initialize URL add view"""
        self.on_back = on_back
        self.on_content_added = on_content_added
        
        # Initialize BaseView first
        super().__init__(app, is_mobile=app.is_mobile)
        
        # Create toolbars after BaseView is initialized
        self._create_toolbars()
        
        logger.info("URL Add View initialized")
    
    def _create_toolbars(self):
        """Create top and bottom toolbars for URL add view"""
        try:
            from fichero.shared.toolbars.bottom_toolbar import BottomToolbar
            
            # Create simple top toolbar using automatic navigation
            self.top_toolbar = SimpleTopToolbar(
                app=self.app,
                title="Add URLs",
                on_back=self.on_back,
                is_mobile=self.is_mobile
            )
            
            # Bottom toolbar (empty for now, but consistent structure)
            class URLAddBottomToolbar(BottomToolbar):
                def _create_toolbar(self):
                    super()._create_toolbar()
                    # URL-specific actions could go here
            
            self.bottom_toolbar = URLAddBottomToolbar(self.app, is_mobile=self.is_mobile)
            
            # Set toolbars on the view (mobile navigation will be connected automatically)
            self.set_top_toolbar(self.top_toolbar)
            self.set_bottom_toolbar(self.bottom_toolbar)
            
            logger.info("URL add view toolbars created with automatic navigation")            
        except Exception as e:
            logger.error(f"Failed to create URL add toolbars: {e}")
    
    def _create_content(self):
        """Create the URL input interface"""
        # Title
        title = toga.Label(
            _("Add URLs to Library"),
            style=Pack(margin=10)
        )
        self.content_container.add(title)
        
        # Description
        description = toga.Label(
            _("Add web content to your library by entering URLs. You can add single URLs or multiple URLs at once."),
            style=Pack(margin=(0, 10, 10, 10))
        )
        self.content_container.add(description)
        
        # Mode selector
        mode_container = toga.Box(
            style=Pack(direction=ROW, margin=10)
        )
        
        mode_label = toga.Label(
            _("Mode:"),
            style=Pack(padding_right=10)
        )
        mode_container.add(mode_label)
        
        self.single_button = toga.Button(
            _("Single URL"),
            on_press=lambda widget: self._switch_mode('single'),
            style=Pack(padding=(5, 10))
        )
        mode_container.add(self.single_button)
        
        self.multiple_button = toga.Button(
            _("Multiple URLs"),
            on_press=lambda widget: self._switch_mode('multiple'),
            style=Pack(padding=(5, 10))
        )
        mode_container.add(self.multiple_button)
        
        self.content_container.add(mode_container)
        
        # Single URL input
        self.single_container = toga.Box(
            style=Pack(direction=COLUMN, margin=10)
        )
        
        single_label = toga.Label(
            _("Enter a single URL:"),
            style=Pack(margin=(10, 0))
        )
        self.single_container.add(single_label)
        
        self.url_input = toga.TextInput(
            placeholder=_("https://example.com"),
            style=Pack(margin=(5, 0), flex=1)
        )
        self.single_container.add(self.url_input)
        
        self.add_single_button = toga.Button(
            _("➕ Add URL to Library"),
            on_press=self._on_add_single,
            style=Pack(margin=(10, 0))
        )
        self.single_container.add(self.add_single_button)
        
        # Multiple URLs input
        self.multiple_container = toga.Box(
            style=Pack(direction=COLUMN, margin=10)
        )
        
        multiple_label = toga.Label(
            _("Enter multiple URLs (one per line):"),
            style=Pack(margin=(10, 0))
        )
        self.multiple_container.add(multiple_label)
        
        demo_label = toga.Label(
            _("You can paste URLs from your demo files or enter them manually"),
            style=Pack(margin=(5, 0))
        )
        self.multiple_container.add(demo_label)
        
        self.multiline_input = toga.MultilineTextInput(
            placeholder=_("https://example1.com\nhttps://example2.com\nhttps://example3.com"),
            style=Pack(margin=(5, 0), flex=1)
        )
        self.multiple_container.add(self.multiline_input)
        
        self.add_multiple_button = toga.Button(
            _("➕ Add URLs to Library"),
            on_press=self._on_add_multiple,
            style=Pack(margin=(10, 0))
        )
        self.multiple_container.add(self.add_multiple_button)
        
        # Status label
        self.status_label = toga.Label(
            _("Ready to add URLs"),
            style=Pack(margin=10)
        )
        
        # Add containers
        self.content_container.add(self.single_container)
        self.content_container.add(self.multiple_container)
        self.content_container.add(self.status_label)
        
        # Start in single mode
        self._switch_mode('single')
    
    def _switch_mode(self, mode: str):
        """Switch between single and multiple URL input modes"""
        self.mode = mode
        
        if mode == 'single':
            self.single_button.enabled = False
            self.multiple_button.enabled = True
            self.single_container.style.visibility = 'visible'
            self.multiple_container.style.visibility = 'hidden'
        else:
            self.single_button.enabled = True
            self.multiple_button.enabled = False
            self.single_container.style.visibility = 'hidden'
            self.multiple_container.style.visibility = 'visible'
    
    def _is_valid_url(self, url: str) -> bool:
        """Validate URL format"""
        url_pattern = re.compile(
            r'^https?://'  # http:// or https://
            r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain...
            r'localhost|'  # localhost...
            r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
            r'(?::\d+)?'  # optional port
            r'(?:/?|[/?]\S+)$', re.IGNORECASE)
        return bool(url_pattern.match(url))
    
    async def _on_add_single(self, widget):
        """Handle adding a single URL"""
        try:
            url = self.url_input.value.strip()
            if not url:
                self.status_label.text = _("Please enter a URL")
                return
            
            if not self._is_valid_url(url):
                self.status_label.text = _("Please enter a valid URL")
                return
            
            self.status_label.text = _("Adding URL to library...")
            
            # Call the callback with the URL
            if self.on_content_added:
                self.on_content_added({'option_id': 'url', 'urls': [url], 'action': 'added'})
                self.status_label.text = _("URL added successfully!")
                logger.info(f"Added URL to library: {url}")
            
        except Exception as e:
            logger.error(f"Failed to add URL: {e}")
            self.status_label.text = _("Error adding URL. Please try again.")
    
    async def _on_add_multiple(self, widget):
        """Handle adding multiple URLs"""
        try:
            text = self.multiline_input.value.strip()
            if not text:
                self.status_label.text = _("Please enter URLs")
                return
            
            # Extract URLs from text
            urls = []
            for line in text.split('\n'):
                url = line.strip()
                if url and self._is_valid_url(url):
                    urls.append(url)
            
            if not urls:
                self.status_label.text = _("No valid URLs found")
                return
            
            self.status_label.text = _("Adding %(count)d URLs to library...") % {'count': len(urls)}
            
            # Call the callback with the URLs
            if self.on_content_added:
                self.on_content_added({'option_id': 'url', 'urls': urls, 'action': 'added'})
                self.status_label.text = _("%(count)d URLs added successfully!") % {'count': len(urls)}
                logger.info(f"Added {len(urls)} URLs to library")
            
        except Exception as e:
            logger.error(f"Failed to add URLs: {e}")
            self.status_label.text = _("Error adding URLs. Please try again.") 