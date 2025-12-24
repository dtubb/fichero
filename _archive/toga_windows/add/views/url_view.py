"""
URL Add View

BaseView for adding URLs to the library.
Simple Mac-like interface for single URL import.
"""

import toga
from toga.style import Pack
from toga.constants import COLUMN, ROW
import logging
from typing import Optional, Callable
import re

from fichero.shared.views.base_view import BaseView
from fichero.shared.toolbars import TopToolbar, BottomToolbar

# Use builtin _ function installed by translation.install()

logger = logging.getLogger(__name__)


class URLAddView(BaseView):
    """View for adding URLs to the library - simple Mac-like design"""

    def __init__(self, app: toga.App, on_content_added: Optional[Callable] = None):
        """Initialize URL add view"""
        self.on_content_added = on_content_added

        # Initialize BaseView first
        super().__init__(app, is_mobile=app.is_mobile)

        # Create toolbars after BaseView is initialized
        self._create_toolbars()

        logger.info("URL Add View initialized")

    def _create_view_structure(self):
        """Override to create simple container without scrolling for dialog"""
        try:
            # Simple container without scroll for this small dialog
            self.container = toga.Box(
                style=Pack(direction=COLUMN, flex=1)
            )

            # Content container (no scroll needed for simple dialog)
            self.content_container = toga.Box(
                style=Pack(direction=COLUMN, flex=1)
            )

            # Add content directly to container (no scroll wrapper)
            self.container.add(self.content_container)

            # Create content
            self._create_content()

            logger.debug("URL add view structure created (no scrolling)")

        except Exception as e:
            logger.error(f"Failed to create URL add view structure: {e}")
            # Fallback
            self.container = toga.Box(style=Pack(direction=COLUMN))

    def _create_toolbars(self):
        """Create toolbars for mobile navigation only"""
        # Only create toolbars for mobile (desktop uses window chrome)
        if self.is_mobile:
            try:
                self.top_toolbar = TopToolbar(
                    app=self.app,
                    title="Import URL",
                    auto_mobile_nav=True,
                    is_mobile=self.is_mobile
                )

                self.bottom_toolbar = BottomToolbar(
                    app=self.app,
                    is_mobile=self.is_mobile
                )

                self.set_top_toolbar(self.top_toolbar)
                self.set_bottom_toolbar(self.bottom_toolbar)

                logger.info("URL add view toolbars created successfully")
            except Exception as e:
                logger.error(f"Failed to create URL add toolbars: {e}")

    def _create_content(self):
        """Create the URL input interface - minimal Mac-like design"""
        # Main container with proper spacing
        main_container = toga.Box(
            style=Pack(direction=COLUMN, margin=20, flex=1)
        )

        # URL input field (no label, window title provides context)
        # on_confirm makes Enter key trigger the Add action (default button behavior)
        self.url_input = toga.TextInput(
            placeholder=_("https://example.com"),
            style=Pack(flex=1, margin=(0, 0, 20, 0)),
            on_confirm=self._on_add_sync  # Enter key triggers Add
        )
        main_container.add(self.url_input)

        # Spacer to push buttons to bottom
        spacer = toga.Box(style=Pack(flex=1))
        main_container.add(spacer)

        # Button container (right-aligned on Mac)
        button_container = toga.Box(
            style=Pack(direction=ROW, margin=(0, 0, 0, 0))
        )

        # Spacer to push buttons to right
        button_spacer = toga.Box(style=Pack(flex=1))
        button_container.add(button_spacer)

        # Cancel button
        self.cancel_button = toga.Button(
            _("Cancel"),
            on_press=self._on_cancel,
            style=Pack(margin=(0, 8, 0, 0), width=80)
        )
        button_container.add(self.cancel_button)

        # Add button (primary action, default)
        self.add_button = toga.Button(
            _("Add"),
            on_press=self._on_add_sync,
            style=Pack(width=80)
        )
        button_container.add(self.add_button)

        main_container.add(button_container)

        # Add to content container
        self.content_container.add(main_container)

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

    def _on_cancel(self, widget):
        """Handle cancel button"""
        if hasattr(self, 'window') and self.window:
            self.window.close()

    def _on_add_sync(self, widget):
        """Synchronous wrapper for _on_add"""
        import asyncio
        asyncio.create_task(self._on_add(widget))

    async def _on_add(self, widget):
        """Handle adding a URL"""
        try:
            url = self.url_input.value.strip()
            if not url:
                await self.app.main_window.dialog(
                    toga.InfoDialog(_("Missing URL"), _("Please enter a URL."))
                )
                return

            if not self._is_valid_url(url):
                await self.app.main_window.dialog(
                    toga.InfoDialog(_("Invalid URL"), _("Please enter a valid URL (must start with http:// or https://)."))
                )
                return

            # Call the callback with the URL and await the import to complete
            if self.on_content_added:
                # Show progress by disabling the button
                self.add_button.enabled = False
                self.add_button.text = _("Adding...")

                # The callback returns an async task that we can await
                task = self.on_content_added({'option_id': 'url', 'urls': [url], 'action': 'added'})
                logger.info(f"Import started for URL: {url}")

                # Wait for the import to complete
                if task:
                    await task
                    logger.info(f"Import completed for URL: {url}")
                else:
                    # If no task returned, just wait a bit for the import to start
                    import asyncio
                    await asyncio.sleep(0.5)

                # Close the window immediately
                if hasattr(self, 'window') and self.window:
                    self.window.close()

        except Exception as e:
            logger.error(f"Failed to add URL: {e}")
            self.add_button.enabled = True
            self.add_button.text = _("Add")
            await self.app.main_window.dialog(
                toga.ErrorDialog(_("Import Failed"), str(e))
            )
