"""
Integration Example for Fichero Library

Shows how to integrate the library system into existing UI components.
"""

import logging
import asyncio
from typing import Optional

from fichero.library.library_manager import LibraryManager
from fichero.library.ui_integration import LibraryUIIntegration
from fichero.library.ui_hooks import LibraryUIHooks

logger = logging.getLogger(__name__)


class LibraryIntegrationExample:
    """Example of how to integrate library system into existing UI"""
    
    def __init__(self, app):
        """Initialize integration example"""
        self.app = app
        
        # Initialize library system
        self.library_manager = LibraryManager(app)
        self.ui_integration = LibraryUIIntegration(self.library_manager)
        self.ui_hooks = LibraryUIHooks(self.ui_integration)
        
        logger.info("Library integration example initialized")
    
    async def integrate_with_main_window(self, main_window) -> bool:
        """Integrate library system with main window"""
        try:
            logger.info("Starting library integration with main window")
            
            # Get the library pane from main window
            library_pane = self._get_library_pane(main_window)
            if not library_pane:
                logger.warning("Library pane not found in main window")
                return False
            
            # Hook into library pane
            if not self.ui_hooks.hook_into_library_pane(library_pane):
                logger.error("Failed to hook into library pane")
                return False
            
            # Get collection view if available
            collection_view = self._get_collection_view(main_window)
            if collection_view:
                if not self.ui_hooks.hook_into_collection_view(collection_view):
                    logger.warning("Failed to hook into collection view")
            
            # Hook into toolbars
            self._hook_into_toolbars(main_window)
            
            # Load existing collections
            await self._load_existing_collections(library_pane)
            
            logger.info("Successfully integrated library system with main window")
            return True
            
        except Exception as e:
            logger.error(f"Failed to integrate with main window: {e}")
            return False
    
    def _get_library_pane(self, main_window) -> Optional[object]:
        """Get the library pane from main window"""
        try:
            # Try to find library pane in main window
            if hasattr(main_window, 'pane_manager'):
                pane_manager = main_window.pane_manager
                if hasattr(pane_manager, 'get_left_pane'):
                    left_pane = pane_manager.get_left_pane()
                    if left_pane and hasattr(left_pane, 'children'):
                        # Look for library pane in children
                        for child in left_pane.children:
                            if hasattr(child, '__class__') and 'Library' in child.__class__.__name__:
                                return child
            
            # Try alternative approach
            if hasattr(main_window, 'library_pane'):
                return main_window.library_pane
            
            logger.warning("Could not find library pane in main window")
            return None
            
        except Exception as e:
            logger.error(f"Failed to get library pane: {e}")
            return None
    
    def _get_collection_view(self, main_window) -> Optional[object]:
        """Get the collection view from main window"""
        try:
            # Try to find collection view
            if hasattr(main_window, 'content_pane'):
                content_pane = main_window.content_pane
                if hasattr(content_pane, 'get_current_view'):
                    current_view = content_pane.get_current_view()
                    if current_view and hasattr(current_view, '__class__') and 'Collection' in current_view.__class__.__name__:
                        return current_view
            
            logger.debug("Collection view not found in main window")
            return None
            
        except Exception as e:
            logger.error(f"Failed to get collection view: {e}")
            return None
    
    def _hook_into_toolbars(self, main_window):
        """Hook into toolbars in main window"""
        try:
            # Try to find toolbars
            if hasattr(main_window, 'toolbar_manager'):
                toolbar_manager = main_window.toolbar_manager
                # Hook into different toolbar types
                self._hook_into_toolbar_by_type(toolbar_manager, "library")
                self._hook_into_toolbar_by_type(toolbar_manager, "collection")
                self._hook_into_toolbar_by_type(toolbar_manager, "fiche")
            
        except Exception as e:
            logger.error(f"Failed to hook into toolbars: {e}")
    
    def _hook_into_toolbar_by_type(self, toolbar_manager, toolbar_type: str):
        """Hook into specific toolbar type"""
        try:
            # Try to get toolbar by type
            if hasattr(toolbar_manager, 'get_toolbar'):
                toolbar = toolbar_manager.get_toolbar(toolbar_type)
                if toolbar:
                    self.ui_hooks.hook_into_toolbar(toolbar, toolbar_type)
                    logger.debug(f"Hooked into {toolbar_type} toolbar")
            
        except Exception as e:
            logger.debug(f"Could not hook into {toolbar_type} toolbar: {e}")
    
    async def _load_existing_collections(self, library_pane):
        """Load existing collections from backend into UI"""
        try:
            # Get collections from backend
            collections = await self.ui_integration.get_collections_for_ui()
            
            # Add to library pane
            for collection in collections:
                if hasattr(library_pane, 'add_collection'):
                    library_pane.add_collection(collection)
                    logger.debug(f"Loaded collection into UI: {collection['name']}")
            
            logger.info(f"Loaded {len(collections)} collections into UI")
            
        except Exception as e:
            logger.error(f"Failed to load existing collections: {e}")
    
    # ===== PUBLIC API =====
    
    async def add_collection(self, name: str, collection_type: str, source_path: Optional[str] = None) -> bool:
        """Add a collection through the library system"""
        return await self.ui_integration.add_collection_from_ui(
            name=name,
            collection_type=collection_type,
            source_path=source_path
        )
    
    async def get_collections(self) -> list:
        """Get all collections from the library system"""
        return await self.ui_integration.get_collections_for_ui()
    
    async def export_collection(self, collection_id: str, output_path: str, include_files: bool = False) -> bool:
        """Export a collection"""
        from pathlib import Path
        return await self.ui_integration.export_collection_from_ui(
            collection_id=collection_id,
            output_path=Path(output_path),
            include_files=include_files
        )
    
    async def import_collection(self, import_path: str, target_name: Optional[str] = None) -> bool:
        """Import a collection"""
        from pathlib import Path
        return await self.ui_integration.import_collection_from_ui(
            import_path=Path(import_path),
            target_name=target_name
        )
    
    def get_library_stats(self) -> dict:
        """Get library statistics"""
        return asyncio.run(self.ui_integration.get_library_stats_for_ui())
    
    # ===== DEMO METHODS =====
    
    async def create_demo_collections(self) -> bool:
        """Create some demo collections for testing"""
        try:
            logger.info("Creating demo collections")
            
            # Create external collection
            await self.add_collection(
                name="Demo External Collection",
                collection_type="external",
                source_path="/tmp/demo_external"
            )
            
            # Create URL collection
            await self.add_collection(
                name="Demo URL Collection",
                collection_type="url",
                source_path="https://example.com/demo"
            )
            
            # Create local collection
            await self.add_collection(
                name="Demo Local Collection",
                collection_type="local",
                source_path="/tmp/demo_local"
            )
            
            logger.info("Demo collections created successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create demo collections: {e}")
            return False
    
    async def run_demo(self) -> bool:
        """Run a complete demo of the library system"""
        try:
            logger.info("Starting library system demo")
            
            # Create demo collections
            if not await self.create_demo_collections():
                return False
            
            # Get collections
            collections = await self.get_collections()
            logger.info(f"Demo created {len(collections)} collections")
            
            # Show library stats
            stats = self.get_library_stats()
            logger.info(f"Library stats: {stats}")
            
            logger.info("Library system demo completed successfully")
            return True
            
        except Exception as e:
            logger.error(f"Demo failed: {e}")
            return False


# Convenience function for quick integration
def integrate_library_with_main_window(app, main_window) -> Optional[LibraryIntegrationExample]:
    """Quick integration function"""
    try:
        integration = LibraryIntegrationExample(app)
        
        # Run integration
        success = asyncio.run(integration.integrate_with_main_window(main_window))
        
        if success:
            logger.info("Library system integrated successfully")
            return integration
        else:
            logger.error("Failed to integrate library system")
            return None
            
    except Exception as e:
        logger.error(f"Integration failed: {e}")
        return None 