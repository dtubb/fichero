"""Window - Native macOS Mail/Finder-style 4-pane layout.

Uses NSSplitViewController directly for native behavior:
- Sidebar extends into title bar (traffic lights in sidebar)
- Native window tabbing (Cmd+T for new tab)
- Animated pane collapse/expand
- View switching: library/workflow/search modes

    ┌─ NSWindow ──────────────────────────────────────────────────────┐
    │ [●●●] ╔══SIDEBAR══╗ NSToolbar                                   │
    │       ║ Library   ║ ┌──────────────────────────────────────────┐│
    │       ║ Searches  ║ │  BROWSER   │   EDITOR    │  INSPECTOR   ││
    │       ║ Workflows ║ │            │             │              ││
    │       ╚═══════════╝ └──────────────────────────────────────────┘│
    └─────────────────────────────────────────────────────────────────┘

Usage:
    controller = MainWindowController(app, ns_window)
    controller.show()

    # Switch views
    controller.switch_view('workflow')  # Show workflow editor
    controller.switch_view('library')   # Back to library browsing
"""
from __future__ import annotations

import logging
from enum import Enum
from typing import TYPE_CHECKING

from rubicon.objc import ObjCClass

if TYPE_CHECKING:
    from fichero.models import Document, Workflow

logger = logging.getLogger(__name__)


# =============================================================================
# View Mode Enum
# =============================================================================

class ViewMode(str, Enum):
    """Available view modes."""
    library = "library"
    workflow = "workflow"
    search = "search"

# =============================================================================
# Cocoa Classes
# =============================================================================

NSSplitViewController = ObjCClass("NSSplitViewController")
NSSplitViewItem = ObjCClass("NSSplitViewItem")
NSViewController = ObjCClass("NSViewController")

# Window style mask
FULL_SIZE_CONTENT = 1 << 15  # NSWindowStyleMaskFullSizeContentView

# Minimum pane widths
SIDEBAR_MIN = 150
BROWSER_MIN = 200
EDITOR_MIN = 300
INSPECTOR_MIN = 200


# =============================================================================
# Helpers
# =============================================================================

def _wrap_view(view, identifier: str):
    """Wrap a view in NSViewController for NSSplitViewItem."""
    vc = NSViewController.alloc().init()
    vc.view = view
    vc.identifier = identifier
    return vc


# =============================================================================
# Main Window Controller
# =============================================================================

class MainWindowController:
    """Native macOS 4-pane window controller.

    Data Flow:
        Sidebar select → Browser loads children
        Browser select → Editor + Inspector load document

    Attributes:
        sidebar: NativeSidebar (NSTreeController) for library navigation
        browser: Document grid/list
        editor: Document viewer (image, text, table)
        inspector: Metadata panel
    """

    def __init__(self, app, ns_window):
        self.app = app
        self._window = ns_window

        # Selection state
        self._selected_collection: Document | None = None
        self._selected_documents: list[Document] = []
        self._selected_workflow: Workflow | None = None
        self._current_browser_parent_id: str | None = None  # Identity check for sidebar

        # View mode state
        self._current_mode: ViewMode = ViewMode.library
        self._views: dict[ViewMode, tuple] = {}  # (editor, inspector) pairs

        # Configure window for Mail-style layout
        self._configure_window()

        # Create split view with 4 panes
        self._create_layout()

        # Create all view pairs
        self._create_views()

        logger.info("MainWindowController initialized")

    def _configure_window(self):
        """Configure window for Mail/Finder style."""
        # Full-size content (sidebar extends to title bar)
        self._window.styleMask = self._window.styleMask | FULL_SIZE_CONTENT
        self._window.titlebarAppearsTransparent = True
        self._window.titleVisibility = 1  # Hidden

        # Enable native window tabbing (Cmd+T)
        self._window.tabbingMode = 0  # NSWindowTabbingModeAutomatic

        # Auto-save window frame (position/size) - FREE from macOS
        self._window.setFrameAutosaveName_("FicheroMainWindow")

    def _create_layout(self):
        """Create 4-pane split view layout."""
        from .sidebar_native import NativeSidebar
        from .browser import Browser
        from .views.library import LibraryEditor, LibraryInspector

        # Create split view controller
        self._split_vc = NSSplitViewController.alloc().init()

        # Sidebar (extends to title bar, vibrant background)
        # Uses NSTreeController - automatic data source, selection, drag-drop
        self.sidebar = NativeSidebar(
            on_select=self._on_sidebar_select,
            on_file_drop=self._on_file_drop,
        )
        sidebar_item = NSSplitViewItem.sidebarWithViewController_(
            _wrap_view(self.sidebar.native, "sidebar")
        )
        sidebar_item.minimumThickness = SIDEBAR_MIN
        self._split_vc.addSplitViewItem_(sidebar_item)

        # Browser (content list - Mail-style)
        self.browser = Browser(
            on_select=self._on_browser_select,
            on_double_click=self._on_browser_double_click,
        )
        browser_item = NSSplitViewItem.contentListWithViewController_(
            _wrap_view(self.browser.native, "browser")
        )
        browser_item.minimumThickness = BROWSER_MIN
        self._split_vc.addSplitViewItem_(browser_item)

        # Editor (main flexible content area)
        self.editor = LibraryEditor()
        editor_item = NSSplitViewItem.splitViewItemWithViewController_(
            _wrap_view(self.editor.native, "editor")
        )
        editor_item.minimumThickness = EDITOR_MIN
        editor_item.holdingPriority = 200  # Grows/shrinks first
        self._split_vc.addSplitViewItem_(editor_item)

        # Inspector (right sidebar)
        self.inspector = LibraryInspector()
        inspector_item = NSSplitViewItem.inspectorWithViewController_(
            _wrap_view(self.inspector.native, "inspector")
        )
        inspector_item.minimumThickness = INSPECTOR_MIN
        self._split_vc.addSplitViewItem_(inspector_item)

        # Store for programmatic access
        self._panes = {
            'sidebar': sidebar_item,
            'browser': browser_item,
            'editor': editor_item,
            'inspector': inspector_item,
        }

        # Wire up
        self._window.contentViewController = self._split_vc
        self._split_vc.splitView.autosaveName = "FicheroMainSplit"
        self._split_vc.minimumThicknessForInlineSidebars = 400

    def _create_views(self):
        """Create all view pairs (editor + inspector) for each mode."""
        from .views.library import LibraryEditor, LibraryInspector
        from .views.workflow import WorkflowEditor, WorkflowInspector
        from .views.search import SearchEditor, SearchInspector

        # Library view (already created in _create_layout)
        self._views[ViewMode.library] = (self.editor, self.inspector)

        # Workflow view
        workflow_editor = WorkflowEditor()
        workflow_inspector = WorkflowInspector(
            on_add_provider=self._show_add_provider_sheet
        )
        self._views[ViewMode.workflow] = (workflow_editor, workflow_inspector)

        # Search view
        search_editor = SearchEditor()
        search_inspector = SearchInspector()
        self._views[ViewMode.search] = (search_editor, search_inspector)

        logger.debug("Created all view pairs")

    def _show_add_provider_sheet(self):
        """Show the Add Provider sheet."""
        from .sheets import ProviderSheet

        def on_provider_added(provider, models):
            logger.info(f"Added provider: {provider.name} with {len(models)} models")
            # Refresh the workflow inspector's provider dropdown
            if self._current_mode == ViewMode.workflow:
                editor, inspector = self._views[ViewMode.workflow]
                inspector.refresh_providers()

        sheet = ProviderSheet(self._window, on_complete=on_provider_added)
        sheet.show()

    # =========================================================================
    # View Switching
    # =========================================================================

    def switch_view(self, mode: ViewMode | str):
        """Switch to a different view mode.

        Args:
            mode: ViewMode enum or string ("library", "workflow", "search")
        """
        # Convert string to ViewMode
        if isinstance(mode, str):
            mode = ViewMode(mode)

        # Already in this mode?
        if self._current_mode == mode:
            return

        # Get the new view pair
        if mode not in self._views:
            logger.error(f"Unknown view mode: {mode}")
            return

        new_editor, new_inspector = self._views[mode]

        # Get the view controllers for editor and inspector panes
        editor_vc = self._panes['editor'].viewController
        inspector_vc = self._panes['inspector'].viewController

        # Swap the views
        editor_vc.view = new_editor.native
        inspector_vc.view = new_inspector.native

        # Update current references
        self.editor = new_editor
        self.inspector = new_inspector
        self._current_mode = mode

        logger.info(f"Switched to {mode.value} view")

    @property
    def current_mode(self) -> ViewMode:
        """Current view mode."""
        return self._current_mode

    # =========================================================================
    # Callbacks
    # =========================================================================

    def _on_sidebar_select(self, document_id: str):
        """Sidebar selection → load browser and switch views if needed.

        View switching logic:
        - Collection/Folder/File → library view
        - Workflow → workflow view
        - SavedSearch → search view

        Sidebar IDs have prefixes (e.g., "doc:abc123", "workflow:xyz").
        We strip the prefix and use the raw ID for db lookups.
        """
        from fichero.models import Document, DocType, Workflow
        from fichero.db import db

        if not document_id:
            logger.debug("Sidebar select called with empty ID")
            return

        logger.info(f"Sidebar selected: {document_id}")

        # Strip prefix: "doc:abc123" → ("doc", "abc123")
        if ":" in document_id:
            prefix, raw_id = document_id.split(":", 1)
        else:
            prefix, raw_id = None, document_id

        # Route based on prefix
        if prefix == "doc":
            # Identity check: skip if already showing this collection (prevents loops)
            if raw_id == self._current_browser_parent_id:
                logger.debug(f"Already showing collection {raw_id}, skipping")
                return
            self._current_browser_parent_id = raw_id

            import time
            t0 = time.perf_counter()

            doc = db.get(Document, raw_id)
            t1 = time.perf_counter()
            logger.info(f"db.get took {(t1-t0)*1000:.1f}ms")

            if doc:
                logger.info(f"Loading collection: {doc.name} (id={raw_id})")
                if self._current_mode != ViewMode.library:
                    self.switch_view(ViewMode.library)
                self._selected_collection = doc

                t2 = time.perf_counter()
                children = list(db.query(Document, parent_id=doc.id))
                t3 = time.perf_counter()
                logger.info(f"db.query took {(t3-t2)*1000:.1f}ms for {len(children)} children")

                try:
                    t4 = time.perf_counter()
                    self.browser.items = children
                    t5 = time.perf_counter()
                    logger.info(f"browser.items setter took {(t5-t4)*1000:.1f}ms")
                    logger.info("Browser items set successfully")
                except Exception as e:
                    logger.error(f"Failed to set browser items: {e}", exc_info=True)
            else:
                logger.warning(f"Document not found: {raw_id}")
            return

        if prefix == "workflow":
            workflow = db.get(Workflow, raw_id)
            if workflow:
                logger.info(f"Loading workflow: {workflow.name}")
                self._selected_workflow = workflow
                self.switch_view(ViewMode.workflow)
                editor, inspector = self._views[ViewMode.workflow]
                editor.load(workflow)
                inspector.load(workflow)
            else:
                logger.warning(f"Workflow not found: {raw_id}")
            return

        if prefix == "search":
            logger.info(f"Loading saved search: {raw_id}")
            # TODO: Load saved search
            self.switch_view(ViewMode.search)
            return

        # No prefix - try Document first (backwards compatibility)
        doc = db.get(Document, raw_id)

        if doc:
            logger.info(f"Loading document (no prefix): {doc.name}")
            if self._current_mode != ViewMode.library:
                self.switch_view(ViewMode.library)

            self._selected_collection = doc
            children = list(db.query(Document, parent_id=doc.id))
            logger.info(f"Found {len(children)} children")
            self.browser.items = children
            return

        # Try as Workflow
        workflow = db.get(Workflow, document_id)
        if workflow:
            logger.info(f"Loading workflow (no prefix): {workflow.name}")
            self._selected_workflow = workflow
            self.switch_view(ViewMode.workflow)

            editor, inspector = self._views[ViewMode.workflow]
            editor.load(workflow)
            inspector.load(workflow)
            return

        # Not found
        logger.warning(f"Sidebar selected unknown ID: {document_id}")
        self.browser.items = []

    def _on_browser_select(self, docs: list):
        """Browser selection → load editor + inspector."""
        self._selected_documents = docs
        if docs:
            doc = docs[0]
            logger.info(f"Browser selected: {doc.name} ({len(docs)} total)")
            self.editor.load(doc)
            self.inspector.load(doc)
        else:
            logger.debug("Browser selection cleared")
            self.editor.clear()
            self.inspector.clear()

    def _on_browser_double_click(self, doc):
        """Double-click → could open in new tab/window."""
        logger.debug(f"Double-click: {doc.name if doc else None}")

    def _on_file_drop(self, target_id: str | None, paths: list[str]):
        """Files dropped on sidebar."""
        self.ingest_files(paths, target_id=target_id)

    def ingest_files(self, paths: list[str], target_id: str | None = None):
        """Ingest files into the library."""
        from pathlib import Path
        from fichero.ingest import ingest_file, ingest_folder, IngestMode

        for p in paths:
            path = Path(p)
            try:
                if path.is_dir():
                    ingest_folder(path, mode=IngestMode.LINK, parent_id=target_id)
                else:
                    ingest_file(path, mode=IngestMode.LINK, parent_id=target_id)
            except Exception as e:
                logger.error(f"Ingest failed: {path}: {e}")

        self.reload_sidebar()

    # =========================================================================
    # Public API
    # =========================================================================

    @property
    def native(self):
        """The NSWindow."""
        return self._window

    def show(self):
        """Show window and set up menu/toolbar."""
        self._window.makeKeyAndOrderFront_(None)
        self._setup_menu_toolbar()
        self.reload_sidebar()

    def toggle_pane(self, name: str):
        """Toggle pane visibility (animated)."""
        if name in self._panes:
            item = self._panes[name]
            item.animator().collapsed = not item.isCollapsed

    def is_pane_visible(self, name: str) -> bool:
        """Check if pane is visible."""
        if name in self._panes:
            return not self._panes[name].isCollapsed
        return False

    def reload_sidebar(self):
        """Reload sidebar from database."""
        self.sidebar.reload()

    def reload_browser(self):
        """Reload browser from current selection."""
        if self._selected_collection:
            from fichero.models import Document
            from fichero.db import db
            self.browser.items = list(db.query(Document, parent_id=self._selected_collection.id))

    def _setup_menu_toolbar(self):
        """Attach menu and toolbar."""
        try:
            from .menu import AppMenu
            from .toolbar import AppToolbar
            from .commands import Commands

            self._commands = Commands(self)
            self._menu = AppMenu(handler=self._commands)
            self._menu.build()

            # Wire toolbar with search callback
            self._toolbar = AppToolbar(
                handler=self._commands,
                on_search=self._on_toolbar_search,
            )
            self._toolbar.attach_to_window_native(self._window)
        except Exception as e:
            logger.error(f"Menu/toolbar setup failed: {e}")

    def _on_toolbar_search(self, query: str):
        """Handle search from toolbar search field.

        Searches the database and displays results in browser.
        Empty query returns to showing the current collection.
        """
        query = query.strip()

        # Empty or too short - show current collection
        if not query or len(query) < 2:
            logger.debug("Search cleared, showing current collection")
            self.reload_browser()
            return

        logger.info(f"Searching for: {query}")

        try:
            from fichero.db import db
            from fichero.models import Document

            # Search using vector similarity
            results = db.search(query, limit=50)

            if not results:
                logger.info("No search results found")
                self.browser.items = []
                return

            # Convert SearchResults to Documents
            docs = []
            for r in results:
                doc = db.get(Document, r.document_id)
                if doc:
                    docs.append(doc)

            logger.info(f"Found {len(docs)} documents for '{query}'")
            self.browser.items = docs

            # Switch to library view if not already there
            if self._current_mode != ViewMode.library:
                self.switch_view(ViewMode.library)

        except Exception as e:
            logger.error(f"Search failed: {e}")
