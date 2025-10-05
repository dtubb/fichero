"""
Base Tool Editor

Abstract base class for tool-specific output editors.
"""

import json
import subprocess
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Any, Optional
import logging

logger = logging.getLogger(__name__)


class BaseToolEditor(ABC):
    """
    Abstract base class for tool output editors.

    Each tool can have its own editor that knows how to:
    - Load and display outputs
    - Edit outputs (CLI via $EDITOR, GUI via Toga widgets)
    - Save changes back to files
    """

    # Subclasses should override these
    tool_name: str = ""
    supported_extensions: List[str] = []
    can_edit_files: bool = True  # Whether files can be edited

    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    @abstractmethod
    def can_edit(self, file_path: Path) -> bool:
        """
        Check if this editor can edit the given file.

        Args:
            file_path: Path to the file

        Returns:
            True if this editor can handle this file
        """
        pass

    @abstractmethod
    def load_content(self, file_path: Path) -> Any:
        """
        Load file content for editing.

        Args:
            file_path: Path to the file

        Returns:
            Loaded content (format depends on editor type)
        """
        pass

    @abstractmethod
    def save_content(self, file_path: Path, content: Any) -> bool:
        """
        Save edited content back to file.

        Args:
            file_path: Path to the file
            content: Content to save

        Returns:
            True if save successful
        """
        pass

    def edit_cli(self, file_path: Path) -> bool:
        """
        Edit file using system $EDITOR.

        Opens the file in the user's preferred editor.
        Default implementation works for text files.

        Args:
            file_path: Path to the file to edit

        Returns:
            True if editing completed (file may or may not be changed)
        """
        import os

        if not self.can_edit_files:
            self.logger.warning(f"Editing not supported for {self.tool_name} outputs")
            return False

        if not file_path.exists():
            self.logger.error(f"File not found: {file_path}")
            return False

        # Get editor from environment or use default
        editor = os.environ.get('EDITOR', 'nano')

        try:
            # Open editor
            result = subprocess.run([editor, str(file_path)], check=True)
            self.logger.info(f"Edited {file_path} with {editor}")
            return True
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Editor failed: {e}")
            return False
        except FileNotFoundError:
            self.logger.error(f"Editor not found: {editor}")
            return False

    def create_gui_editor(self, app, file_path: Path):
        """
        Create GUI editor widget (Toga).

        To be implemented by subclasses for GUI editing.
        Base class returns None (no GUI editor).

        Args:
            app: Toga application instance
            file_path: Path to the file

        Returns:
            Toga widget or None
        """
        self.logger.warning(f"GUI editor not implemented for {self.__class__.__name__}")
        return None

    def validate_content(self, content: Any) -> tuple[bool, str]:
        """
        Validate content before saving.

        Args:
            content: Content to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Default: always valid
        return True, ""

    def get_metadata(self, file_path: Path) -> dict:
        """
        Get metadata about the file.

        Args:
            file_path: Path to the file

        Returns:
            Dictionary with metadata
        """
        if not file_path.exists():
            return {}

        stat = file_path.stat()
        return {
            'size': stat.st_size,
            'modified': stat.st_mtime,
            'extension': file_path.suffix,
            'name': file_path.name
        }
