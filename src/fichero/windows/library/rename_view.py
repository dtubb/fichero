"""
Simple Rename Collection View

Minimal view for renaming collections with text input.
"""

import toga
from toga.style import Pack
from toga.constants import COLUMN, ROW
import logging
from typing import Optional, Callable
import asyncio

from fichero.shared.views.base_view import BaseView
from fichero.shared.toolbars import TopToolbar

logger = logging.getLogger(__name__)


class RenameCollectionView(BaseView):
    """Simple view for renaming collections"""

    def __init__(self, app: toga.App, collection_id: str, collection_name: str, on_renamed: Optional[Callable] = None):
        """Initialize rename collection view"""
        self.collection_id = collection_id
        self.collection_name = collection_name
        self.on_renamed = on_renamed

        # UI components
        self.name_input: Optional[toga.TextInput] = None

        # Window reference for desktop modal closing
        self.modal_window: Optional[toga.Window] = None

        # Initialize BaseView first
        super().__init__(app, is_mobile=app.is_mobile)

        logger.info(f"Rename Collection View initialized for: {collection_name}")

    def set_modal_window(self, window: toga.Window):
        """Set the modal window reference for desktop closing"""
        self.modal_window = window
        logger.debug(f"Modal window reference set: {window}")

    def _create_content(self):
        """Create the simple rename form content"""
        try:
            # Create a vertically and horizontally centered container
            center_container = toga.Box(
                style=Pack(
                    direction=COLUMN,
                    align_items="center",
                    flex=1
                )
            )

            # Inner container for the form elements
            form_container = toga.Box(
                style=Pack(
                    direction=COLUMN,
                    align_items="center",
                    margin=(0, 40, 0, 40)  # Horizontal margins only
                )
            )

            # Text input with current name
            self.name_input = toga.TextInput(
                value=self.collection_name,
                on_confirm=self._on_ok_pressed,
                style=Pack(
                    margin=(0, 0, 20, 0),
                    width=250,  # Fixed width for better centering
                    text_align="left"  # Keep text left-aligned
                )
            )
            form_container.add(self.name_input)

            # Button container
            button_box = toga.Box(
                style=Pack(
                    direction=ROW,
                    align_items="center"
                )
            )

            # Cancel button
            cancel_button = toga.Button(
                "Cancel",
                on_press=self._on_cancel_pressed,
                style=Pack(
                    margin=(0, 10, 0, 0),
                    width=80
                )
            )
            button_box.add(cancel_button)

            # OK button
            ok_button = toga.Button(
                "OK",
                on_press=self._on_ok_pressed,
                style=Pack(
                    background_color="#007AFF",
                    color="white",
                    width=80
                )
            )
            button_box.add(ok_button)

            form_container.add(button_box)
            center_container.add(form_container)
            self.content_container.add(center_container)

        except Exception as e:
            logger.error(f"Failed to create rename content: {e}")

    def _create_toolbars(self):
        """Create minimal toolbar"""
        try:
            # Simple top toolbar with back navigation
            self.top_toolbar = TopToolbar(
                app=self.app,
                title="Rename",
                auto_mobile_nav=True,
                is_mobile=self.is_mobile
            )

        except Exception as e:
            logger.error(f"Failed to create rename view toolbars: {e}")

    def _on_ok_pressed(self, widget=None):
        """Handle OK button press"""
        try:
            new_name = self.name_input.value.strip() if self.name_input else ""

            if not new_name:
                # Show error for empty name
                asyncio.create_task(self._show_error("Please enter a collection name."))
                return

            if new_name == self.collection_name:
                # No change, just close the modal
                asyncio.create_task(self._close_modal())
                return

            # Perform the rename
            asyncio.create_task(self._perform_rename(new_name))

        except Exception as e:
            logger.error(f"Failed to handle OK press: {e}")

    def _on_cancel_pressed(self, widget=None):
        """Handle cancel button press"""
        try:
            # Close the modal without making changes
            asyncio.create_task(self._close_modal())
        except Exception as e:
            logger.error(f"Failed to handle cancel: {e}")

    def _go_back(self):
        """Navigate back using the same pattern as other modal views"""
        try:
            if self.is_mobile and hasattr(self.app, 'window_view_manager'):
                self.app.window_view_manager._close_modal_overlay()
            else:
                # Fallback: use NavigationController back navigation
                if hasattr(self.app, 'view_integration'):
                    nav_controller = self.app.view_integration.navigation_controller
                    if nav_controller:
                        nav_controller.navigate_back()
        except Exception as e:
            logger.error(f"Failed to navigate back: {e}")

    async def _perform_rename(self, new_name: str):
        """Perform the actual rename operation"""
        try:
            if hasattr(self.app, 'library_manager') and self.app.library_manager:
                logger.info(f"Renaming collection '{self.collection_name}' to '{new_name}'")

                # Update collection name using library manager
                success = await self.app.library_manager.update_collection(
                    self.collection_id,
                    name=new_name
                )

                if success:
                    logger.info(f"Successfully renamed collection: {self.collection_name} -> {new_name}")

                    # Call the callback if provided first
                    if self.on_renamed:
                        self.on_renamed(self.collection_id, new_name)

                    # Force a navigation event to refresh all views (primary method)
                    await self._emit_collection_updated()

                    # Also try direct refresh as backup
                    await self._refresh_library_view()

                    # LAST: Close the modal window
                    await self._close_modal()
                else:
                    await self._show_error(f"Failed to rename collection. Please try again.")
                    logger.error(f"Failed to rename collection in library: {self.collection_name}")
            else:
                await self._show_error("Library manager not available. Cannot rename collection.")
                logger.error("No library manager available for rename")

        except Exception as e:
            logger.error(f"Failed to perform rename: {e}")
            await self._show_error(f"An error occurred while renaming: {str(e)}")

    async def _refresh_library_view(self):
        """Simple reload of library collections"""
        try:
            logger.info("🔄 REFRESH DEBUG: Starting library view refresh")

            # First try to get the cached library view directly
            if hasattr(self.app, 'main_window') and self.app.main_window:
                main_window = self.app.main_window
                logger.info(f"🔄 REFRESH DEBUG: Found main_window: {main_window}")

                # Check for cached_library_view (correct attribute name)
                if hasattr(main_window, 'cached_library_view') and main_window.cached_library_view:
                    library_view = main_window.cached_library_view
                    logger.info(f"🔄 REFRESH DEBUG: Found cached_library_view: {library_view}")

                    # Simple approach: just reload collections from database
                    if hasattr(library_view, '_load_collections_async'):
                        logger.info("🔄 REFRESH DEBUG: Calling _load_collections_async()")
                        await library_view._load_collections_async()
                        logger.info("🔄 REFRESH DEBUG: Successfully reloaded library collections after rename")
                        return
                    else:
                        logger.warning("🔄 REFRESH DEBUG: library_view has no _load_collections_async method")
                else:
                    logger.warning("🔄 REFRESH DEBUG: main_window has no cached_library_view or it's None")
                    # Fallback: Force create the library view and refresh it
                    try:
                        logger.info("🔄 REFRESH DEBUG: Attempting to create library view and refresh")
                        library_view = main_window._get_or_create_library_view()
                        if library_view and hasattr(library_view, '_load_collections_async'):
                            logger.info("🔄 REFRESH DEBUG: Calling _load_collections_async() on created view")
                            await library_view._load_collections_async()
                            logger.info("🔄 REFRESH DEBUG: Successfully reloaded library collections via created view")
                            return
                    except Exception as fallback_e:
                        logger.error(f"🔄 REFRESH DEBUG: Fallback creation failed: {fallback_e}")
            else:
                logger.warning("🔄 REFRESH DEBUG: Could not find main_window")

            logger.warning("Could not find library view to refresh")
        except Exception as e:
            logger.error(f"🔄 REFRESH DEBUG: Failed to refresh library view: {e}")

    async def _emit_collection_updated(self):
        """Emit a navigation event to force refresh of all library views"""
        try:
            from fichero.shared.navigation.navigation_event_bus import emit_navigation_event, NavigationEvents

            # Emit a library show event to force refresh
            emit_navigation_event(NavigationEvents.SHOW_LIBRARY, {
                'force_refresh': True,
                'updated_collection_id': self.collection_id
            })
            logger.info("Emitted collection updated event")
        except Exception as e:
            logger.error(f"Failed to emit collection updated event: {e}")

    async def _close_modal(self):
        """Close the modal window using the same pattern as other modal views"""
        try:
            # Use the same pattern as settings and other modal views
            if self.is_mobile and hasattr(self.app, 'window_view_manager'):
                self.app.window_view_manager._close_modal_overlay()
                logger.info("Closed modal via window_view_manager (mobile)")
            else:
                # Desktop: First handle navigation state, then close the physical window
                if hasattr(self.app, 'view_integration'):
                    nav_controller = self.app.view_integration.navigation_controller
                    if nav_controller:
                        nav_controller.navigate_back()
                        logger.info("Updated navigation state for modal close (desktop)")

                # Close the actual Toga window using stored reference
                if self.modal_window:
                    try:
                        self.modal_window.close()
                        logger.info("Closed Toga modal window (desktop)")
                    except Exception as e:
                        logger.warning(f"Could not close modal window: {e}")
                else:
                    logger.warning("No modal window reference available for closing")

        except Exception as e:
            logger.error(f"Failed to close modal: {e}")

    async def _show_error(self, message: str):
        """Show error dialog"""
        try:
            error_dialog = toga.ErrorDialog(
                title="Rename Error",
                message=message
            )
            await self.app.main_window.dialog(error_dialog)
        except Exception as e:
            logger.error(f"Failed to show error dialog: {e}")