#!/usr/bin/env python3
"""
Test script for ToolsMenuManager

Tests the menu structure without running the full GUI.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

import logging

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(levelname)s - %(name)s - %(message)s'
)

logger = logging.getLogger(__name__)


def test_tools_menu_manager():
    """Test ToolsMenuManager initialization and menu building"""
    logger.info("=" * 70)
    logger.info("Testing ToolsMenuManager")
    logger.info("=" * 70)

    try:
        # Import renderer registry
        from fichero.library.renderers.renderer_registry import RendererRegistry

        # Create registry
        registry = RendererRegistry()
        logger.info(f"✅ RendererRegistry initialized")
        logger.info(f"   Registered tools: {registry.list_registered_tools()}")

        # Create mock output_view
        class MockStepManager:
            def __init__(self):
                self.steps = []

            def get_state(self):
                class State:
                    item_id = None
                    step_index = 0
                return State()

            def get_current_step(self):
                return None

        class MockApp:
            class MainWindow:
                def info_dialog(self, title, message):
                    logger.info(f"Dialog: {title} - {message}")

            main_window = MainWindow()

        class MockOutputView:
            def __init__(self):
                self.step_manager = MockStepManager()
                self.app = MockApp()

            def _show_inspector(self):
                logger.info("_show_inspector called")

        output_view = MockOutputView()

        # Import ToolsMenuManager
        from fichero.windows.main.views.output.tools_menu_manager import ToolsMenuManager

        # Create manager
        manager = ToolsMenuManager(output_view, registry)
        logger.info(f"✅ ToolsMenuManager created")

        # Build menu
        tools_menu = manager.build_menu()
        logger.info(f"✅ Tools menu built")
        logger.info(f"   Menu: {tools_menu}")

        # Test menu state updates
        logger.info("\nTesting menu state updates...")
        manager.update_menu_states()
        logger.info("✅ Menu states updated")

        # Check menu items
        logger.info(f"\nMenu items created:")
        logger.info(f"   Adjust menu items: {len(manager.adjust_menu_items)}")
        logger.info(f"   Go To menu items: {len(manager.goto_menu_items)}")
        logger.info(f"   Process menu items: {len(manager.process_menu_items)}")

        # Test adjust action (should show error dialog since no item selected)
        logger.info("\nTesting Adjust Rotate action...")
        manager._on_adjust('rotate')

        # Test goto original
        logger.info("\nTesting Go To Original action...")
        manager._goto_original()

        # Test process rotate (should show error dialog)
        logger.info("\nTesting Process Rotate action...")
        manager._process_rotate()

        logger.info("\n" + "=" * 70)
        logger.info("✅ ALL TESTS PASSED")
        logger.info("=" * 70)

        return True

    except Exception as e:
        logger.error(f"❌ Test failed: {e}", exc_info=True)
        return False


if __name__ == '__main__':
    success = test_tools_menu_manager()
    sys.exit(0 if success else 1)
