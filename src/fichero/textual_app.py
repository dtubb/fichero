"""
Textual Version of Fichero

A command-line interface using the same NavigationController
to test navigation logic without GUI complexity.
"""

import logging
from typing import Optional
import asyncio

from fichero.shared.navigation.navigation_controller import NavigationController
from fichero.shared.navigation.navigation_event_bus import subscribe_to_navigation, NavigationEvents
from fichero.core.app_initializer import FicheroAppInitializer

logger = logging.getLogger(__name__)


class TextualFichero:
    """Textual interface for Fichero navigation testing"""

    def __init__(self):
        """Initialize textual interface"""
        self.navigation_controller: Optional[NavigationController] = None
        self.current_view = "library"
        self.running = False

        print("🔧 Initializing Textual Fichero...")

    async def initialize(self):
        """Initialize the core systems"""
        try:
            # Create a minimal mock library service for testing
            print("🧭 Creating NavigationController with mock services...")

            class MockLibraryService:
                """Mock library service for testing"""
                pass

            library_service = MockLibraryService()

            self.navigation_controller = NavigationController(
                library_service=library_service,
                is_mobile=False  # Textual is like desktop
            )

            # Subscribe to navigation events
            print("📡 Subscribing to navigation events...")
            subscribe_to_navigation(NavigationEvents.SHOW_LIBRARY, self._on_show_library)
            subscribe_to_navigation(NavigationEvents.SHOW_COLLECTION, self._on_show_collection)
            subscribe_to_navigation(NavigationEvents.SHOW_PREVIEW, self._on_show_preview)
            subscribe_to_navigation(NavigationEvents.NAVIGATION_ERROR, self._on_navigation_error)

            print("✅ Textual Fichero initialized successfully")
            return True

        except Exception as e:
            print(f"❌ Failed to initialize Textual Fichero: {e}")
            logger.error(f"Textual initialization failed: {e}")
            return False

    def _on_show_library(self, event):
        """Handle show library event"""
        self.current_view = "library"
        print("\n📚 === LIBRARY VIEW ===")
        print("Available collections:")
        print("  1. Sample Collection")
        print("  2. Demo Collection")
        print("  3. Test Collection")
        self._show_commands()

    def _on_show_collection(self, event):
        """Handle show collection event"""
        data = event.data
        collection_name = data.get('collection_name', 'Unknown')
        self.current_view = "collection"
        print(f"\n📁 === COLLECTION: {collection_name} ===")
        print("Collection contents:")
        print("  📄 document1.pdf")
        print("  📄 document2.jpg")
        print("  📁 subfolder/")
        print("  📄 image3.png")
        self._show_commands()

    def _on_show_preview(self, event):
        """Handle show preview event"""
        data = event.data
        file_path = data.get('file_path', 'Unknown')
        self.current_view = "preview"
        print(f"\n🔍 === PREVIEW: {file_path} ===")
        print("File preview content would be shown here")
        print("Metadata:")
        print("  Size: 1.2 MB")
        print("  Type: PDF")
        print("  Created: 2024-01-15")
        self._show_commands()

    def _on_navigation_error(self, event):
        """Handle navigation error event"""
        data = event.data
        title = data.get('title', 'Error')
        message = data.get('message', 'Unknown error')
        print(f"\n❌ {title}: {message}")
        self._show_commands()

    def _show_commands(self):
        """Show available commands"""
        print("\nAvailable commands:")

        if self.current_view == "library":
            print("  c1, c2, c3 - Navigate to collection 1, 2, or 3")
        elif self.current_view == "collection":
            print("  f1, f2, f3, f4 - Open file 1, 2, 3, or 4")
            print("  back - Navigate back to library")
        elif self.current_view == "preview":
            print("  back - Navigate back to collection")

        print("  state - Show navigation state")
        print("  breadcrumbs - Show breadcrumb trail")
        print("  history - Show navigation history")
        print("  help - Show this help")
        print("  quit - Exit")
        print()

    async def run(self):
        """Run the textual interface"""
        if not await self.initialize():
            return

        self.running = True
        print("\n🚀 Textual Fichero started!")
        print("Type 'help' for commands\n")

        # Start in library view
        self.navigation_controller.navigate_to_library()

        while self.running:
            try:
                command = input("fichero> ").strip().lower()
                await self._handle_command(command)
            except KeyboardInterrupt:
                print("\n👋 Goodbye!")
                break
            except Exception as e:
                print(f"❌ Error: {e}")

    async def _handle_command(self, command: str):
        """Handle user commands"""
        if command == "quit" or command == "exit":
            self.running = False
            print("👋 Goodbye!")

        elif command == "help":
            self._show_commands()

        elif command == "state":
            self._show_navigation_state()

        elif command == "breadcrumbs":
            self._show_breadcrumbs()

        elif command == "history":
            self._show_history()

        elif command == "back":
            success = self.navigation_controller.navigate_back()
            if not success:
                print("ℹ️ Already at root - cannot go back")

        elif command in ["c1", "c2", "c3"]:
            collection_map = {
                "c1": ("collection_1", "Sample Collection"),
                "c2": ("collection_2", "Demo Collection"),
                "c3": ("collection_3", "Test Collection")
            }
            collection_id, collection_name = collection_map[command]
            self.navigation_controller.navigate_to_collection(collection_id, collection_name)

        elif command in ["f1", "f2", "f3", "f4"]:
            file_map = {
                "f1": "/path/to/document1.pdf",
                "f2": "/path/to/document2.jpg",
                "f3": "/path/to/subfolder/",
                "f4": "/path/to/image3.png"
            }
            file_path = file_map[command]
            if file_path.endswith("/"):
                # It's a folder
                folder_name = file_path.rstrip("/").split("/")[-1]
                self.navigation_controller.navigate_to_folder(folder_name)
            else:
                # It's a file
                self.navigation_controller.navigate_to_preview(file_path)

        elif command == "":
            pass  # Empty command

        else:
            print(f"❓ Unknown command: {command}")
            print("Type 'help' for available commands")

    def _show_navigation_state(self):
        """Show current navigation state"""
        state = self.navigation_controller.get_current_state()
        print("\n🧭 Navigation State:")
        print(f"  Context: {state.context.value}")
        print(f"  Collection ID: {state.collection_id or 'None'}")
        print(f"  Collection Name: {state.collection_name or 'None'}")
        print(f"  Current Path: '{state.current_path}'")
        print(f"  File Path: {state.file_path or 'None'}")
        print(f"  Can go back: {self.navigation_controller.can_navigate_back()}")
        print(f"  Can go forward: {self.navigation_controller.can_navigate_forward()}")

    def _show_breadcrumbs(self):
        """Show breadcrumb trail"""
        breadcrumbs = self.navigation_controller.get_breadcrumbs()
        print("\n🍞 Breadcrumbs:")
        if not breadcrumbs:
            print("  (empty)")
        else:
            for i, crumb in enumerate(breadcrumbs):
                prefix = "  └─ " if i == len(breadcrumbs) - 1 else "  ├─ "
                print(f"{prefix}{crumb['name']} ({crumb['context']})")

    def _show_history(self):
        """Show navigation history"""
        history = self.navigation_controller.history
        print("\n📜 Navigation History:")
        print(f"  Current index: {history.current_index}")
        print(f"  History size: {len(history.history)}")
        for i, state in enumerate(history.history):
            marker = " -> " if i == history.current_index else "    "
            print(f"{marker}{i}: {state.context.value}")


async def main():
    """Main entry point for textual interface"""
    app = TextualFichero()
    await app.run()


if __name__ == "__main__":
    # Set up logging
    logging.basicConfig(level=logging.INFO)

    # Run the textual interface
    asyncio.run(main())