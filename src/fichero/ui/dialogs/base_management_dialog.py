"""
Base Management Dialog
Abstract base class for file management dialogs with tree view and operations
"""

import toga
from toga.style import Pack
from toga.constants import COLUMN, ROW, CENTER, LEFT
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from abc import ABC, abstractmethod
import logging
import shutil
import subprocess
import platform

from ...utils.config_loader import ConfigLoader
from ...utils.app_settings import get_app_settings

logger = logging.getLogger(__name__)


class BaseManagementDialog(ABC):
    """
    Base class for file management dialogs
    Provides tree view, import/export, and common file operations
    """
    
    def __init__(self, app, current_file: Optional[Path] = None):
        self.app = app
        self.current_file = current_file
        self.window = None
        self.tree_data = []
        self.selected_file = None
    
    # Abstract methods that subclasses must implement
    
    @abstractmethod
    def get_file_type(self) -> str:
        """Get the file type name (e.g., 'plans', 'prompts', 'settings')"""
        pass
    
    @abstractmethod
    def get_file_extensions(self) -> List[str]:
        """Get supported file extensions for this type"""
        pass
    
    @abstractmethod
    def get_default_template(self) -> Dict[str, Any]:
        """Get default data structure for new files"""
        pass
    
    def get_directories(self) -> Tuple[Optional[Path], Optional[Path]]:
        """Get default and user directories for this file type"""
        try:
            file_type = self.get_file_type()
            if self.app and hasattr(self.app, 'paths'):
                # Default files from app resources
                default_dir = self.app.paths.app / "resources" / file_type
                # User files from app data
                user_dir = self.app.paths.data / file_type
            else:
                # Fallback paths
                default_dir = Path(__file__).parent.parent.parent / "resources" / file_type
                user_dir = None
            
            return default_dir, user_dir
        except Exception:
            return None, None
    
    def get_active_file(self) -> Optional[Path]:
        """Get the currently active file for this type from app settings"""
        try:
            if not self.app:
                return None
            
            app_settings = get_app_settings(self.app)
            active_file_str = app_settings.get_shared_setting(f"active_{self.get_file_type()}")
            
            if active_file_str:
                active_file = Path(active_file_str)
                if active_file.exists():
                    return active_file
            
            return None
        except Exception as e:
            logger.error(f"Failed to get active {self.get_file_type()} file: {e}")
            return None
    
    def set_active_file(self, file_path: Path) -> bool:
        """Set the active file for this type in app settings"""
        try:
            if not self.app:
                return False
            
            app_settings = get_app_settings(self.app)
            app_settings.set_shared_setting(f"active_{self.get_file_type()}", str(file_path), immediate_save=True)
            
            print(f"✅ Set {self.get_file_type()} active file: {file_path.name}")
            return True
        except Exception as e:
            logger.error(f"Failed to set active {self.get_file_type()} file: {e}")
            print(f"❌ Failed to set active file: {e}")
            return False
    
    # Core functionality
    
    def show(self):
        """Show the management dialog"""
        if self.window:
            self.window.show()
            return
        
        try:
            self._create_dialog()
            self._populate_tree()
            self.window.show()
            
        except Exception as e:
            logger.error(f"Failed to show management dialog: {e}")
            print(f"❌ Failed to open file manager: {e}")
    
    def _create_dialog(self):
        """Create the modal dialog window"""
        self.window = toga.Window(
            title=f"Manage {self.get_file_type().title()} Files",
            size=(600, 250),
            resizable=True
        )
        
        # Main container - no margin for full width tree
        main_container = toga.Box(
            style=Pack(direction=COLUMN, flex=1)
        )
        
        # Tree view for files - full width, no margin, multiple columns
        self.tree_view = toga.Tree(
            headings=["Name", "Description"],
            on_select=self._on_tree_select,
            style=Pack(flex=1)
        )
        
        # Action buttons - compact icon style
        button_box = toga.Box(
            style=Pack(direction=ROW, margin=10)
        )
        
        # Icon buttons
        new_btn = toga.Button(
            "+",
            on_press=self._handle_new,
            style=Pack(margin_right=5, width=30)
        )
        
        delete_btn = toga.Button(
            "−",
            on_press=self._handle_delete,
            style=Pack(margin_right=5, width=30)
        )
        
        duplicate_btn = toga.Button(
            "⎘", 
            on_press=self._handle_duplicate,
            style=Pack(margin_right=5, width=30)
        )
        
        import_btn = toga.Button(
            "📥",
            on_press=self._handle_import,
            style=Pack(margin_right=5, width=30)
        )
        
        export_btn = toga.Button(
            "📤",
            on_press=self._handle_export,
            style=Pack(margin_right=5, width=30)
        )
        
        # Set Active button
        set_active_btn = toga.Button(
            "★",
            on_press=self._handle_set_active,
            style=Pack(margin_right=5, width=30)
        )
        
        # Spacer to push reveal button to the right
        spacer = toga.Box(style=Pack(flex=1))
        
        # Reveal button on the right
        reveal_btn = toga.Button(
            "📂",
            on_press=self._handle_reveal,
            style=Pack(width=30)
        )
        
        button_box.add(new_btn)
        button_box.add(delete_btn)
        button_box.add(duplicate_btn)
        button_box.add(import_btn)
        button_box.add(export_btn)
        button_box.add(set_active_btn)
        button_box.add(spacer)
        button_box.add(reveal_btn)
        
        # Assemble dialog
        main_container.add(self.tree_view)
        main_container.add(button_box)
        
        self.window.content = main_container
    
    def _populate_tree(self):
        """Populate the tree view with files"""
        try:
            default_dir, user_dir = self.get_directories()
            active_file = self.get_active_file()
            
            # Clear existing data
            self.tree_view.data.clear()
            
            # Add default files directly to tree root
            if default_dir and default_dir.exists():
                for ext in self.get_file_extensions():
                    for file_path in sorted(default_dir.glob(f"*{ext}")):
                        # Check if this is the active file
                        description = f"Default • {file_path.suffix}"
                        if active_file and file_path == active_file:
                            description = f"★ Active • Default • {file_path.suffix}"
                        
                        node = self.tree_view.data.append({
                            "Name": file_path.stem,
                            "Description": description
                        })
                        node._file_path = file_path
                        node._is_default = True
                        node._is_special = False
                        node._is_active = (active_file and file_path == active_file)
            
            # Add user files directly to tree root
            if user_dir and user_dir.exists():
                for ext in self.get_file_extensions():
                    for file_path in sorted(user_dir.glob(f"*{ext}")):
                        # Check if this is the active file
                        description = f"Custom • {file_path.suffix}"
                        if active_file and file_path == active_file:
                            description = f"★ Active • Custom • {file_path.suffix}"
                        
                        node = self.tree_view.data.append({
                            "Name": file_path.stem,
                            "Description": description
                        })
                        node._file_path = file_path
                        node._is_default = False
                        node._is_special = False
                        node._is_active = (active_file and file_path == active_file)
            
            # Select current file if it exists
            if self.current_file:
                self._select_file_in_tree(self.current_file)
                        
        except Exception as e:
            logger.error(f"Failed to populate tree: {e}")
            print(f"❌ Failed to load file list: {e}")
    
    def _select_file_in_tree(self, file_path: Path):
        """Select a specific file in the tree"""
        try:
            # Search through tree nodes (now flat list)
            for node in self.tree_view.data:
                if hasattr(node, '_file_path') and node._file_path == file_path:
                    self.tree_view.selection = node
                    return
        except Exception as e:
            logger.error(f"Failed to select file in tree: {e}")
    
    def _on_tree_select(self, widget):
        """Handle tree selection"""
        selection = widget.selection
        if selection:
            self.selected_file = {
                "file_path": getattr(selection, '_file_path', None),
                "is_default": getattr(selection, '_is_default', False),
                "is_special": getattr(selection, '_is_special', False),
                "is_active": getattr(selection, '_is_active', False)
            }
    
    def _handle_new(self, widget):
        """Handle new file creation"""
        try:
            # Create new file dialog
            self._show_new_file_dialog()
            
        except Exception as e:
            logger.error(f"Failed to create new file: {e}")
            print(f"❌ Failed to create new file: {e}")
    
    def _show_new_file_dialog(self):
        """Show dialog for creating new file"""
        # For now, create with default name - could be enhanced with input dialog
        default_dir, user_dir = self.get_directories()
        if not user_dir:
            print("❌ User directory not available")
            return
        
        # Ensure user directory exists
        user_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate unique filename
        base_name = f"new_{self.get_file_type()}"
        ext = self.get_file_extensions()[0]
        counter = 1
        
        while True:
            filename = f"{base_name}_{counter}{ext}"
            file_path = user_dir / filename
            if not file_path.exists():
                break
            counter += 1
        
        # Create file with default template
        template = self.get_default_template()
        ConfigLoader.save_config_file(file_path, template)
        
        # Refresh tree
        self._populate_tree()
        print(f"✅ Created new {self.get_file_type()} file: {filename}")
    
    def _handle_delete(self, widget):
        """Handle file deletion"""
        if not self.selected_file:
            print("❌ No file selected")
            return
        
        if self.selected_file.get("is_default", False):
            print("❌ Cannot delete default files")
            return
        
        if self.selected_file.get("is_special", False):
            print("❌ Cannot delete category folders")
            return
        
        try:
            file_path = self.selected_file["file_path"]
            if not file_path:
                print("❌ No file path available")
                return
                
            file_path.unlink()
            self._populate_tree()
            print(f"✅ Deleted {self.get_file_type()} file: {file_path.name}")
            
        except Exception as e:
            logger.error(f"Failed to delete file: {e}")
            print(f"❌ Failed to delete file: {e}")
    
    def _handle_duplicate(self, widget):
        """Handle file duplication - copy default files to user area for editing"""
        if not self.selected_file:
            print("❌ No file selected")
            return
        
        file_path = self.selected_file.get("file_path")
        if not file_path:
            print("❌ No file path available")
            return
        
        try:
            default_dir, user_dir = self.get_directories()
            if not user_dir:
                print("❌ User directory not available")
                return
            
            # Ensure user directory exists
            user_dir.mkdir(parents=True, exist_ok=True)
            
            # Generate unique filename in user directory
            original_name = file_path.stem
            file_ext = file_path.suffix
            counter = 1
            
            # Try original name first, then add numbers
            new_name = original_name
            while True:
                new_file_path = user_dir / f"{new_name}{file_ext}"
                if not new_file_path.exists():
                    break
                new_name = f"{original_name}_copy_{counter}"
                counter += 1
            
            # Copy the file
            shutil.copy2(file_path, new_file_path)
            
            # Refresh tree to show the new file
            self._populate_tree()
            
            # Select the new file
            self._select_file_in_tree(new_file_path)
            
            print(f"✅ Duplicated {file_path.name} as {new_file_path.name}")
            
        except Exception as e:
            logger.error(f"Failed to duplicate file: {e}")
            print(f"❌ Failed to duplicate file: {e}")
    
    def _handle_import(self, widget):
        """Handle file import"""
        try:
            print(f"📥 Import {self.get_file_type()} file (functionality to be implemented)")
            # Could be enhanced with file picker dialog
            
        except Exception as e:
            logger.error(f"Failed to import file: {e}")
            print(f"❌ Failed to import file: {e}")
    
    def _handle_export(self, widget):
        """Handle file export"""
        if not self.selected_file:
            print("❌ No file selected")
            return
        
        if self.selected_file.get("is_special", False):
            print("❌ Cannot export category folders")
            return
        
        try:
            file_path = self.selected_file["file_path"]
            if not file_path:
                print("❌ No file path available")
                return
                
            print(f"📤 Export {file_path.name} (functionality to be implemented)")
            # Could be enhanced with save dialog
            
        except Exception as e:
            logger.error(f"Failed to export file: {e}")
            print(f"❌ Failed to export file: {e}")
    
    def _handle_reveal(self, widget):
        """Handle reveal button - open user data directory in file manager"""
        try:
            default_dir, user_dir = self.get_directories()
            
            # Use user_dir if it exists, otherwise create it and show it
            if user_dir:
                # Ensure directory exists
                user_dir.mkdir(parents=True, exist_ok=True)
                
                # Open in file manager using platform-appropriate command
                system = platform.system()
                if system == "Darwin":  # macOS
                    subprocess.run(["open", str(user_dir)])
                elif system == "Windows":
                    subprocess.run(["explorer", str(user_dir)])
                elif system == "Linux":
                    subprocess.run(["xdg-open", str(user_dir)])
                else:
                    print(f"📂 User {self.get_file_type()} directory: {user_dir}")
                    return
                
                print(f"📂 Opened {self.get_file_type()} directory: {user_dir}")
            else:
                print("❌ User directory not available")
                
        except Exception as e:
            logger.error(f"Failed to reveal directory: {e}")
            print(f"❌ Failed to reveal directory: {e}")
    
    def _handle_set_active(self, widget):
        """Handle set active button - set selected file as active for the app"""
        if not self.selected_file:
            print("❌ No file selected")
            return
        
        file_path = self.selected_file.get("file_path")
        if not file_path:
            print("❌ No file path available")
            return
        
        if self.selected_file.get("is_special", False):
            print("❌ Cannot set category folders as active")
            return
        
        try:
            # Set as active file
            if self.set_active_file(file_path):
                # Refresh tree to show new active state
                self._populate_tree()
                
                # Re-select the file to maintain selection
                self._select_file_in_tree(file_path)
                
                # If this is a settings file, apply it immediately
                if self.get_file_type() == "settings":
                    self._apply_settings_immediately(file_path)
                    
        except Exception as e:
            logger.error(f"Failed to set active file: {e}")
            print(f"❌ Failed to set active file: {e}")
    
    def _apply_settings_immediately(self, settings_file: Path):
        """Apply settings file to the running app immediately"""
        try:
            # Load the settings file
            settings_data = ConfigLoader.load_config_file(settings_file)
            
            # Update app settings
            app_settings = get_app_settings(self.app)
            app_settings.save_settings(settings_data)
            
            print(f"✅ Applied settings from {settings_file.name} to running app")
        except Exception as e:
            logger.error(f"Failed to apply settings immediately: {e}")
            print(f"❌ Failed to apply settings: {e}")
    
    def close(self):
        """Close the dialog"""
        if self.window:
            self.window.close()
            self.window = None
    
    def get_selected_file_path(self) -> Optional[Path]:
        """Get the currently selected file path"""
        if self.selected_file:
            return self.selected_file.get("file_path")
        return None 