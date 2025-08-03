"""
Command Manager for Fichero - Cross-Platform Toga Approach

This is the single source of truth for all application commands.
Commands are created once and added to app.commands, making them available
across all platforms (macOS, Windows, Linux, iOS, Android) in both menus and toolbars.
"""

import toga
from toga.constants import WindowState
import logging
from typing import List
from pathlib import Path
import asyncio

import gettext

from fichero.ui.windows.about_window import AboutWindow
from fichero.ui.windows.activity_monitor_window import ActivityMonitorWindow

logger = logging.getLogger(__name__)


class CommandManager:
    """Central command manager - creates all commands once for cross-platform use"""
    
    def __init__(self, app):
        """Initialize command manager with reference to app"""
        self.app = app
        self.commands: List[toga.Command] = []
        
        # Create all commands immediately
        self._create_all_commands()
    
    def _create_all_commands(self):
        """Create all application commands - single source of truth"""
        try:
            # ===== FILE OPERATIONS =====
            # Use Toga's standard FILE group instead of creating our own
            
            # Add command
            add_cmd = toga.Command(
                self._on_add,
                text="Add",
                tooltip="Add files or folders to the library",
                icon=toga.Icon("resources/icons/plus"),
                group=toga.Group.FILE,
                section=0,
                order=0
            )
            self.commands.append(add_cmd)
            
            # Delete command
            delete_cmd = toga.Command(
                self._on_delete_collection,
                text=_("main_window_delete"),
                tooltip=_("main_window_delete_tooltip"),
                icon=toga.Icon("resources/icons/trash"),
                group=toga.Group.FILE,
                section=0,
                order=1
            )
            self.commands.append(delete_cmd)
            
            # Separator after delete
            separator1 = toga.Command(
                None,  # No action
                text="",  # No text
                group=toga.Group.FILE,
                section=0,
                order=2
            )
            self.commands.append(separator1)
            
            # Process Folder command
            process_folder_cmd = toga.Command(
                self._on_process_folder,
                text="Process Folder",
                tooltip="Open a new document window to process a folder",
                icon=toga.Icon("resources/icons/folder"),
                group=toga.Group.FILE,
                section=0,
                order=3
            )
            self.commands.append(process_folder_cmd)
            
            # ===== APP OPERATIONS =====
            # Settings command (in App menu)
            settings_cmd = toga.Command(
                self._on_settings,
                text=_("main_window_settings"),
                tooltip=_("main_window_settings_tooltip"),
                icon=toga.Icon("resources/icons/gear"),
                group=toga.Group.APP,
                section=0,
                order=0
            )
            self.commands.append(settings_cmd)
            
            # ===== WINDOW OPERATIONS =====
            # Activity Monitor command (in Window menu)
            activity_cmd = toga.Command(
                self._on_activity_monitor,
                text=_("main_window_activity"),
                tooltip=_("main_window_activity_tooltip"),
                icon=toga.Icon("resources/icons/activity"),
                group=toga.Group.WINDOW,
                section=0,
                order=0
            )
            self.commands.append(activity_cmd)
            
            logger.info(f"Created {len(self.commands)} commands for cross-platform use")
            
        except Exception as e:
            logger.error(f"Failed to create commands: {e}")
    
    def add_to_app(self):
        """Add all commands to the app - makes them available everywhere"""
        try:
            for command in self.commands:
                self.app.commands.add(command)
            logger.info(f"Added {len(self.commands)} commands to app")
        except Exception as e:
            logger.error(f"Failed to add commands to app: {e}")
    
    def add_to_toolbar(self, window):
        """Add commands to a specific window's toolbar"""
        try:
            for command in self.commands:
                window.toolbar.add(command)
            logger.info(f"Added {len(self.commands)} commands to window toolbar")
        except Exception as e:
            logger.error(f"Failed to add commands to toolbar: {e}")
    
    def remove_from_app(self):
        """Remove all commands from the app"""
        try:
            for command in self.commands:
                self.app.commands.remove(command)
            logger.info(f"Removed {len(self.commands)} commands from app")
        except Exception as e:
            logger.error(f"Failed to remove commands from app: {e}")
    
    def cleanup(self):
        """Clean up command manager"""
        try:
            self.remove_from_app()
            self.commands.clear()
            logger.info("Command manager cleaned up")
        except Exception as e:
            logger.error(f"Failed to cleanup command manager: {e}")
    
    # ===== COMMAND HANDLERS =====
    
    async def _on_add(self, widget):
        """Handle add command"""
        try:
            # Show folder selection dialog
            dialog = toga.SelectFolderDialog(
                title="Select Folder to Add to Library"
            )
            selected_folder = await self.app.main_window.dialog(dialog)
            
            if selected_folder:
                # Add the folder to the library
                await self._add_folder_to_library(Path(selected_folder))
                logger.info(f"Added folder to library: {selected_folder}")
                
                # Refresh the main window
                if hasattr(self.app, 'main_window_wrapper'):
                    await self.app.main_window_wrapper._load_collection_data()
                    
        except Exception as e:
            logger.error(f"Failed to add folder: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    async def _add_folder_to_library(self, folder_path: Path):
        """Add a folder to the library"""
        try:
            logger.info(f"Adding folder to library: {folder_path}")
            
            # Get the library manager from the main window
            if hasattr(self.app, 'main_window_wrapper') and hasattr(self.app.main_window_wrapper, 'library_manager'):
                library_manager = self.app.main_window_wrapper.library_manager
                logger.info("Library manager found")
                
                # Get library path and create collections directory
                library_path = library_manager.get_library_path()
                collections_path = library_path / "collections"
                collections_path.mkdir(parents=True, exist_ok=True)
                logger.info(f"Collections path: {collections_path}")
                
                # Copy the folder to collections directory
                import shutil
                collection_name = folder_path.name
                destination_path = collections_path / collection_name
                
                if destination_path.exists():
                    # Remove existing collection first
                    shutil.rmtree(destination_path)
                    logger.info(f"Removed existing collection: {destination_path}")
                
                # Copy the folder
                shutil.copytree(folder_path, destination_path)
                logger.info(f"Copied folder to collections: {destination_path}")
                
                # Check if folder contains image files
                image_files = list(destination_path.glob("*.jpg")) + list(destination_path.glob("*.jpeg")) + list(destination_path.glob("*.png"))
                logger.info(f"Found {len(image_files)} image files in {destination_path}")
                
                if image_files:
                    # Create manifest in library directory (not in collections subfolder)
                    manifest_path = library_path / f"{collection_name}.jsonl"
                    logger.info(f"Creating manifest: {manifest_path}")
                    
                    await library_manager._create_collection_manifest(manifest_path, destination_path, image_files)
                    logger.info(f"Successfully created manifest: {manifest_path}")
                    
                    # Verify the file was created
                    if manifest_path.exists():
                        logger.info(f"Manifest file confirmed to exist: {manifest_path}")
                        logger.info(f"Manifest file size: {manifest_path.stat().st_size} bytes")
                    else:
                        logger.error(f"Manifest file was not created: {manifest_path}")
                else:
                    logger.warning(f"No image files found in folder: {destination_path}")
                    
            else:
                logger.error("Library manager not found in main window wrapper")
            
        except Exception as e:
            logger.error(f"Failed to add folder to library: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    def _on_delete_collection(self, widget):
        """Handle delete collection command"""
        try:
            # Get the selected collection from the main window
            if hasattr(self.app, 'main_window_wrapper') and hasattr(self.app.main_window_wrapper, 'collection_list'):
                collection_list = self.app.main_window_wrapper.collection_list
                selected_collection = collection_list.selected_collection
                
                if selected_collection:
                    # Delete the collection manifest
                    asyncio.create_task(self._delete_collection_from_library(selected_collection))
                else:
                    logger.warning("No collection selected for deletion")
            else:
                logger.warning("Collection list not available")
                
        except Exception as e:
            logger.error(f"Failed to delete collection: {e}")
    
    async def _delete_collection_from_library(self, collection_data):
        """Delete a collection from the library"""
        try:
            logger.info(f"Deleting collection: {collection_data.title}")
            logger.info(f"Collection manifest path: {collection_data.manifest_path}")
            
            # Get the library manager to find the collections directory
            if hasattr(self.app, 'main_window_wrapper') and hasattr(self.app.main_window_wrapper, 'library_manager'):
                library_manager = self.app.main_window_wrapper.library_manager
                library_path = library_manager.get_library_path()
                collections_path = library_path / "collections"
                
                # Delete the copied folder from collections directory
                collection_folder = collections_path / collection_data.title
                if collection_folder.exists():
                    import shutil
                    shutil.rmtree(collection_folder)
                    logger.info(f"Deleted collection folder: {collection_folder}")
                else:
                    logger.warning(f"Collection folder not found: {collection_folder}")
            
            # Delete the manifest file
            if collection_data.manifest_path.exists():
                collection_data.manifest_path.unlink()
                logger.info(f"Deleted collection manifest: {collection_data.manifest_path}")
                
                # Refresh the main window
                if hasattr(self.app, 'main_window_wrapper'):
                    await self.app.main_window_wrapper._load_collection_data()
            else:
                logger.warning(f"Manifest file not found: {collection_data.manifest_path}")
            
        except Exception as e:
            logger.error(f"Failed to delete collection from library: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    def _on_settings(self, widget):
        """Handle settings command"""
        try:
            # Use the app's settings window method
            if hasattr(self.app, 'show_settings'):
                self.app.show_settings()
            else:
                logger.warning("Settings window not available")
        except Exception as e:
            logger.error(f"Failed to open settings: {e}")
    
    def _on_activity_monitor(self, widget):
        """Handle activity monitor command"""
        try:
            # Use the app's activity monitor method
            if hasattr(self.app, 'show_activity_monitor'):
                self.app.show_activity_monitor()
            else:
                logger.warning("Activity monitor not available")
        except Exception as e:
            logger.error(f"Failed to show activity monitor: {e}")
    
    def _on_about(self, widget):
        """Handle about command"""
        try:
            # Use the app's about method
            if hasattr(self.app, 'show_about'):
                self.app.show_about()
            else:
                logger.warning("About dialog not available")
        except Exception as e:
            logger.error(f"Failed to show about dialog: {e}")
    
    def _on_process_folder(self, widget):
        """Handle Process Folder command - create new processing window"""
        try:
            # Create a new processing window
            from fichero.ui.windows.processing_window import ProcessingWindow
            
            # Create processing window directly
            processing_window = ProcessingWindow(self.app)
            
            # Show the window
            processing_window.show()
            
            logger.info("Created new Process Folder window")
            
        except Exception as e:
            logger.error(f"Failed to create Process Folder window: {e}")
            import traceback
            logger.error(traceback.format_exc()) 