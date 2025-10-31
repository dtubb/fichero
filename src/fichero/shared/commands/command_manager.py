"""
CommandManager - Platform-Adaptive Command Management

Manages command registration and platform-specific presentation:
- Desktop: Registers commands with Toga's native menu system (with keyboard shortcuts)
- Mobile: Stores commands for custom toolbar use only (no native menus)

This replaces the old MenuManager with a more comprehensive system.
"""

import toga
import logging
from typing import Dict, Optional
from fichero.shared.commands.command import FicheroCommand
from fichero.shared.commands.registry import CommandRegistry

logger = logging.getLogger(__name__)


class CommandManager:
    """
    Platform-adaptive command manager

    Desktop:
      - Registers commands as toga.Command → added to app.commands → appears in native menus
      - Keyboard shortcuts work automatically
      - Commands can also be used in custom toolbars

    Mobile:
      - Commands stored in registry only
      - No native menus (mobile doesn't use them)
      - Commands exposed through custom toolbars only
    """

    _instance: Optional['CommandManager'] = None

    def __init__(self, app):
        """Initialize the command manager"""
        self.app = app
        self.is_mobile = getattr(app, 'is_mobile', False)
        self._toga_commands: Dict[str, toga.Command] = {}  # Maps FicheroCommand.id to toga.Command
        self.registry = CommandRegistry.get_instance()

        # Track menu commands for ordering and submenu building
        # Format: {(group, section): [FicheroCommand, ...]}
        self._menu_commands: Dict[tuple, list] = {}

        # Track parent commands for submenu hierarchies
        # Format: {parent_id: toga.Group}
        self._submenu_groups: Dict[str, toga.Group] = {}

        # Track command handlers by label for routing
        # Format: {(group, section, label): [FicheroCommand, ...]}
        # Multiple views can register commands with same label - routing chooses based on active view
        self._command_handlers_by_label: Dict[tuple, list] = {}

        logger.info(f"CommandManager initialized (is_mobile={self.is_mobile})")

    @classmethod
    def get_instance(cls, app=None) -> 'CommandManager':
        """Get singleton instance"""
        if cls._instance is None:
            if app is None:
                raise ValueError("First call to get_instance() requires app parameter")
            cls._instance = cls(app)
        return cls._instance

    def register_command(self, command: FicheroCommand) -> None:
        """
        Register a command and add to appropriate UI elements based on platform

        Args:
            command: FicheroCommand to register

        Platform behavior:
            Desktop:
                - If show_in_menu=True: Creates toga.Command, adds to app.commands (native menu)
                - If show_in_toolbar=True: Command available for native toolbar OR custom toolbar
                  (Native toolbar preferred, custom toolbar as override)
            Mobile:
                - show_in_menu ignored (no native menus)
                - If show_in_toolbar=True: Command available for custom toolbar only
        """
        # Check platform compatibility
        if command.mobile_only and not self.is_mobile:
            logger.debug(f"Skipping mobile-only command on desktop: {command.id}")
            return
        if command.desktop_only and self.is_mobile:
            logger.debug(f"Skipping desktop-only command on mobile: {command.id}")
            return

        # Register in command registry (always)
        self.registry.register(command)

        # Desktop: Add to native menu system if requested
        if not self.is_mobile and command.show_in_menu:
            self._add_to_native_menu(command)

        # Log toolbar availability
        if command.show_in_toolbar:
            platform_str = "native/custom toolbar" if not self.is_mobile else "custom toolbar"
            logger.debug(f"Command {command.id} available for {platform_str}")

    def _create_routing_action(self, label_key: tuple):
        """
        Create a routing action that delegates to the active view's command handler.

        Args:
            label_key: Tuple of (group, section, label) identifying the command

        Returns:
            Callable action that routes to the appropriate view's handler
        """
        def routing_action(widget):
            try:
                # Get the active view from main window
                active_view = None
                if hasattr(self.app, 'main_window') and self.app.main_window:
                    active_view = getattr(self.app.main_window, 'current_view', None)

                if not active_view:
                    logger.warning(f"No active view found for command routing: {label_key[2]}")
                    return

                # Get command handlers for this label
                handlers = self._command_handlers_by_label.get(label_key, [])
                if not handlers:
                    logger.warning(f"No handlers registered for command: {label_key[2]}")
                    return

                # Try to find handler from active view
                # Commands have IDs like "view_id.command_name"
                active_view_id = None
                if hasattr(active_view, 'view_id'):
                    active_view_id = active_view.view_id

                # Find matching handler for active view
                matching_handler = None
                for handler in handlers:
                    if handler.id.startswith(f"{active_view_id}."):
                        matching_handler = handler
                        break

                # Fallback to first handler if no match
                if not matching_handler:
                    matching_handler = handlers[0]
                    logger.debug(f"No view-specific handler found for '{active_view_id}', using fallback: {matching_handler.id}")

                # Execute the matched handler
                logger.info(f"🎯 Menu/Shortcut triggered: {matching_handler.id} ({matching_handler.label})")
                return matching_handler.execute(widget)

            except Exception as e:
                logger.error(f"Failed to route command {label_key[2]}: {e}")

        return routing_action

    def _create_and_add_toga_command(self, command: FicheroCommand, cmd_group: toga.Group, use_routing: bool = False, label_key: tuple = None) -> None:
        """
        Create a toga.Command and add it to app.commands.

        Handles submenu creation via parent/child relationships.
        If command has a parent, creates/uses a submenu group.

        Args:
            command: FicheroCommand to create toga.Command for
            cmd_group: Toga group to add command to
            use_routing: If True, uses routing action instead of direct command execution
            label_key: Tuple of (group, section, label) for routing lookup
        """
        try:
            # Create wrapper action - either routing or direct
            if use_routing and label_key:
                action = self._create_routing_action(label_key)
            else:
                # Direct action with logging
                def logged_action(widget, cmd=command):
                    logger.info(f"🎯 Menu/Shortcut triggered: {cmd.id} ({cmd.label})")
                    return cmd.execute(widget)
                action = logged_action

            # Determine the group for this command
            # If command has a parent, create or use a submenu group
            target_group = cmd_group
            if command.parent:
                # Create submenu group if it doesn't exist
                if command.parent not in self._submenu_groups:
                    # Create a group for the submenu using parent command's label
                    parent_cmd = self.registry.get(command.parent)
                    if parent_cmd:
                        submenu_label = parent_cmd.label
                    else:
                        submenu_label = command.parent.split('.')[-1].replace('_', ' ').title()

                    # Create submenu as child of parent group
                    self._submenu_groups[command.parent] = toga.Group(
                        submenu_label,
                        parent=cmd_group,
                        section=command.section
                    )
                    logger.debug(f"Created submenu group: {submenu_label} (parent={command.parent})")

                target_group = self._submenu_groups[command.parent]

            # Load icon if specified (for toolbar display)
            icon_resource = None
            if command.icon:
                try:
                    from pathlib import Path
                    if isinstance(command.icon, str):
                        icon_path = self.app.paths.app / command.icon
                        icon_resource = toga.Icon(str(icon_path))
                        logger.debug(f"Loading icon for command {command.id}: {icon_path}")
                    else:
                        # Already a Path or toga.Icon object
                        icon_resource = toga.Icon(command.icon) if not isinstance(command.icon, toga.Icon) else command.icon
                except Exception as icon_error:
                    logger.warning(f"Failed to load icon for {command.id}: {icon_error}")

            # Create Toga command with icon (works in both menus and toolbars)
            toga_cmd = toga.Command(
                action=action,
                text=command.label,
                tooltip=command.description,
                shortcut=command.shortcut,  # toga.Key combination or None
                icon=icon_resource,  # Icon for toolbar buttons (menus typically don't show icons on macOS)
                group=target_group,
                section=command.section  # Section for dividers
            )

            # Remove old version if it exists (to prevent duplicates during rebuilds)
            if command.id in self._toga_commands:
                try:
                    self.app.commands.discard(self._toga_commands[command.id])
                except Exception as discard_error:
                    logger.debug(f"Could not discard old command {command.id}: {discard_error}")

            # Add to app commands (automatically appears in native menus)
            self.app.commands.add(toga_cmd)

            # Store mapping and set reference on FicheroCommand for enable/disable sync
            self._toga_commands[command.id] = toga_cmd
            command._toga_command = toga_cmd

        except Exception as e:
            logger.error(f"Failed to create toga command for {command.id}: {e}")

    def _add_to_native_menu(self, command: FicheroCommand) -> None:
        """
        Add command to native Toga menu system with proper ordering and submenu support.

        Commands are organized by:
        1. group (which menu: FILE, EDIT, VIEW, etc.)
        2. section (groups within menu, with dividers between sections)
        3. order (position within section, lower numbers first)
        4. parent (creates submenus when specified)

        This method implements label-based deduplication with routing:
        - Multiple views can register commands with the same label (e.g., "New Collection")
        - Only one menu item is created per label
        - The menu item routes to the active view's command handler
        """
        try:
            # IMPORTANT: Skip submenu parent commands (those with action=None)
            # These are organizational commands that only exist to group their children
            # The submenu will be created automatically when child commands are added
            if command.action is None:
                logger.debug(f"Skipping submenu parent command (action=None): {command.id}")
                return

            # Determine group (default to COMMANDS if not specified)
            cmd_group = command.group or toga.Group.COMMANDS
            section_key = (cmd_group, command.section)

            # Create label key for deduplication (group, section, label)
            # Commands with same label in same group/section are considered duplicates
            label_key = (cmd_group, command.section, command.label)

            # Track this handler for routing
            if label_key not in self._command_handlers_by_label:
                self._command_handlers_by_label[label_key] = []

            # Add this command as a handler for this label (insert at beginning for priority)
            # Note: Commands are now stateless and query NavigationController for current location,
            # so we don't need to clean up handlers - they work correctly regardless of which
            # collection is active
            self._command_handlers_by_label[label_key].insert(0, command)

            # Check if we already have a menu item with this label
            has_existing_menu_item = any(
                cmd.label == command.label and cmd.group == cmd_group and cmd.section == command.section
                for cmd in self._menu_commands.get(section_key, [])
            )

            if has_existing_menu_item:
                # This is a duplicate label - just register the handler, don't create new menu item
                logger.info(f"🔀 Registered handler for existing menu item: {command.label} → {command.id}")
                logger.debug(f"   Total handlers for '{command.label}': {len(self._command_handlers_by_label[label_key])}")
                return

            # This is a new menu item - add it to tracking
            if section_key not in self._menu_commands:
                self._menu_commands[section_key] = []
            self._menu_commands[section_key].append(command)

            # Sort commands in this section by order
            self._menu_commands[section_key].sort(key=lambda cmd: cmd.order)

            # Remove existing toga commands for this section
            for cmd in self._menu_commands[section_key]:
                if cmd.id in self._toga_commands:
                    try:
                        self.app.commands.discard(self._toga_commands[cmd.id])
                        del self._toga_commands[cmd.id]
                    except Exception as remove_error:
                        logger.debug(f"Could not remove command {cmd.id}: {remove_error}")

            # Rebuild section with commands in sorted order
            # Use routing if we have multiple handlers for any command in this section
            for cmd in self._menu_commands[section_key]:
                cmd_label_key = (cmd.group or toga.Group.COMMANDS, cmd.section, cmd.label)
                handler_count = len(self._command_handlers_by_label.get(cmd_label_key, []))
                use_routing = handler_count > 1

                if use_routing:
                    logger.debug(f"Creating routed menu item for '{cmd.label}' ({handler_count} handlers)")

                self._create_and_add_toga_command(cmd, cmd_group, use_routing=use_routing, label_key=cmd_label_key)

            shortcut_str = f" (shortcut: {command.shortcut})" if command.shortcut else ""
            group_name = cmd_group.text if hasattr(cmd_group, 'text') else str(cmd_group)
            parent_str = f", parent={command.parent}" if command.parent else ""
            logger.info(f"✅ Added to native menu: {command.label} → {group_name} [section={command.section}, order={command.order}{parent_str}]{shortcut_str} (id: {command.id})")

        except Exception as e:
            logger.error(f"Failed to add command {command.id} to native menu: {e}")

    def get_command(self, command_id: str) -> Optional[FicheroCommand]:
        """Get a registered FicheroCommand by ID"""
        return self.registry.get(command_id)

    def get_toga_command(self, command_id: str) -> Optional[toga.Command]:
        """Get the toga.Command wrapper for a FicheroCommand (desktop only)"""
        return self._toga_commands.get(command_id)

    def build_native_toolbar(self, window: 'toga.Window', command_ids: list = None, view_id: str = None, context: str = 'normal', mode: str = 'add') -> None:
        """
        Build native Toga toolbar for a window (desktop only)

        On desktop platforms (macOS, Windows, Linux), this creates a native platform
        toolbar with commands. Commands are organized by Toga groups for proper visual organization.

        Args:
            window: Toga window to add toolbar to
            command_ids: List of command IDs to include in toolbar (optional)
                        If None, uses view_id + context to filter commands
            view_id: View identifier to filter commands (e.g., "library", "output")
            context: Context to filter commands (e.g., "normal", "edit")
            mode: 'add' to add commands (default), 'replace' to clear and rebuild, 'remove' to remove view's commands

        Example:
            # Add LibraryView commands to toolbar:
            command_manager = CommandManager.get_instance()
            command_manager.build_native_toolbar(
                self.window,
                view_id='library',
                context='normal',
                mode='add'
            )

            # Remove LibraryView commands from toolbar:
            command_manager.build_native_toolbar(
                self.window,
                view_id='library',
                mode='remove'
            )
        """
        if self.is_mobile:
            logger.debug("Skipping native toolbar on mobile platform")
            return

        try:
            # Handle remove mode
            if mode == 'remove':
                if view_id:
                    # Remove all commands that start with view_id
                    commands_to_remove = [cmd_id for cmd_id in self._toga_commands.keys() if cmd_id.startswith(f"{view_id}.")]
                    for cmd_id in commands_to_remove:
                        toga_cmd = self._toga_commands.get(cmd_id)
                        if toga_cmd:
                            try:
                                window.toolbar.remove(toga_cmd)
                                logger.debug(f"Removed toolbar command: {cmd_id}")
                            except Exception as e:
                                logger.debug(f"Could not remove command {cmd_id}: {e}")
                    logger.info(f"Removed {len(commands_to_remove)} toolbar commands for view '{view_id}'")
                return

            # Handle replace mode (clear everything first)
            if mode == 'replace':
                window.toolbar.clear()
                self._toga_commands.clear()
                logger.debug("Cleared toolbar for rebuild")

            toolbar_items = []

            # Get commands to include in toolbar
            if command_ids:
                # Use specified command list
                commands_to_add = [self.registry.get(cmd_id) for cmd_id in command_ids]
                commands_to_add = [cmd for cmd in commands_to_add if cmd is not None]
            elif view_id:
                # Use view_id + context to filter, specifically for native toolbar
                commands_to_add = self.get_toolbar_commands(view_id=view_id, context=context, toolbar_type="native")
            else:
                # Use all registered commands with any toolbar flag
                commands_to_add = self.get_toolbar_commands(toolbar_type="native")

            # Determine Toga group based on view_id
            # This organizes toolbar commands visually by view
            view_group_map = {
                'library': toga.Group.VIEW,  # Library commands
                'collection': toga.Group.EDIT,  # Collection editing commands
                'output': toga.Group.FILE,  # Output/file commands
            }
            default_group = view_group_map.get(view_id, toga.Group.VIEW)

            # Build toolbar items from commands
            for command in commands_to_add:
                # Check if command already exists in window's toolbar
                try:
                    existing_in_toolbar = any(
                        item.text == (command.toolbar_text or command.label)
                        for item in window.toolbar
                    )
                    if existing_in_toolbar:
                        logger.debug(f"Skipping command already in toolbar: {command.id}")
                        continue
                except Exception:
                    # If we can't check, just proceed (better to have duplicates than miss commands)
                    pass

                # Check if this command already has a toga.Command (from menu registration)
                existing_toga_cmd = self._toga_commands.get(command.id)

                if existing_toga_cmd:
                    # REUSE existing toga.Command for toolbar
                    # Toga allows the same Command object in both app.commands (menu) and window.toolbar
                    toolbar_items.append(existing_toga_cmd)
                    logger.debug(f"Reusing existing toga.Command for toolbar: {command.id}")
                else:
                    # Create NEW toga.Command for toolbar-only commands
                    def logged_action(widget, cmd=command):
                        logger.info(f"🎯 Toolbar button pressed: {cmd.id} ({cmd.label})")
                        return cmd.execute(widget)

                    # Convert relative icon path to absolute path using app.paths.app
                    icon_resource = None
                    if command.icon:
                        try:
                            from pathlib import Path
                            if isinstance(command.icon, str):
                                icon_path = self.app.paths.app / command.icon
                                icon_resource = toga.Icon(str(icon_path))
                                logger.debug(f"Loading toolbar icon from: {icon_path}")
                            else:
                                # Already a Path or toga.Icon object
                                icon_resource = toga.Icon(command.icon) if not isinstance(command.icon, toga.Icon) else command.icon
                        except Exception as icon_error:
                            logger.warning(f"Failed to load toolbar icon for {command.id}: {icon_error}")

                    # For toolbar-only commands (not in menus), use group=None to prevent menu appearance
                    # This is important: setting group=None prevents the command from appearing in menus
                    toolbar_cmd = toga.Command(
                        action=logged_action,
                        text=command.toolbar_text or command.label,
                        tooltip=command.description,
                        icon=icon_resource,
                        group=None,  # No group = toolbar only, won't appear in menus
                    )
                    toolbar_items.append(toolbar_cmd)

                    # Store for future reuse and set reference on FicheroCommand for enable/disable sync
                    self._toga_commands[command.id] = toolbar_cmd
                    command._toga_command = toolbar_cmd
                    logger.debug(f"Created new toolbar-only toga.Command: {command.id}")

            # Add toolbar items (additive approach)
            if toolbar_items:
                window.toolbar.add(*toolbar_items)
                logger.info(f"✅ Native toolbar {mode}: added {len(toolbar_items)} items for view '{view_id}', context '{context}' (group: {default_group.text})")
            else:
                logger.debug(f"No toolbar items to add for view '{view_id}', context '{context}'")

        except Exception as e:
            logger.error(f"Failed to build native toolbar: {e}")

    def register_view_commands(self, view_id: str, commands: Dict[str, FicheroCommand]) -> None:
        """
        Register multiple commands from a view with automatic platform handling.

        This is the unified way for views to register commands. The CommandManager
        automatically routes commands to the appropriate UI elements based on platform:
        - Desktop: Menus (with shortcuts) + custom toolbars
        - Mobile: Custom toolbars only

        Args:
            view_id: Identifier for the view (e.g., "library", "output", "collection")
            commands: Dict mapping command names to FicheroCommand instances

        Example:
            command_manager.register_view_commands("output", {
                "rotate_left": FicheroCommand(...),
                "rotate_right": FicheroCommand(...),
                "crop": FicheroCommand(...)
            })
        """
        try:
            logger.info(f"Registering {len(commands)} commands for view '{view_id}'")

            for cmd_name, command in commands.items():
                # Register each command using existing logic
                self.register_command(command)

            logger.info(f"✅ Successfully registered {len(commands)} commands for '{view_id}'")

        except Exception as e:
            logger.error(f"Failed to register commands for view '{view_id}': {e}")

    def get_toolbar_commands(self, view_id: str = None, context: str = None, toolbar_type: str = None) -> list:
        """
        Get commands suitable for toolbar display based on view and context.

        Args:
            view_id: Optional view identifier to filter commands
            context: Optional context (e.g., "edit", "normal") to filter commands
            toolbar_type: Optional toolbar type filter ("top", "bottom", "native")
                         If None, returns commands with any toolbar flag set

        Returns:
            List of FicheroCommand instances suitable for toolbar
        """
        try:
            all_commands = self.registry.list_all()

            # Filter commands for toolbar based on toolbar_type
            if toolbar_type == "top":
                # Only commands with show_in_top_toolbar=True
                toolbar_commands = [
                    cmd for cmd in all_commands
                    if getattr(cmd, 'show_in_top_toolbar', False)
                ]
            elif toolbar_type == "bottom":
                # Only commands with show_in_bottom_toolbar=True
                toolbar_commands = [
                    cmd for cmd in all_commands
                    if getattr(cmd, 'show_in_bottom_toolbar', False)
                ]
            elif toolbar_type == "native":
                # Commands for native window.toolbar (desktop only)
                # Check show_in_toolbar (primary) or show_in_top_toolbar
                # NOTE: Do NOT include show_in_bottom_toolbar here - that's for mobile only!
                toolbar_commands = [
                    cmd for cmd in all_commands
                    if (getattr(cmd, 'show_in_toolbar', False) or
                        getattr(cmd, 'show_in_top_toolbar', False))
                ]
            else:
                # Legacy: Any toolbar flag (including deprecated show_in_toolbar)
                toolbar_commands = [
                    cmd for cmd in all_commands
                    if (getattr(cmd, 'show_in_toolbar', False) or
                        getattr(cmd, 'show_in_top_toolbar', False) or
                        getattr(cmd, 'show_in_bottom_toolbar', False))
                ]

            # Filter by view_id if provided (commands have IDs like "view.action")
            if view_id:
                toolbar_commands = [
                    cmd for cmd in toolbar_commands
                    if cmd.id.startswith(f"{view_id}.")
                ]

            # Filter by context if provided
            if context:
                toolbar_commands = [
                    cmd for cmd in toolbar_commands
                    if getattr(cmd, 'context', 'normal') == context
                ]

            # Filter by platform compatibility
            # Remove mobile_only commands on desktop, remove desktop_only commands on mobile
            before_platform_filter = len(toolbar_commands)
            toolbar_commands = [
                cmd for cmd in toolbar_commands
                if not (getattr(cmd, 'mobile_only', False) and not self.is_mobile) and
                   not (getattr(cmd, 'desktop_only', False) and self.is_mobile)
            ]
            after_platform_filter = len(toolbar_commands)

            if before_platform_filter != after_platform_filter:
                logger.debug(f"Platform filtering: {before_platform_filter} -> {after_platform_filter} commands (is_mobile={self.is_mobile})")

            logger.debug(f"Found {len(toolbar_commands)} toolbar commands for view '{view_id}', context '{context}', type '{toolbar_type}'")
            if toolbar_commands:
                command_ids = [cmd.id for cmd in toolbar_commands]
                logger.debug(f"Command IDs: {command_ids}")
            return toolbar_commands

        except Exception as e:
            logger.error(f"Failed to get toolbar commands: {e}")
            return []

    def customize_standard_commands(self):
        """Remove unimplemented standard commands"""
        try:
            # Remove document commands we don't implement
            document_commands_to_remove = [
                toga.Command.OPEN,
                toga.Command.SAVE,
                toga.Command.SAVE_AS,
                toga.Command.SAVE_ALL
            ]

            for cmd_id in document_commands_to_remove:
                try:
                    if cmd_id in self.app.commands:
                        logger.info(f"Removing unimplemented command: {cmd_id}")
                        self.app.commands.discard(cmd_id)
                except Exception as cmd_error:
                    logger.debug(f"Could not remove command {cmd_id}: {cmd_error}")

            logger.info("Standard commands customized")

        except Exception as e:
            logger.error(f"Error customizing standard commands: {e}")
