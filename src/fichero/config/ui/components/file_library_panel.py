"""
File Library Panel Component
Simplified UI component for the file library with data separated from display
"""

import toga
from toga.style import Pack
from toga.constants import COLUMN, ROW, CENTER, LEFT
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable
import logging

logger = logging.getLogger(__name__)


class FileLibraryPanel(toga.Box):
    """Simplified file library panel with data separated from display
    
    Shows files in a tree structure with clear separation between
    data management and UI display.
    """
    
    def __init__(self, 
                 file_manager,
                 on_file_select: Callable = None,
                 on_new_file: Callable = None,
                 on_delete_file: Callable = None,
                 on_duplicate_file: Callable = None,
                 on_import_file: Callable = None,
                 on_export_file: Callable = None,
                 on_restore_defaults: Callable = None):
        
        super().__init__(style=Pack(direction=COLUMN, width=200, margin=0))
        
        self.file_manager = file_manager
        self.on_file_select = on_file_select
        self.on_new_file = on_new_file
        self.on_delete_file = on_delete_file
        self.on_duplicate_file = on_duplicate_file

        self.on_import_file = on_import_file
        self.on_export_file = on_export_file
        self.on_restore_defaults = on_restore_defaults
        
        # Data storage - separate from display
        self.file_data = {}  # Dict keyed by file_path storing file info
        self.selected_file_path = None
        
        # Tree nodes for organization
        self.default_folder_node = None
        self.custom_folder_node = None
        
        self._create_ui()
        self.refresh_files()
        # Update active file label after initial load
        self.update_active_file_indicator()
    
    def _create_ui(self):
        """Create the UI components"""
        
        # Tree view for files - simple display only
        self.tree_view = toga.Tree(
            headings=["Name"],
            on_select=self._on_tree_select,
            on_activate=self._on_tree_activate,
            style=Pack(flex=1, margin=0)
        )
        self.add(self.tree_view)
        
        # Active file label
        self.active_file_label = toga.Label(
            "No file selected",
            style=Pack(margin=(5, 5, 0, 5), font_size=9, text_align=CENTER)
        )
        self.add(self.active_file_label)
        
        # Action buttons section
        self._create_action_buttons()
        
        # Restore defaults button
        self._create_restore_section()
    
    def _create_action_buttons(self):
        """Create the action buttons"""
        
        button_container = toga.Box(
            style=Pack(direction=COLUMN, margin=(5, 5, 5, 5))
        )
        
        # Primary actions row
        primary_row = toga.Box(style=Pack(direction=ROW, margin_bottom=3))
        
        new_btn = toga.Button(
            "New",
            on_press=self._handle_new,
            style=Pack(flex=1, margin_right=3, height=24, font_size=9)
        )
        
        delete_btn = toga.Button(
            "Delete",
            on_press=self._handle_delete,
            style=Pack(flex=1, margin_right=3, height=24, font_size=9)
        )
        
        rename_btn = toga.Button(
            "Rename",
            on_press=self._handle_rename,
            style=Pack(flex=1, height=24, font_size=9)
        )
        
        primary_row.add(new_btn)
        primary_row.add(delete_btn)
        primary_row.add(rename_btn)
        
        # Secondary actions row
        secondary_row = toga.Box(style=Pack(direction=ROW, margin_top=3))
        
        duplicate_btn = toga.Button(
            "Copy",
            on_press=self._handle_duplicate,
            style=Pack(flex=1, margin_right=3, height=24, font_size=9)
        )
        
        import_btn = toga.Button(
            "Import",
            on_press=self._handle_import,
            style=Pack(flex=1, margin_right=3, height=24, font_size=9)
        )
        
        export_btn = toga.Button(
            "Export",
            on_press=self._handle_export,
            style=Pack(flex=1, height=24, font_size=9)
        )
        
        secondary_row.add(duplicate_btn)
        secondary_row.add(import_btn)
        secondary_row.add(export_btn)
        
        button_container.add(primary_row)
        button_container.add(secondary_row)
        self.add(button_container)
    
    def _create_restore_section(self):
        """Create the restore defaults section"""
        restore_container = toga.Box(
            style=Pack(direction=ROW, margin=(5, 5, 5, 5))
        )
        
        restore_btn = toga.Button(
            "Restore Defaults",
            on_press=self._handle_restore_defaults,
            style=Pack(flex=1, height=24, font_size=9)
        )
        
        restore_container.add(restore_btn)
        self.add(restore_container)
    
    def refresh_files(self):
        """Refresh the file tree and data"""
        try:
            active_file = self.file_manager.get_active_file()
            
            # Clear existing data
            self.tree_view.data.clear()
            self.file_data.clear()
            
            # Get file information from file manager
            files = self.file_manager.discover_files()
            
            # Store file data separately
            for file_info in files:
                file_path = str(file_info["path"])
                self.file_data[file_path] = {
                    "name": file_info["name"],
                    "path": file_info["path"],
                    "description": file_info["description"],
                    "folder_type": file_info["folder_type"],
                    "is_default": file_info["folder_type"] == "default"
                }
            
            # Group files by folder type
            default_files = [f for f in files if f["folder_type"] == "default"]
            custom_files = [f for f in files if f["folder_type"] == "custom"]
            
            # Add Default folder
            self.default_folder_node = self.tree_view.data.append({
                "name": "📁 Default"
            })
            
            # Add default files
            for file_info in default_files:
                display_name = self._get_display_name(file_info)
                node_data = {
                    "name": display_name,
                    "file_path": str(file_info["path"])
                }
                self.default_folder_node.append(node_data)
            
            # Add Custom folder
            self.custom_folder_node = self.tree_view.data.append({
                "name": "📁 Custom"
            })
            
            # Add custom files
            for file_info in custom_files:
                display_name = self._get_display_name(file_info)
                node_data = {
                    "name": display_name,
                    "file_path": str(file_info["path"])
                }
                self.custom_folder_node.append(node_data)
            
            # Expand folders
            self.tree_view.expand(self.default_folder_node)
            self.tree_view.expand(self.custom_folder_node)
            
        except Exception as e:
            logger.error(f"Failed to refresh files: {e}")
    
    def update_active_file_indicator(self):
        """Update the active file label"""
        try:
            active_file = self.file_manager.get_active_file()
            if active_file:
                self.active_file_label.text = f"Active: {active_file.stem}"
            else:
                self.active_file_label.text = "No file selected"
        except Exception as e:
            logger.warning(f"Failed to update active file indicator: {e}")
            self.active_file_label.text = "Unable to determine active file"
    
    def _get_display_name(self, file_info: Dict) -> str:
        """Get display name for a file"""
        name = file_info["name"]
        # Simple display with file icon
        return f"📄 {name}"
    
    def _is_active_file(self, file_path: str) -> bool:
        """Check if this is the active file (the one being edited)"""
        try:
            active_file = self.file_manager.get_active_file()
            if not active_file:
                return False
            
            return Path(active_file).resolve() == Path(file_path).resolve()
            
        except Exception as e:
            logger.warning(f"Error checking active file: {e}")
            return False
    
    def _on_tree_select(self, widget):
        """Handle tree selection"""
        selection = widget.selection
        
        if selection is None:
            self.selected_file_path = None
            return
        
        file_path = getattr(selection, 'file_path', None)
        if not file_path:
            return  # Folder selected
        
        self.selected_file_path = file_path
        
        if self.on_file_select:
            file_info = self._get_file_info(file_path)
            self.on_file_select(Path(file_path), file_info)
    
    def _on_tree_activate(self, widget):
        """Handle tree double-click/activation - open file for editing"""
        # Double-click behaves the same as single-click - just selects the file
        self._on_tree_select(widget)
    
    def _get_file_info(self, file_path: str) -> Dict:
        """Get file info from our data store"""
        data = self.file_data.get(file_path, {})
        return {
            "file_path": Path(file_path),
            "is_default": data.get("is_default", False),
            "is_currently_editing": self._is_active_file(file_path),
            "file_info": data
        }
    

    
    # Button handlers - simple and direct
    
    def _handle_new(self, widget):
        """Handle new file button"""
        if self.on_new_file:
            self.on_new_file()
    
    def _handle_delete(self, widget):
        """Handle delete file button"""
        if not self.selected_file_path:
            logger.warning("No file selected for deletion")
            return
        
        file_info = self._get_file_info(self.selected_file_path)
        
        if file_info["is_default"]:
            logger.warning("Cannot delete default files")
            return
        
        if self.on_delete_file:
            self.on_delete_file(file_info)
    
    def _handle_duplicate(self, widget):
        """Handle duplicate file button"""
        if not self.selected_file_path:
            logger.warning("No file selected for duplication")
            return
        
        file_info = self._get_file_info(self.selected_file_path)
        if self.on_duplicate_file:
            self.on_duplicate_file(file_info)
    
    def _handle_rename(self, widget):
        """Handle rename file button"""
        if not self.selected_file_path:
            logger.warning("No file selected for renaming")
            return
        
        file_info = self._get_file_info(self.selected_file_path)
        
        if file_info["is_default"]:
            logger.warning("Cannot rename default files")
            return
        
        self._show_rename_dialog(file_info['file_path'])
    
    def _show_rename_dialog(self, file_path: Path):
        """Show rename dialog - simple Toga window"""
        try:
            current_name = file_path.stem
            
            # Create simple dialog window
            dialog = toga.Window(
                title="Rename",
                size=(280, 120)
            )
            
            container = toga.Box(style=Pack(direction=COLUMN, padding=15))
            
            container.add(toga.Label(
                f"Rename '{current_name}':",
                style=Pack(margin_bottom=10)
            ))
            
            name_input = toga.TextInput(
                value=current_name,
                style=Pack(margin_bottom=15, width=250)
            )
            container.add(name_input)
            
            button_box = toga.Box(style=Pack(direction=ROW))
            
            def handle_ok(widget):
                new_name = name_input.value.strip()
                if new_name and new_name != current_name:
                    self._perform_rename(file_path, new_name)
                dialog.close()
            
            def handle_cancel(widget):
                dialog.close()
            
            ok_btn = toga.Button("OK", on_press=handle_ok, style=Pack(margin_right=10, width=80))
            cancel_btn = toga.Button("Cancel", on_press=handle_cancel, style=Pack(width=80))
            
            button_box.add(ok_btn)
            button_box.add(cancel_btn)
            container.add(button_box)
            
            dialog.content = container
            dialog.show()
            
        except Exception as e:
            logger.error(f"Failed to show rename dialog: {e}")
    
    def _perform_rename(self, file_path: Path, new_name: str):
        """Perform the actual file rename"""
        try:
            new_file_path = self.file_manager.rename_file(file_path, new_name)
            if new_file_path:
                # Update active file if needed
                if self.file_manager.get_active_file() == file_path:
                    self.file_manager.set_active_file(new_file_path)
                
                self.refresh_files()
                self.update_active_file_indicator()
            else:
                logger.warning(f"Failed to rename file: {file_path.name}")
                
        except Exception as e:
            logger.error(f"Failed to perform rename: {e}")
    
    def _handle_import(self, widget):
        """Handle import file button"""
        if self.on_import_file:
            self.on_import_file()
    
    def _handle_export(self, widget):
        """Handle export file button"""
        if not self.selected_file_path:
            logger.warning("No file selected for export")
            return
        
        file_info = self._get_file_info(self.selected_file_path)
        
        if self.on_export_file:
            self.on_export_file(file_info)
    
    def _handle_restore_defaults(self, widget):
        """Handle restore defaults button"""
        if self.on_restore_defaults:
            self.on_restore_defaults() 