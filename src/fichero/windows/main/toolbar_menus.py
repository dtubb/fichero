"""
Toolbar Menu Definitions for Main Window

Defines the 4 initial toolbar dropdown menus:
1. View Menu - Editor layout commands
2. Editor Layout Menu - Quick access to split layouts
3. Share/Export Menu - Export-related commands
4. Ellipsis Menu (...) - Empty initially (infrastructure only)

These are registered with ToolbarMenuManager and appear in the macOS toolbar.
"""

import logging
from gettext import gettext as _
from fichero.shared.commands.toolbar_menu import ToolbarMenu

logger = logging.getLogger(__name__)


def create_toolbar_menus():
    """
    Create all toolbar menus for the main window

    Returns:
        List of ToolbarMenu instances
    """
    menus = []

    # NOTE: Individual toggle buttons are now implemented as toolbar commands
    # instead of dropdown menus. See main_window.py _register_view_commands()
    # for the view.toggle_sidebar, view.toggle_collection, and view.toggle_inspector
    # FicheroCommand definitions with show_in_titlebar=True

    # 2. Editor Layout Menu - Split layout commands
    # Note: Commented out because split commands are now in View > Editor Layout submenu
    # The new commands are output.split_right, output.split_down, etc.
    # layout_menu = ToolbarMenu(
    #     id="toolbar.layout_menu",
    #     label=_("Layout"),
    #     icon="NSIconViewTemplate",  # System icon for layout/grid
    #     display_mode="icon",
    #     items=[
    #         "output.split_right",
    #         "output.split_down",
    #     ],
    #     order=1,
    #     context="main",
    #     platform="darwin",
    #     tooltip=_("Split panes")
    # )
    # menus.append(layout_menu)
    # logger.debug("Created Layout menu")

    # 3. Share/Export Menu - Export commands
    # Note: Commented out until export commands are implemented
    # Uncomment and populate items list when ready
    # share_menu = ToolbarMenu(
    #     id="toolbar.share_menu",
    #     label=_("Share"),
    #     icon="NSShareTemplate",  # System share icon
    #     display_mode="icon",
    #     items=[
    #         "file.export_pdf",
    #         "file.export_word",
    #         "file.export_images",
    #     ],
    #     order=2,
    #     context="main",
    #     platform="darwin",
    #     tooltip=_("Export and share")
    # )
    # menus.append(share_menu)
    # logger.debug("Created Share menu")

    # 4. Ellipsis Menu (...) - Infrastructure only, empty initially
    # Uncomment and populate items list when ready
    # ellipsis_menu = ToolbarMenu(
    #     id="toolbar.ellipsis_menu",
    #     label="...",
    #     icon="NSMenuOnStateTemplate",  # System icon for more options
    #     display_mode="icon",
    #     items=[
    #         "view.toggle_markup_toolbar",
    #         "view.toggle_path_bar",
    #         "view.toggle_status_bar",
    #     ],
    #     order=3,
    #     context="main",
    #     platform="darwin",
    #     tooltip=_("More options")
    # )
    # menus.append(ellipsis_menu)
    # logger.debug("Created Ellipsis menu")

    logger.info(f"Created {len(menus)} toolbar menus")
    return menus


def register_toolbar_menus(toolbar_menu_manager):
    """
    Register all toolbar menus with the ToolbarMenuManager

    Args:
        toolbar_menu_manager: ToolbarMenuManager instance
    """
    try:
        menus = create_toolbar_menus()

        for menu in menus:
            toolbar_menu_manager.register_menu(menu)

        logger.info(f"✅ Registered {len(menus)} toolbar menus")

    except Exception as e:
        logger.error(f"Failed to register toolbar menus: {e}")
        import traceback
        logger.error(traceback.format_exc())


__all__ = ['create_toolbar_menus', 'register_toolbar_menus']
