"""
Abstract File Manager
Handles file operations, discovery, and management for different config types
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import logging

from fichero.config.core.loader import ConfigLoader

logger = logging.getLogger(__name__)


class FileManager(ABC):
    """Abstract base class for managing configuration files"""
    
    def __init__(self, app=None):
        self.app = app
        
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
    
    def get_active_file(self) -> Optional[Path]:
        """Get the currently active file for this type (optional)"""
        return None
    
    def set_active_file(self, file_path: Path) -> bool:
        """Set the active file for this type (optional)"""
        return True
    
    def get_directories(self) -> Tuple[Optional[Path], Optional[Path]]:
        """Get default and user directories for this file type"""
        try:
            file_type = self.get_file_type()
            if self.app and hasattr(self.app, 'paths'):
                # Default files from app resources
                default_dir = self.app.paths.app / "resources" / "config_defaults" / file_type
                # User files from app data
                user_dir = self.app.paths.data / file_type
            else:
                # For CLI or when app is not available - fail if no app
                try:
                    import toga
                    app = toga.App.app
                    if not app or not hasattr(app, 'paths'):
                        raise RuntimeError(f"Toga app not available - cannot get {file_type} directories")
                    
                    default_dir = app.paths.app / "resources" / "config_defaults" / file_type
                    user_dir = app.paths.data / file_type
                except ImportError:
                    # Toga not available (e.g., during early iOS startup)
                    logger.warning(f"Toga not available - cannot get {file_type} directories")
                    return None, None
            
            return default_dir, user_dir
        except Exception:
            return None, None
    
    def discover_files(self) -> List[Dict[str, Any]]:
        """Discover all files of this type and return metadata"""
        files = []
        default_dir, user_dir = self.get_directories()
        
        # Add default files (sorted alphabetically for consistency)
        if default_dir and default_dir.exists():
            for ext in self.get_file_extensions():
                for file_path in sorted(default_dir.glob(f"*{ext}")):
                    files.append({
                        "name": file_path.stem,
                        "path": file_path,
                        "is_default": True,
                        "description": self._get_file_description(file_path),
                        "folder_type": "default"
                    })
        
        # Add user files (sorted by creation time - oldest first, newest at bottom)
        if user_dir and user_dir.exists():
            user_files = []
            for ext in self.get_file_extensions():
                for file_path in user_dir.glob(f"*{ext}"):
                    user_files.append(file_path)
            
            # Sort by creation time (oldest first, newest at bottom)
            user_files.sort(key=lambda p: p.stat().st_ctime)
            
            for file_path in user_files:
                files.append({
                    "name": file_path.stem,
                    "path": file_path,
                    "is_default": False,
                    "description": self._get_file_description(file_path),
                    "folder_type": "custom"
                })
        
        return files
    
    def load_file(self, file_path: Path) -> Dict[str, Any]:
        """Load a configuration file"""
        try:
            data = ConfigLoader.load_config_file(file_path)
            return data
        except Exception as e:
            logger.error(f"Failed to load file {file_path}: {e}")
            return {}
    
    def save_file(self, file_path: Path, data: Dict[str, Any]) -> bool:
        """Save data to a configuration file"""
        try:
            ConfigLoader.save_config_file(file_path, data)
            logger.info(f"Saved {file_path.name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save {file_path}: {e}")
            return False
    
    def create_new_file(self, filename: str = None) -> Optional[Path]:
        """Create a new file by copying from the first default file"""
        try:
            default_dir, user_dir = self.get_directories()
            if not user_dir:
                raise ValueError("User directory not available")
            
            # Ensure user directory exists
            user_dir.mkdir(parents=True, exist_ok=True)
            
            # Generate unique filename if not provided
            if not filename:
                file_type = self.get_file_type().title()  # "Settings", "Plans", "Prompts"
                ext = self.get_file_extensions()[0]
                
                # Try "Untitled Settings" first
                filename = f"Untitled {file_type}{ext}"
                file_path = user_dir / filename
                
                if file_path.exists():
                    # If exists, try "Untitled Settings 1", "Untitled Settings 2", etc.
                    counter = 1
                    while True:
                        filename = f"Untitled {file_type} {counter}{ext}"
                        file_path = user_dir / filename
                        if not file_path.exists():
                            break
                        counter += 1
            else:
                # Ensure extension
                if not any(filename.endswith(ext) for ext in self.get_file_extensions()):
                    filename += self.get_file_extensions()[0]
                file_path = user_dir / filename
            
            # Try to copy from first default file instead of using template
            default_data = None
            if default_dir and default_dir.exists():
                # Find first default file
                for ext in self.get_file_extensions():
                    default_files = sorted(default_dir.glob(f"*{ext}"))
                    if default_files:
                        try:
                            default_data = self.load_file(default_files[0])
                            break
                        except Exception:
                            continue
            
            # Fall back to template if no default file found
            if default_data is None:
                default_data = self.get_default_template()
            
            if self.save_file(file_path, default_data):
                return file_path
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to create new file: {e}")
            return None
    
    def duplicate_file(self, source_path: Path, new_name: str = None) -> Optional[Path]:
        """Duplicate an existing file"""
        try:
            default_dir, user_dir = self.get_directories()
            if not user_dir:
                raise ValueError("User directory not available")
            
            # Ensure user directory exists
            user_dir.mkdir(parents=True, exist_ok=True)
            
            # Generate new filename
            if not new_name:
                original_name = source_path.stem
                file_ext = source_path.suffix
                counter = 1
                
                # Try "Original Name 1", "Original Name 2", etc.
                while True:
                    new_name = f"{original_name} {counter}"
                    new_file_path = user_dir / f"{new_name}{file_ext}"
                    if not new_file_path.exists():
                        break
                    counter += 1
            else:
                # Ensure extension
                if not any(new_name.endswith(ext) for ext in self.get_file_extensions()):
                    new_name += source_path.suffix
                new_file_path = user_dir / new_name
            
            # Load source and save to new location
            source_data = self.load_file(source_path)
            if self.save_file(new_file_path, source_data):
                return new_file_path
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to duplicate file: {e}")
            return None
    
    def delete_file(self, file_path: Path) -> bool:
        """Delete a file (only user files, not defaults)"""
        try:
            default_dir, user_dir = self.get_directories()
            
            # Prevent deletion of default files
            if default_dir and str(file_path).startswith(str(default_dir)):
                logger.warning(f"Cannot delete default file: {file_path}")
                return False
            
            # Delete the file
            file_path.unlink()
            logger.info(f"Deleted file: {file_path.name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete file: {e}")
            return False
    
    def rename_file(self, old_path: Path, new_name: str) -> Optional[Path]:
        """Rename a file (only user files, not defaults)"""
        try:
            default_dir, user_dir = self.get_directories()
            
            # Prevent renaming of default files
            if default_dir and str(old_path).startswith(str(default_dir)):
                logger.warning(f"Cannot rename default file: {old_path}")
                return None
            
            # Ensure new name has proper extension
            if not any(new_name.endswith(ext) for ext in self.get_file_extensions()):
                new_name += old_path.suffix
            
            # Create new path
            new_path = old_path.parent / new_name
            
            # Check if new name already exists
            if new_path.exists():
                logger.warning(f"File already exists: {new_name}")
                return None
            
            # Rename the file
            old_path.rename(new_path)
            
            # Update active file reference if this was the active file
            active_file = self.get_active_file()
            if active_file and active_file == old_path:
                self.set_active_file(new_path)
            
            logger.info(f"Renamed file: {old_path.name} -> {new_path.name}")
            return new_path
            
        except Exception as e:
            logger.error(f"Failed to rename file: {e}")
            return None
    
    def get_user_save_path(self, filename: str) -> Optional[Path]:
        """Get path for saving user version of a file"""
        try:
            default_dir, user_dir = self.get_directories()
            if not user_dir:
                return None
            
            # Ensure user directory exists
            user_dir.mkdir(parents=True, exist_ok=True)
            
            return user_dir / filename
            
        except Exception as e:
            logger.error(f"Failed to get user save path: {e}")
            return None
    
    def _get_file_description(self, file_path: Path) -> str:
        """Load description from the actual file"""
        try:
            data = self.load_file(file_path)
            
            # Try different description fields
            description = (
                data.get("description") or 
                data.get("title") or 
                data.get("name") or 
                file_path.stem.replace("_", " ").title()
            )
            return str(description)
        except Exception:
            # Fallback to filename
            return file_path.stem.replace("_", " ").title()
    

    
    def is_default_file(self, file_path: Path) -> bool:
        """Check if the file is a default file"""
        default_dir, user_dir = self.get_directories()
        return default_dir and str(file_path).startswith(str(default_dir)) 