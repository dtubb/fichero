"""
Plugin Registry

Manages registration and discovery of import plugins.
"""

import logging
from typing import List, Optional, Dict, Any
from .base import ImportPlugin

logger = logging.getLogger(__name__)


class PluginRegistry:
    """
    Registry for import plugins

    Manages plugin registration, discovery, and routing of URLs to appropriate plugins.
    """

    def __init__(self):
        """Initialize empty registry"""
        self._plugins: List[ImportPlugin] = []

    def register(self, plugin: ImportPlugin) -> None:
        """
        Register a plugin

        Args:
            plugin: Plugin instance to register
        """
        if not isinstance(plugin, ImportPlugin):
            raise TypeError(f"Plugin must be instance of ImportPlugin, got {type(plugin)}")

        # Check for duplicate
        for existing in self._plugins:
            if existing.__class__ == plugin.__class__:
                logger.warning(f"Plugin {plugin.name} already registered, skipping")
                return

        self._plugins.append(plugin)
        logger.info(f"Registered plugin: {plugin.name} v{plugin.version}")

    def unregister(self, plugin_name: str) -> bool:
        """
        Unregister a plugin by name

        Args:
            plugin_name: Name of plugin to unregister

        Returns:
            True if plugin was found and unregistered, False otherwise
        """
        for i, plugin in enumerate(self._plugins):
            if plugin.name == plugin_name:
                self._plugins.pop(i)
                logger.info(f"Unregistered plugin: {plugin_name}")
                return True
        return False

    def get_plugin(self, plugin_name: str) -> Optional[ImportPlugin]:
        """
        Get plugin by name

        Args:
            plugin_name: Name of plugin to retrieve

        Returns:
            Plugin instance or None if not found
        """
        for plugin in self._plugins:
            if plugin.name == plugin_name:
                return plugin
        return None

    def get_plugin_by_name(self, plugin_name: str) -> Optional[ImportPlugin]:
        """Alias for get_plugin for compatibility"""
        return self.get_plugin(plugin_name)

    def find_plugin_for_url(self, url: str) -> Optional[ImportPlugin]:
        """
        Find the first plugin that can handle a given URL

        Args:
            url: URL to check

        Returns:
            Plugin instance or None if no plugin can handle the URL
        """
        for plugin in self._plugins:
            if plugin.can_handle(url):
                logger.debug(f"Found plugin {plugin.name} for URL: {url}")
                return plugin

        logger.debug(f"No plugin found for URL: {url}")
        return None

    def list_plugins(self) -> List[Dict[str, Any]]:
        """
        Get list of all registered plugins with their info

        Returns:
            List of plugin info dictionaries
        """
        return [plugin.get_plugin_info() for plugin in self._plugins]

    def get_all_plugins(self) -> List[ImportPlugin]:
        """
        Get all registered plugin instances

        Returns:
            List of plugin instances
        """
        return self._plugins.copy()

    def clear(self) -> None:
        """Clear all registered plugins"""
        count = len(self._plugins)
        self._plugins.clear()
        logger.info(f"Cleared {count} plugins from registry")

    def __len__(self) -> int:
        """Get number of registered plugins"""
        return len(self._plugins)

    def __repr__(self) -> str:
        """String representation of registry"""
        plugin_names = [p.name for p in self._plugins]
        return f"<PluginRegistry plugins={plugin_names}>"
