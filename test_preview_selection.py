#!/usr/bin/env python3
"""
Test script for Phase 1: Selection Integration

Tests that preview pane updates when items are selected in collection view.

Usage:
    python test_preview_selection.py

Expected behavior:
    1. App launches with Library view
    2. Select a collection
    3. Collection view shows items
    4. Select an item in collection view
    5. Preview pane should automatically load that item
    6. Deselect the item
    7. Preview pane should clear
"""

import logging
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

def test_selection_integration():
    """
    Manual test procedure for selection integration.

    This script just launches the app - the actual testing is manual:
    1. Launch app
    2. Select a collection from Library
    3. Select an item in Collection view
    4. Verify Preview pane loads the selected item
    5. Deselect the item
    6. Verify Preview pane clears
    """

    logger.info("=" * 60)
    logger.info("Phase 1: Selection Integration Test")
    logger.info("=" * 60)
    logger.info("")
    logger.info("MANUAL TEST PROCEDURE:")
    logger.info("1. App will launch - wait for Library view to appear")
    logger.info("2. Select a collection from the Library sidebar")
    logger.info("3. Collection view will show items")
    logger.info("4. Click on an item in the collection view")
    logger.info("5. VERIFY: Preview pane automatically loads the item")
    logger.info("6. Click again to deselect the item")
    logger.info("7. VERIFY: Preview pane clears")
    logger.info("")
    logger.info("Look for these log messages:")
    logger.info("  - '🔍 Preview selection change from view: collection'")
    logger.info("  - '📄 Loading preview for: [file path]'")
    logger.info("  - '✅ Preview event emitted for [file path]'")
    logger.info("  - '📤 Clearing preview pane (no selection)'")
    logger.info("")
    logger.info("=" * 60)
    logger.info("")

    # Import and run the app
    try:
        from fichero.app import main

        logger.info("Starting Fichero app...")
        app = main()

        if app:
            logger.info("App launched successfully")
            logger.info("Perform manual tests as described above")
            return app
        else:
            logger.error("Failed to launch app")
            return None

    except Exception as e:
        logger.error(f"Error launching app: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    test_selection_integration()
