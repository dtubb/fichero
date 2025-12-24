"""
Native macOS toolbar using NSToolbar.

Declarative toolbar definition with i18n support and Apple HIG compliance.
Uses dataclasses for type-safe, self-documenting item definitions.

Usage:
    toolbar = AppToolbar(handler=main_window, on_search=handler.search)
    toolbar.attach_to_window(window)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable, Optional

from rubicon.objc import ObjCClass, SEL, objc_method, NSObject, at

from fichero.ui.i18n import _

logger = logging.getLogger(__name__)

# ObjC Classes
NSToolbar = ObjCClass("NSToolbar")
NSToolbarItem = ObjCClass("NSToolbarItem")
NSSearchToolbarItem = ObjCClass("NSSearchToolbarItem")
NSMenuToolbarItem = ObjCClass("NSMenuToolbarItem")
NSImage = ObjCClass("NSImage")
NSMenu = ObjCClass("NSMenu")
NSMenuItem = ObjCClass("NSMenuItem")
NSImageSymbolConfiguration = ObjCClass("NSImageSymbolConfiguration")
NSColor = ObjCClass("NSColor")

# Standard toolbar identifiers
FLEX = "NSToolbarFlexibleSpaceItem"
SIDEBAR_SEPARATOR = "NSToolbarSidebarTrackingSeparatorItemIdentifier"

# Display modes
DISPLAY_ICON_ONLY = 2
DISPLAY_ICON_AND_LABEL = 0
DISPLAY_LABEL_ONLY = 1

# Separator (None = separator in menus)
SEP = None


# =============================================================================
# Dataclasses - Pythonic, type-safe item definitions
# =============================================================================

@dataclass(frozen=True)
class MenuItem:
    """A dropdown menu item."""
    label: str
    icon: str
    handler: str


@dataclass(frozen=True)
class Button:
    """A toolbar button."""
    id: str
    icon: str
    label: str
    tooltip: str = ""


@dataclass(frozen=True)
class Dropdown:
    """A toolbar dropdown menu."""
    id: str
    icon: str
    label: str
    tooltip: str
    items: tuple[MenuItem | None, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class Search:
    """A search field."""
    id: str = "search"
    label: str = "Search"


# =============================================================================
# SF Symbol Styling
# =============================================================================

def _symbol(name: str, label: str):
    """Create SF Symbol with small scale and blue tint."""
    img = NSImage.imageWithSystemSymbolName_accessibilityDescription_(name, label)
    if not img:
        return None
    scale = NSImageSymbolConfiguration.configurationWithScale_(1)  # Small
    color = NSImageSymbolConfiguration.configurationWithHierarchicalColor_(
        NSColor.systemBlueColor
    )
    return img.imageWithSymbolConfiguration_(
        scale.configurationByApplyingConfiguration_(color)
    )


# =============================================================================
# Toolbar Layout - Clear, readable, type-checked
# =============================================================================

IMPORT_MENU = (
    MenuItem("File...", "doc", "import_file"),
    MenuItem("Folder...", "folder", "import_folder"),
    MenuItem("URL...", "link", "import_url"),
    SEP,
    MenuItem("Link File...", "doc.badge.plus", "link_file"),
    MenuItem("Link Folder...", "folder.badge.plus", "link_folder"),
)

TOOLBAR = (
    Button("toggle_library", "sidebar.left", "Library", "Toggle Library Sidebar"),
    SIDEBAR_SEPARATOR,  # Sidebar toggle appears LEFT of window title
    Button("toggle_collection", "square.grid.2x2", "Collection", "Toggle Collection"),
    FLEX,
    Search(),
    FLEX,
    Dropdown("import_menu", "square.and.arrow.down", "Import", "Import Files", IMPORT_MENU),
    Button("settings", "gearshape", "Settings"),
    Button("show_inspector", "info.circle", "Info", "Show Inspector"),
    Button("process", "sparkles", "Process", "Process Selected Items"),
)


# =============================================================================
# Delegate
# =============================================================================

class _ToolbarDelegate(NSObject):
    """NSToolbar delegate."""
    # Instance attributes set by AppToolbar.__init__
    items: dict
    handler: object
    on_search: Callable | None

    @objc_method
    def toolbarDefaultItemIdentifiers_(self, toolbar):
        return at([x if isinstance(x, str) else x.id for x in TOOLBAR])

    @objc_method
    def toolbarAllowedItemIdentifiers_(self, toolbar):
        return at([x if isinstance(x, str) else x.id for x in TOOLBAR])

    @objc_method
    def toolbar_itemForItemIdentifier_willBeInsertedIntoToolbar_(
        self, toolbar, identifier, insert: bool
    ):
        return _ToolbarDelegate.items.get(str(identifier))

    @objc_method
    def handleAction_(self, sender):
        if method := getattr(_ToolbarDelegate.handler, str(sender.itemIdentifier), None):
            try:
                method()
            except Exception as e:
                logger.error(f"Action error: {e}")

    @objc_method
    def handleMenu_(self, sender):
        if method := getattr(_ToolbarDelegate.handler, str(sender.representedObject), None):
            try:
                method()
            except Exception as e:
                logger.error(f"Menu error: {e}")

    @objc_method
    def searchChanged_(self, sender):
        if _ToolbarDelegate.on_search:
            try:
                _ToolbarDelegate.on_search(str(sender.stringValue))
            except Exception as e:
                logger.error(f"Search error: {e}")


# =============================================================================
# Item Builders
# =============================================================================

def _build(item, delegate):
    """Build native toolbar item from dataclass."""
    match item:
        case Button(id=id_, icon=icon, label=label, tooltip=tooltip):
            ti = NSToolbarItem.alloc().initWithItemIdentifier(id_)
            ti.label = _(label)
            ti.paletteLabel = _(label)
            ti.toolTip = _(tooltip or label)
            ti.setTarget_(delegate)
            ti.setAction_(SEL("handleAction:"))
            ti.setEnabled_(True)
            if img := _symbol(icon, _(label)):
                ti.setImage(img)
            return ti

        case Search(id=id_, label=label):
            ti = NSSearchToolbarItem.alloc().initWithItemIdentifier(id_)
            ti.searchField.placeholderString = _(label)
            ti.searchField.setTarget_(delegate)
            ti.searchField.setAction_(SEL("searchChanged:"))
            return ti

        case Dropdown(id=id_, icon=icon, label=label, tooltip=tooltip, items=items):
            ti = NSMenuToolbarItem.alloc().initWithItemIdentifier(id_)
            ti.label = _(label)
            ti.paletteLabel = _(label)
            ti.toolTip = _(tooltip)
            ti.showsIndicator = True
            if img := _symbol(icon, _(label)):
                ti.setImage(img)

            menu = NSMenu.alloc().initWithTitle_(_(label))
            for mi in items:
                if mi is None:
                    menu.addItem_(NSMenuItem.separatorItem())
                else:
                    nmi = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                        _(mi.label), SEL("handleMenu:"), ""
                    )
                    nmi.target = delegate
                    nmi.representedObject = mi.handler
                    if img := _symbol(mi.icon, _(mi.label)):
                        nmi.image = img
                    menu.addItem_(nmi)
            ti.menu = menu
            return ti

        case _:
            return None


# =============================================================================
# AppToolbar
# =============================================================================

class AppToolbar:
    """Native macOS toolbar with SF Symbols."""

    def __init__(self, handler, on_search: Optional[Callable[[str], None]] = None):
        _ToolbarDelegate.handler = handler
        _ToolbarDelegate.on_search = on_search
        _ToolbarDelegate.items = {}

        self._delegate = _ToolbarDelegate.alloc().init()

        # Build items from dataclasses
        for item in TOOLBAR:
            if isinstance(item, str):
                continue
            if built := _build(item, self._delegate):
                _ToolbarDelegate.items[item.id] = built

        self._toolbar = NSToolbar.alloc().initWithIdentifier("com.fichero.toolbar")
        self._toolbar.setDelegate_(self._delegate)
        self._toolbar.setDisplayMode_(DISPLAY_ICON_ONLY)
        self._toolbar.setAllowsUserCustomization_(True)
        self._toolbar.setAutosavesConfiguration_(True)

        logger.info(f"Toolbar created ({len(_ToolbarDelegate.items)} items)")

    @property
    def native(self):
        return self._toolbar

    def attach_to_window(self, window):
        """Attach to Toga window."""
        try:
            native = window._impl.native
            native.setToolbar(self._toolbar)
            self._toolbar.setVisible(True)
            logger.info("Toolbar attached")
        except Exception as e:
            logger.error(f"Attach failed: {e}")

    def set_enabled(self, id: str, enabled: bool):
        """Enable/disable item."""
        if item := _ToolbarDelegate.items.get(id):
            item.setEnabled_(enabled)
