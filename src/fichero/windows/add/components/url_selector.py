"""
URL Selector Component

UI component for adding URLs to the library.
Supports single URLs or multiple URLs via multiline text input.
"""

import toga
from toga.style import Pack
from toga.constants import COLUMN, ROW
import logging
from typing import Optional, Callable, List
import re

# Use builtin _ function installed by translation.install()

logger = logging.getLogger(__name__)


class URLSelector:
    """URL selector component for adding web content"""
    
    def __init__(self, app: toga.App):
        """Initialize URL selector"""
        self.app = app
        self.on_urls_added: Optional[Callable] = None
        self.url_input: Optional[toga.TextInput] = None
        self.multiline_input: Optional[toga.MultilineTextInput] = None
        self.mode = "single"  # "single" or "multiple"
    
    async def execute(self) -> List[str]:
        """
        Execute URL collection.
        
        Returns:
            List[str]: List of valid URLs, empty list if none provided
        """
        try:
            if self.mode == "single" and self.url_input:
                url = self.url_input.value.strip()
                if url and self._is_valid_url(url):
                    logger.info(f"Single URL added: {url}")
                    if self.on_urls_added:
                        self.on_urls_added([url])
                    return [url]
                else:
                    logger.warning(f"Invalid URL provided: {url}")
                    return []
                    
            elif self.mode == "multiple" and self.multiline_input:
                text = self.multiline_input.value.strip()
                urls = self._extract_urls_from_text(text)
                if urls:
                    logger.info(f"Multiple URLs added: {len(urls)} URLs")
                    if self.on_urls_added:
                        self.on_urls_added(urls)
                    return urls
                else:
                    logger.warning("No valid URLs found in text")
                    return []
            else:
                logger.warning("No URL input available")
                return []
                
        except Exception as e:
            logger.error(f"Failed to process URLs: {e}")
            return []
    
    def _is_valid_url(self, url: str) -> bool:
        """Check if a URL is valid"""
        url_pattern = re.compile(
            r'^https?://'  # http:// or https://
            r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain...
            r'localhost|'  # localhost...
            r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
            r'(?::\d+)?'  # optional port
            r'(?:/?|[/?]\S+)$', re.IGNORECASE)
        return url_pattern.match(url) is not None
    
    def _extract_urls_from_text(self, text: str) -> List[str]:
        """Extract valid URLs from multiline text"""
        # Split by lines and filter valid URLs
        lines = text.split('\n')
        urls = []
        
        for line in lines:
            line = line.strip()
            if line and self._is_valid_url(line):
                urls.append(line)
            elif line and not line.startswith('#') and not line.startswith('//'):
                # Try to add http:// if missing
                if not line.startswith(('http://', 'https://')):
                    test_url = 'https://' + line
                    if self._is_valid_url(test_url):
                        urls.append(test_url)
        
        return urls
    
    def create(self):
        """Create the URL selector UI"""
        container = toga.Box(
            style=Pack(
                direction=COLUMN,
                margin=(0, 0, 10, 0)
            )
        )
        
        # Mode selection
        mode_container = toga.Box(
            style=Pack(
                direction=ROW,
                margin=(0, 0, 10, 0)
            )
        )
        
        single_button = toga.Button(
            _("Single URL"),
            on_press=lambda w: self._set_mode("single"),
            style=Pack(flex=0, margin=(0, 5, 0, 0))
        )
        mode_container.add(single_button)
        
        multiple_button = toga.Button(
            _("Multiple URLs"),
            on_press=lambda w: self._set_mode("multiple"),
            style=Pack(flex=0, margin=(0, 5, 0, 0))
        )
        mode_container.add(multiple_button)
        
        container.add(mode_container)
        
        # Single URL input
        self.single_container = toga.Box(
            style=Pack(
                direction=ROW,
                margin=(0, 0, 10, 0)
            )
        )
        
        self.url_input = toga.TextInput(
            placeholder=_("Enter URL (e.g., https://example.com)..."),
            style=Pack(flex=1, margin=(0, 10, 0, 0))
        )
        self.single_container.add(self.url_input)
        
        add_single_button = toga.Button(
            _("Add URL"),
            on_press=self._on_add_single_url,
            style=Pack(flex=0)
        )
        self.single_container.add(add_single_button)
        
        container.add(self.single_container)
        
        # Multiple URLs input
        self.multiple_container = toga.Box(
            style=Pack(
                direction=COLUMN,
                margin=(0, 0, 10, 0)
            )
        )
        
        multiple_label = toga.Label(
            _("Enter multiple URLs (one per line):"),
            style=Pack(margin=(0, 0, 5, 0))
        )
        self.multiple_container.add(multiple_label)
        
        self.multiline_input = toga.MultilineTextInput(
            placeholder=_("https://example1.com\nhttps://example2.com\n..."),
            style=Pack(flex=1, height=120, margin=(0, 0, 10, 0))
        )
        self.multiple_container.add(self.multiline_input)
        
        add_multiple_button = toga.Button(
            _("Add URLs"),
            on_press=self._on_add_multiple_urls,
            style=Pack(flex=0)
        )
        self.multiple_container.add(add_multiple_button)
        
        container.add(self.multiple_container)
        
        # Start with single mode
        self._set_mode("single")
        
        return container
    
    def _set_mode(self, mode: str):
        """Set the URL input mode"""
        self.mode = mode
        
        if mode == "single":
            self.single_container.style.visibility = "visible"
            self.multiple_container.style.visibility = "hidden"
        else:
            self.single_container.style.visibility = "hidden"
            self.multiple_container.style.visibility = "visible"
    
    async def _on_add_single_url(self, widget):
        """Handle single URL addition"""
        urls = await self.execute()
        if urls:
            self.url_input.value = ""
    
    async def _on_add_multiple_urls(self, widget):
        """Handle multiple URL addition"""
        urls = await self.execute()
        if urls:
            self.multiline_input.value = ""
    
    def register_callback(self, callback: Callable):
        """Register callback for when URLs are added"""
        self.on_urls_added = callback


# Use builtin _ function installed by translation.install()
