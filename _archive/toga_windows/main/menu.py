"""
Native macOS menu bar using NSMenu.

Declarative menu definitions with i18n support using dataclasses.
Only includes app-specific items; macOS adds system items automatically.

Usage:
    menu = AppMenu(handler=main_window)
    menu.build()
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from rubicon.objc import ObjCClass, SEL, objc_method, objc_property, NSObject

from fichero.ui.i18n import _

logger = logging.getLogger(__name__)

# ObjC Classes
NSApplication = ObjCClass("NSApplication")
NSMenu = ObjCClass("NSMenu")
NSMenuItem = ObjCClass("NSMenuItem")

# Modifier keys
SHIFT = 1 << 17
CTRL = 1 << 18
OPT = 1 << 19
CMD = 1 << 20


# =============================================================================
# Dataclasses - Pythonic menu definitions
# =============================================================================

@dataclass(frozen=True)
class Item:
    """A menu item."""
    label: str
    handler: str = ""
    key: str = ""
    mods: int = 0


@dataclass(frozen=True)
class Submenu:
    """A submenu with nested items."""
    label: str
    items: tuple = field(default_factory=tuple)


@dataclass(frozen=True)
class Menu:
    """A top-level menu."""
    title: str
    items: tuple = field(default_factory=tuple)


# Separator constant
SEP = None


# =============================================================================
# Menu Definitions
# =============================================================================

MENU_APP = Menu("Fichero", (
    Item("About Fichero", "about"),
    SEP,
    Item("Settings...", "open_settings", ","),
    SEP,
    Item("Plans...", "show_plans", "l", SHIFT),
    Item("Prompts...", "show_prompts", "p", SHIFT),
    SEP,
    Submenu("Services", ()),  # Special: macOS Services menu
    SEP,
    Item("Hide Fichero", "hide_app", "h"),
    Item("Hide Others", "hide_others", "h", OPT),
    Item("Show All", "show_all"),
    SEP,
    Item("Quit Fichero", "quit_app", "q"),
))

MENU_FILE = Menu("File", (
    Item("New Collection", "new_collection", "n"),
    Item("New External Collection...", "new_collection_from_folder"),
    SEP,
    Item("Delete Collection", "delete_collection", "\x7f"),  # Backspace
    SEP,
    Submenu("Import", (
        Item("File...", "import_file", "i"),
        Item("Folder...", "import_folder", "i", SHIFT),
        Item("URL...", "import_url", "i", OPT),
        SEP,
        Item("Link File...", "link_file"),
        Item("Link Folder...", "link_folder"),
    )),
    SEP,
    Item("Close", "close_window", "w"),
    Item("Close All", "close_all", "w", OPT),
))

MENU_EDIT = Menu("Edit", (
    Item("Undo", "undo", "z"),
    Item("Redo", "redo", "z", SHIFT),
    SEP,
    Item("Cut", "cut", "x"),
    Item("Copy", "copy", "c"),
    Item("Paste", "paste", "v"),
    Item("Paste and Match Style", "paste_match_style", "v", OPT | SHIFT),
    Item("Delete", "delete"),
    SEP,
    Item("Select All", "select_all", "a"),
))

MENU_VIEW = Menu("View", (
    Item("Library", "toggle_library", "1", OPT),
    Item("Collection", "toggle_collection", "2", OPT),
    Item("Preview Image", "toggle_preview_image", "3", OPT),
    Item("Preview Metadata", "toggle_preview_metadata", "4", OPT),
    Item("Info", "toggle_inspector", "5", OPT),
    SEP,
    Item("Cycle Preview Width", "cycle_ratios", "r"),
    SEP,
    Item("Actual Size", "zoom_actual_size", "0"),
    Item("Zoom In", "zoom_in", "="),
    Item("Zoom Out", "zoom_out", "-"),
    Item("Zoom to Fit", "zoom_to_fit", "9"),
    Item("Zoom to Selection", "zoom_to_selection", "8", SHIFT),
    SEP,
    Item("Magnifier Zoom In", "magnifier_zoom_in", "=", SHIFT),
    Item("Magnifier Zoom Out", "magnifier_zoom_out", "-", SHIFT),
    Item("Show Magnifier", "toggle_magnifier", "`"),
    SEP,
    Item("Show Markup Toolbar", "toggle_markup_toolbar", "t", SHIFT),
    Item("Show Path Bar", "toggle_path_bar", "p", OPT),
    Item("Show Status Bar", "toggle_status_bar", "/"),
))

MENU_GO = Menu("Go", (
    Item("Next Item", "go_next"),
    Item("Previous Item", "go_previous"),
))

MENU_TOOLS = Menu("Tools", (
    Item("Show Inspector...", "show_inspector", "i", SHIFT),
    SEP,
    Item("Process", "process", "\r"),  # Return
    SEP,
    Submenu("Tools", (
        Item("Crop Images", "process_crop"),
        Item("Rotate Images", "process_rotate"),
        Item("Split Images", "process_split"),
        Item("Enhance Images", "process_enhance"),
        Item("Remove Background", "process_remove_background"),
        Item("Prepare Images", "process_prepare"),
        SEP,
        Item("Segment Images", "process_segment"),
        Item("Recombine Segments", "process_recombine"),
        SEP,
        Item("Transcribe", "process_transcribe"),
        Item("Describe", "process_describe"),
        Item("LLM Catalogue", "process_llm"),
        SEP,
        Item("Convert to Word", "process_convert_word"),
    )),
))

MENU_WINDOW = Menu("Window", (
    Item("Activity", "show_activity"),
    Item("Minimize", "minimize", "m"),
    Item("Output", "show_output"),
    Item("Processing", "show_processing"),
))

MENU_HELP = Menu("Help", (
    Item("Visit homepage", "visit_homepage"),
))

# Complete menu bar
MENUS = (MENU_APP, MENU_FILE, MENU_EDIT, MENU_VIEW, MENU_GO, MENU_TOOLS, MENU_WINDOW, MENU_HELP)


# =============================================================================
# Delegate
# =============================================================================

class _Delegate(NSObject):
    """Menu action handler."""
    _menu = objc_property(object, weak=True)

    @objc_method
    def dispatch_(self, sender):
        handler = str(sender.representedObject)
        if self._menu and self._menu.handler:
            if method := getattr(self._menu.handler, handler, None):
                try:
                    method()
                except Exception as e:
                    logger.error(f"Menu error [{handler}]: {e}")
            else:
                logger.warning(f"No handler: {handler}")

    @objc_method
    def validateMenuItem_(self, item) -> bool:
        return bool(item.isEnabled())


# =============================================================================
# AppMenu
# =============================================================================

class AppMenu:
    """Native macOS menu bar."""

    def __init__(self, handler):
        self.handler = handler
        self._delegate = _Delegate.alloc().init()
        self._delegate._menu = self
        self._items: dict[str, NSMenuItem] = {}

    def build(self):
        """Build and install the menu bar."""
        app = NSApplication.sharedApplication
        main = NSMenu.alloc().initWithTitle_("")

        for menu in MENUS:
            main.addItem_(self._build_menu(menu))

        app.mainMenu = main
        logger.info(f"Menu bar built ({len(MENUS)} menus)")

    def _build_menu(self, menu: Menu) -> NSMenuItem:
        """Build a menu from dataclass definition."""
        app = NSApplication.sharedApplication
        title = menu.title if menu.title == "Fichero" else _(menu.title)
        ns_menu = NSMenu.alloc().initWithTitle_(title)
        ns_menu.autoenablesItems = False

        for entry in menu.items:
            if entry is None:
                ns_menu.addItem_(NSMenuItem.separatorItem())

            elif isinstance(entry, Submenu):
                # Handle Services menu specially
                if entry.label == "Services":
                    mi = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                        _("Services"), None, ""
                    )
                    svc = NSMenu.alloc().initWithTitle_("Services")
                    mi.submenu = svc
                    app.setServicesMenu_(svc)
                    ns_menu.addItem_(mi)
                else:
                    # Regular submenu
                    mi = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                        _(entry.label), None, ""
                    )
                    sub = NSMenu.alloc().initWithTitle_(_(entry.label))
                    sub.autoenablesItems = False
                    for sub_item in entry.items:
                        if sub_item is None:
                            sub.addItem_(NSMenuItem.separatorItem())
                        else:
                            sub.addItem_(self._build_item(sub_item))
                    mi.submenu = sub
                    ns_menu.addItem_(mi)

            elif isinstance(entry, Item):
                ns_menu.addItem_(self._build_item(entry))

        # Register system menus
        if menu.title == "Window":
            app.setWindowsMenu_(ns_menu)
        elif menu.title == "Help":
            app.setHelpMenu_(ns_menu)

        container = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, None, "")
        container.submenu = ns_menu
        return container

    def _build_item(self, item: Item) -> NSMenuItem:
        """Build a single menu item."""
        mi = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            _(item.label), SEL("dispatch:"), item.key or ""
        )
        mi.target = self._delegate
        mi.representedObject = item.handler
        if item.mods:
            mi.keyEquivalentModifierMask = CMD | item.mods
        self._items[item.handler] = mi
        return mi

    def set_enabled(self, handler: str, enabled: bool):
        """Enable/disable a menu item."""
        if mi := self._items.get(handler):
            mi.setEnabled_(enabled)
