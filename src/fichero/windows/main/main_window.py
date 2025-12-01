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
# Preview views now imported inline where needed
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
        self.cached_collection_view: Optional[CollectionView] = None  # Cache single reusable instance

        # Session state tracking for persistence
        self.current_collection_id: Optional[str] = None
        self.current_item_id: Optional[str] = None
        self._save_state_timer: Optional = None  # Debounced save timer

        # Get NavigationController from app
        self.navigation_controller = self._get_navigation_controller()

        # Get StateManager from app for enhanced state management
        self.state_manager = getattr(self.app, 'state_manager', None)
        if not self.state_manager:
            logger.warning("StateManager not available in app - some features may be limited")
        else:
            logger.debug("StateManager reference stored for enhanced state management")

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

        # Note: Preview panes are created in layout, no need for pre-creation

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

        # Apply saved pane visibility synchronously BEFORE showing initial view
        # This prevents the visible "flash" where the layout changes after window appears
        if not self.is_mobile:
            self._apply_initial_pane_visibility()

        # Set up initial view
        self._show_initial_view()

        # Restore window state from saved preferences (async task)
        # This restores window size, column visibility, and preview pane layouts
        import asyncio
        asyncio.create_task(self.restore_window_state())

        # Restore session state (last collection, item, etc.)
        # This runs after window state to ensure UI is ready
        asyncio.create_task(self.restore_session_state())

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
        """Create the main window with saved size and position"""
        try:
            # Get saved size (or default)
            size = self._get_window_size()

            self.window = toga.MainWindow(
                title=self.app.formal_name,
                size=size
            )

            if not self.is_mobile:
                self.window.min_size = (1000, 600)

            # Set initial position from saved state (before showing)
            position = self._get_window_position()
            if position:
                self.window.position = position
                logger.info(f"Set initial window position: {position}")

            # Register with window state tracker for native state tracking
            # NOTE: We use restore=False because position/size is set above
            if hasattr(self.app, 'window_state_tracker') and self.app.window_state_tracker:
                self.app.window_state_tracker.register_window("main", self.window, restore=False)
                logger.debug("Main window registered with window state tracker")

            logger.debug(f"Main window created with size={size}, position={position}")

        except Exception as e:
            logger.error(f"Failed to create main window: {e}")

    def _get_window_size(self) -> tuple:
        """Get appropriate window size for platform, checking saved state first"""
        if self.is_mobile:
            return (375, 667)  # iPhone dimensions

        # Check for saved window state first
        try:
            state_manager = getattr(self.app, 'state_manager', None)
            if state_manager:
                saved = state_manager.get_window_state("main")
                if saved and saved.get('width') and saved.get('height'):
                    width = saved['width']
                    height = saved['height']
                    logger.info(f"Using saved window size: {width}x{height}")
                    return (width, height)
        except Exception as e:
            logger.debug(f"Could not get saved window size: {e}")

        return (1600, 1000)  # Desktop default

    def _get_window_position(self) -> tuple:
        """Get saved window position, or None for system default"""
        if self.is_mobile:
            return None

        try:
            state_manager = getattr(self.app, 'state_manager', None)
            if state_manager:
                saved = state_manager.get_window_state("main")
                if saved and saved.get('x') is not None and saved.get('y') is not None:
                    x = saved['x']
                    y = saved['y']
                    logger.info(f"Using saved window position: ({x}, {y})")
                    return (x, y)
        except Exception as e:
            logger.debug(f"Could not get saved window position: {e}")

        return None  # Let system choose default position

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

                # Import simplified Adjust view
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

                # Creating 5-column layout: Library | Collection | PreviewImage | PreviewMetadata | Adjust

                # DUAL-PANE PREVIEW: Create 5-column layout with separate image and transcription panes
                # Columns: Library | Collection | ImagePane | TranscriptionPane | Adjust
                import toga
                from toga.style import Pack

                # Create two dedicated preview panes with specific purposes
                from fichero.windows.main.views.preview.preview_image_pane import PreviewImagePane
                from fichero.windows.main.views.preview.preview_metadata_pane import PreviewMetadataPane

                # Get library_manager for preview panes
                library_manager = getattr(self.app, 'library_manager', None)

                image_pane = PreviewImagePane(self.app, self.is_mobile, library_manager=library_manager)
                metadata_pane = PreviewMetadataPane(self.app, self.is_mobile, library_manager=library_manager)

                # Create AdjustView for metadata display
                adjust_view = AdjustView(
                    self.app,
                    is_mobile=False
                )
                self.views['adjust'] = adjust_view

                # SIMPLIFIED: Wire up AdjustView to library_manager for metadata display
                if hasattr(adjust_view, 'set_library_manager'):
                    adjust_view.set_library_manager(library_manager)
                    logger.info("✅ AdjustView wired to LibraryManager for metadata display")

                logger.info("✅ AdjustView will be loaded directly from main_window (no event subscription)")

                # Store references for item loading
                self.image_pane = image_pane
                self.metadata_pane = metadata_pane
                self.views['image'] = image_pane
                self.views['metadata'] = metadata_pane

                views = [
                    library_view,
                    collection_view,
                    image_pane,    # Left preview pane (dedicated image display)
                    metadata_pane, # Right preview pane (dedicated metadata/transcription)
                    adjust_view
                ]
                # Fixed widths: sidebars fixed, preview panes with 75%/25% ratio, adjust fixed
                widths = [180, 200, None, None, 300]

                # Set initial flex ratios for 75%/25% preview split
                # We'll modify the layout creation to apply these ratios

                # Column names for menu commands (show/hide)
                column_names = ["Library", "Collection", "PreviewImage", "PreviewMetadata", "Adjust"]

                # Mark columns as collapsible (all panes can now be toggled)
                collapsible = [True, True, True, True, True]

                # Minimum widths for auto-collapse behavior
                min_widths = [180, 200, 400, 400, 300]

                logger.info(f"Creating DUAL-PANE 5-column layout")
                logger.info(f"  - Library: 180px fixed, collapsible")
                logger.info(f"  - Collection: 200px fixed, collapsible")
                logger.info(f"  - ImagePane: flexible (min 400px), collapsible")
                logger.info(f"  - MetadataPane: flexible (min 400px), collapsible")
                logger.info(f"  - Adjust: 300px fixed, collapsible")

                slot_ids = layout_manager.add_columns_fixed(
                    views,
                    widths=widths,
                    column_names=column_names,
                    collapsible=collapsible,
                    min_widths=min_widths
                )

                # Store slot IDs for 5-column layout
                self.library_slot_id = slot_ids[0]
                self.collection_slot_id = slot_ids[1]
                self.image_slot_id = slot_ids[2]
                self.metadata_slot_id = slot_ids[3]
                self.adjust_slot_id = slot_ids[4]
                # Backward compatibility for preview_slot_id
                self.preview_slot_id = slot_ids[2]  # For any legacy code

                # Apply 75%/25% ratio to preview panes
                # Get the preview slots and set their flex ratios
                if not self.is_mobile:  # Only apply on desktop
                    image_slot = layout_manager.view_slots[self.image_slot_id]
                    metadata_slot = layout_manager.view_slots[self.metadata_slot_id]

                    # Set 75% for image, 25% for metadata
                    image_slot.container.style.flex = 75
                    metadata_slot.container.style.flex = 25
                    logger.info("Applied 75%/25% flex ratio to preview panes (ImagePane:75, MetadataPane:25)")

                    # Also set the default state in the state manager if available
                    if hasattr(self.app, 'state_manager') and self.app.state_manager:
                        self.app.state_manager.set_current_preview_preset("wide_content")

                # Wire up focus system: Set on_click callbacks on views and slots
                # The combined view acts as one focusable unit
                all_views_and_slots = [
                    (self.library_slot_id, library_view),
                    (self.collection_slot_id, collection_view),
                    (slot_ids[2], image_pane),  # Image preview pane
                    (slot_ids[3], metadata_pane),  # Metadata preview pane
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
                self.image_pane_container = image_pane.container
                self.metadata_pane_container = metadata_pane.container
                self.adjust_pane = adjust_view.container
                # Backward compatibility for preview_pane
                self.preview_pane = image_pane.container  # For any legacy code

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

                logger.info(f"✅ Desktop layout created: 5-column layout with dual preview panes (Library | Collection | ImagePane | TranscriptionPane | Adjust)")
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
            subscribe_to_navigation(NavigationEvents.SHOW_MODAL, self._on_show_modal)
            subscribe_to_navigation(NavigationEvents.NAVIGATION_ERROR, self._on_navigation_error)

            # Phase 2: Subscribe to selection changes for status bar updates
            if self.status_bar:
                subscribe_to_navigation(NavigationEvents.SELECTION_CHANGED, self._handle_selection_changed)
                logger.debug("Status bar subscribed to selection events")

            # Phase 1: Subscribe to selection changes for preview updates
            subscribe_to_navigation(NavigationEvents.SELECTION_CHANGED, self._handle_preview_selection_changed)
            logger.debug("Preview pane subscribed to selection events")

            # Subscribe to processing completion for preview reload
            subscribe_to_navigation("processing_completed", self._on_processing_completed_for_preview)
            logger.debug("Preview pane subscribed to processing_completed events")

            logger.debug("Subscribed to navigation events")

        except Exception as e:
            logger.error(f"Failed to subscribe to navigation events: {e}")

    # _precreate_output_view removed - using dedicated preview panes instead

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
            # Order: Library, Collection, Preview, Adjust
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
                    label=_("2 Collection"),
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
                # Preview Image toggle
                'view.toggle_preview_image': FicheroCommand(
                    id='view.toggle_preview_image',
                    label=_("3 Preview Image"),
                    action=self._toggle_preview_image_pane,
                    shortcut=toga.Key.MOD_1 + toga.Key.MOD_2 + '3',
                    description=_("Show/hide Preview Image pane"),
                    group=toga.Group.VIEW,
                    section=0,
                    order=2,
                    show_in_menu=True,
                    show_in_top_toolbar=False,
                    desktop_only=True,
                    context='normal'
                ),
                # Preview Metadata toggle
                'view.toggle_preview_metadata': FicheroCommand(
                    id='view.toggle_preview_metadata',
                    label=_("4 Preview Metadata"),
                    action=self._toggle_preview_metadata_pane,
                    shortcut=toga.Key.MOD_1 + toga.Key.MOD_2 + '4',
                    description=_("Show/hide Preview Metadata pane"),
                    group=toga.Group.VIEW,
                    section=0,
                    order=3,
                    show_in_menu=True,
                    show_in_top_toolbar=False,
                    desktop_only=True,
                    context='normal'
                ),
                # Info toggle button (toolbar button)
                'view.toggle_inspector': FicheroCommand(
                    id='view.toggle_inspector',
                    label=_("5 Info"),
                    action=self._toggle_inspector_pane,
                    icon="resources/icons/toolbar/sidebar.right@10x.png",  # PNG icon for right sidebar
                    toolbar_icon="resources/icons/toolbar/sidebar.right@10x.png",  # PNG icon
                    shortcut=toga.Key.MOD_1 + toga.Key.MOD_2 + '5',
                    description=_("Show/hide Info pane"),
                    group=toga.Group.VIEW,
                    section=0,
                    order=4,
                    show_in_menu=True,
                    show_in_top_toolbar=True,  # Add to native toolbar
                    show_in_titlebar=False,  # Remove from titlebar accessories
                    desktop_only=True,
                    context='normal',  # Required for toolbar filtering
                    visibility_priority=900,  # Very high priority - Phase 2 (stays visible)
                    tooltip=_("Show/hide Info pane")  # Tooltip for toolbar button
                ),

                # === PREVIEW RATIO CONTROLS ===
                'view.cycle_ratios': FicheroCommand(
                    id='view.cycle_ratios',
                    label=_("Cycle Preview Width"),
                    action=self._cycle_preview_ratios,
                    shortcut=toga.Key.MOD_1 + 'r',
                    description=_("Cycle through preview pane width ratios (25/75, 50/50, 75/25)"),
                    group=toga.Group.VIEW,
                    section=10,
                    order=0,
                    show_in_menu=True,
                    desktop_only=True
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

                # === ZOOM COMMANDS ===
                'view.zoom_in': FicheroCommand(
                    id='view.zoom_in',
                    label=_("Zoom In"),
                    action=self._zoom_in_preview,
                    shortcut=toga.Key.MOD_1 + '=',  # Cmd++ (same key as +)
                    description=_("Zoom in on preview image"),
                    group=toga.Group.VIEW,
                    section=15,
                    order=0,
                    show_in_menu=True,
                    desktop_only=True
                ),
                'view.zoom_out': FicheroCommand(
                    id='view.zoom_out',
                    label=_("Zoom Out"),
                    action=self._zoom_out_preview,
                    shortcut=toga.Key.MOD_1 + '-',  # Cmd+-
                    description=_("Zoom out on preview image"),
                    group=toga.Group.VIEW,
                    section=15,
                    order=1,
                    show_in_menu=True,
                    desktop_only=True
                ),
                'view.actual_size': FicheroCommand(
                    id='view.actual_size',
                    label=_("Actual Size"),
                    action=self._actual_size_preview,
                    shortcut=toga.Key.MOD_1 + '0',  # Cmd+0
                    description=_("Show preview image at actual size"),
                    group=toga.Group.VIEW,
                    section=15,
                    order=2,
                    show_in_menu=True,
                    desktop_only=True
                ),
                'view.zoom_to_fit': FicheroCommand(
                    id='view.zoom_to_fit',
                    label=_("Zoom to Fit"),
                    action=self._zoom_to_fit_preview,
                    shortcut=toga.Key.MOD_1 + '9',  # Cmd+9
                    description=_("Fit preview image to window"),
                    group=toga.Group.VIEW,
                    section=15,
                    order=3,
                    show_in_menu=True,
                    desktop_only=True
                ),
                'view.zoom_to_selection': FicheroCommand(
                    id='view.zoom_to_selection',
                    label=_("Zoom to Selection"),
                    action=self._zoom_to_selection_preview,
                    shortcut=toga.Key.MOD_1 + toga.Key.SHIFT + '8',  # Cmd+* (Shift+8)
                    description=_("Zoom to current selection"),
                    group=toga.Group.VIEW,
                    section=15,
                    order=4,
                    show_in_menu=True,
                    desktop_only=True
                ),
                # Magnifier controls (section 16 = after divider, grouped together)
                'view.toggle_magnifier': FicheroCommand(
                    id='view.toggle_magnifier',
                    label=_("Show Magnifier"),
                    action=self._toggle_magnifier_preview,
                    shortcut=toga.Key.MOD_1 + '`',  # Cmd+` (backtick)
                    description=_("Show magnifier panel for detailed view"),
                    group=toga.Group.VIEW,
                    section=16,
                    order=0,
                    show_in_menu=True,
                    desktop_only=True
                ),
                'view.magnifier_zoom_in': FicheroCommand(
                    id='view.magnifier_zoom_in',
                    label=_("Magnifier Zoom In"),
                    action=self._magnifier_zoom_in_preview,
                    shortcut=toga.Key.MOD_1 + toga.Key.SHIFT + '=',  # Cmd+Shift+=
                    description=_("Zoom in on magnifier"),
                    group=toga.Group.VIEW,
                    section=16,
                    order=1,
                    show_in_menu=True,
                    desktop_only=True
                ),
                'view.magnifier_zoom_out': FicheroCommand(
                    id='view.magnifier_zoom_out',
                    label=_("Magnifier Zoom Out"),
                    action=self._magnifier_zoom_out_preview,
                    shortcut=toga.Key.MOD_1 + toga.Key.SHIFT + '-',  # Cmd+Shift+-
                    description=_("Zoom out on magnifier"),
                    group=toga.Group.VIEW,
                    section=16,
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

    def _apply_initial_pane_visibility(self):
        """
        Apply saved pane visibility synchronously before showing initial view.

        This prevents the visible "flash" where the window appears with default
        layout then changes to saved layout.
        """
        try:
            if not self.state_manager:
                logger.debug("No state_manager - using default visibility")
                return

            if not self.navigation_controller or not hasattr(self.navigation_controller, 'layout_manager'):
                logger.debug("No layout_manager - cannot apply visibility")
                return

            # Get saved pane visibility
            pane_visibility = self.state_manager.get_all_pane_visibility()
            if not pane_visibility:
                logger.debug("No saved pane visibility - using defaults")
                return

            # Map pane keys to column names
            pane_to_column = {
                'library': 'Library',
                'collection': 'Collection',
                'previewimage': 'PreviewImage',
                'previewmetadata': 'PreviewMetadata',
                'adjust': 'Adjust',
            }

            layout_manager = self.navigation_controller.layout_manager
            if not hasattr(layout_manager, 'set_column_visibility'):
                logger.debug("Layout manager doesn't support set_column_visibility")
                return

            # Apply visibility for each pane
            for pane_key, column_name in pane_to_column.items():
                if pane_key in pane_visibility:
                    is_visible = pane_visibility[pane_key]
                    try:
                        layout_manager.set_column_visibility(column_name, is_visible)
                        logger.debug(f"Initial visibility: {column_name} = {is_visible}")
                    except Exception as e:
                        logger.debug(f"Could not set initial {column_name} visibility: {e}")

            logger.info("✅ Applied initial pane visibility from saved state")

        except Exception as e:
            logger.warning(f"Could not apply initial pane visibility: {e}")

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

            # 🔍 DEBUG POINT 10: Log toolbar build for library view
            logger.info(f"🔍 BUILDING TOOLBAR for view_id='library', context={context}")

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
            # Note: PreviewView handles its own events, no need to call load_output
            if hasattr(self, 'cached_output_view') and self.cached_output_view:
                logger.info("📤 Clearing output view (navigating to library)")
                # Reset the current item ID
                self.cached_output_view.current_item_id = None

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
                # CRITICAL FIX: Actually refresh the data when reusing the view
                current_view._load_collection_items()
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

            # Track current collection for state persistence
            self.current_collection_id = collection_id
            # Trigger debounced state save
            self._schedule_debounced_save()

            # Update status bar to show focused pane
            self._update_focused_pane_display('collection')

        except Exception as e:
            logger.error(f"Failed to handle show collection event: {e}")

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

    def _toggle_preview_image_pane(self, widget):
        """Toggle Preview Image pane visibility

        Smart behavior:
        - If both hidden: Show image first
        - If image hidden, metadata visible: Show image (both now visible)
        - If image visible: Hide image
        - When hiding image and metadata hidden: Show metadata (can't hide both)
        - Info pane auto-hides when both preview panes are hidden
        """
        if self.is_mobile:
            return

        try:
            if self.navigation_controller and self.navigation_controller.layout_manager:
                lm = self.navigation_controller.layout_manager

                image_slot = lm._find_slot_by_name("PreviewImage")
                metadata_slot = lm._find_slot_by_name("PreviewMetadata")

                if not image_slot or not metadata_slot:
                    logger.warning("Cannot toggle Preview Image: slots not found")
                    return

                # Get current visibility states
                image_visible = image_slot.is_visible
                metadata_visible = metadata_slot.is_visible

                # Toggle image
                new_state = lm.toggle_column("PreviewImage")
                logger.info(f"📐 Toggle Preview Image pane: {new_state}")

                # Smart behavior: Can't hide both preview panes
                if not new_state and not metadata_visible:
                    logger.info("📐 Both preview panes would be hidden, showing metadata")
                    lm.show_column("PreviewMetadata")
                    # Also hide Info pane if both were hidden
                    lm.hide_column("Adjust")

                # If both preview panes are now hidden, hide Info pane too
                if not image_slot.is_visible and not metadata_slot.is_visible:
                    logger.info("📐 Both preview panes hidden, hiding Info")
                    lm.hide_column("Adjust")

                self._update_toolbar_menu_checkmarks()
            else:
                logger.warning("Cannot toggle Preview Image: layout_manager not available")
        except Exception as e:
            logger.error(f"Failed to toggle Preview Image pane: {e}")

    def _toggle_preview_metadata_pane(self, widget):
        """Toggle Preview Metadata pane visibility

        Smart behavior:
        - If both hidden: Show metadata first
        - If metadata hidden, image visible: Show metadata (both now visible)
        - If metadata visible: Hide metadata
        - When hiding metadata and image hidden: Show image (can't hide both)
        - Info pane auto-hides when both preview panes are hidden
        """
        if self.is_mobile:
            return

        try:
            if self.navigation_controller and self.navigation_controller.layout_manager:
                lm = self.navigation_controller.layout_manager

                image_slot = lm._find_slot_by_name("PreviewImage")
                metadata_slot = lm._find_slot_by_name("PreviewMetadata")

                if not image_slot or not metadata_slot:
                    logger.warning("Cannot toggle Preview Metadata: slots not found")
                    return

                # Get current visibility states
                image_visible = image_slot.is_visible
                metadata_visible = metadata_slot.is_visible

                # Toggle metadata
                new_state = lm.toggle_column("PreviewMetadata")
                logger.info(f"📐 Toggle Preview Metadata pane: {new_state}")

                # Smart behavior: Can't hide both preview panes
                if not new_state and not image_visible:
                    logger.info("📐 Both preview panes would be hidden, showing image")
                    lm.show_column("PreviewImage")
                    # Also hide Info pane if both were hidden
                    lm.hide_column("Adjust")

                # If both preview panes are now hidden, hide Info pane too
                if not image_slot.is_visible and not metadata_slot.is_visible:
                    logger.info("📐 Both preview panes hidden, hiding Info")
                    lm.hide_column("Adjust")

                self._update_toolbar_menu_checkmarks()
            else:
                logger.warning("Cannot toggle Preview Metadata: layout_manager not available")
        except Exception as e:
            logger.error(f"Failed to toggle Preview Metadata pane: {e}")

    def _toggle_inspector_pane(self, widget):
        """Toggle Info pane visibility

        When hiding the Info view, the Preview pane expands to fill the available space.
        When showing the Info view, the Preview pane shrinks to make room.
        The window size remains unchanged.

        Note: Info pane cannot be shown if both preview panes are hidden.
        """
        if self.is_mobile:
            return

        try:
            if self.navigation_controller and self.navigation_controller.layout_manager:
                lm = self.navigation_controller.layout_manager

                # Check if at least one preview pane is visible
                image_slot = lm._find_slot_by_name("PreviewImage")
                metadata_slot = lm._find_slot_by_name("PreviewMetadata")

                if image_slot and metadata_slot:
                    if not image_slot.is_visible and not metadata_slot.is_visible:
                        logger.warning("📐 Cannot toggle Info: Both preview panes are hidden")
                        return

                # Toggle Adjust/Info column
                new_state = lm.toggle_column("Adjust")
                logger.info(f"📐 Toggle Info pane: {new_state} - preview panes will {'shrink' if new_state else 'expand'}")
                self._update_toolbar_menu_checkmarks()

                # Note: Removed window resizing - preview panes will automatically expand/shrink
                # The layout will redistribute space to the remaining visible columns
            else:
                logger.warning("Cannot toggle Info: layout_manager not available")
        except Exception as e:
            logger.error(f"Failed to toggle Info pane: {e}")

    # === PREVIEW RATIO ACTION METHODS ===

    def _apply_ratio_balanced(self, widget):
        """Apply balanced 50/50 ratio to preview split"""
        self._apply_preview_ratio("balanced", widget)

    def _apply_ratio_wide_content(self, widget):
        """Apply wide content 75/25 ratio to preview split"""
        self._apply_preview_ratio("wide_content", widget)

    def _apply_ratio_wide_image(self, widget):
        """Apply wide image 25/75 ratio to preview split"""
        self._apply_preview_ratio("wide_image", widget)

    def _cycle_preview_ratios(self, widget):
        """Cycle through available preview ratios (25/75, 50/50, 75/25)

        Only works when both preview panes are visible.
        """
        try:
            if not self.navigation_controller or not self.navigation_controller.layout_manager:
                logger.warning("Cannot cycle ratios: layout_manager not available")
                return

            lm = self.navigation_controller.layout_manager

            # Check if both preview panes are visible
            image_slot = lm._find_slot_by_name("PreviewImage")
            metadata_slot = lm._find_slot_by_name("PreviewMetadata")

            if not image_slot or not metadata_slot:
                logger.warning("Cannot cycle ratios: Preview slots not found")
                return

            if not image_slot.is_visible or not metadata_slot.is_visible:
                logger.info("📐 Cannot cycle ratios: Both preview panes must be visible")
                return

            # Get current preset from state manager
            current_preset = "wide_content"  # Default
            if hasattr(self.app, 'state_manager') and self.app.state_manager:
                current_preset = self.app.state_manager.get_current_preview_preset() or "wide_content"

            # Cycle: wide_image (25/75) -> balanced (50/50) -> wide_content (75/25) -> wide_image
            cycle_order = ["wide_image", "balanced", "wide_content"]
            try:
                current_idx = cycle_order.index(current_preset)
                next_idx = (current_idx + 1) % len(cycle_order)
                next_preset = cycle_order[next_idx]
            except ValueError:
                next_preset = "wide_image"  # Start from beginning if unknown

            # Apply the next preset
            self._apply_preview_ratio(next_preset, widget)
            logger.info(f"📐 Cycled preview ratio to: {next_preset}")

        except Exception as e:
            logger.error(f"Failed to cycle preview ratios: {e}")

    def _apply_preview_ratio(self, preset_name: str, widget):
        """Apply a specific ratio preset to the preview columns

        Only works when both preview panes are visible.
        When only one pane is visible, it takes 100% of the space automatically.
        """
        try:
            # Work with the dual-column system (PreviewImage and PreviewMetadata)
            if not self.navigation_controller or not self.navigation_controller.layout_manager:
                logger.warning(f"Cannot apply ratio {preset_name}: layout_manager not available")
                return

            lm = self.navigation_controller.layout_manager

            # Find both preview columns
            image_slot = lm._find_slot_by_name("PreviewImage")
            metadata_slot = lm._find_slot_by_name("PreviewMetadata")

            if not (image_slot and metadata_slot):
                logger.warning(f"Cannot apply ratio {preset_name}: Preview columns not found")
                return

            # Only apply ratios if both panes are visible
            if not image_slot.is_visible or not metadata_slot.is_visible:
                logger.info(f"📐 Cannot apply ratio {preset_name}: Both preview panes must be visible")
                return

            # Get ratio from preset
            ratio_presets = {
                "wide_content": 0.75,    # 75%/25% - content-focused
                "wide_image": 0.25,      # 25%/75% - image-focused
                "balanced": 0.5          # 50%/50% - balanced
            }

            ratio = ratio_presets.get(preset_name, 0.75)  # Default to 75%/25%

            # Apply flex ratios (ratio = image_flex / (image_flex + metadata_flex))
            total_flex = 100
            image_flex = int(ratio * total_flex)
            metadata_flex = total_flex - image_flex

            # Update container flex values
            image_slot.container.style.flex = image_flex
            metadata_slot.container.style.flex = metadata_flex

            logger.info(f"Applied preview ratio preset: {preset_name} ({image_flex}:{metadata_flex})")

            # Update state manager if available
            if hasattr(self.app, 'state_manager') and self.app.state_manager:
                self.app.state_manager.set_current_preview_preset(preset_name)
                logger.debug(f"Updated state manager with preset: {preset_name}")

        except Exception as e:
            logger.error(f"Failed to apply ratio {preset_name}: {e}")

    # === PREVIEW ZOOM ACTION METHODS ===

    def _zoom_in_preview(self, widget):
        """Zoom in on preview image"""
        self._execute_preview_zoom_command("zoomIn()")

    def _zoom_out_preview(self, widget):
        """Zoom out on preview image"""
        self._execute_preview_zoom_command("zoomOut()")

    def _actual_size_preview(self, widget):
        """Show preview image at actual size"""
        self._execute_preview_zoom_command("actualSize()")

    def _zoom_to_fit_preview(self, widget):
        """Fit preview image to window"""
        self._execute_preview_zoom_command("fitToWindow()")

    def _zoom_to_selection_preview(self, widget):
        """Zoom to current selection (if any)"""
        self._execute_preview_zoom_command("zoomToCurrentSelection()")

    def _toggle_magnifier_preview(self, widget):
        """Toggle magnifier panel"""
        self._execute_preview_zoom_command("toggleMagnifier()")

    def _magnifier_zoom_in_preview(self, widget):
        """Zoom in on magnifier"""
        self._execute_preview_zoom_command("magnifierZoomIn()")

    def _magnifier_zoom_out_preview(self, widget):
        """Zoom out on magnifier"""
        self._execute_preview_zoom_command("magnifierZoomOut()")

    def _execute_preview_zoom_command(self, js_command: str):
        """Execute a JavaScript command in the preview image WebView"""
        try:
            # Access image_pane directly from main_window (5-column desktop layout)
            if hasattr(self, 'image_pane') and self.image_pane:
                if hasattr(self.image_pane, 'image_webview') and self.image_pane.image_webview:
                    webview = self.image_pane.image_webview
                    webview.evaluate_javascript(js_command)
                    logger.info(f"Executed zoom command: {js_command}")
                    return
                else:
                    logger.warning("Cannot execute zoom command: image_webview not available on image_pane")

            # Fallback: try navigation controller's current view (mobile or legacy)
            if hasattr(self, 'navigation_controller') and self.navigation_controller:
                current_view = self.navigation_controller.current_view
                if current_view:
                    # Try preview_image_pane attribute
                    if hasattr(current_view, 'preview_image_pane'):
                        image_pane = current_view.preview_image_pane
                        if image_pane and hasattr(image_pane, 'image_webview') and image_pane.image_webview:
                            image_pane.image_webview.evaluate_javascript(js_command)
                            logger.info(f"Executed zoom command via preview_image_pane: {js_command}")
                            return

                    # Try image_pane attribute
                    if hasattr(current_view, 'image_pane'):
                        image_pane = current_view.image_pane
                        if image_pane and hasattr(image_pane, 'image_webview') and image_pane.image_webview:
                            image_pane.image_webview.evaluate_javascript(js_command)
                            logger.info(f"Executed zoom command via image_pane: {js_command}")
                            return

            logger.warning("Cannot execute zoom command: no image WebView found")

        except Exception as e:
            logger.error(f"Failed to execute zoom command {js_command}: {e}")

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
            pane_count = 0
            for pane in layout_manager.panes:
                if pane._path_bar:
                    old_state = pane._path_bar_visible
                    pane._path_bar_visible = not pane._path_bar_visible
                    logger.info(f"🔧 Pane {pane_count}: Toggling path bar {old_state} → {pane._path_bar_visible}")
                    # Rebuild the pane content to show/hide path bar
                    pane._show_content()
                    pane_count += 1
            logger.info(f"🔧 Toggle Path Bar - toggled {pane_count} panes")
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

        Enhanced with StateManager integration for better state persistence.

        Saves:
        - Window size, position, and display information
        - Main layout state (column visibility, widths)
        - Preview layout state (split panes, contexts, viewer states, ratios)
        - Pane visibility tracking
        """
        try:
            # Get StateManager for enhanced state persistence
            state_manager = getattr(self.app, 'state_manager', None)

            # Fallback to app preferences if StateManager is not available
            if state_manager:
                logger.debug("Using StateManager for window state persistence")
                self._save_window_state_enhanced(state_manager)
            else:
                logger.debug("StateManager not available, using legacy preferences")
                self._save_window_state_legacy()

            logger.info("✅ Window state saved successfully")

        except Exception as e:
            logger.error(f"Failed to save window state: {e}")
            import traceback
            logger.error(traceback.format_exc())

    def _save_window_state_enhanced(self, state_manager):
        """
        Save window state using enhanced StateManager with comprehensive tracking.

        Args:
            state_manager: StateManager instance for state persistence

        Saves:
        - Layout state (column visibility, widths)
        - Session state (current collection/item, focus state)
        - Pane content state (what's loaded in each pane)

        Note: Window position/size handled by WindowStateTracker.
        Note: Preview viewer zoom/scroll requires async, saved periodically during session.
        """
        # Save current collection/item selection
        if hasattr(self, 'current_collection_id') and self.current_collection_id:
            state_manager.set_last_collection_id(self.current_collection_id)
            state_manager.set_library_selected_collection(self.current_collection_id)
            logger.debug(f"Saved last collection: {self.current_collection_id}")

        if hasattr(self, 'current_item_id') and self.current_item_id:
            state_manager.set_last_item_id(self.current_item_id)
            state_manager.set_preview_item_id(self.current_item_id)
            logger.debug(f"Saved last item: {self.current_item_id}")

        # Save preview visibility and focus state
        preview_view = self.views.get('output')
        if preview_view:
            is_visible = bool(getattr(self, 'current_item_id', None))
            state_manager.set_preview_visible(is_visible)

            if hasattr(self, 'focused_pane'):
                state_manager.set_active_pane(self.focused_pane)

        # Save main layout state (column visibility, widths) with StateManager
        if self.navigation_controller and hasattr(self.navigation_controller, 'layout_manager'):
            try:
                layout_state = self.navigation_controller.layout_manager.get_layout_state()
                state_manager.set_main_layout_state(layout_state)

                # Save individual pane visibility states
                if 'slots' in layout_state:
                    for slot in layout_state['slots']:
                        pane_name = slot.get('name', '').lower()
                        is_visible = slot.get('is_visible', True)
                        if pane_name:
                            state_manager.set_pane_visibility(pane_name, is_visible)

                logger.debug(f"Enhanced: Saved main layout state with {len(layout_state.get('slots', []))} slots")
            except Exception as e:
                logger.warning(f"Could not save enhanced main layout state: {e}")

        # Save collection pane state (which collection is open, selected item)
        if hasattr(self, 'current_collection_id'):
            state_manager.set_collection_pane_state(
                getattr(self, 'current_collection_id', None),
                getattr(self, 'current_item_id', None)
            )

    def _save_window_state_legacy(self):
        """
        Fallback method using legacy app preferences when StateManager is not available.
        """
        from fichero.config.core.app_preferences import get_app_preferences

        prefs = get_app_preferences(self.app)

        # NOTE: Window position and size are now handled by WindowStateTracker
        # (saved in save_session_state via window_state_tracker.save_all_states())
        # This method only saves layout state

        # Save layout states (legacy method)
        if self.navigation_controller and hasattr(self.navigation_controller, 'layout_manager'):
            try:
                layout_state = self.navigation_controller.layout_manager.get_layout_state()
                prefs._preferences['main_layout'] = layout_state
                prefs._save_preferences()
                logger.debug(f"Legacy: Saved main layout state: {len(layout_state.get('slots', []))} slots")
            except Exception as e:
                logger.warning(f"Could not save legacy main layout state: {e}")

        # Preview layout state now handled by UniversalLayoutManager + StateManager
        # No legacy preview layout saving needed

    def _save_display_info_macos(self, state_manager):
        """
        Save macOS display information for proper multi-monitor support.

        Args:
            state_manager: StateManager instance
        """
        try:
            # macOS-specific display detection using Cocoa
            import toga
            if hasattr(toga.platform, 'cocoa'):
                # Get main screen bounds for validation
                import rubicon.objc as objc
                from rubicon.objc.runtime import load_library

                # This is a placeholder for macOS display detection
                # In a real implementation, you'd use NSScreen APIs
                logger.debug("macOS display info saved (placeholder implementation)")
        except Exception as e:
            logger.debug(f"macOS display detection failed: {e}")

    async def restore_window_state(self):
        """
        Restore window state from saved preferences.

        Enhanced with StateManager integration for better state restoration.

        Restores:
        - Window size, position, and display validation
        - Main layout state (column visibility, widths)
        - Preview layout state (split panes, contexts, viewer states, ratios)
        - Pane visibility and focus states
        """
        try:
            # Get StateManager for enhanced state restoration
            state_manager = getattr(self.app, 'state_manager', None)

            # Use StateManager if available, otherwise fall back to legacy preferences
            if state_manager:
                logger.debug("Using StateManager for window state restoration")
                await self._restore_window_state_enhanced(state_manager)
            else:
                logger.debug("StateManager not available, using legacy preferences")
                await self._restore_window_state_legacy()

            logger.info("✅ Window state restored successfully")

        except Exception as e:
            logger.error(f"Failed to restore window state: {e}")
            import traceback
            logger.error(traceback.format_exc())

    def restore_window_position_and_size(self):
        """
        Restore window position and size from saved state.

        NOTE: This method is now mostly unused since position/size are set
        during window creation in _create_window(). Kept as a fallback.
        """
        try:
            if hasattr(self.app, 'window_state_tracker') and self.app.window_state_tracker:
                logger.debug("Restoring window position and size via tracker")
                self.app.window_state_tracker.restore_window_state("main", self.window)
            else:
                logger.warning("No window_state_tracker available for position restoration")
        except Exception as e:
            logger.error(f"Failed to restore window position/size: {e}")

    async def _restore_window_state_enhanced(self, state_manager):
        """
        Restore window state using enhanced StateManager with validation and error handling.

        Args:
            state_manager: StateManager instance
        """
        # NOTE: Window position and size are handled by WindowStateTracker
        # via restore_window_position_and_size() called from app.py AFTER the window is shown.
        # This method only restores layout and pane visibility state.

        # Restore main layout with pane visibility states
        if self.navigation_controller and hasattr(self.navigation_controller, 'layout_manager'):
            try:
                # Restore main layout state
                main_layout = state_manager.get_main_layout_state()
                if main_layout:
                    self.navigation_controller.layout_manager.restore_layout(main_layout)
                    logger.debug(f"Enhanced: Restored main layout: {len(main_layout.get('slots', []))} slots")

                # Restore individual pane visibility states
                pane_visibility = state_manager.get_all_pane_visibility()
                if pane_visibility:
                    # Map actual column name keys to layout manager column names
                    # IMPORTANT: Only use actual keys, not aliases, to avoid conflicts
                    # (e.g., if library=False but sidebar=True, we want library to win)
                    actual_keys = {
                        'library': 'Library',
                        'collection': 'Collection',
                        'previewimage': 'PreviewImage',
                        'previewmetadata': 'PreviewMetadata',
                        'adjust': 'Adjust',
                    }
                    # Legacy aliases - only used if actual key doesn't exist
                    legacy_aliases = {
                        'sidebar': ('library', 'Library'),
                        'preview': ('previewimage', 'PreviewImage'),
                        'inspector': ('adjust', 'Adjust'),
                    }

                    # First pass: apply actual column name keys
                    applied_columns = set()
                    for pane_key, column_name in actual_keys.items():
                        if pane_key in pane_visibility:
                            is_visible = pane_visibility[pane_key]
                            try:
                                layout_manager = self.navigation_controller.layout_manager
                                if hasattr(layout_manager, 'set_column_visibility'):
                                    layout_manager.set_column_visibility(column_name, is_visible)
                                    applied_columns.add(column_name)
                                    logger.debug(f"Enhanced: Set {column_name} visibility: {is_visible}")
                            except Exception as e:
                                logger.debug(f"Could not set {column_name} visibility: {e}")

                    # Second pass: apply legacy aliases only if actual key wasn't in state
                    for alias_key, (actual_key, column_name) in legacy_aliases.items():
                        if alias_key in pane_visibility and actual_key not in pane_visibility:
                            is_visible = pane_visibility[alias_key]
                            if column_name not in applied_columns:
                                try:
                                    layout_manager = self.navigation_controller.layout_manager
                                    if hasattr(layout_manager, 'set_column_visibility'):
                                        layout_manager.set_column_visibility(column_name, is_visible)
                                        logger.debug(f"Enhanced: Set {column_name} visibility (via alias {alias_key}): {is_visible}")
                                except Exception as e:
                                    logger.debug(f"Could not set {column_name} visibility: {e}")

            except Exception as e:
                logger.warning(f"Could not restore enhanced main layout: {e}")

        # After layout restoration, reapply the saved preview ratio preset
        # This ensures the correct 75/25 ratio is applied even if layout restoration overwrote flex values
        if state_manager:
            try:
                current_preset = state_manager.get_current_preview_preset()
                if current_preset:
                    # Use dummy widget for the ratio application
                    self._apply_preview_ratio(current_preset, None)
                    logger.info(f"✅ Reapplied preview ratio preset after restoration: {current_preset}")
                else:
                    # Fallback to wide_content if no preset saved
                    self._apply_preview_ratio("wide_content", None)
                    logger.info("✅ Applied default wide_content ratio after restoration")
            except Exception as e:
                logger.warning(f"Could not reapply preview ratios after restoration: {e}")
                # Fallback to wide_content
                try:
                    self._apply_preview_ratio("wide_content", None)
                    logger.info("✅ Applied fallback wide_content ratio after restoration error")
                except Exception as e2:
                    logger.error(f"Could not apply fallback ratio: {e2}")

    async def _restore_window_state_legacy(self):
        """
        Fallback method using legacy app preferences when StateManager is not available.
        """
        from fichero.config.core.app_preferences import get_app_preferences

        prefs = get_app_preferences(self.app)

        # NOTE: Window position and size are handled by WindowStateTracker
        # via restore_window_position_and_size() called from app.py AFTER the window is shown.
        # This method only restores layout state.

        # Restore layout states (legacy method)
        main_layout = prefs._preferences.get('main_layout')
        if main_layout and self.navigation_controller and hasattr(self.navigation_controller, 'layout_manager'):
            try:
                self.navigation_controller.layout_manager.restore_layout(main_layout)
                logger.debug(f"Legacy: Restored main layout: {len(main_layout.get('slots', []))} slots")
            except Exception as e:
                logger.warning(f"Could not restore legacy main layout: {e}")

        # After legacy layout restoration, apply default wide_content ratio
        # This ensures the correct 75/25 ratio is applied even if layout restoration overwrote flex values
        try:
            self._apply_preview_ratio("wide_content", None)
            logger.info("✅ Applied wide_content ratio after legacy restoration")
        except Exception as e:
            logger.error(f"Could not apply wide_content ratio after legacy restoration: {e}")

    async def save_session_state(self):
        """
        Save session state for restoration on next launch.

        Enhanced with better pane visibility tracking and ratio persistence.

        Saves:
        - Last selected collection ID and item ID
        - Preview pane visibility and focus state
        - Column visibility states and layout proportions
        - Preview layout ratios and presets
        """
        try:
            state_manager = getattr(self.app, 'state_manager', None)
            if not state_manager:
                logger.warning("No state_manager available for session state saving")
                return

            # Save current collection/item selection with validation
            if hasattr(self, 'current_collection_id') and self.current_collection_id:
                state_manager.set_last_collection_id(self.current_collection_id)
                logger.debug(f"Saved last collection: {self.current_collection_id}")

            if hasattr(self, 'current_item_id') and self.current_item_id:
                state_manager.set_last_item_id(self.current_item_id)
                logger.debug(f"Saved last item: {self.current_item_id}")

            # Enhanced preview pane visibility tracking
            preview_view = self.views.get('output')
            if preview_view:
                is_visible = bool(self.current_item_id)
                state_manager.set_preview_visible(is_visible)

                # Save active pane tracking
                if hasattr(self, 'focused_pane'):
                    state_manager.set_active_pane(self.focused_pane)

                logger.debug(f"Saved preview visible: {is_visible}, active pane: {getattr(self, 'focused_pane', 'unknown')}")

            # Enhanced layout state persistence with ratios
            if self.navigation_controller and hasattr(self.navigation_controller, 'layout_manager'):
                layout_state = self.navigation_controller.layout_manager.get_layout_state()
                state_manager.set_main_layout_state(layout_state)

                # Save individual pane visibility from layout state
                if 'slots' in layout_state:
                    for slot in layout_state['slots']:
                        pane_name = slot.get('name', '').lower()
                        is_visible = slot.get('is_visible', True)
                        if pane_name:
                            state_manager.set_pane_visibility(pane_name, is_visible)

            # Preview layout state now handled by UniversalLayoutManager + StateManager
            # No preview-specific session state saving needed

            # Save all window states via the window state tracker (macOS native)
            if hasattr(self.app, 'window_state_tracker') and self.app.window_state_tracker:
                self.app.window_state_tracker.save_all_states()
                logger.debug("Saved all window states via tracker")

            # Save preview viewer state (zoom, scroll, rotation) - restored on restart
            preview_view = self.views.get('output')
            if preview_view and hasattr(preview_view, 'preview_image_pane'):
                image_pane = preview_view.preview_image_pane
                if image_pane and hasattr(image_pane, 'get_viewer_state'):
                    try:
                        viewer_state = await image_pane.get_viewer_state()
                        if viewer_state:
                            state_manager.set_preview_viewer_state(viewer_state)
                            logger.debug(f"Saved preview viewer state: {viewer_state}")
                    except Exception as e:
                        logger.debug(f"Could not save preview viewer state: {e}")

            # Save metadata pane scroll position
            if preview_view and hasattr(preview_view, 'preview_metadata_pane'):
                metadata_pane = preview_view.preview_metadata_pane
                if metadata_pane and hasattr(metadata_pane, 'get_scroll_state'):
                    try:
                        scroll_state = metadata_pane.get_scroll_state()
                        if scroll_state:
                            # Save to pane_content.preview_metadata
                            pane_content = state_manager.get_pane_content('preview_metadata')
                            pane_content['scroll_position'] = scroll_state.get('scroll_y', 0)
                            state_manager.set_pane_content('preview_metadata', pane_content)
                            logger.debug(f"Saved metadata pane scroll state: {scroll_state}")
                    except Exception as e:
                        logger.debug(f"Could not save metadata pane scroll state: {e}")

            # Perform async save with error handling
            try:
                await state_manager.save_state()
                logger.info("✅ Enhanced session state saved successfully")
            except Exception as e:
                logger.error(f"Failed to save state to disk: {e}")
                # Continue execution even if disk save fails

        except Exception as e:
            logger.error(f"Failed to save session state: {e}")
            import traceback
            logger.error(traceback.format_exc())

    async def restore_session_state(self):
        """
        Restore session state from last launch.

        Restores:
        - Last selected collection (auto-navigates)
        - Last selected item (auto-loads in preview)
        - Preview pane visibility
        """
        import asyncio

        try:
            if not hasattr(self.app, 'state_manager'):
                logger.warning("No state_manager available")
                return

            # Give UI a moment to fully initialize
            await asyncio.sleep(0.5)

            state_manager = self.app.state_manager

            # Get last session state
            last_collection_id = state_manager.get_last_collection_id()
            last_item_id = state_manager.get_last_item_id()
            preview_was_visible = state_manager.get_preview_visible()

            logger.debug(f"Restoring session: collection={last_collection_id}, item={last_item_id}, preview_visible={preview_was_visible}")

            # Restore last collection
            if last_collection_id:
                try:
                    # Verify collection still exists
                    collection = self.app.library_manager.storage.get_collection(last_collection_id)
                    if collection:
                        logger.info(f"Restoring last collection: {collection.name}")

                        # Navigate to collection first (this will populate collection view)
                        if self.navigation_controller:
                            self.navigation_controller.navigate_to_collection(last_collection_id)
                            self.current_collection_id = last_collection_id

                        # Wait for views to fully initialize
                        await asyncio.sleep(1.0)  # Increased delay for widget initialization

                        # Select collection in library sidebar (after navigation completes)
                        try:
                            if self.cached_library_view and hasattr(self.cached_library_view, 'select_collection'):
                                self.cached_library_view.select_collection(last_collection_id)
                                logger.debug(f"✅ Selected collection in library sidebar")
                        except Exception as e:
                            logger.warning(f"Could not select collection in sidebar: {e}")

                        # Restore last item if available
                        if last_item_id and preview_was_visible:

                            # Verify item still exists
                            item = self.app.library_manager.storage.get_item(last_item_id)
                            if item:
                                logger.info(f"Restoring last item: {item.name}")

                                # Get output data
                                output_data = await self.app.library_manager.get_item_output_data(last_item_id)

                                # Load item in both views (same as _on_show_preview)
                                self.current_item_id = last_item_id

                                # NOTE: Do NOT show preview slot here - respect saved visibility
                                # The pane visibility was already restored by restore_window_state()
                                # Only load content into visible panes

                                # Load in both preview panes using centralized method
                                # Pass show_pane=False to respect saved visibility
                                await self._load_item_in_preview_panes(last_item_id, output_data, show_pane=False)
                                logger.info(f"✅ Restored preview for item: {last_item_id}")

                                # Restore preview viewer state (zoom, scroll) on startup
                                # Give the webview a moment to render
                                await asyncio.sleep(0.3)
                                saved_viewer_state = state_manager.get_preview_viewer_state()
                                if saved_viewer_state and saved_viewer_state.get('scale', 1.0) != 1.0:
                                    preview_view = self.views.get('output')
                                    if preview_view and hasattr(preview_view, 'preview_image_pane'):
                                        image_pane = preview_view.preview_image_pane
                                        if image_pane and hasattr(image_pane, 'restore_viewer_state'):
                                            try:
                                                await image_pane.restore_viewer_state(saved_viewer_state)
                                                logger.info(f"✅ Restored preview viewer state")
                                            except Exception as e:
                                                logger.debug(f"Could not restore viewer state: {e}")

                                # Restore metadata pane scroll position
                                saved_metadata_state = state_manager.get_pane_content('preview_metadata')
                                saved_scroll_position = saved_metadata_state.get('scroll_position', 0)
                                if saved_scroll_position > 0:
                                    preview_view = self.views.get('output')
                                    if preview_view and hasattr(preview_view, 'preview_metadata_pane'):
                                        metadata_pane = preview_view.preview_metadata_pane
                                        if metadata_pane and hasattr(metadata_pane, 'restore_scroll_state'):
                                            try:
                                                metadata_pane.restore_scroll_state({'scroll_y': saved_scroll_position})
                                                logger.info(f"✅ Restored metadata pane scroll position")
                                            except Exception as e:
                                                logger.debug(f"Could not restore metadata scroll state: {e}")

                                # Load in AdjustView
                                adjust_view = self.views.get('adjust')
                                if adjust_view:
                                    await adjust_view.load_item(last_item_id, output_data=output_data)
                                    logger.info(f"✅ Restored adjust view for item: {last_item_id}")

                                # Select item in collection view list
                                try:
                                    collection_view = self.views.get('collection') or self.cached_collection_view
                                    if collection_view and hasattr(collection_view, 'items_list') and collection_view.items_list:
                                        # Give widget extra time to settle
                                        await asyncio.sleep(0.3)
                                        if collection_view.items_list.select_item_by_id(last_item_id):
                                            logger.debug(f"✅ Selected item in collection view list")
                                        else:
                                            logger.debug(f"⚠️ Could not select item in collection view (not yet loaded or not found)")
                                except Exception as e:
                                    logger.warning(f"Could not select item in collection view: {e}")
                            else:
                                logger.info(f"Last item {last_item_id} no longer exists")
                    else:
                        logger.info(f"Last collection {last_collection_id} no longer exists")

                except Exception as e:
                    logger.warning(f"Could not restore last collection/item: {e}")

            logger.info("✅ Session state restored successfully")

        except Exception as e:
            logger.error(f"Failed to restore session state: {e}")
            import traceback
            logger.error(traceback.format_exc())

    def _schedule_debounced_save(self):
        """
        Schedule debounced save of session state.

        Cancels any existing save timer and creates a new one.
        State will be saved 2 seconds after last selection change.
        """
        import asyncio

        # Cancel existing timer if any
        if self._save_state_timer:
            self._save_state_timer.cancel()

        # Schedule new save
        async def delayed_save():
            try:
                await asyncio.sleep(2.0)  # Wait 2 seconds
                await self.save_session_state()
                logger.debug("⏱️ Debounced state save completed")
            except asyncio.CancelledError:
                logger.debug("⏱️ Debounced state save cancelled")
            except Exception as e:
                logger.error(f"Failed in debounced save: {e}")

        self._save_state_timer = asyncio.create_task(delayed_save())

    # ===== PUBLIC INTERFACE =====

    def show(self):
        """Show the main window"""
        try:
            if self.window:
                self.window.show()
                logger.info("Main window shown")
        except Exception as e:
            logger.error(f"Failed to show main window: {e}")

    async def close(self):
        """Close the main window with proper cleanup"""
        try:
            # Save session state before closing (async)
            await self.save_session_state()

            # Save window state before closing
            self.save_window_state()

            # Clean up all cached views before closing
            self._cleanup_all_cached_views()

            # Ensure final state sync with StateManager
            if self.state_manager:
                try:
                    # Final state sync now handled by UniversalLayoutManager + StateManager
                    logger.debug("Final StateManager sync - using universal layout system")
                except Exception as e:
                    logger.warning(f"Final StateManager sync failed: {e}")

            if self.window:
                self.window.close()
                logger.info("Main window closed with enhanced state cleanup")
        except Exception as e:
            logger.error(f"Failed to close main window: {e}")

    # Phase 1: Preview integration event handlers

    async def _load_item_in_preview_panes(self, item_id: str, output_data: dict = None, show_pane: bool = True):
        """
        Load item in both preview panes (PreviewView and AdjustView).

        This is the simplified, centralized method for loading items in preview panes.
        It follows the pattern from restore_session_state() - direct method calls with
        proper error handling.

        Args:
            item_id: The item ID to load
            output_data: Optional pre-fetched output data (if None, will fetch)
            show_pane: Whether to show the preview slot (default True).
                       Set to False when restoring session to respect saved visibility.
        """
        try:
            logger.info(f"📊 Loading item {item_id} in preview panes")

            # Fetch output data if not provided
            if output_data is None and hasattr(self.app, 'library_manager'):
                output_data = await self.app.library_manager.get_item_output_data(item_id)
                if output_data and output_data.get('has_outputs'):
                    steps_count = len(output_data.get('processing_steps', []))
                    logger.info(f"📊 Fetched output data: {steps_count} processing steps")

            # Show preview slot on desktop (unless restoring session)
            if show_pane and not self.is_mobile and hasattr(self, 'preview_slot_id'):
                if (hasattr(self, 'navigation_controller') and
                    self.navigation_controller and
                    hasattr(self.navigation_controller, 'layout_manager') and
                    self.navigation_controller.layout_manager):
                    self.navigation_controller.layout_manager.show_slot(self.preview_slot_id)

            # Load in both preview panes (ImagePane and TranscriptionPane)
            # Load in ImagePane - pass metadata for direct access to paths
            if hasattr(self, 'image_pane') and self.image_pane:
                # Get metadata if available from the current selection
                item_metadata = None
                if hasattr(self, '_current_selection_metadata'):
                    item_metadata = self._current_selection_metadata
                await self.image_pane.load_item(item_id, output_data=output_data, item_metadata=item_metadata)
                logger.info(f"✅ Loaded item {item_id} in ImagePane")
            else:
                logger.warning("ImagePane not available")

            # Load in MetadataPane
            if hasattr(self, 'metadata_pane') and self.metadata_pane:
                await self.metadata_pane.load_item(item_id, output_data=output_data)
                logger.info(f"✅ Loaded item {item_id} in MetadataPane")
            else:
                logger.warning("MetadataPane not available")

            # Load in AdjustView
            adjust_view = self.views.get('adjust')
            if adjust_view:
                await adjust_view.load_item(item_id, output_data=output_data)
                logger.info(f"✅ Loaded item {item_id} in AdjustView")

            # Track current item for state persistence
            self.current_item_id = item_id

            # Trigger debounced state save
            self._schedule_debounced_save()

            # Update status bar to show focused pane
            self._update_focused_pane_display('output')

        except Exception as e:
            logger.error(f"Failed to load item in preview panes: {e}", exc_info=True)

    def _handle_preview_selection_changed(self, event):
        """
        Handle SELECTION_CHANGED events to update preview pane.

        Responds to selections from collection view and library sidebar,
        automatically loading the selected item in the preview/inspector pane.
        """
        try:
            # Extract event data
            view_id = event.data.get('view_id', '')
            item_ids = event.data.get('new_selection', [])
            metadata = event.data.get('metadata', [])

            logger.info(f"🔍 Preview selection change from view: {view_id}, items: {len(item_ids)}")

            # Only respond to collection view selections
            if view_id != 'collection':
                logger.debug(f"Ignoring selection from {view_id}")
                return

            # If no selection, clear preview
            if not item_ids or not metadata:
                logger.info("Empty selection, clearing preview")
                self._clear_preview()
                return

            # Get item ID from first selected item
            first_item_meta = metadata[0]
            item_id = first_item_meta.get('item_id')  # Match key from collection_view metadata

            if not item_id:
                logger.warning(f"No item ID in selection metadata: {first_item_meta}")
                return

            # Store current selection metadata for preview panes
            self._current_selection_metadata = first_item_meta

            # Note: Using dedicated preview panes now - no need for cached_output_view

            # Show preview pane
            if self.is_mobile:
                pass  # Preview panes already visible in 5-column layout
            else:
                pass  # Preview panes already visible in 5-column layout

            # Update toolbar
            if not self.is_mobile:
                self._update_toolbar_for_output_view(context='normal')

            # Load item in both preview panes with output data
            # Fetch output_data first to avoid duplicate queries and ensure adjust view gets full metadata
            import asyncio
            asyncio.create_task(self._load_preview_with_data(item_id))

        except Exception as e:
            logger.error(f"Failed to handle preview selection change: {e}", exc_info=True)

    async def _load_preview_with_data(self, item_id):
        """
        Helper to fetch output_data and load preview panes.

        This ensures we pass output_data to _load_item_in_preview_panes() to avoid
        duplicate database queries and ensure adjust view gets full metadata.
        """
        try:
            # Fetch output data from library manager
            output_data = None
            if hasattr(self.app, 'library_manager') and self.app.library_manager:
                output_data = await self.app.library_manager.get_item_output_data(item_id)
                if output_data and output_data.get('has_outputs'):
                    logger.info(f"📦 Fetched output data for preview: {len(output_data.get('processing_steps', []))} steps")
                else:
                    logger.debug(f"No output data available for item {item_id}")

            # Load preview panes with the fetched data
            await self._load_item_in_preview_panes(item_id, output_data)

        except Exception as e:
            logger.error(f"Failed to load preview with data: {e}", exc_info=True)

    def _clear_preview(self):
        """Clear the preview pane when no item is selected"""
        # Simplified preview keeps showing last item (no need to clear)
        logger.debug("📤 Preview keeps showing last selected item (no clearing needed)")

    def _on_processing_completed_for_preview(self, event):
        """
        Reload preview when processing completes for the currently displayed item.

        When a user processes an item that's currently shown in the preview panes,
        this handler fetches the fresh output data (including new transcription)
        and reloads both preview panes to display the updated content.

        Args:
            event: processing_completed event with item_id and collection_id
        """
        try:
            item_id = event.data.get("item_id")
            collection_id = event.data.get("collection_id")

            if not item_id:
                logger.debug("Processing completed but no item_id in event")
                return

            # Only reload if this is the currently displayed item in preview
            if not (hasattr(self, 'current_item_id') and
                    self.current_item_id == item_id and
                    hasattr(self, 'cached_output_view') and
                    self.cached_output_view):
                logger.debug(f"Processing completed for {item_id}, but not currently displayed in preview")
                return

            logger.info(f"🔄 Reloading preview after processing completed: {item_id}")

            # Fetch fresh output data from library (includes new transcription)
            if not hasattr(self.app, 'library_manager'):
                logger.warning("Library manager not available for preview reload")
                return

            library_manager = self.app.library_manager
            item = library_manager.storage.get_item(item_id)

            if not item:
                logger.warning(f"Item {item_id} not found in library")
                return

            # Build fresh output_data structure
            output_data = None
            if item.metadata.get('output_path'):
                output_path = item.metadata['output_path']
                logger.info(f"📊 Fetching fresh outputs from: {output_path}")

                output_data = {
                    'has_outputs': True,
                    'output_path': output_path,
                    'item_id': item_id,
                    'collection_id': collection_id
                }

            # Reload the preview view with fresh data (async task)
            import asyncio
            asyncio.create_task(self.cached_output_view.load_item(
                item_id=item_id,
                output_data=output_data
            ))

            logger.info(f"✅ Preview reload scheduled for {item_id}")

        except Exception as e:
            logger.error(f"Failed to reload preview after processing: {e}", exc_info=True)

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

        # Enhanced: Update StateManager active pane tracking
        if self.state_manager:
            try:
                self.state_manager.set_active_pane(view_id)
                logger.debug(f"StateManager active pane updated to: {view_id}")
            except Exception as e:
                logger.debug(f"Could not update StateManager active pane: {e}")


    def get_window_info(self) -> Dict[str, Any]:
        """Get window information for debugging with enhanced StateManager info"""
        return {
            "is_mobile": self.is_mobile,
            "current_view_key": self.current_view_key,
            "has_navigation_controller": self.navigation_controller is not None,
            "has_state_manager": self.state_manager is not None,
            "window_size": self._get_window_size(),
            "state_manager_info": self._get_state_manager_info()
        }

    def _get_state_manager_info(self) -> Dict[str, Any]:
        """Get StateManager information for debugging and validation"""
        if not self.state_manager:
            return {"available": False, "reason": "No StateManager instance"}

        try:
            return {
                "available": True,
                "last_collection_id": self.state_manager.get_last_collection_id(),
                "preview_visible": self.state_manager.get_preview_visible(),
                "current_preset": self.state_manager.get_current_preview_preset(),
                "window_size": self.state_manager.get_window_size(),
                "pane_visibility": self.state_manager.get_all_pane_visibility()
            }
        except Exception as e:
            return {"available": False, "reason": f"StateManager error: {e}"}

    def ensure_state_manager_connectivity(self):
        """Ensure all components have proper StateManager connectivity"""
        if not self.state_manager:
            logger.warning("StateManager not available - enhanced state features disabled")
            return False

        try:
            # PreviewView no longer has layout_manager - using UniversalLayoutManager + StateManager
            logger.debug("StateManager integration uses universal layout system")

            # Test StateManager connectivity
            test_value = self.state_manager.get_window_state_change_count()
            logger.debug(f"StateManager connectivity verified - state changes: {test_value}")
            return True

        except Exception as e:
            logger.error(f"StateManager connectivity check failed: {e}")
            return False