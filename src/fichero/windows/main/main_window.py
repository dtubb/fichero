"""
Refactored Main Window for Fichero

Simple event-driven main window that listens to NavigationController events.
Replaces the complex NavigationManager/PaneManager system with clean event handling.
"""

import toga
from toga.style import Pack
from toga.constants import ROW, COLUMN
import logging
from typing import Optional, Dict, Any
from pathlib import Path

from fichero.shared.navigation.navigation_event_bus import subscribe_to_navigation, NavigationEvents
from fichero.shared.navigation.navigation_controller import NavigationController
from fichero.windows.main.views.library.library_view import LibraryView
from fichero.windows.main.views.collection.collection_view import CollectionView
from fichero.windows.main.views.preview import PreviewView
from fichero.shared.bars.status_bar import StatusBar

logger = logging.getLogger(__name__)


class MainWindow:
    """Simple event-driven main window"""

    def __init__(self, app):
        """Initialize main window with event-driven navigation"""
        self.app = app
        self.is_mobile = app.is_mobile

        # Window
        self.window: Optional[toga.Window] = None

        # Simple view containers
        self.main_container: Optional[toga.Box] = None
        self.current_view: Optional = None
        self.current_view_key: Optional[str] = None

        # Track views in each pane for inspector window
        self.left_pane_view: Optional = None   # LibraryView
        self.center_pane_view: Optional = None # CollectionView
        self.right_pane_view: Optional = None  # PreviewView
        self.focused_pane: str = 'center'      # Which pane currently has focus

        # Desktop layout containers
        self.left_pane: Optional[toga.Box] = None
        self.center_pane: Optional[toga.Box] = None
        self.right_pane: Optional[toga.Box] = None
        self.content_area: Optional[toga.Box] = None  # Container for center+right+status bar

        # Mobile layout container
        self.mobile_container: Optional[toga.Box] = None

        # Status bar (shown at bottom of window)
        self.status_bar: Optional[StatusBar] = None
        self.status_bar_visible: bool = True  # Visible by default

        # Cached views to maintain state
        self.cached_library_view: Optional[LibraryView] = None
        self.cached_output_view: Optional[PreviewView] = None
        self.cached_collection_view: Optional[CollectionView] = None  # Cache single reusable instance

        # DEPRECATED: Pane visibility state - now handled by layout_manager.toggle_column()
        # Kept for compatibility with any remaining legacy code
        self.pane_visibility = {
            'library': True,     # Now controlled by layout_manager column "Library"
            'collection': True,  # Now controlled by layout_manager column "Collection"
            'output': True,      # Preview column (always visible)
            'inspector': False   # Now controlled by layout_manager column "Adjust"
        }

        # DEPRECATED: Pane pixel widths - now handled by layout_manager add_columns_fixed()
        # Widths are now set in _create_desktop_layout() method
        self.pane_widths = {
            'library': 150,
            'collection': 150,
            'inspector': 350
        }

        # Get NavigationController from app
        self.navigation_controller = self._get_navigation_controller()

        # Get SelectionManager from app
        self.selection_manager = getattr(self.app, 'selection_manager', None)
        if not self.selection_manager:
            logger.warning("SelectionManager not available in app")
        else:
            logger.debug("SelectionManager reference stored in main window")

        # Create views dict to store all column views
        # (Note: NavigationController doesn't have a views dict - we create our own)
        self.views = {}

        # Create window and layout
        self._create_window()
        self._create_layout()

        # Subscribe to navigation events
        self._subscribe_to_events()

        # Pre-create PreviewView to register its Edit menu commands at startup
        # (Even though the view won't be shown until needed, its commands need to be available)
        self._precreate_output_view()

        # Pre-create CollectionView on desktop to register its commands (import, process, etc.)
        # On desktop, all command menus should be available even before opening a collection
        if not self.is_mobile:
            self._precreate_collection_view()

        # Register View menu commands for pane visibility toggles (desktop only)
        if not self.is_mobile:
            self._register_view_commands()

        # Register toolbar menus (desktop macOS only)
        if not self.is_mobile:
            self._register_toolbar_menus()
            # Don't initialize toolbar here - it will be built by build_native_toolbar()
            # after commands are registered and app.main_window is set

        # Set up initial view
        self._show_initial_view()

        # Restore window state from saved preferences (async task)
        # This restores window size, column visibility, and preview pane layouts
        import asyncio
        asyncio.create_task(self.restore_window_state())

        logger.info("Refactored main window initialized successfully")

    def _get_navigation_controller(self) -> Optional[NavigationController]:
        """Get NavigationController from app"""
        try:
            if hasattr(self.app, 'view_integration') and self.app.view_integration:
                return self.app.view_integration.get_navigation_controller()
            else:
                logger.warning("No view_integration found in app")
                return None
        except Exception as e:
            logger.error(f"Failed to get NavigationController: {e}")
            return None

    def _create_window(self):
        """Create the main window"""
        try:
            self.window = toga.MainWindow(
                title=self.app.formal_name,  # Set window title
                size=self._get_window_size()
            )

            if not self.is_mobile:
                self.window.min_size = (1000, 600)

            logger.debug("Main window created")

        except Exception as e:
            logger.error(f"Failed to create main window: {e}")

    def _get_window_size(self) -> tuple:
        """Get appropriate window size for platform"""
        if self.is_mobile:
            return (375, 667)  # iPhone dimensions
        else:
            return (1200, 800)  # Desktop dimensions

    def _create_layout(self):
        """Create layout containers"""
        try:
            if self.is_mobile:
                self._create_mobile_layout()
            else:
                self._create_desktop_layout()

            # Set window content
            if self.window and self.main_container:
                self.window.content = self.main_container
                logger.debug("Window content set")

        except Exception as e:
            logger.error(f"Failed to create layout: {e}")

    def _create_mobile_layout(self):
        """Create mobile single-pane layout"""
        try:
            self.mobile_container = toga.Box(
                style=Pack(
                    direction=COLUMN,
                    flex=1,
                    background_color="#FFFFFF"
                )
            )

            self.main_container = toga.Box(
                style=Pack(
                    direction=COLUMN,
                    flex=1,
                    background_color="#FFFFFF"
                )
            )

            self.main_container.add(self.mobile_container)
            logger.debug("Mobile layout created")

        except Exception as e:
            logger.error(f"Failed to create mobile layout: {e}")

    def _create_desktop_layout(self):
        """Create desktop three-pane layout using SplitContainers (Phase 3.2)"""
        try:
            # PHASE 3.2: Use SplitContainer-based UniversalLayoutManager with actual views
            if self.navigation_controller and self.navigation_controller.layout_manager:
                layout_manager = self.navigation_controller.layout_manager

                # Import new views for Steps and Adjust columns
                from fichero.windows.main.views.steps import StepBrowserView
                from fichero.windows.main.views.adjust import AdjustView

                # Create actual views for 5-column layout
                # Column 1: Library (create if doesn't exist)
                if 'library' not in self.views:
                    library_view = self._get_or_create_library_view()
                    self.views['library'] = library_view
                else:
                    library_view = self.views['library']

                # Column 2: Collection (create if doesn't exist)
                if 'collection' not in self.views:
                    collection_view = self._get_or_create_collection_view("", "")
                    self.views['collection'] = collection_view
                else:
                    collection_view = self.views['collection']

                # Column 4: Preview/Output (create if doesn't exist)
                if 'output' not in self.views:
                    library_manager = getattr(self.app, 'library_manager', None)
                    preview_view = PreviewView(self.app, self.is_mobile, library_manager=library_manager)
                    self.views['output'] = preview_view
                else:
                    preview_view = self.views['output']

                # Column 3: Steps (NEW - extracted from PreviewView)
                library_manager = getattr(self.app, 'library_manager', None)
                steps_view = StepBrowserView(
                    self.app,
                    is_mobile=False,
                    library_manager=library_manager
                )
                self.views['steps'] = steps_view

                # Wire up StepBrowserView to PreviewView (bidirectional)
                # When a step is selected in Column 3, update the preview in Column 4
                if hasattr(preview_view, 'step_manager'):
                    # Create callback that updates the preview when step is selected
                    def on_step_selected(index):
                        """Update preview when step is selected in steps list"""
                        if hasattr(preview_view, 'step_manager') and preview_view.step_manager:
                            preview_view.step_manager.set_current_step(index)
                            logger.info(f"Step selection updated preview to index {index}")

                    steps_view.set_on_step_selected(on_step_selected)
                    logger.info("✅ StepBrowserView wired up to PreviewView step_manager")

                # Wire up PreviewView to StepBrowserView (reverse direction)
                # When PreviewView loads steps, update the StepBrowserView
                if hasattr(preview_view, 'set_step_browser_view'):
                    preview_view.set_step_browser_view(steps_view)
                    logger.info("✅ PreviewView wired up to StepBrowserView for step loading")
                else:
                    logger.warning("⚠️ PreviewView does not have set_step_browser_view method")

                # Column 5: Adjust (NEW - extracted from PreviewView)
                adjust_view = AdjustView(
                    self.app,
                    is_mobile=False
                )
                self.views['adjust'] = adjust_view

                # Wire up AdjustView to PreviewView
                # Pass the preview_view reference so AdjustView can call its image manipulation methods
                if hasattr(adjust_view, 'set_preview_view'):
                    adjust_view.set_preview_view(preview_view)
                    logger.info("✅ AdjustView wired up to PreviewView")

                # Wire up PreviewView Edit button to toggle Adjust pane
                # The Edit button will now show/hide the Adjust column instead of the old inspector
                if hasattr(preview_view, 'set_adjust_toggle_callback'):
                    preview_view.set_adjust_toggle_callback(self._toggle_inspector_pane)
                    logger.info("✅ PreviewView Edit button wired to toggle Adjust pane")

                # Create a combined container for Collection + Steps (stacked vertically)
                # Use a simple Box instead of SplitContainer to avoid toggle complexity
                # 75%/25% split: Collection gets flex=3, Steps gets flex=1
                import toga
                from toga.style import Pack

                # Set flex values for 75%/25% vertical split
                collection_view.container.style.flex = 3  # 75%
                steps_view.container.style.flex = 1       # 25%

                collection_and_steps_box = toga.Box(style=Pack(direction='column', flex=1))
                collection_and_steps_box.add(collection_view.container)
                collection_and_steps_box.add(steps_view.container)

                # Create wrapper view for the combined box
                class CombinedView:
                    def __init__(self, container):
                        self.container = container
                combined_view = CombinedView(collection_and_steps_box)

                # Create 4-column layout with fixed sidebars and flexible preview
                # Columns: Library (140px fixed) | Collection+Steps (200px fixed) | Preview (flexible) | Adjust (200px fixed)
                views = [
                    library_view,
                    combined_view,  # Collection + Steps in one column
                    preview_view,
                    adjust_view
                ]
                # Fixed widths for sidebars, None for flexible preview
                # Library: 180px (native sidebar - narrow with text truncation)
                # Collection/Adjust: 200px (same width, narrower than before)
                widths = [180, 200, None, 200]

                # Column names for menu commands (show/hide)
                column_names = ["Library", "Collection", "Preview", "Adjust"]

                # Mark all columns as collapsible for Finder-style flexibility
                # Only Collection is required (can close everything else for Finder-style window)
                collapsible = [True, True, True, True]

                # Minimum widths for auto-collapse behavior
                # Preview needs 800px minimum before sidebars start hiding
                min_widths = [180, 200, 800, 200]

                logger.info(f"Creating 4-column layout with collapsible sidebars")
                logger.info(f"  - Library: 180px fixed, collapsible (native macOS sidebar)")
                logger.info(f"  - Collection: 200px fixed, collapsible")
                logger.info(f"  - Preview: flexible (min 800px), NOT collapsible")
                logger.info(f"  - Adjust: 200px fixed, collapsible")

                slot_ids = layout_manager.add_columns_fixed(
                    views,
                    widths=widths,
                    column_names=column_names,
                    collapsible=collapsible,
                    min_widths=min_widths
                )

                # Store slot IDs - Collection column contains both Collection and Steps
                self.library_slot_id = slot_ids[0]
                self.collection_slot_id = slot_ids[1]  # Contains both Collection + Steps
                self.preview_slot_id = slot_ids[2]
                self.adjust_slot_id = slot_ids[3]

                # Steps is in the Collection column, sharing the same slot
                self.steps_slot_id = self.collection_slot_id

                # Wire up focus system: Set on_click callbacks on views and slots
                # The combined view acts as one focusable unit
                all_views_and_slots = [
                    (self.library_slot_id, library_view),
                    (self.collection_slot_id, collection_view),  # Collection view gets focus for the combined column
                    (self.preview_slot_id, preview_view),
                    (self.adjust_slot_id, adjust_view)
                ]

                for i, (slot_id, view) in enumerate(all_views_and_slots):
                    # Create a closure to capture the slot_id
                    def make_focus_handler(sid):
                        def handler():
                            layout_manager.focus_slot(sid)
                            logger.debug(f"Slot focused: {sid}")
                        return handler

                    focus_handler = make_focus_handler(slot_id)

                    # Set callback on view if it supports it
                    if hasattr(view, 'on_click'):
                        view.on_click = focus_handler
                        logger.debug(f"Set on_click handler on view {i}")

                    # Set callback on slot
                    slot = layout_manager.view_slots.get(slot_id)
                    if slot:
                        slot.on_click = focus_handler
                        logger.debug(f"Set on_click handler on slot {i}")

                # Set library view as initially focused
                layout_manager.focus_slot(self.library_slot_id)
                logger.info(f"Library view set as initially focused: {self.library_slot_id}")

                # Store pane references (actual view containers)
                self.library_pane = library_view.container
                self.collection_pane = collection_view.container
                self.steps_pane = steps_view.container
                self.preview_pane = preview_view.container
                self.adjust_pane = adjust_view.container

                # Backward compatibility aliases
                self.left_pane = self.library_pane
                self.center_pane = self.collection_pane
                self.right_pane = self.preview_pane

                # Create StatusBar (empty by default - no "Ready" text)
                self.status_bar = StatusBar(platform='desktop')

                # Wrap layout container + status bar in a Box
                # Height is 100% minus status bar
                self.content_area = toga.Box(
                    style=Pack(direction=COLUMN, flex=1)
                )
                self.content_area.add(layout_manager.container)
                if self.status_bar_visible:
                    self.content_area.add(self.status_bar.container)

                # Set main container
                self.main_container = self.content_area

                logger.info(f"✅ Desktop layout created: 4-column layout with vertical split (Library | Collection+Steps | Preview | Adjust), widths=[270px, 250px, flex, 250px], Collection:Steps=70:30")
            else:
                # No layout manager available - this shouldn't happen
                logger.error("❌ NavigationController layout_manager not available! Cannot create desktop layout.")
                raise RuntimeError("UniversalLayoutManager is required for desktop layout")

        except Exception as e:
            logger.error(f"❌ Failed to create desktop layout: {e}")
            import traceback
            logger.error(traceback.format_exc())
            raise  # Don't silently fail - we need the layout manager

    def _subscribe_to_events(self):
        """Subscribe to navigation events"""
        try:
            subscribe_to_navigation(NavigationEvents.SHOW_LIBRARY, self._on_show_library)
            subscribe_to_navigation(NavigationEvents.SHOW_COLLECTION, self._on_show_collection)
            subscribe_to_navigation(NavigationEvents.SHOW_PREVIEW, self._on_show_preview)
            subscribe_to_navigation(NavigationEvents.SHOW_MODAL, self._on_show_modal)
            subscribe_to_navigation(NavigationEvents.NAVIGATION_ERROR, self._on_navigation_error)

            # Phase 2: Subscribe to selection changes for status bar updates
            if self.status_bar:
                subscribe_to_navigation(NavigationEvents.SELECTION_CHANGED, self._handle_selection_changed)
                logger.debug("Status bar subscribed to selection events")

            # Phase 1: Subscribe to selection changes for preview updates
            subscribe_to_navigation(NavigationEvents.SELECTION_CHANGED, self._handle_preview_selection_changed)
            logger.debug("Preview pane subscribed to selection events")

            logger.debug("Subscribed to navigation events")

        except Exception as e:
            logger.error(f"Failed to subscribe to navigation events: {e}")

    def _precreate_output_view(self):
        """
        Pre-create PreviewView at startup to register its Edit menu commands.
        The view won't be shown yet, but its commands need to be available in menus.
        """
        try:
            if self.cached_output_view is None:
                logger.debug("Pre-creating PreviewView to register Edit menu commands")
                # Pass library_manager for file-specific filtering
                library_manager = getattr(self.app, 'library_manager', None)
                self.cached_output_view = PreviewView(self.app, self.is_mobile, library_manager=library_manager)

                # PHASE 5: Pass status bar to layout manager for pane selection updates
                if hasattr(self.cached_output_view, 'layout_manager') and self.status_bar:
                    self.cached_output_view.layout_manager.status_bar = self.status_bar
                    logger.debug("✅ Status bar linked to PreviewView layout manager")

                logger.info("✅ PreviewView pre-created - Edit menu commands registered")
        except Exception as e:
            logger.error(f"Failed to pre-create PreviewView: {e}")

    def _precreate_collection_view(self):
        """
        Pre-create CollectionView at startup to register its commands (desktop only).
        This ensures import/process commands are available in menus from app launch.
        """
        try:
            if self.cached_collection_view is None:
                logger.debug("Pre-creating CollectionView to register collection commands")
                # Create with empty collection - will be populated when user selects a collection
                self.cached_collection_view = CollectionView(self.app, "", self.is_mobile, collection_id=None)
                self.cached_collection_view.register_preview_callback(self._on_file_preview_requested)
                logger.info("✅ CollectionView pre-created - Import/Process commands registered")

                # Update native toolbar so collection commands appear at startup
                # (Note: This updates the toolbar even though library view is shown)
                # On Mac, all commands from all views should be accessible at all times
                self._update_toolbar_for_collection_view(context='normal')
                logger.info("✅ Native toolbar updated with collection commands at startup")
        except Exception as e:
            logger.error(f"Failed to pre-create CollectionView: {e}")

    def _register_toolbar_menus(self):
        """Register toolbar dropdown menus (desktop macOS only)"""
        try:
            from fichero.shared.commands.toolbar_menu_manager import ToolbarMenuManager
            from fichero.windows.main.toolbar_menus import register_toolbar_menus

            # Get or create ToolbarMenuManager
            toolbar_menu_manager = ToolbarMenuManager.get_instance(self.app)

            # Register all toolbar menus
            register_toolbar_menus(toolbar_menu_manager)

            logger.info("✅ Toolbar menus registered")

        except Exception as e:
            logger.error(f"Failed to register toolbar menus: {e}")
            import traceback
            logger.error(traceback.format_exc())

    def _initialize_empty_toolbar(self):
        """Initialize empty NSToolbar (items will be added as commands are registered)"""
        try:
            from fichero.shared.commands import CommandManager

            command_manager = CommandManager.get_instance(self.app)

            # Check if MacToolbarManager is available
            if not command_manager._mac_toolbar_available:
                logger.debug("MacToolbarManager not available, skipping toolbar initialization")
                return

            # Get or create MacToolbarManager for this window
            window_id = id(self.window)
            if window_id not in command_manager.mac_toolbar_managers:
                from fichero.shared.commands.mac_toolbar_manager import MacToolbarManager
                manager = MacToolbarManager(self.app, self.window)
                command_manager.mac_toolbar_managers[window_id] = manager
                logger.debug(f"Created MacToolbarManager for window: {self.window.title}")
            else:
                manager = command_manager.mac_toolbar_managers[window_id]

            # Initialize empty toolbar (items will be added dynamically as commands are registered)
            manager.initialize_empty_toolbar(toolbar_id="fichero.main.toolbar")

            logger.info("✅ Empty NSToolbar initialized (items will be added as commands are registered)")

        except Exception as e:
            logger.error(f"Failed to initialize empty toolbar: {e}")
            import traceback
            logger.error(traceback.format_exc())

    def _register_view_commands(self):
        """Register View menu commands for pane visibility toggles (desktop only)"""
        try:
            from fichero.shared.commands import CommandManager, FicheroCommand
            from gettext import gettext as _

            command_manager = CommandManager.get_instance(self.app)

            # Define View menu commands
            # Section 0: Pane visibility toggles at the TOP of the View menu
            # Section 10: Zoom commands (creates divider below pane toggles)
            # Section 20: Toolbar toggles (creates another divider below zoom)
            # Using Preview-style shortcuts: Cmd+Option+1,2,3,4,5 for panes
            # Order: Library, Collection, Step, Preview (output), Adjust
            # Note: macOS alphabetizes within sections, so we put each in separate sections to force order
            view_commands = {
                # Library/Sidebar toggle button (NSToolbar item, positioned left of centered item)
                'view.toggle_sidebar': FicheroCommand(
                    id='view.toggle_sidebar',
                    label=_("Library"),
                    action=self._toggle_library_pane,
                    icon="resources/icons/toolbar/sidebar.left@10x.png",
                    toolbar_icon="resources/icons/toolbar/sidebar.left@10x.png",
                    description=_("Show/hide Library sidebar"),
                    show_in_menu=False,
                    show_in_top_toolbar=True,
                    show_in_titlebar=False,
                    desktop_only=True,
                    context='normal',
                    visibility_priority=1000,
                    tooltip=_("Show/hide Library sidebar"),
                    navigational=True
                ),
                'view.toggle_collection': FicheroCommand(
                    id='view.toggle_collection',
                    label=_("Collection"),
                    action=self._toggle_collection_pane,
                    icon="resources/icons/toolbar/list.bullet.rectangle@10x.png",
                    toolbar_icon=None,  # Use PNG icon instead of SF Symbol
                    shortcut=toga.Key.MOD_1 + toga.Key.MOD_2 + '2',
                    description=_("Show/hide Collection pane"),
                    group=toga.Group.VIEW,
                    section=0,
                    order=1,
                    show_in_menu=True,
                    show_in_top_toolbar=True,
                    show_in_titlebar=False,
                    desktop_only=True,
                    context='normal',
                    visibility_priority=600,
                    tooltip=_("Show/hide Collection pane")
                ),
                # Adjust toggle button (toolbar button)
                'view.toggle_inspector': FicheroCommand(
                    id='view.toggle_inspector',
                    label=_("Adjust"),  # Removed "3" prefix (not needed in toolbar)
                    action=self._toggle_inspector_pane,
                    icon="resources/icons/toolbar/sidebar.right@10x.png",  # PNG icon for right sidebar
                    toolbar_icon="resources/icons/toolbar/sidebar.right@10x.png",  # PNG icon
                    shortcut=toga.Key.MOD_1 + toga.Key.MOD_2 + '3',
                    description=_("Show/hide Adjust pane"),
                    group=toga.Group.VIEW,
                    section=0,
                    order=3,
                    show_in_menu=True,
                    show_in_top_toolbar=True,  # Add to native toolbar
                    show_in_titlebar=False,  # Remove from titlebar accessories
                    desktop_only=True,
                    context='normal',  # Required for toolbar filtering
                    visibility_priority=900,  # Very high priority - Phase 2 (stays visible)
                    tooltip=_("Show/hide Adjust pane")  # Tooltip for toolbar button
                ),
                # Library toggle (menu only, no toolbar button - covered by sidebar button)
                'view.toggle_library': FicheroCommand(
                    id='view.toggle_library',
                    label=_("1 Library"),
                    action=self._toggle_library_pane,
                    shortcut=toga.Key.MOD_1 + toga.Key.MOD_2 + '1',
                    description=_("Show/hide Library pane"),
                    group=toga.Group.VIEW,
                    section=0,
                    order=0,
                    show_in_menu=True,
                    show_in_titlebar=False,  # Not in titlebar (sidebar button handles it)
                    desktop_only=True
                ),
                'view.toggle_markup_toolbar': FicheroCommand(
                    id='view.toggle_markup_toolbar',
                    label=_("Show Markup Toolbar"),
                    action=self._toggle_markup_toolbar,
                    shortcut=toga.Key.MOD_1 + toga.Key.SHIFT + 't',
                    description=_("Show/hide markup toolbar in Preview pane"),
                    group=toga.Group.VIEW,
                    section=20,
                    order=0,
                    show_in_menu=True,
                    desktop_only=True
                ),
                'view.toggle_path_bar': FicheroCommand(
                    id='view.toggle_path_bar',
                    label=_("Show Path Bar"),
                    action=self._toggle_path_bar,
                    shortcut=toga.Key.MOD_1 + toga.Key.MOD_2 + 'p',
                    description=_("Show/hide path bar in Preview pane"),
                    group=toga.Group.VIEW,
                    section=20,
                    order=1,
                    show_in_menu=True,
                    desktop_only=True
                ),
                'view.toggle_status_bar': FicheroCommand(
                    id='view.toggle_status_bar',
                    label=_("Show Status Bar"),
                    action=self._toggle_status_bar,
                    shortcut=toga.Key.MOD_1 + toga.Key.SLASH,
                    description=_("Show/hide status bar at bottom of window"),
                    group=toga.Group.VIEW,
                    section=20,
                    order=2,
                    show_in_menu=True,
                    desktop_only=True
                ),
            }

            # Register all View commands
            for command_id, command in view_commands.items():
                command_manager.register_command(command)
                logger.debug(f"Registered View command: {command_id}")

            logger.info("✅ View menu commands registered (5 pane toggles + 3 toolbar toggles)")

        except Exception as e:
            logger.error(f"Failed to register View commands: {e}")

    def _show_initial_view(self):
        """Show the initial library view"""
        try:
            # Get or create library view (will cache for later reuse)
            library_view = self._get_or_create_library_view()

            # Update native toolbar on desktop (LibraryView shows Add File/Folder/URL commands)
            if not self.is_mobile:
                self._update_toolbar_for_library_view(context='normal')

            # Show in appropriate pane
            if self.is_mobile:
                self._show_view_mobile("library", library_view)
            else:
                self._show_view_desktop("library", library_view, "left")

            logger.info("Initial library view displayed")

        except Exception as e:
            logger.error(f"Failed to show initial view: {e}")

    def _get_or_create_library_view(self) -> LibraryView:
        """Get cached library view or create new one if needed"""
        try:
            if self.cached_library_view is None:
                logger.debug("Creating new LibraryView instance")
                self.cached_library_view = LibraryView(self.app, self.is_mobile)
                self.cached_library_view.register_collection_callback(self._on_collection_selected)
            else:
                logger.debug("Reusing cached LibraryView instance")
                # Note: Do NOT call show() here - it causes recursion!
                # _show_desktop_view() will call show() after this returns

            return self.cached_library_view
        except Exception as e:
            logger.error(f"Failed to get or create library view: {e}")
            # Fallback: create new instance and cache it to prevent duplicate subscriptions
            self.cached_library_view = LibraryView(self.app, self.is_mobile)
            self.cached_library_view.register_collection_callback(self._on_collection_selected)
            return self.cached_library_view

    def _get_or_create_collection_view(self, collection_id: str, collection_name: str) -> CollectionView:
        """
        Get cached CollectionView or create once.
        Simple approach: ONE view, NavigationController events update its data.
        """
        try:
            if self.cached_collection_view is None:
                logger.debug(f"Creating CollectionView instance")
                collection_view = CollectionView(self.app, "", self.is_mobile, collection_id=None)
                collection_view.register_preview_callback(self._on_file_preview_requested)
                self.cached_collection_view = collection_view
                logger.info("✅ CollectionView created and cached")

            # Don't update here - let NavigationController event handler update it
            # This prevents double-loading and keeps state management centralized
            logger.debug(f"Returning cached CollectionView (will be updated by navigation event)")

            return self.cached_collection_view

        except Exception as e:
            logger.error(f"Failed to get/create collection view: {e}")
            # Fallback: create new instance
            collection_view = CollectionView(self.app, collection_name, self.is_mobile, collection_id=collection_id)
            collection_view.register_preview_callback(self._on_file_preview_requested)
            return collection_view

    # ===== TOOLBAR MANAGEMENT =====

    def _update_toolbar_for_library_view(self, context: str = 'normal'):
        """Update native toolbar for LibraryView on desktop"""
        try:
            # Check if app.main_window is set yet
            # During initialization, this may be called before app.main_window exists
            # In that case, toolbar will be built later by explicit call from app.py
            try:
                _ = self.app.main_window
            except (AttributeError, ValueError):
                logger.debug("app.main_window not set yet, deferring toolbar build")
                return

            from fichero.shared.commands import CommandManager

            command_manager = CommandManager.get_instance(self.app)
            command_manager.build_native_toolbar(
                self.window,
                view_id='library',
                context=context
            )

            logger.debug(f"Updated native toolbar for LibraryView (context={context})")

        except Exception as e:
            logger.error(f"Failed to update toolbar for LibraryView: {e}")

    def _update_toolbar_for_collection_view(self, context: str = 'normal'):
        """Update native toolbar for CollectionView on desktop"""
        try:
            # Check if app.main_window is set yet
            try:
                _ = self.app.main_window
            except (AttributeError, ValueError):
                logger.debug("app.main_window not set yet, deferring toolbar build")
                return

            from fichero.shared.commands import CommandManager

            command_manager = CommandManager.get_instance(self.app)
            command_manager.build_native_toolbar(
                self.window,
                view_id='collection',
                context=context
            )

            logger.debug(f"Updated native toolbar for CollectionView (context={context})")

        except Exception as e:
            logger.error(f"Failed to update toolbar for CollectionView: {e}")

    def _update_toolbar_for_output_view(self, context: str = 'normal'):
        """Update native toolbar for PreviewView on desktop"""
        try:
            # Check if app.main_window is set yet
            try:
                _ = self.app.main_window
            except (AttributeError, ValueError):
                logger.debug("app.main_window not set yet, deferring toolbar build")
                return

            from fichero.shared.commands import CommandManager

            command_manager = CommandManager.get_instance(self.app)
            command_manager.build_native_toolbar(
                self.window,
                view_id='output',
                context=context
            )

            logger.debug(f"Updated native toolbar for PreviewView (context={context})")

        except Exception as e:
            logger.error(f"Failed to update toolbar for PreviewView: {e}")

    # ===== EVENT HANDLERS =====

    def _on_show_library(self, event):
        """Handle show library event"""
        try:
            logger.info(f"Event: Show library - {event}")

            # Clear output view when navigating to library (no file selected)
            if hasattr(self, 'cached_output_view') and self.cached_output_view:
                logger.info("📤 Clearing output view (navigating to library)")
                self.cached_output_view.load_output()

            # Get or create library view (reuses cached instance to maintain state)
            library_view = self._get_or_create_library_view()

            # Check if force refresh is requested (e.g., after collection rename)
            force_refresh = False
            if hasattr(event, 'data') and event.data:
                force_refresh = event.data.get('force_refresh', False)
            elif hasattr(event, 'get'):
                force_refresh = event.get('force_refresh', False)

            if force_refresh:
                logger.info("🔄 LIBRARY REFRESH: Force refresh requested - reloading collections")
                # Force reload collections from database before showing
                if hasattr(library_view, '_load_collections_async'):
                    import asyncio
                    asyncio.create_task(library_view._load_collections_async())

            # Update native toolbar on desktop (LibraryView shows Add File/Folder/URL commands)
            if not self.is_mobile:
                self._update_toolbar_for_library_view(context='normal')

            # Show in appropriate pane
            if self.is_mobile:
                self._show_view_mobile("library", library_view)
            else:
                self._show_view_desktop("library", library_view, "left")

                # If there are no collections, clear the center pane
                if hasattr(library_view, 'collections') and len(library_view.collections) == 0:
                    logger.info("📭 No collections - clearing center pane")
                    if hasattr(self, 'center_pane') and self.center_pane:
                        self.center_pane.clear()

        except Exception as e:
            logger.error(f"Failed to handle show library event: {e}")

    def _on_show_collection(self, event):
        """Handle show collection event with improved view lifecycle management"""
        try:
            data = event.data
            collection_id = data.get('collection_id')
            collection_name = data.get('collection_name', collection_id)

            logger.info(f"Event: Show collection {collection_name}")

            view_key = f"collection_{collection_id}"

            # Check if we already have the same collection view active
            current_view = self.current_view
            if (current_view and
                hasattr(current_view, 'collection_id') and
                current_view.collection_id == collection_id):
                # This is the same collection - refresh and ensure it's shown
                logger.info(f"Refreshing existing active collection view for {collection_name}")
                collection_view = current_view
            else:
                # Get or create collection view from cache
                collection_view = self._get_or_create_collection_view(collection_id, collection_name)

            # Note: Toolbar is already populated at startup (see _precreate_collection_view)
            # No need to update it again when showing a collection

            # Always show in appropriate pane (even if refreshing same view)
            # This ensures the view is visible after deselection cleared the center pane
            if self.is_mobile:
                self._show_view_mobile(view_key, collection_view)
            else:
                self._show_view_desktop(view_key, collection_view, "center")

            # NOTE: Do NOT call show() on desktop when using UniversalLayoutManager
            # The layout manager handles view lifecycle. Only call show() on mobile.
            # See line 1134-1138 for detailed explanation.
            if self.is_mobile and hasattr(collection_view, 'show'):
                collection_view.show()

            # Update status bar to show focused pane
            self._update_focused_pane_display('collection')

        except Exception as e:
            logger.error(f"Failed to handle show collection event: {e}")

    def _on_show_preview(self, event):
        """Handle show preview event - now shows PreviewView with optional pre-filtered outputs"""
        try:
            data = event.data
            file_path = data.get('file_path')
            output_path = data.get('output_path')  # LEGACY: Optional Director output folder path
            output_data = data.get('output_data')  # NEW: Pre-filtered output data from LibraryManager
            item_id = data.get('item_id')  # Item ID for file-specific filtering
            file_metadata = data.get('file_metadata', {})
            collection_items = data.get('collection_items', [])
            item_index = data.get('item_index', 0)

            # Track last loaded item to prevent duplicates
            if not hasattr(self, '_last_preview_item_id'):
                self._last_preview_item_id = None

            # Skip if this item is already loaded
            current_item_id = item_id
            if current_item_id and current_item_id == self._last_preview_item_id:
                logger.debug(f"Item {current_item_id} already loaded in preview, skipping")
                return

            self._last_preview_item_id = current_item_id

            logger.info(f"Event: Show output for {file_path}")
            if output_data:
                logger.info(f"📊 With pre-filtered output data ({len(output_data.get('processing_steps', []))} steps)")
            elif output_path:
                logger.info(f"📊 With legacy output_path: {output_path}")

            # Create or reuse PreviewView
            if not self.cached_output_view:
                # Pass library_manager for file-specific filtering
                library_manager = getattr(self.app, 'library_manager', None)
                self.cached_output_view = PreviewView(self.app, self.is_mobile, library_manager=library_manager)
                logger.debug("Created new PreviewView")

            # Get collection items from current center view if not provided
            if not collection_items:
                # The center view is stored in self.current_view (from _show_view_desktop)
                center_view = self.current_view if hasattr(self, 'current_view') else None
                logger.info(f"📋 Getting collection items from center view: {center_view}")
                if center_view and hasattr(center_view, 'collection_items'):
                    collection_items = center_view.collection_items
                    logger.info(f"📋 Found {len(collection_items)} items in collection_items")
                else:
                    logger.warning(f"📋 No collection_items found on center view")

            # Convert collection items to source file paths AND item IDs
            source_files = []
            source_item_ids = []  # NEW: Extract item IDs for library-based navigation
            source_index = 0

            if collection_items:
                for i, item in enumerate(collection_items):
                    item_file_path = item.get('file_path') or item.get('path')
                    item_id_str = item.get('id')  # Extract item ID

                    if item_file_path:
                        # Don't convert URLs to Path objects - they should stay as strings
                        if isinstance(item_file_path, str) and item_file_path.startswith(('http://', 'https://')):
                            source_files.append(item_file_path)  # Keep as string
                        else:
                            source_files.append(Path(item_file_path))  # Convert to Path

                        # Store item ID with None placeholder to maintain index alignment
                        # CRITICAL: source_item_ids must have same length as source_files!
                        source_item_ids.append(item_id_str if item_id_str else None)

                        # Track which index matches our current file
                        if str(item_file_path) == str(file_path):
                            source_index = i

                logger.info(f"📋 Extracted {len(source_files)} source files + {len(source_item_ids)} item IDs, current index={source_index}")

            # Determine what to load into PreviewView
            # Priority: output_data (pre-filtered) > output_path (legacy) > original file only

            # Don't convert URLs to Path objects - keep as strings
            if isinstance(file_path, str) and file_path.startswith(('http://', 'https://')):
                file_path_arg = file_path  # Keep URL as string
            else:
                file_path_arg = Path(file_path)  # Convert local path to Path object

            if output_data and output_data.get('has_outputs'):
                # NEW: Use pre-filtered output data from LibraryManager
                logger.info(f"📊 Loading from pre-filtered output data ({len(output_data['processing_steps'])} steps)")

                self.cached_output_view.load_output(
                    file_path=file_path_arg,
                    source_files=source_files,
                    source_index=source_index,
                    item_id=item_id,  # Pass item_id for file-specific filtering
                    source_item_ids=source_item_ids  # Pass item IDs for library-based navigation
                )
            else:
                # Load original file (no processing outputs)
                logger.info(f"📊 Loading original file only (no processing outputs)")

                self.cached_output_view.load_output(
                    file_path=file_path_arg,
                    source_files=source_files,
                    source_index=source_index,
                    item_id=item_id,  # Pass item_id for file-specific filtering
                    source_item_ids=source_item_ids  # NEW: Pass item IDs for library-based navigation
                )

            # Update native toolbar on desktop (PreviewView has persistent toolbar with editing commands)
            if not self.is_mobile:
                self._update_toolbar_for_output_view(context='normal')

            # Show in appropriate pane
            if self.is_mobile:
                self._show_view_mobile("output", self.cached_output_view)
            else:
                self._show_view_desktop("output", self.cached_output_view, "right")

                # CRITICAL: Actually show the preview pane using layout manager
                if (hasattr(self, 'preview_slot_id') and
                    hasattr(self, 'navigation_controller') and
                    self.navigation_controller and
                    hasattr(self.navigation_controller, 'layout_manager') and
                    self.navigation_controller.layout_manager):
                    self.navigation_controller.layout_manager.show_slot(self.preview_slot_id)
                    logger.info(f"✅ Preview pane shown via layout manager (slot: {self.preview_slot_id})")

            # Update status bar to show focused pane
            self._update_focused_pane_display('output')

        except Exception as e:
            logger.error(f"Failed to handle show preview event: {e}")

    def _on_show_modal(self, event):
        """Handle show modal event - now handles desktop window creation directly"""
        try:
            data = event.data
            modal_type = data.get('modal_type')
            context = data.get('context')
            view = data.get('view')

            logger.info(f"Event: Show modal {modal_type}")

            if not view:
                logger.error(f"No view provided for modal {modal_type}")
                return

            # For desktop (non-mobile), create a standalone window (not modal)
            # Only rename/delete dialogs should be truly modal
            if not self.is_mobile:
                window_size = self._get_modal_size(modal_type)
                is_dialog = modal_type in ['collection', 'rename', 'delete']

                standalone_window = toga.Window(
                    title=self._get_modal_title(modal_type),
                    size=window_size,
                    minimizable=not is_dialog,  # Dialogs can't minimize
                    resizable=not is_dialog,    # Dialogs can't resize
                    closable=True
                )

                # Set the view content in the window
                container = view.get_container() if hasattr(view, 'get_container') else view

                # For standalone windows, temporarily remove toolbars (they have window chrome)
                removed_top = None
                removed_bottom = None
                if hasattr(view, 'container') and view.container:
                    if hasattr(view, 'top_toolbar_container') and view.top_toolbar_container:
                        try:
                            view.container.remove(view.top_toolbar_container)
                            removed_top = view.top_toolbar_container
                            logger.debug(f"Removed top toolbar for standalone window {modal_type}")
                        except Exception as e:
                            logger.debug(f"Could not remove top toolbar: {e}")

                    if hasattr(view, 'bottom_toolbar_container') and view.bottom_toolbar_container:
                        try:
                            view.container.remove(view.bottom_toolbar_container)
                            removed_bottom = view.bottom_toolbar_container
                            logger.debug(f"Removed bottom toolbar for standalone window {modal_type}")
                        except Exception as e:
                            logger.debug(f"Could not remove bottom toolbar: {e}")

                standalone_window.content = container

                # Store removed toolbars on the view for potential restoration
                if removed_top or removed_bottom:
                    view._desktop_removed_toolbars = {
                        'top': removed_top,
                        'bottom': removed_bottom
                    }

                # Set the window reference on the view for closing
                if hasattr(view, 'set_modal_window'):
                    view.set_modal_window(standalone_window)

                # Show the window (non-blocking for standalone windows, blocking for dialogs)
                standalone_window.show()

                window_type = "dialog" if is_dialog else "standalone window"
                logger.info(f"{modal_type} shown as {window_type} on desktop")
            else:
                # Mobile is handled by NavigationController's _show_modal_overlay
                logger.info(f"Modal {modal_type} handled by NavigationController overlay")

        except Exception as e:
            logger.error(f"Failed to handle show modal event: {e}")

    def _get_modal_title(self, modal_type: str) -> str:
        """Get user-friendly title for modal windows with translation support"""
        # Use the globally installed _() function from gettext.install()
        try:
            title_map = {
                'settings': _('preferences_title'),
                'activity_monitor': _('activity_monitor_title'),
                'processing': _('document_processing'),
                'plans': _('menu_plans'),
                'prompts': _('menu_prompts'),
                'about': _('about_window_title'),
                'url': _('Add URL'),
                'website': _('Add Website'),
                'file': _('Add File'),
                'folder': _('Add Folder'),
                'camera': _('Add Picture'),
                'collection': _('Rename')
            }
            return title_map.get(modal_type, modal_type.title())
        except NameError:
            # Fallback if _ is not defined
            logger.warning("Translation function _ not available, using English fallbacks")
            fallback_map = {
                'settings': 'Settings',
                'activity_monitor': 'Activity Monitor',
                'processing': 'Processing',
                'plans': 'Plans',
                'prompts': 'Prompts',
                'about': 'About Fichero',
                'url': 'Add URL',
                'website': 'Add Website',
                'file': 'Add File',
                'folder': 'Add Folder',
                'camera': 'Add Picture',
                'collection': 'Rename'
            }
            return fallback_map.get(modal_type, modal_type.title())

    def _get_modal_size(self, modal_type: str) -> tuple:
        """Get appropriate size for modal windows based on type"""
        size_map = {
            'settings': (700, 600),
            'activity_monitor': (800, 600),
            'processing': (700, 600),
            'plans': (700, 600),
            'prompts': (700, 600),
            'about': (300, 400),
            'url': (600, 500),
            'website': (800, 600),
            'file': (600, 500),
            'folder': (600, 500),
            'camera': (600, 500),
            'collection': (400, 200)  # Smaller for simple rename dialog
        }
        return size_map.get(modal_type, (700, 600))

    def _on_navigation_error(self, event):
        """Handle navigation error event"""
        try:
            data = event.data
            title = data.get('title', 'Navigation Error')
            message = data.get('message', 'Unknown error')

            logger.error(f"Navigation error: {title} - {message}")

            # Could show error dialog here
            # For now, just log the error

        except Exception as e:
            logger.error(f"Failed to handle navigation error event: {e}")

    # ===== VIEW MANAGEMENT =====

    def _cleanup_current_view_callbacks(self):
        """Clean up NavigationController callbacks from the current view before replacing it"""
        try:
            if hasattr(self, 'current_view') and self.current_view:
                # Clean up view callbacks
                if hasattr(self.current_view, 'cleanup_callbacks'):
                    self.current_view.cleanup_callbacks()
                    logger.debug(f"Cleaned up callbacks for view: {getattr(self.current_view, '__class__', type(self.current_view)).__name__}")

                # Clean up toolbar callbacks in the view
                if hasattr(self.current_view, 'top_toolbar') and hasattr(self.current_view.top_toolbar, 'cleanup_callbacks'):
                    self.current_view.top_toolbar.cleanup_callbacks()
                    logger.debug("Cleaned up top toolbar callbacks")

                if hasattr(self.current_view, 'bottom_toolbar') and hasattr(self.current_view.bottom_toolbar, 'cleanup_callbacks'):
                    self.current_view.bottom_toolbar.cleanup_callbacks()
                    logger.debug("Cleaned up bottom toolbar callbacks")

        except Exception as e:
            logger.error(f"Failed to cleanup current view callbacks: {e}")

    def _cleanup_all_cached_views(self):
        """Clean up all cached views to prevent memory leaks and orphaned callbacks"""
        try:
            # Clean up cached library view
            if self.cached_library_view:
                try:
                    # Call cleanup method if it exists (P0-1 fix)
                    if hasattr(self.cached_library_view, 'cleanup'):
                        self.cached_library_view.cleanup()
                        logger.debug("Called LibraryView.cleanup()")

                    # Legacy cleanup methods (kept for backward compatibility)
                    if hasattr(self.cached_library_view, 'cleanup_callbacks'):
                        self.cached_library_view.cleanup_callbacks()

                    if hasattr(self.cached_library_view, 'top_toolbar') and hasattr(self.cached_library_view.top_toolbar, 'cleanup_callbacks'):
                        self.cached_library_view.top_toolbar.cleanup_callbacks()

                    if hasattr(self.cached_library_view, 'bottom_toolbar') and hasattr(self.cached_library_view.bottom_toolbar, 'cleanup_callbacks'):
                        self.cached_library_view.bottom_toolbar.cleanup_callbacks()

                    logger.debug("Cleaned up cached LibraryView")
                except Exception as e:
                    logger.error(f"Failed to cleanup cached library view: {e}")
                finally:
                    # Null out reference to allow garbage collection (P0-5 fix)
                    self.cached_library_view = None

            # Clean up cached collection view
            if self.cached_collection_view:
                try:
                    if hasattr(self.cached_collection_view, 'cleanup'):
                        self.cached_collection_view.cleanup()
                except Exception as e:
                    logger.error(f"Failed to cleanup cached collection view: {e}")
                finally:
                    self.cached_collection_view = None

            # Clean up cached output view
            if self.cached_output_view:
                try:
                    if hasattr(self.cached_output_view, 'cleanup'):
                        self.cached_output_view.cleanup()
                except Exception as e:
                    logger.error(f"Failed to cleanup cached output view: {e}")
                finally:
                    self.cached_output_view = None

            logger.debug("All cached views cleaned up")

        except Exception as e:
            logger.error(f"Failed to cleanup all cached views: {e}")

    def _show_view_mobile(self, view_key: str, view):
        """Show view in mobile layout"""
        try:
            if not self.mobile_container:
                logger.error("No mobile container available")
                return

            # Clean up callbacks from previous view to prevent duplicate events
            self._cleanup_current_view_callbacks()

            # Clear current view
            self.mobile_container.clear()

            # Add new view
            view_container = view.get_container() if hasattr(view, 'get_container') else view
            self.mobile_container.add(view_container)

            # Update tracking
            self.current_view = view
            self.current_view_key = view_key

            # Show the view
            if hasattr(view, 'show'):
                view.show()

            logger.debug(f"Mobile view '{view_key}' displayed")

        except Exception as e:
            logger.error(f"Failed to show mobile view {view_key}: {e}")

    def _show_view_desktop(self, view_key: str, view, pane: str):
        """Show view in desktop layout - updates tracking only when using UniversalLayoutManager

        IMPORTANT: When using UniversalLayoutManager, views are added once during _create_desktop_layout()
        and never removed. This method only updates tracking variables - NO pane manipulation.
        """
        try:
            # Check if UniversalLayoutManager is active
            using_layout_manager = (
                hasattr(self, 'navigation_controller') and
                self.navigation_controller and
                hasattr(self.navigation_controller, 'layout_manager') and
                self.navigation_controller.layout_manager
            )

            if not using_layout_manager:
                logger.error("UniversalLayoutManager not available - desktop layout requires it")
                return

            # Update tracking (for mobile fallback)
            if pane == "center":  # Track center pane as current view
                self.current_view = view
                self.current_view_key = view_key
                # Log current view with collection ID if applicable
                if hasattr(view, 'collection_id'):
                    logger.info(f"📍 Current view updated: CollectionView for collection_id={view.collection_id}")
                else:
                    logger.info(f"📍 Current view updated: {type(view).__name__}")

            # Track view in each pane for inspector window
            if pane == "left":
                self.left_pane_view = view
                self.focused_pane = 'left'
            elif pane == "center":
                self.center_pane_view = view
                self.focused_pane = 'center'
            elif pane in ("right", "preview"):
                self.right_pane_view = view
                self.focused_pane = 'right'
            elif pane == "steps":
                self.steps_pane_view = view if hasattr(self, 'steps_pane') else None
                self.focused_pane = 'steps'

            # NOTE: Do NOT call view.show() here when using UniversalLayoutManager
            # The layout manager handles view lifecycle management
            # Calling show() can cause recursion issues
            # if hasattr(view, 'show'):
            #     view.show()

            logger.debug(f"Desktop view '{view_key}' displayed in '{pane}' pane")

        except Exception as e:
            logger.error(f"Failed to show desktop view {view_key} in {pane}: {e}")

    # ===== VIEW VISIBILITY TOGGLES (Desktop only) =====

    def _update_toolbar_menu_checkmarks(self):
        """Update toolbar menu checkmarks after pane visibility changes"""
        try:
            from fichero.shared.commands.toolbar_menu_manager import ToolbarMenuManager
            toolbar_menu_manager = ToolbarMenuManager.get_instance(self.app)
            if toolbar_menu_manager:
                toolbar_menu_manager.update_menu_states()
        except Exception as e:
            logger.debug(f"Could not update toolbar menu checkmarks: {e}")

    def _toggle_library_pane(self, widget):
        """Toggle Library pane visibility"""
        if self.is_mobile:
            return

        try:
            if self.navigation_controller and self.navigation_controller.layout_manager:
                new_state = self.navigation_controller.layout_manager.toggle_column("Library")
                logger.info(f"📐 Toggle Library pane: {new_state}")
                self._update_toolbar_menu_checkmarks()
            else:
                logger.warning("Cannot toggle Library: layout_manager not available")
        except Exception as e:
            logger.error(f"Failed to toggle Library pane: {e}")

    def _toggle_collection_pane(self, widget):
        """Toggle Collection/Browser pane visibility"""
        if self.is_mobile:
            return

        try:
            if self.navigation_controller and self.navigation_controller.layout_manager:
                new_state = self.navigation_controller.layout_manager.toggle_column("Collection")
                logger.info(f"📐 Toggle Collection pane: {new_state}")
                self._update_toolbar_menu_checkmarks()
            else:
                logger.warning("Cannot toggle Collection: layout_manager not available")
        except Exception as e:
            logger.error(f"Failed to toggle Collection pane: {e}")

    def _toggle_output_pane(self, widget):
        """Toggle Output/Preview pane visibility

        Preview can now be hidden for Finder-style window (Collection only).
        When hiding Preview:
        - Adjust is also hidden
        - Collection must stay visible (cannot hide everything)
        - Window resizes to fit remaining columns
        """
        if self.is_mobile:
            return

        try:
            if self.navigation_controller and self.navigation_controller.layout_manager:
                lm = self.navigation_controller.layout_manager

                # Toggle Preview column
                new_state = lm.toggle_column("Preview")
                logger.info(f"📐 Toggle Preview pane: {new_state}")

                # If hiding Preview, also hide Adjust (but remember if it was already hidden)
                if not new_state:
                    logger.info("📐 Preview hidden, also hiding Adjust")
                    adjust_slot = lm._find_slot_by_name("Adjust")

                    # Remember if Adjust was already hidden before we hide Preview
                    # Store this in a window attribute so we can restore it later
                    if adjust_slot:
                        self._adjust_was_visible_before_preview_hide = adjust_slot.is_visible
                        logger.info(f"📐 Adjust was {'visible' if adjust_slot.is_visible else 'hidden'} before Preview hide")
                        lm.hide_column("Adjust")

                    # Ensure Collection stays visible (cannot have nothing)
                    collection_slot = lm._find_slot_by_name("Collection")
                    if collection_slot and not collection_slot.is_visible:
                        logger.info("📐 Showing Collection (cannot hide everything)")
                        lm.show_column("Collection")
                else:
                    # When showing Preview, restore Adjust to its previous state
                    # Only show it if it was visible before we hid Preview
                    if hasattr(self, '_adjust_was_visible_before_preview_hide') and self._adjust_was_visible_before_preview_hide:
                        logger.info("📐 Preview shown, restoring Adjust (was visible before)")
                        lm.show_column("Adjust")
                    else:
                        logger.info("📐 Preview shown, NOT showing Adjust (was hidden before or never set)")

                # Resize window to fit visible columns
                self._resize_window_to_content()
            else:
                logger.warning("Cannot toggle Preview: layout_manager not available")
        except Exception as e:
            logger.error(f"Failed to toggle Preview pane: {e}")

    def _toggle_inspector_pane(self, widget):
        """Toggle Inspector/Adjust pane visibility

        Note: If Preview is hidden, Adjust cannot be shown (it's auto-hidden with Preview).
        """
        if self.is_mobile:
            return

        try:
            if self.navigation_controller and self.navigation_controller.layout_manager:
                lm = self.navigation_controller.layout_manager

                # Check if Preview is visible
                preview_slot = lm._find_slot_by_name("Preview")
                if preview_slot and not preview_slot.is_visible:
                    logger.warning("📐 Cannot toggle Adjust: Preview is hidden (Adjust is auto-hidden with Preview)")
                    return

                # Toggle Adjust column
                new_state = lm.toggle_column("Adjust")
                logger.info(f"📐 Toggle Adjust pane: {new_state}")
                self._update_toolbar_menu_checkmarks()

                # Resize window to fit visible columns
                self._resize_window_to_content()
            else:
                logger.warning("Cannot toggle Adjust: layout_manager not available")
        except Exception as e:
            logger.error(f"Failed to toggle Adjust pane: {e}")

    def _resize_window_to_content(self):
        """Resize window to fit visible columns

        Calculates the total width of visible columns and resizes the window accordingly.
        This ensures the window size matches the content when columns are toggled.

        Column widths:
        - Library: 180px (when visible)
        - Collection: 200px (when visible)
        - Preview: flexible (minimum 400px)
        - Adjust: 200px (when visible)
        """
        if self.is_mobile:
            return

        try:
            if not self.navigation_controller or not self.navigation_controller.layout_manager:
                return

            lm = self.navigation_controller.layout_manager

            # Calculate total width of visible columns
            total_width = 0

            # Library (180px)
            library_slot = lm._find_slot_by_name("Library")
            if library_slot and library_slot.is_visible:
                total_width += 180

            # Collection (200px)
            collection_slot = lm._find_slot_by_name("Collection")
            if collection_slot and collection_slot.is_visible:
                total_width += 200

            # Preview (flexible, minimum 400px when visible)
            preview_slot = lm._find_slot_by_name("Preview")
            if preview_slot and preview_slot.is_visible:
                total_width += 600  # Use a comfortable default for Preview

            # Adjust (200px)
            adjust_slot = lm._find_slot_by_name("Adjust")
            if adjust_slot and adjust_slot.is_visible:
                total_width += 200

            # Set a minimum width
            total_width = max(total_width, 600)  # Minimum window width

            # Get current window height
            current_height = self.window.size[1] if self.window.size else 800

            # Resize window
            self.window.size = (total_width, current_height)
            logger.info(f"📐 Resized window to {total_width}x{current_height}")

        except Exception as e:
            logger.error(f"Failed to resize window: {e}")

    def _toggle_markup_toolbar(self, widget):
        """Toggle markup toolbar visibility in Preview pane"""
        if self.is_mobile:
            return

        # Delegate to PreviewView's toolbar toggle
        if self.cached_output_view:
            self.cached_output_view.toggle_toolbar()
            logger.info(f"🔧 Toggle Markup Toolbar")
        else:
            logger.warning("Cannot toggle toolbar: PreviewView not created yet")

    def _toggle_path_bar(self, widget):
        """Toggle path bar visibility in Preview pane"""
        if self.is_mobile:
            return

        # Delegate to PreviewView's layout manager to toggle path bars in all panes
        if self.cached_output_view and hasattr(self.cached_output_view, 'layout_manager'):
            layout_manager = self.cached_output_view.layout_manager
            # Toggle path bar visibility in all output panes
            for pane in layout_manager.panes:
                if pane._path_bar:
                    pane._path_bar_visible = not pane._path_bar_visible
                    # Rebuild the pane content to show/hide path bar
                    pane._show_content()
            logger.info(f"🔧 Toggle Path Bar")
        else:
            logger.warning("Cannot toggle path bar: PreviewView not created yet")

    def _toggle_status_bar(self, widget):
        """Toggle status bar visibility at bottom of content area (collection + output panes)"""
        if self.is_mobile:
            return

        # Toggle status bar visibility
        self.status_bar_visible = not self.status_bar_visible

        if self.status_bar and self.content_area:
            if self.status_bar_visible:
                # Add status bar if not already present
                if self.status_bar.container not in self.content_area.children:
                    self.content_area.add(self.status_bar.container)
                    logger.info(f"🔧 Status Bar shown")
            else:
                # Remove status bar
                if self.status_bar.container in self.content_area.children:
                    self.content_area.remove(self.status_bar.container)
                    logger.info(f"🔧 Status Bar hidden")
        else:
            logger.warning("Cannot toggle status bar: StatusBar not created yet")

    # ===== PREVIEW LAYOUT SWITCHING (PHASE 5) =====

    # _split_pane() REMOVED - split commands now handled directly in PreviewView
    # Split commands are organized under View > Editor Layout submenu

    # _update_pane_layout() REMOVED - replaced by layout_manager.toggle_column()
    # Old method manipulated Box containers directly (left_pane, center_pane, etc.)
    # New layout system uses layout_manager API for column visibility

    # ===== LEGACY CALLBACKS (for views that haven't been updated yet) =====

    def _on_collection_selected(self, collection_id: str, collection_name: str = ""):
        """Handle collection selection - delegate to NavigationController"""
        try:
            logger.info(f"🎯 main_window._on_collection_selected: collection_id={collection_id}, collection_name={collection_name}")
            if self.navigation_controller:
                self.navigation_controller.navigate_to_collection(collection_id, collection_name)
            else:
                logger.error("No NavigationController available for collection selection")

        except Exception as e:
            logger.error(f"Failed to handle collection selection: {e}")

    def _on_file_preview_requested(self, file_path: str, file_data: Dict[str, Any] = None):
        """Handle file preview request - delegate to NavigationController"""
        try:
            if self.navigation_controller:
                self.navigation_controller.navigate_to_preview(file_path, file_data)
            else:
                logger.error("No NavigationController available for preview request")

        except Exception as e:
            logger.error(f"Failed to handle file preview request: {e}")

    # ===== STATE PERSISTENCE =====

    def save_window_state(self):
        """
        Save complete window state including layout for restoration on next launch.

        Saves:
        - Window size and position
        - Main layout state (column visibility, widths)
        - Preview layout state (split panes, contexts, viewer states)
        """
        try:
            from fichero.config.core.app_preferences import get_app_preferences

            prefs = get_app_preferences(self.app)

            # Save window size and position
            if self.window:
                # Get window position and size
                try:
                    position = getattr(self.window, 'position', (100, 100))
                    size = getattr(self.window, 'size', (1200, 800))

                    prefs.set_window_position('main', {
                        'x': position[0] if position else 100,
                        'y': position[1] if position else 100,
                        'width': size[0] if size else 1200,
                        'height': size[1] if size else 800
                    })
                    logger.debug(f"Saved window position: {position}, size: {size}")
                except Exception as e:
                    logger.warning(f"Could not save window position/size: {e}")

            # Save main layout state (column visibility, widths)
            if self.navigation_controller and hasattr(self.navigation_controller, 'layout_manager'):
                try:
                    layout_state = self.navigation_controller.layout_manager.get_layout_state()
                    prefs._preferences['main_layout'] = layout_state
                    prefs._save_preferences()
                    logger.debug(f"Saved main layout state: {len(layout_state.get('slots', []))} slots")
                except Exception as e:
                    logger.warning(f"Could not save main layout state: {e}")

            # Save preview layout state (split panes)
            preview_view = self.views.get('output')
            if preview_view and hasattr(preview_view, 'layout_manager'):
                try:
                    preview_layout = preview_view.layout_manager.get_layout_state()
                    prefs._preferences['preview_layout'] = preview_layout
                    prefs._save_preferences()
                    logger.debug(f"Saved preview layout state: {preview_layout.get('layout_type')}")
                except Exception as e:
                    logger.warning(f"Could not save preview layout state: {e}")

            logger.info("✅ Window state saved successfully")

        except Exception as e:
            logger.error(f"Failed to save window state: {e}")
            import traceback
            logger.error(traceback.format_exc())

    async def restore_window_state(self):
        """
        Restore window state from saved preferences.

        Restores:
        - Window size and position
        - Main layout state (column visibility, widths)
        - Preview layout state (split panes, contexts, viewer states)
        """
        try:
            from fichero.config.core.app_preferences import get_app_preferences

            prefs = get_app_preferences(self.app)

            # Restore window size and position
            window_state = prefs.get_window_position('main')
            if window_state and self.window:
                try:
                    self.window.position = (window_state['x'], window_state['y'])
                    self.window.size = (window_state['width'], window_state['height'])
                    logger.debug(f"Restored window position: ({window_state['x']}, {window_state['y']})")
                    logger.debug(f"Restored window size: {window_state['width']}x{window_state['height']}")
                except Exception as e:
                    logger.warning(f"Could not restore window position/size: {e}")

            # Restore main layout (column visibility and widths)
            main_layout = prefs._preferences.get('main_layout')
            if main_layout and self.navigation_controller and hasattr(self.navigation_controller, 'layout_manager'):
                try:
                    self.navigation_controller.layout_manager.restore_layout(main_layout)
                    logger.debug(f"Restored main layout: {len(main_layout.get('slots', []))} slots")
                except Exception as e:
                    logger.warning(f"Could not restore main layout: {e}")

            # Restore preview layout (split panes)
            preview_layout = prefs._preferences.get('preview_layout')
            preview_view = self.views.get('output')
            if preview_layout and preview_view and hasattr(preview_view, 'layout_manager'):
                try:
                    await preview_view.layout_manager.restore_layout_state(preview_layout)
                    logger.debug(f"Restored preview layout: {preview_layout.get('layout_type')}")
                except Exception as e:
                    logger.warning(f"Could not restore preview layout: {e}")

            logger.info("✅ Window state restored successfully")

        except Exception as e:
            logger.error(f"Failed to restore window state: {e}")
            import traceback
            logger.error(traceback.format_exc())

    # ===== PUBLIC INTERFACE =====

    def show(self):
        """Show the main window"""
        try:
            if self.window:
                self.window.show()
                logger.info("Main window shown")
        except Exception as e:
            logger.error(f"Failed to show main window: {e}")

    def close(self):
        """Close the main window with proper cleanup"""
        try:
            # Save window state before closing
            self.save_window_state()

            # Clean up all cached views before closing
            self._cleanup_all_cached_views()

            if self.window:
                self.window.close()
                logger.info("Main window closed")
        except Exception as e:
            logger.error(f"Failed to close main window: {e}")

    # Phase 1: Preview integration event handlers

    def _handle_preview_selection_changed(self, event):
        """
        Handle SELECTION_CHANGED events to update preview pane.

        Responds to selections from collection view and library sidebar,
        automatically loading the selected item in the preview/inspector pane.
        """
        try:
            # Extract event data
            view_id = event.data.get('view_id', '')
            item_ids = event.data.get('new_selection', [])  # SelectionManager emits 'new_selection'
            metadata = event.data.get('metadata', [])

            logger.info(f"🔍 Preview selection change from view: {view_id}, items: {len(item_ids)}")

            # Only respond to collection view selections (not library, not preview itself)
            if view_id != 'collection':
                logger.debug(f"Ignoring selection from {view_id} (preview only responds to collection)")
                return

            # If no selection, clear preview
            if not item_ids or not metadata:
                logger.info("Empty selection, clearing preview")
                self._clear_preview()
                return

            # Load first selected item (multi-select shows first item)
            first_item_meta = metadata[0]
            self._load_preview_from_selection(first_item_meta, metadata)

        except Exception as e:
            logger.error(f"Failed to handle preview selection change: {e}", exc_info=True)

    def _load_preview_from_selection(self, item_meta: dict, all_metadata: list):
        """
        Load item in preview pane from selection metadata.

        Args:
            item_meta: Metadata for the selected item
            all_metadata: Full list of selected items (for navigation)
        """
        try:
            # Extract file path (prefer local_path for downloaded files)
            file_path = item_meta.get('local_path') or item_meta.get('file_path')
            item_id = item_meta.get('id')

            if not file_path:
                logger.warning(f"No file path in selection metadata: {item_meta}")
                return

            logger.info(f"📄 Loading preview for: {file_path}")

            # Check if item has processing outputs via library_manager
            output_data = None
            if hasattr(self.app, 'library_manager') and item_id:
                try:
                    # Get processing outputs for this item
                    library_manager = self.app.library_manager
                    item = library_manager.storage.get_item(item_id)

                    if item and item.metadata.get('output_path'):
                        output_path = item.metadata['output_path']
                        logger.info(f"📊 Item has processing outputs: {output_path}")

                        # Create output_data structure expected by _on_show_preview
                        output_data = {
                            'has_outputs': True,
                            'output_path': output_path,
                            # OutputsManager will discover steps when preview loads
                        }
                except Exception as e:
                    logger.debug(f"Could not check for outputs: {e}")

            # Trigger existing preview loading mechanism via SHOW_PREVIEW event
            from fichero.shared.navigation.navigation_event_bus import emit_navigation_event, NavigationEvent, NavigationEvents

            preview_event_data = {
                'file_path': file_path,
                'item_id': item_id,
                'output_data': output_data,
                'file_metadata': item_meta,
                'collection_items': all_metadata,  # For prev/next navigation
                'item_index': 0,  # First selected item
            }

            emit_navigation_event(
                NavigationEvents.SHOW_PREVIEW,
                preview_event_data
            )

            logger.info(f"✅ Preview event emitted for {file_path}")

        except Exception as e:
            logger.error(f"Failed to load preview from selection: {e}", exc_info=True)

    def _clear_preview(self):
        """Clear the preview pane when no item is selected"""
        try:
            if self.cached_output_view:
                logger.info("📤 Clearing preview pane (no selection)")
                # Call load_output with no arguments to clear
                self.cached_output_view.load_output()
            else:
                logger.debug("No cached output view to clear")
        except Exception as e:
            logger.error(f"Failed to clear preview: {e}", exc_info=True)

    # Phase 2: Selection tracking event handler

    def _handle_selection_changed(self, event):
        """
        Handle SELECTION_CHANGED events to update status bar.

        Called by NavigationEventBus when any view's selection changes.
        Updates status bar with selection count and total item count.

        CRITICAL FIX #2: Includes defensive checks for view readiness.

        Args:
            event: NavigationEvent with selection data
        """
        try:
            # CRITICAL FIX #2: Early return if status bar not ready
            if not self.status_bar:
                logger.debug("Status bar not available, skipping update")
                return

            # Extract event data
            view_id = event.data.get('view_id', '')
            context = event.data.get('context', '')
            selected_count = event.data.get('count', 0)
            metadata = event.data.get('metadata', [])

            logger.debug(f"Selection changed: view_id={view_id}, context={context}, count={selected_count}")

            # Get total item count and folder count for this view
            total_items = 0
            folder_count = 0

            if view_id == 'library':
                # CRITICAL FIX #2: Defensive check with early return
                if not hasattr(self, 'left_pane_view') or self.left_pane_view is None:
                    logger.debug("Library view not ready, skipping status update")
                    return

                if hasattr(self.left_pane_view, 'collections'):
                    total_items = len(self.left_pane_view.collections)
                    logger.debug(f"Library view has {total_items} collections")
                else:
                    logger.debug("Library view has no collections attribute, skipping")
                    return

            elif view_id == 'collection':
                # CRITICAL FIX #2: Defensive check with early return
                if not hasattr(self, 'center_pane_view') or self.center_pane_view is None:
                    logger.debug("Collection view not ready, skipping status update")
                    return

                if hasattr(self.center_pane_view, 'collection_items'):
                    items = self.center_pane_view.collection_items
                    total_items = len(items)
                    logger.debug(f"Collection view has {total_items} items")

                    # CRITICAL FIX #1: Count folders using item.get() for dictionaries
                    folder_count = sum(
                        1 for item in items
                        if isinstance(item, dict) and item.get('is_folder', False)
                    )
                    logger.debug(f"Collection has {folder_count} folders")
                else:
                    logger.debug("Collection view has no collection_items attribute, skipping")
                    return

            elif view_id == 'steps':
                # CRITICAL FIX #2: Defensive check with early return
                if not hasattr(self, 'right_pane_view') or self.right_pane_view is None:
                    logger.debug("Preview view not ready, skipping status update")
                    return

                # Get total steps from PreviewView (if it has step browser)
                if hasattr(self.right_pane_view, 'step_browser'):
                    step_browser = self.right_pane_view.step_browser
                    if step_browser and hasattr(step_browser, 'steps'):
                        total_items = len(step_browser.steps)
                        logger.debug(f"Steps view has {total_items} steps")
                    else:
                        logger.debug("Step browser not ready, skipping")
                        return
                else:
                    logger.debug("Preview view has no step_browser attribute, skipping")
                    return

            # Update status bar with formatted message
            self.status_bar.update_status_from_selection(
                context=context,
                selected_count=selected_count,
                metadata={
                    'total_items': total_items,
                    'folder_count': folder_count
                }
            )

        except Exception as e:
            logger.error(f"Failed to update status bar on selection change: {e}")
            import traceback
            traceback.print_exc()

    def _update_focused_pane_display(self, view_id: str):
        """
        Update status bar to show which pane is currently focused.

        Args:
            view_id: ID of the focused view ('library', 'collection', 'output', etc.)
        """
        if not self.status_bar:
            return

        # Map view IDs to readable pane names
        pane_names = {
            'library': 'Library Sidebar',
            'collection': 'Collection View',
            'output': 'Preview Pane',
            'steps': 'Steps Browser',
            'preview': 'Preview Pane',
        }

        pane_name = pane_names.get(view_id, view_id.title())
        self.status_bar.set_focused_pane(pane_name)
        logger.debug(f"Status bar focused pane updated to: {pane_name}")


    def get_window_info(self) -> Dict[str, Any]:
        """Get window information for debugging"""
        return {
            "is_mobile": self.is_mobile,
            "current_view_key": self.current_view_key,
            "has_navigation_controller": self.navigation_controller is not None,
            "window_size": self._get_window_size()
        }