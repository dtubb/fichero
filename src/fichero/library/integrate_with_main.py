"""
Integration Script for Fichero Library

Shows how to integrate the library system with the existing main window.
Run this after your main window is created to add library functionality.
"""

import logging
import asyncio
from typing import Optional

logger = logging.getLogger(__name__)


def integrate_library_into_main_window(app, main_window) -> Optional[object]:
    """
    Integrate the library system into the existing main window.
    
    This function should be called after your main window is fully initialized.
    
    Args:
        app: Toga app instance
        main_window: Main window instance
        
    Returns:
        Library integration object if successful, None otherwise
    """
    try:
        logger.info("Starting library integration with main window")
        
        # Import library components
        from fichero.library.integration_example import LibraryIntegrationExample
        
        # Create integration instance
        integration = LibraryIntegrationExample(app)
        
        # Run integration asynchronously
        success = asyncio.run(integration.integrate_with_main_window(main_window))
        
        if success:
            logger.info("✓ Library system successfully integrated with main window")
            return integration
        else:
            logger.error("✗ Failed to integrate library system with main window")
            return None
            
    except Exception as e:
        logger.error(f"✗ Library integration failed: {e}")
        return None


def add_library_to_library_pane(app, library_pane) -> bool:
    """
    Add library functionality to an existing library pane.
    
    This is a simpler integration that just adds library features to the library pane.
    
    Args:
        app: Toga app instance
        library_pane: Library pane instance
        
    Returns:
        True if successful, False otherwise
    """
    try:
        logger.info("Adding library functionality to library pane")
        
        # Import library components
        from fichero.library.library_manager import LibraryManager
        from fichero.library.ui_integration import LibraryUIIntegration
        from fichero.library.ui_hooks import LibraryUIHooks
        
        # Initialize library system
        library_manager = LibraryManager(app)
        ui_integration = LibraryUIIntegration(library_manager)
        ui_hooks = LibraryUIHooks(ui_integration)
        
        # Hook into library pane
        success = ui_hooks.hook_into_library_pane(library_pane)
        
        if success:
            logger.info("✓ Library functionality added to library pane")
            
            # Load existing collections
            asyncio.create_task(_load_collections_into_pane(ui_integration, library_pane))
            
            return True
        else:
            logger.error("✗ Failed to add library functionality to library pane")
            return False
            
    except Exception as e:
        logger.error(f"✗ Failed to add library to library pane: {e}")
        return False


async def _load_collections_into_pane(ui_integration, library_pane):
    """Load existing collections into the library pane"""
    try:
        # Get collections from backend
        collections = await ui_integration.get_collections_for_ui()
        
        # Add to library pane
        for collection in collections:
            if hasattr(library_pane, 'add_collection'):
                library_pane.add_collection(collection)
                logger.debug(f"Loaded collection into pane: {collection['name']}")
        
        logger.info(f"Loaded {len(collections)} collections into library pane")
        
    except Exception as e:
        logger.error(f"Failed to load collections into pane: {e}")


def add_library_to_toolbars(app, toolbars: dict) -> bool:
    """
    Add library functionality to existing toolbars.
    
    Args:
        app: Toga app instance
        toolbars: Dictionary of toolbars by type
        
    Returns:
        True if successful, False otherwise
    """
    try:
        logger.info("Adding library functionality to toolbars")
        
        # Import library components
        from fichero.library.library_manager import LibraryManager
        from fichero.library.ui_integration import LibraryUIIntegration
        from fichero.library.ui_hooks import LibraryUIHooks
        
        # Initialize library system
        library_manager = LibraryManager(app)
        ui_integration = LibraryUIIntegration(library_manager)
        ui_hooks = LibraryUIHooks(ui_integration)
        
        # Hook into toolbars
        success_count = 0
        for toolbar_type, toolbar in toolbars.items():
            if toolbar:
                if ui_hooks.hook_into_toolbar(toolbar, toolbar_type):
                    success_count += 1
                    logger.debug(f"Hooked into {toolbar_type} toolbar")
                else:
                    logger.warning(f"Failed to hook into {toolbar_type} toolbar")
        
        if success_count > 0:
            logger.info(f"✓ Successfully hooked into {success_count} toolbars")
            return True
        else:
            logger.error("✗ Failed to hook into any toolbars")
            return False
            
    except Exception as e:
        logger.error(f"✗ Failed to add library to toolbars: {e}")
        return False


def create_library_manager(app) -> Optional[object]:
    """
    Create a library manager instance for manual use.
    
    This is useful if you want to use the library system programmatically
    without full UI integration.
    
    Args:
        app: Toga app instance
        
    Returns:
        LibraryManager instance if successful, None otherwise
    """
    try:
        logger.info("Creating library manager instance")
        
        # Import library manager
        from fichero.library.library_manager import LibraryManager
        
        # Create instance
        library_manager = LibraryManager(app)
        
        logger.info("✓ Library manager created successfully")
        return library_manager
        
    except Exception as e:
        logger.error(f"✗ Failed to create library manager: {e}")
        return None


# Example usage functions
def example_full_integration(app, main_window):
    """Example of full integration with main window"""
    logger.info("Running full integration example")
    
    integration = integrate_library_into_main_window(app, main_window)
    if integration:
        logger.info("Full integration completed successfully")
        
        # You can now use the integration object
        # collections = await integration.get_collections()
        # integration.add_collection("My Collection", "external", "/path/to/source")
        
        return integration
    else:
        logger.error("Full integration failed")
        return None


def example_library_pane_integration(app, library_pane):
    """Example of integrating just the library pane"""
    logger.info("Running library pane integration example")
    
    success = add_library_to_library_pane(app, library_pane)
    if success:
        logger.info("Library pane integration completed successfully")
        return True
    else:
        logger.error("Library pane integration failed")
        return False


def example_toolbar_integration(app, toolbars):
    """Example of integrating just the toolbars"""
    logger.info("Running toolbar integration example")
    
    success = add_library_to_toolbars(app, toolbars)
    if success:
        logger.info("Toolbar integration completed successfully")
        return True
    else:
        logger.error("Toolbar integration failed")
        return False


def example_manual_usage(app):
    """Example of manual library usage without UI integration"""
    logger.info("Running manual usage example")
    
    library_manager = create_library_manager(app)
    if library_manager:
        logger.info("Manual usage setup completed successfully")
        
        # You can now use the library manager directly
        # collection_id = await library_manager.add_collection("Manual Collection", "external", "/path")
        # collections = await library_manager.get_all_collections()
        
        return library_manager
    else:
        logger.error("Manual usage setup failed")
        return None


# Main integration function
def integrate_library_system(app, main_window, integration_level: str = "full") -> Optional[object]:
    """
    Main function to integrate the library system.
    
    Args:
        app: Toga app instance
        main_window: Main window instance
        integration_level: Level of integration ("full", "pane", "toolbars", "manual")
        
    Returns:
        Integration object if successful, None otherwise
    """
    try:
        logger.info(f"Starting library system integration (level: {integration_level})")
        
        if integration_level == "full":
            return example_full_integration(app, main_window)
        elif integration_level == "pane":
            # Try to get library pane from main window
            library_pane = _find_library_pane(main_window)
            if library_pane:
                return example_library_pane_integration(app, library_pane)
            else:
                logger.error("Library pane not found for pane-level integration")
                return None
        elif integration_level == "toolbars":
            # Try to get toolbars from main window
            toolbars = _find_toolbars(main_window)
            if toolbars:
                return example_toolbar_integration(app, toolbars)
            else:
                logger.error("Toolbars not found for toolbar-level integration")
                return None
        elif integration_level == "manual":
            return example_manual_usage(app)
        else:
            logger.error(f"Unknown integration level: {integration_level}")
            return None
            
    except Exception as e:
        logger.error(f"Library system integration failed: {e}")
        return None


def _find_library_pane(main_window) -> Optional[object]:
    """Find the library pane in the main window"""
    try:
        # Try different approaches to find the library pane
        if hasattr(main_window, 'library_pane'):
            return main_window.library_pane
        
        if hasattr(main_window, 'pane_manager'):
            pane_manager = main_window.pane_manager
            if hasattr(pane_manager, 'get_left_pane'):
                left_pane = pane_manager.get_left_pane()
                if left_pane:
                    # Look for library pane in children
                    for child in left_pane.children:
                        if hasattr(child, '__class__') and 'Library' in child.__class__.__name__:
                            return child
        
        logger.warning("Could not find library pane in main window")
        return None
        
    except Exception as e:
        logger.error(f"Failed to find library pane: {e}")
        return None


def _find_toolbars(main_window) -> dict:
    """Find toolbars in the main window"""
    try:
        toolbars = {}
        
        # Try to find toolbar manager
        if hasattr(main_window, 'toolbar_manager'):
            toolbar_manager = main_window.toolbar_manager
            
            # Try to get different toolbar types
            for toolbar_type in ["library", "collection", "fiche", "preview"]:
                if hasattr(toolbar_manager, 'get_toolbar'):
                    toolbar = toolbar_manager.get_toolbar(toolbar_type)
                    if toolbar:
                        toolbars[toolbar_type] = toolbar
        
        if not toolbars:
            logger.warning("No toolbars found in main window")
        
        return toolbars
        
    except Exception as e:
        logger.error(f"Failed to find toolbars: {e}")
        return {}


# Convenience function for quick integration
def quick_integrate(app, main_window) -> Optional[object]:
    """
    Quick integration function that tries different integration levels.
    
    Args:
        app: Toga app instance
        main_window: Main window instance
        
    Returns:
        Integration object if successful, None otherwise
    """
    logger.info("Attempting quick library integration")
    
    # Try full integration first
    integration = integrate_library_system(app, main_window, "full")
    if integration:
        return integration
    
    # Try pane integration
    integration = integrate_library_system(app, main_window, "pane")
    if integration:
        return integration
    
    # Try toolbar integration
    integration = integrate_library_system(app, main_window, "toolbars")
    if integration:
        return integration
    
    # Fall back to manual usage
    logger.info("Falling back to manual library usage")
    return integrate_library_system(app, main_window, "manual") 