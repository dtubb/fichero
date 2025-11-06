"""
Editor Registry

Maps tools and file types to appropriate editors.
"""

from pathlib import Path
from typing import Optional, List
import logging

from .base_editor import BaseToolEditor
from .json_editor import JSONEditor
from .image_editor import ImageEditor

logger = logging.getLogger(__name__)


class EditorRegistry:
    """
    Registry for tool output editors.

    Maps tools and file extensions to appropriate editors.
    """

    def __init__(self):
        self._editors: List[BaseToolEditor] = []
        self._tool_map: dict[str, BaseToolEditor] = {}

        # Register default editors
        self._register_defaults()

    def _register_defaults(self):
        """Register default editors"""
        # JSON editor for transcriptions and catalogues
        json_editor = JSONEditor()
        self.register_editor(json_editor)
        self._tool_map['transcribe_qwen_max'] = json_editor
        self._tool_map['transcribe_lmstudio'] = json_editor
        self._tool_map['catalogue_folder'] = json_editor
        self._tool_map['llm_process'] = json_editor

        # New tools - JSON outputs
        self._tool_map['describe_images'] = json_editor
        self._tool_map['extract_library_metadata'] = json_editor
        self._tool_map['analyze_document_groups'] = json_editor

        # Image editor for prepared images
        image_editor = ImageEditor()
        self.register_editor(image_editor)
        self._tool_map['prepare_images'] = image_editor
        self._tool_map['crop'] = image_editor
        self._tool_map['rotate'] = image_editor
        self._tool_map['enhance'] = image_editor

        # New tools - SVG outputs (using ImageEditor for now, can create SVGEditor later)
        self._tool_map['convert_to_svg'] = image_editor

    def register_editor(self, editor: BaseToolEditor):
        """
        Register an editor.

        Args:
            editor: Editor instance to register
        """
        if editor not in self._editors:
            self._editors.append(editor)
            logger.debug(f"Registered editor: {editor.__class__.__name__}")

    def get_editor_for_tool(self, tool_name: str) -> Optional[BaseToolEditor]:
        """
        Get editor for a specific tool.

        Args:
            tool_name: Name of the tool

        Returns:
            Editor instance or None
        """
        return self._tool_map.get(tool_name)

    def get_editor_for_file(self, file_path: Path) -> Optional[BaseToolEditor]:
        """
        Get editor for a file based on extension.

        Args:
            file_path: Path to the file

        Returns:
            Editor instance or None
        """
        for editor in self._editors:
            if editor.can_edit(file_path):
                return editor

        logger.debug(f"No editor found for {file_path}")
        return None

    def get_editor_for_tool_and_file(self, tool_name: str, file_path: Path) -> Optional[BaseToolEditor]:
        """
        Get editor for a specific tool and file.

        Tries tool-specific editor first, falls back to file extension.

        Args:
            tool_name: Name of the tool
            file_path: Path to the file

        Returns:
            Editor instance or None
        """
        # Try tool-specific editor first
        editor = self.get_editor_for_tool(tool_name)
        if editor and editor.can_edit(file_path):
            return editor

        # Fall back to file extension
        return self.get_editor_for_file(file_path)

    def list_editors(self) -> List[BaseToolEditor]:
        """
        List all registered editors.

        Returns:
            List of editor instances
        """
        return self._editors.copy()

    def can_edit_file(self, file_path: Path) -> bool:
        """
        Check if any editor can edit this file.

        Args:
            file_path: Path to the file

        Returns:
            True if an editor is available
        """
        editor = self.get_editor_for_file(file_path)
        return editor is not None and editor.can_edit_files
