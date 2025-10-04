"""
Bulk Import View

BaseView for importing content from text files (URLs, paths, or mixed).
Supports zip file import as well.
"""

import toga
from toga.style import Pack
from toga.constants import COLUMN, ROW
import logging
from typing import Optional, Callable
from pathlib import Path
import asyncio

from fichero.shared.views.base_view import BaseView
from fichero.shared.toolbars import TopToolbar, BottomToolbar

logger = logging.getLogger(__name__)


class BulkImportView(BaseView):
    """View for bulk importing from text files or zip archives"""

    def __init__(self, app: toga.App, on_content_added: Optional[Callable] = None):
        """Initialize bulk import view"""
        self.on_content_added = on_content_added
        self.selected_file = None
        self.collection_type = "hybrid"  # Default

        # Initialize BaseView first
        super().__init__(app, is_mobile=app.is_mobile)

        # Create toolbars after BaseView is initialized
        self._create_toolbars()

        logger.info("Bulk Import View initialized")

    def _create_toolbars(self):
        """Create top and bottom toolbars"""
        try:
            # Create top toolbar
            self.top_toolbar = TopToolbar(
                app=self.app,
                title="Bulk Import",
                auto_mobile_nav=True,
                is_mobile=self.is_mobile
            )

            # Add centered title for desktop
            if not self.is_mobile:
                self.top_toolbar.add_centered_title_only(
                    title_text="Bulk Import",
                    on_title_click=None
                )

            # Create bottom toolbar
            self.bottom_toolbar = BottomToolbar(
                app=self.app,
                is_mobile=self.is_mobile
            )

            # Set toolbars on the view
            self.set_top_toolbar(self.top_toolbar)
            self.set_bottom_toolbar(self.bottom_toolbar)

            logger.info("Bulk import view toolbars created successfully")
        except Exception as e:
            logger.error(f"Failed to create bulk import toolbars: {e}")

    def _create_content(self):
        """Create the bulk import interface"""
        # Title
        title = toga.Label(
            "Bulk Import from Text File or Zip",
            style=Pack(margin=10, font_size=16, font_weight="bold")
        )
        self.content_container.add(title)

        # Description
        description = toga.Label(
            "Import multiple URLs, file paths, or folders from a text file (one per line), or import a zip archive.",
            style=Pack(margin=(0, 10, 20, 10))
        )
        self.content_container.add(description)

        # Collection type selector
        type_container = toga.Box(style=Pack(direction=COLUMN, margin=10))

        type_label = toga.Label(
            "Collection Type:",
            style=Pack(margin_bottom=5)
        )
        type_container.add(type_label)

        self.type_selection = toga.Selection(
            items=["hybrid (Auto-detect URLs & Paths)", "url (URLs only)", "local (Local paths)", "external (External paths)"],
            style=Pack(flex=1, margin_bottom=10)
        )
        self.type_selection.value = "hybrid (Auto-detect URLs & Paths)"
        type_container.add(self.type_selection)

        type_help = toga.Label(
            "• hybrid: Auto-detects URLs (http/https/ftp) and file/folder paths\n"
            "• url: Filters and imports only URLs\n"
            "• local/external: Filters and imports only file/folder paths",
            style=Pack(margin_top=5, font_size=10)
        )
        type_container.add(type_help)

        self.content_container.add(type_container)

        # File selection
        file_container = toga.Box(style=Pack(direction=ROW, margin=10))

        self.file_button = toga.Button(
            "Select File...",
            on_press=self._on_select_file,
            style=Pack(flex=1, margin_right=10)
        )
        file_container.add(self.file_button)

        self.file_label = toga.Label(
            "No file selected",
            style=Pack(flex=2)
        )
        file_container.add(self.file_label)

        self.content_container.add(file_container)

        # Collection name input
        name_container = toga.Box(style=Pack(direction=COLUMN, margin=10))

        name_label = toga.Label(
            "Collection Name:",
            style=Pack(margin_bottom=5)
        )
        name_container.add(name_label)

        self.name_input = toga.TextInput(
            placeholder="My Collection",
            style=Pack(flex=1)
        )
        name_container.add(self.name_input)

        self.content_container.add(name_container)

        # Description input
        desc_container = toga.Box(style=Pack(direction=COLUMN, margin=10))

        desc_label = toga.Label(
            "Description (optional):",
            style=Pack(margin_bottom=5)
        )
        desc_container.add(desc_label)

        self.description_input = toga.MultilineTextInput(
            placeholder="Collection description...",
            style=Pack(flex=1, height=100)
        )
        desc_container.add(self.description_input)

        self.content_container.add(desc_container)

        # Options
        options_container = toga.Box(style=Pack(direction=COLUMN, margin=10))

        self.validate_switch = toga.Switch(
            "Validate URLs before adding",
            value=True,
            style=Pack(margin_bottom=5)
        )
        options_container.add(self.validate_switch)

        self.skip_duplicates_switch = toga.Switch(
            "Skip duplicate entries",
            value=True,
            style=Pack(margin_bottom=5)
        )
        options_container.add(self.skip_duplicates_switch)

        self.content_container.add(options_container)

        # Import button
        import_button = toga.Button(
            "Import Collection",
            on_press=self._on_import,
            style=Pack(margin=20)
        )
        self.content_container.add(import_button)

    def _on_select_file(self, widget):
        """Handle file selection"""
        try:
            # Create file dialog
            self.app.main_window.open_file_dialog(
                title="Select Text File or Zip Archive",
                file_types=['txt', 'zip'],
                on_result=self._on_file_selected
            )
        except Exception as e:
            logger.error(f"Failed to open file dialog: {e}")
            self.app.main_window.info_dialog("Error", f"Failed to open file dialog: {e}")

    def _on_file_selected(self, widget, path):
        """Handle file selected from dialog"""
        if path:
            self.selected_file = Path(path)
            self.file_label.text = self.selected_file.name

            # Auto-fill collection name if empty
            if not self.name_input.value:
                self.name_input.value = self.selected_file.stem

    def _on_import(self, widget):
        """Handle import button click"""
        # Validation
        if not self.selected_file:
            self.app.main_window.info_dialog("No File Selected", "Please select a text file or zip archive to import.")
            return

        if not self.name_input.value:
            self.app.main_window.info_dialog("No Collection Name", "Please enter a name for the collection.")
            return

        # Get collection type from selection
        type_map = {
            "hybrid (Auto-detect URLs & Paths)": "hybrid",
            "url (URLs only)": "url",
            "local (Local paths)": "local",
            "external (External paths)": "external"
        }
        self.collection_type = type_map.get(self.type_selection.value, "hybrid")

        # Start import
        asyncio.create_task(self._import_collection())

    async def _import_collection(self):
        """Import the collection"""
        try:
            # Check file type
            if self.selected_file.suffix.lower() == '.zip':
                await self._import_zip()
            else:
                await self._import_text_file()

        except Exception as e:
            logger.error(f"Import failed: {e}")
            self.app.main_window.info_dialog("Import Failed", f"Failed to import: {e}")

    async def _import_text_file(self):
        """Import from text file"""
        try:
            # Get library service
            if not hasattr(self.app, 'view_integration'):
                self.app.main_window.info_dialog("Error", "Library service not available")
                return

            library_service = self.app.view_integration.library_service

            # Read file
            async with asyncio.to_thread(open, self.selected_file, 'r') as f:
                content = await asyncio.to_thread(f.read)

            lines = [line.strip() for line in content.split('\n') if line.strip()]

            if not lines:
                self.app.main_window.info_dialog("Empty File", "The selected file contains no content.")
                return

            # Categorize based on collection type
            urls = []
            paths = []

            for line in lines:
                if line.startswith(('http://', 'https://', 'ftp://')):
                    urls.append(line)
                else:
                    paths.append(line)

            # Filter based on type
            if self.collection_type == "url":
                paths = []  # Only keep URLs
            elif self.collection_type in ["local", "external"]:
                urls = []  # Only keep paths
            # hybrid keeps both

            total_items = len(urls) + len(paths)
            if total_items == 0:
                self.app.main_window.info_dialog(
                    "No Valid Items",
                    f"No valid {self.collection_type} items found in file."
                )
                return

            # Create collection
            collection_id = await library_service.create_collection_for_ui(
                name=self.name_input.value,
                collection_type=self.collection_type
            )

            # Add items
            for url in urls:
                await library_service.add_item_to_collection_for_ui(
                    collection_id=collection_id,
                    item_type="url",
                    source=url,
                    name=Path(url).name or url
                )

            for path in paths:
                path_obj = Path(path)
                item_type = "folder" if path_obj.is_dir() else "file"
                await library_service.add_item_to_collection_for_ui(
                    collection_id=collection_id,
                    item_type=item_type,
                    source=path,
                    name=path_obj.name
                )

            # Success
            self.app.main_window.info_dialog(
                "Import Successful",
                f"Imported {total_items} items ({len(urls)} URLs, {len(paths)} paths) to collection '{self.name_input.value}'"
            )

            # Callback
            if self.on_content_added:
                await self.on_content_added({
                    'collection_id': collection_id,
                    'collection_name': self.name_input.value,
                    'item_count': total_items
                })

            # Navigate back
            if hasattr(self.app, 'view_integration'):
                self.app.view_integration.navigation_controller.navigate_back()

        except Exception as e:
            logger.error(f"Text file import failed: {e}")
            self.app.main_window.info_dialog("Import Failed", str(e))

    async def _import_zip(self):
        """Import from zip file"""
        try:
            # Get library service
            if not hasattr(self.app, 'view_integration'):
                self.app.main_window.info_dialog("Error", "Library service not available")
                return

            library_service = self.app.view_integration.library_service

            # Use library manager's import functionality
            await library_service.import_collection_from_path_for_ui(
                path=str(self.selected_file),
                name=self.name_input.value
            )

            # Success
            self.app.main_window.info_dialog(
                "Import Successful",
                f"Imported zip archive to collection '{self.name_input.value}'"
            )

            # Navigate back
            if hasattr(self.app, 'view_integration'):
                self.app.view_integration.navigation_controller.navigate_back()

        except Exception as e:
            logger.error(f"Zip import failed: {e}")
            self.app.main_window.info_dialog("Import Failed", str(e))
