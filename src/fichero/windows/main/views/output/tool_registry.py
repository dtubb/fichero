"""
ToolRegistry - Registry for tool-specific renderers

Provides a plugin architecture where each tool can have its own renderer
for displaying outputs. Makes it easy to add new tool visualizations.
"""

import logging
from typing import Dict, Type, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class ToolRegistry:
    """
    Registry for tool renderers.

    Each tool (prepare_images, transcribe_qwen_max, etc.) can register
    a renderer class that knows how to display its outputs.
    """

    _instance = None
    _renderers: Dict[str, Type] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        """Initialize registry with built-in renderers"""
        logger.info("Initializing ToolRegistry")
        self._renderers = {}

    @classmethod
    def register(cls, tool_name: str, renderer_class: Type):
        """
        Register a renderer for a tool.

        Args:
            tool_name: Tool name (e.g. "prepare_images", "transcribe_qwen_max")
            renderer_class: Renderer class (must subclass BaseRenderer)
        """
        instance = cls()
        instance._renderers[tool_name] = renderer_class
        logger.info(f"Registered renderer for tool: {tool_name}")

    @classmethod
    def get_renderer(cls, tool_name: str, file_path: Path = None) -> Optional[Type]:
        """
        Get renderer for a tool.

        Args:
            tool_name: Tool name
            file_path: Optional file path (for fallback based on file type)

        Returns:
            Renderer class or None if not found
        """
        instance = cls()

        # Try exact tool name match first
        if tool_name in instance._renderers:
            return instance._renderers[tool_name]

        # Fallback: Try to determine renderer from file extension
        if file_path:
            ext = file_path.suffix.lower()

            # Image files
            if ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp']:
                return instance._renderers.get('image', None)

            # Text files
            elif ext in ['.txt', '.md']:
                return instance._renderers.get('text', None)

            # JSON files
            elif ext == '.json' or ext == '.jsonl':
                return instance._renderers.get('json', None)

            # Document files
            elif ext in ['.docx', '.doc']:
                return instance._renderers.get('document', None)

        # No renderer found
        logger.warning(f"No renderer found for tool: {tool_name}, file: {file_path}")
        return None

    @classmethod
    def get_renderer_for_file_type(cls, file_type: str) -> Optional[Type]:
        """
        Get renderer based on file type.

        Args:
            file_type: File type ("image", "text", "json", "document", "folder")

        Returns:
            Renderer class or None
        """
        instance = cls()
        return instance._renderers.get(file_type, None)

    @classmethod
    def list_registered_tools(cls) -> list:
        """List all registered tool names"""
        instance = cls()
        return list(instance._renderers.keys())
