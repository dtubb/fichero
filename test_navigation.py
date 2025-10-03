#!/usr/bin/env python3
"""
Navigation Test Script

Demonstrates the navigation system by running a series of commands
to show how the event-driven navigation works.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

import asyncio
from fichero.textual_app import TextualFichero

async def test_navigation():
    """Test navigation flows"""
    app = TextualFichero()

    # Initialize
    print("=== INITIALIZING NAVIGATION SYSTEM ===")
    if not await app.initialize():
        print("❌ Failed to initialize")
        return

    # Start in library view
    print("\n=== STARTING IN LIBRARY ===")
    app.navigation_controller.navigate_to_library()

    # Show current state
    print("\n=== CURRENT STATE ===")
    app._show_navigation_state()

    print("\n=== NAVIGATING TO COLLECTION 1 ===")
    app.navigation_controller.navigate_to_collection("collection_1", "Sample Collection")

    # Show state after navigation
    print("\n=== STATE AFTER COLLECTION NAVIGATION ===")
    app._show_navigation_state()

    print("\n=== NAVIGATION HISTORY ===")
    app._show_history()

    print("\n=== BREADCRUMBS ===")
    app._show_breadcrumbs()

    print("\n=== NAVIGATING TO FILE PREVIEW ===")
    app.navigation_controller.navigate_to_preview("/path/to/document1.pdf", {"name": "document1.pdf"})

    print("\n=== STATE IN PREVIEW ===")
    app._show_navigation_state()

    print("\n=== HISTORY AFTER PREVIEW ===")
    app._show_history()

    print("\n=== NAVIGATING BACK ===")
    success = app.navigation_controller.navigate_back()
    print(f"Back navigation success: {success}")

    print("\n=== STATE AFTER GOING BACK ===")
    app._show_navigation_state()

    print("\n=== NAVIGATING BACK AGAIN ===")
    success = app.navigation_controller.navigate_back()
    print(f"Back navigation success: {success}")

    print("\n=== FINAL STATE ===")
    app._show_navigation_state()

    print("\n=== CAN GO BACK? ===")
    print(f"Can navigate back: {app.navigation_controller.can_navigate_back()}")
    print(f"Can navigate forward: {app.navigation_controller.can_navigate_forward()}")

    print("\n✅ Navigation test complete!")

if __name__ == "__main__":
    asyncio.run(test_navigation())