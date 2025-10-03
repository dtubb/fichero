"""
Navigation commands for Fichero

Command pattern for navigation actions that can be executed by both GUI and console interfaces.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)


class NavigationCommand(ABC):
    """Base class for navigation commands"""

    @abstractmethod
    def execute(self, controller) -> bool:
        """Execute the command with the given navigation controller"""
        pass

    @abstractmethod
    def can_execute(self, controller) -> bool:
        """Check if the command can be executed in current state"""
        pass

    def get_description(self) -> str:
        """Get human-readable description of the command"""
        return self.__class__.__name__


@dataclass
class NavigateToLibrary(NavigationCommand):
    """Command to navigate to the library (root) view"""

    def execute(self, controller) -> bool:
        """Execute navigation to library"""
        try:
            return controller.navigate_to_library()
        except Exception as e:
            logger.error(f"Failed to execute NavigateToLibrary: {e}")
            return False

    def can_execute(self, controller) -> bool:
        """Can always navigate to library"""
        return True

    def get_description(self) -> str:
        return "Navigate to Library"


@dataclass
class NavigateToCollection(NavigationCommand):
    """Command to navigate to a specific collection"""
    collection_id: str
    collection_name: Optional[str] = None

    def execute(self, controller) -> bool:
        """Execute navigation to collection"""
        try:
            return controller.navigate_to_collection(self.collection_id, self.collection_name)
        except Exception as e:
            logger.error(f"Failed to execute NavigateToCollection: {e}")
            return False

    def can_execute(self, controller) -> bool:
        """Can navigate to collection if we have a valid collection ID"""
        return bool(self.collection_id and controller.library_service)

    def get_description(self) -> str:
        name = self.collection_name or self.collection_id
        return f"Navigate to Collection: {name}"


@dataclass
class NavigateToPath(NavigationCommand):
    """Command to navigate to a specific path within current collection"""
    path: str

    def execute(self, controller) -> bool:
        """Execute navigation to path"""
        try:
            return controller.navigate_to_path(self.path)
        except Exception as e:
            logger.error(f"Failed to execute NavigateToPath: {e}")
            return False

    def can_execute(self, controller) -> bool:
        """Can navigate to path if we're in a collection context"""
        current_state = controller.get_current_state()
        return (current_state and
                current_state.context.value == "collection" and
                current_state.collection_id)

    def get_description(self) -> str:
        return f"Navigate to Path: {self.path or 'root'}"


@dataclass
class NavigateBack(NavigationCommand):
    """Command to navigate back in history"""

    def execute(self, controller) -> bool:
        """Execute back navigation"""
        try:
            return controller.navigate_back()
        except Exception as e:
            logger.error(f"Failed to execute NavigateBack: {e}")
            return False

    def can_execute(self, controller) -> bool:
        """Can navigate back if there's history"""
        return controller.can_navigate_back()

    def get_description(self) -> str:
        return "Navigate Back"


@dataclass
class NavigateToPreview(NavigationCommand):
    """Command to navigate to file preview"""
    file_path: str
    file_metadata: Optional[Dict[str, Any]] = None

    def execute(self, controller) -> bool:
        """Execute navigation to preview"""
        try:
            return controller.navigate_to_preview(self.file_path, self.file_metadata)
        except Exception as e:
            logger.error(f"Failed to execute NavigateToPreview: {e}")
            return False

    def can_execute(self, controller) -> bool:
        """Can navigate to preview if we have a valid file path"""
        return bool(self.file_path)

    def get_description(self) -> str:
        return f"Navigate to Preview: {self.file_path}"


@dataclass
class NavigateToFolder(NavigationCommand):
    """Command to navigate into a folder within current collection"""
    folder_name: str

    def execute(self, controller) -> bool:
        """Execute navigation to folder"""
        try:
            return controller.navigate_to_folder(self.folder_name)
        except Exception as e:
            logger.error(f"Failed to execute NavigateToFolder: {e}")
            return False

    def can_execute(self, controller) -> bool:
        """Can navigate to folder if we're in a collection context"""
        current_state = controller.get_current_state()
        return (current_state and
                current_state.context.value == "collection" and
                current_state.collection_id)

    def get_description(self) -> str:
        return f"Navigate to Folder: {self.folder_name}"