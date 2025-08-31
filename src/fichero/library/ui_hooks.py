"""
UI Hooks for Fichero Library

Provides hooks and utilities for integrating library functionality into existing UI components.
"""

import logging
import asyncio
from typing import List, Optional, Dict, Any, Callable
from pathlib import Path

try:
    from fichero.library.ui_integration import LibraryUIIntegration
    from fichero.library.models import Collection
except ImportError:
    try:
        from .ui_integration import LibraryUIIntegration
        from .models import Collection
    except ImportError:
        # Direct import for testing
        import ui_integration
        import models
        LibraryUIIntegration = ui_integration.LibraryUIIntegration
        Collection = models.Collection

logger = logging.getLogger(__name__)


class LibraryUIHooks:
    """Provides hooks for integrating library functionality into existing UI"""
    
    def __init__(self, ui_integration: LibraryUIIntegration):
        """Initialize UI hooks with integration layer"""
        self.ui_integration = ui_integration
        
        # Hook callbacks
        self._hooks: Dict[str, List[Callable]] = {}
        
        logger.info("Library UI hooks initialized")
    
    # ===== LIBRARY PANE HOOKS =====
    
    def hook_into_library_pane(self, library_pane) -> bool:
        """Hook library functionality into existing library pane"""
        try:
            # Register callbacks
            self.ui_integration.register_ui_callbacks(
                on_collection_added=self._on_collection_added,
                on_collection_updated=self._on_collection_updated,
                on_collection_deleted=self._on_collection_deleted
            )
            
            # Hook into library pane methods
            if hasattr(library_pane, 'add_collection'):
                # Store original method
                original_add = library_pane.add_collection
                
                # Create hooked method
                async def hooked_add_collection(collection_data: Dict[str, Any]):
                    # Call original method
                    if asyncio.iscoroutinefunction(original_add):
                        await original_add(collection_data)
                    else:
                        original_add(collection_data)
                    
                    # Add to library backend
                    await self._add_collection_to_backend(collection_data)
                
                # Replace method
                library_pane.add_collection = hooked_add_collection
                logger.debug("Hooked into library_pane.add_collection")
            
            # Hook into refresh method
            if hasattr(library_pane, 'refresh'):
                original_refresh = library_pane.refresh
                
                async def hooked_refresh():
                    # Call original method
                    if asyncio.iscoroutinefunction(original_refresh):
                        await original_refresh()
                    else:
                        original_refresh()
                    
                    # Refresh from backend
                    await self._refresh_from_backend(library_pane)
                
                library_pane.refresh = hooked_refresh
                logger.debug("Hooked into library_pane.refresh")
            
            logger.info("Successfully hooked into library pane")
            return True
            
        except Exception as e:
            logger.error(f"Failed to hook into library pane: {e}")
            return False
    
    async def _add_collection_to_backend(self, collection_data: Dict[str, Any]):
        """Add collection to backend when added through UI"""
        try:
            name = collection_data.get('name', 'Unknown')
            collection_type = collection_data.get('type', 'external')
            source_path = collection_data.get('source_path')
            
            await self.ui_integration.add_collection_from_ui(
                name=name,
                collection_type=collection_type,
                source_path=source_path
            )
            
        except Exception as e:
            logger.error(f"Failed to add collection to backend: {e}")
    
    async def _refresh_from_backend(self, library_pane):
        """Refresh library pane from backend data"""
        try:
            # Get collections from backend
            collections = await self.ui_integration.get_collections_for_ui()
            
            # Update library pane if it has a method to do so
            if hasattr(library_pane, 'update_collections_from_backend'):
                library_pane.update_collections_from_backend(collections)
            elif hasattr(library_pane, 'clear_collections'):
                # Clear and rebuild
                library_pane.clear_collections()
                for collection in collections:
                    library_pane.add_collection(collection)
            
        except Exception as e:
            logger.error(f"Failed to refresh from backend: {e}")
    
    # ===== COLLECTION VIEW HOOKS =====
    
    def hook_into_collection_view(self, collection_view) -> bool:
        """Hook library functionality into existing collection view"""
        try:
            # Hook into add methods
            if hasattr(collection_view, 'add_folder'):
                original_add_folder = collection_view.add_folder
                
                async def hooked_add_folder(folder_path: str):
                    # Call original method
                    if asyncio.iscoroutinefunction(original_add_folder):
                        await original_add_folder(folder_path)
                    else:
                        original_add_folder(folder_path)
                    
                    # Add to backend
                    await self._add_folder_to_backend(collection_view, folder_path)
                
                collection_view.add_folder = hooked_add_folder
                logger.debug("Hooked into collection_view.add_folder")
            
            if hasattr(collection_view, 'add_file'):
                original_add_file = collection_view.add_file
                
                async def hooked_add_file(file_path: str):
                    # Call original method
                    if asyncio.iscoroutinefunction(original_add_file):
                        await original_add_file(file_path)
                    else:
                        original_add_file(file_path)
                    
                    # Add to backend
                    await self._add_file_to_backend(collection_view, file_path)
                
                collection_view.add_file = hooked_add_file
                logger.debug("Hooked into collection_view.add_file")
            
            logger.info("Successfully hooked into collection view")
            return True
            
        except Exception as e:
            logger.error(f"Failed to hook into collection view: {e}")
            return False
    
    async def _add_folder_to_backend(self, collection_view, folder_path: str):
        """Add folder to backend when added through collection view"""
        try:
            # Get current collection ID from view
            collection_id = getattr(collection_view, 'collection_id', None)
            if not collection_id:
                logger.warning("No collection ID found in collection view")
                return
            
            await self.ui_integration.add_folder_to_collection_from_ui(
                collection_id=collection_id,
                folder_path=folder_path,
                operation="link"  # Default to linking
            )
            
        except Exception as e:
            logger.error(f"Failed to add folder to backend: {e}")
    
    async def _add_file_to_backend(self, collection_view, file_path: str):
        """Add file to backend when added through collection view"""
        try:
            # Get current collection ID from view
            collection_id = getattr(collection_view, 'collection_id', None)
            if not collection_id:
                logger.warning("No collection ID found in collection view")
                return
            
            await self.ui_integration.add_file_to_collection_from_ui(
                collection_id=collection_id,
                file_path=file_path,
                operation="link"  # Default to linking
            )
            
        except Exception as e:
            logger.error(f"Failed to add file to backend: {e}")
    
    # ===== TOOLBAR HOOKS =====
    
    def hook_into_toolbar(self, toolbar, toolbar_type: str) -> bool:
        """Hook library functionality into existing toolbars"""
        try:
            if toolbar_type == "library":
                return self._hook_into_library_toolbar(toolbar)
            elif toolbar_type == "collection":
                return self._hook_into_collection_toolbar(toolbar)
            elif toolbar_type == "fiche":
                return self._hook_into_fiche_toolbar(toolbar)
            else:
                logger.warning(f"Unknown toolbar type: {toolbar_type}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to hook into toolbar: {e}")
            return False
    
    def _hook_into_library_toolbar(self, toolbar) -> bool:
        """Hook into library toolbar"""
        try:
            # Hook into add collection button
            if hasattr(toolbar, 'on_add_collection'):
                original_callback = toolbar.on_add_collection
                
                async def hooked_add_collection():
                    # Call original callback
                    if asyncio.iscoroutinefunction(original_callback):
                        await original_callback()
                    else:
                        original_callback()
                    
                    # Show add collection dialog
                    await self._show_add_collection_dialog()
                
                toolbar.on_add_collection = hooked_add_collection
                logger.debug("Hooked into library toolbar add collection")
            
            logger.info("Successfully hooked into library toolbar")
            return True
            
        except Exception as e:
            logger.error(f"Failed to hook into library toolbar: {e}")
            return False
    
    def _hook_into_collection_toolbar(self, toolbar) -> bool:
        """Hook into collection toolbar"""
        try:
            # Hook into add folder/file buttons
            if hasattr(toolbar, 'on_add_folder'):
                original_callback = toolbar.on_add_folder
                
                async def hooked_add_folder():
                    # Call original callback
                    if asyncio.iscoroutinefunction(original_callback):
                        await original_callback()
                    else:
                        original_callback()
                    
                    # Show add folder dialog
                    await self._show_add_folder_dialog()
                
                toolbar.on_add_folder = hooked_add_folder
                logger.debug("Hooked into collection toolbar add folder")
            
            logger.info("Successfully hooked into collection toolbar")
            return True
            
        except Exception as e:
            logger.error(f"Failed to hook into collection toolbar: {e}")
            return False
    
    def _hook_into_fiche_toolbar(self, toolbar) -> bool:
        """Hook into fiche toolbar"""
        try:
            # Hook into process button
            if hasattr(toolbar, 'on_process_folder'):
                original_callback = toolbar.on_process_folder
                
                async def hooked_process_folder():
                    # Call original callback
                    if asyncio.iscoroutinefunction(original_callback):
                        await original_callback()
                    else:
                        original_callback()
                    
                    # Start processing
                    await self._start_folder_processing()
                
                toolbar.on_process_folder = hooked_process_folder
                logger.debug("Hooked into fiche toolbar process folder")
            
            logger.info("Successfully hooked into fiche toolbar")
            return True
            
        except Exception as e:
            logger.error(f"Failed to hook into fiche toolbar: {e}")
            return False
    
    # ===== DIALOG HOOKS =====
    
    async def _show_add_collection_dialog(self):
        """Show add collection dialog"""
        try:
            # This would show a dialog for adding collections
            # For now, just log the action
            logger.debug("Add collection dialog requested")
            
            # You could integrate with your existing dialog system here
            
        except Exception as e:
            logger.error(f"Failed to show add collection dialog: {e}")
    
    async def _show_add_folder_dialog(self):
        """Show add folder dialog"""
        try:
            # This would show a dialog for adding folders
            # For now, just log the action
            logger.debug("Add folder dialog requested")
            
            # You could integrate with your existing dialog system here
            
        except Exception as e:
            logger.error(f"Failed to show add folder dialog: {e}")
    
    async def _start_folder_processing(self):
        """Start folder processing"""
        try:
            # This would start the processing workflow
            # For now, just log the action
            logger.debug("Folder processing requested")
            
            # You could integrate with your director system here
            
        except Exception as e:
            logger.error(f"Failed to start folder processing: {e}")
    
    # ===== EVENT HOOKS =====
    
    def _on_collection_added(self, collection: Collection):
        """Handle collection added event"""
        try:
            logger.debug(f"Collection added event: {collection.name}")
            
            # Trigger hooks
            self._trigger_hooks('collection_added', collection)
            
        except Exception as e:
            logger.error(f"Failed to handle collection added event: {e}")
    
    def _on_collection_updated(self, collection: Collection):
        """Handle collection updated event"""
        try:
            logger.debug(f"Collection updated event: {collection.name}")
            
            # Trigger hooks
            self._trigger_hooks('collection_updated', collection)
            
        except Exception as e:
            logger.error(f"Failed to handle collection updated event: {e}")
    
    def _on_collection_deleted(self, collection_id: str):
        """Handle collection deleted event"""
        try:
            logger.debug(f"Collection deleted event: {collection_id}")
            
            # Trigger hooks
            self._trigger_hooks('collection_deleted', collection_id)
            
        except Exception as e:
            logger.error(f"Failed to handle collection deleted event: {e}")
    
    # ===== HOOK REGISTRATION =====
    
    def register_hook(self, event: str, callback: Callable):
        """Register a hook for library events"""
        if event not in self._hooks:
            self._hooks[event] = []
        
        self._hooks[event].append(callback)
        logger.debug(f"Hook registered for event: {event}")
    
    def _trigger_hooks(self, event: str, data: Any):
        """Trigger hooks for an event"""
        if event in self._hooks:
            for callback in self._hooks[event]:
                try:
                    callback(data)
                except Exception as e:
                    logger.error(f"Hook callback failed: {e}")
    
    # ===== UTILITY METHODS =====
    
    def get_hook_info(self) -> Dict[str, Any]:
        """Get information about registered hooks"""
        return {
            "total_hooks": sum(len(callbacks) for callbacks in self._hooks.values()),
            "events": list(self._hooks.keys()),
            "hook_counts": {event: len(callbacks) for event, callbacks in self._hooks.items()}
        } 