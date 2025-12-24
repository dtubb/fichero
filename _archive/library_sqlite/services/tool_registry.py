"""
ToolRegistry - Central tool discovery and registration

Provides decorator-based registration system for StandardTool implementations.
All tools must register to be discoverable by ToolExecutionService.
"""

from typing import Dict, Type, Optional, List
import logging

logger = logging.getLogger(__name__)


class ToolRegistry:
    """
    Central registry for all processing tools.

    Tools register themselves via decorator:
        @ToolRegistry.register
        class CropTool(StandardTool):
            ...

    ToolExecutionService queries this registry to find and instantiate tools.
    """

    _tools: Dict[str, Type['StandardTool']] = {}
    _initialized: bool = False

    @classmethod
    def register(cls, tool_class: Type['StandardTool']):
        """
        Register a tool class.

        Can be used as a decorator:
            @ToolRegistry.register
            class MyCropTool(StandardTool):
                def get_tool_name(self) -> str:
                    return "crop"

        Args:
            tool_class: StandardTool subclass to register

        Returns:
            The tool class (for decorator usage)

        Raises:
            ValueError: If tool_name already registered
        """
        # Instantiate to get tool name
        try:
            tool_instance = tool_class()
            tool_name = tool_instance.get_tool_name()
        except Exception as e:
            logger.error(f"Failed to instantiate tool {tool_class.__name__}: {e}")
            return tool_class

        # Check for conflicts
        if tool_name in cls._tools:
            existing_class = cls._tools[tool_name]
            logger.warning(
                f"Tool '{tool_name}' already registered by {existing_class.__name__}, "
                f"overwriting with {tool_class.__name__}"
            )

        cls._tools[tool_name] = tool_class
        logger.info(f"Registered tool: {tool_name} ({tool_class.__name__})")

        return tool_class

    @classmethod
    def get_tool(cls, tool_name: str) -> Optional['StandardTool']:
        """
        Get tool instance by name.

        Args:
            tool_name: Tool identifier (e.g., 'crop', 'enhance')

        Returns:
            Tool instance or None if not found

        Example:
            >>> tool = ToolRegistry.get_tool('crop')
            >>> if tool:
            ...     result = await tool.process(...)
        """
        tool_class = cls._tools.get(tool_name)
        if not tool_class:
            logger.warning(f"Tool '{tool_name}' not found in registry")
            return None

        try:
            return tool_class()
        except Exception as e:
            logger.error(f"Failed to instantiate tool '{tool_name}': {e}")
            return None

    @classmethod
    def get_tool_class(cls, tool_name: str) -> Optional[Type['StandardTool']]:
        """
        Get tool class (not instance) by name.

        Useful when you want to check tool properties without instantiating.

        Args:
            tool_name: Tool identifier

        Returns:
            Tool class or None if not found
        """
        return cls._tools.get(tool_name)

    @classmethod
    def list_tools(cls) -> List[str]:
        """
        List all registered tool names.

        Returns:
            List of tool names (sorted alphabetically)

        Example:
            >>> ToolRegistry.list_tools()
            ['crop', 'enhance', 'rotate', 'split']
        """
        return sorted(cls._tools.keys())

    @classmethod
    def is_registered(cls, tool_name: str) -> bool:
        """
        Check if a tool is registered.

        Args:
            tool_name: Tool identifier

        Returns:
            True if tool is registered

        Example:
            >>> ToolRegistry.is_registered('crop')
            True
            >>> ToolRegistry.is_registered('unknown')
            False
        """
        return tool_name in cls._tools

    @classmethod
    def unregister(cls, tool_name: str) -> bool:
        """
        Unregister a tool.

        Useful for testing or dynamic tool loading/unloading.

        Args:
            tool_name: Tool to unregister

        Returns:
            True if tool was unregistered, False if not found
        """
        if tool_name in cls._tools:
            del cls._tools[tool_name]
            logger.info(f"Unregistered tool: {tool_name}")
            return True
        return False

    @classmethod
    def clear(cls):
        """
        Clear all registered tools.

        Useful for testing. Use with caution in production.
        """
        cls._tools.clear()
        logger.warning("Cleared all registered tools")

    @classmethod
    def get_tools_info(cls) -> Dict[str, Dict[str, any]]:
        """
        Get detailed information about all registered tools.

        Returns:
            Dictionary mapping tool names to their info:
                {
                    'crop': {
                        'class': 'CropTool',
                        'module': 'fichero.tools.crop_tool',
                        'supports_batch': True,
                        'formats': ['jpg', 'png']
                    },
                    ...
                }
        """
        info = {}
        for tool_name, tool_class in cls._tools.items():
            try:
                tool = tool_class()
                info[tool_name] = {
                    'class': tool_class.__name__,
                    'module': tool_class.__module__,
                    'supports_batch': tool.supports_batch_processing(),
                    'formats': tool.get_supported_input_formats(),
                    'manifest_folder': tool.get_manifest_folder(),
                }
            except Exception as e:
                logger.error(f"Failed to get info for tool '{tool_name}': {e}")
                info[tool_name] = {'error': str(e)}

        return info

    @classmethod
    def __repr__(cls) -> str:
        """String representation for debugging"""
        tools = cls.list_tools()
        return f"<ToolRegistry: {len(tools)} tools registered: {', '.join(tools)}>"
