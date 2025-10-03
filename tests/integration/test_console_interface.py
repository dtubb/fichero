"""
Integration tests for console interface

Tests the console interface functionality without GUI.
"""

import unittest
import tempfile
import os
from pathlib import Path

from fichero.interfaces.console_interface import ConsoleLibraryInterface


class TestConsoleInterface(unittest.TestCase):
    """Test console interface functionality"""

    def setUp(self):
        """Set up test environment"""
        # Create temporary database
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.temp_db.close()
        self.db_path = self.temp_db.name

        # Create console interface
        self.interface = ConsoleLibraryInterface(self.db_path)

    def tearDown(self):
        """Clean up test environment"""
        self.interface.cleanup()
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    def test_basic_navigation_commands(self):
        """Test basic navigation commands"""
        # Test library navigation
        result = self.interface.execute_command("nav library")
        self.assertTrue(result)

        # Test status command
        result = self.interface.execute_command("nav status")
        self.assertTrue(result)

        # Test breadcrumbs
        result = self.interface.execute_command("nav breadcrumbs")
        self.assertTrue(result)

    def test_library_commands(self):
        """Test library management commands"""
        # Test list collections (should be empty initially)
        result = self.interface.execute_command("library list")
        self.assertTrue(result)

        # Test add collection with unique name
        import uuid
        unique_name = f"TestCollection_{uuid.uuid4().hex[:8]}"
        result = self.interface.execute_command(f"library add {unique_name} local")
        self.assertTrue(result)

        # Test list collections again (should have one now)
        result = self.interface.execute_command("library list")
        self.assertTrue(result)

        # Get collections to verify
        collections = self.interface.library_viewmodel.get_collections()
        self.assertTrue(len(collections) > 0)

        # Test collection info
        if collections:
            collection_id = collections[0].get('id')
            result = self.interface.execute_command(f"library info {collection_id}")
            self.assertTrue(result)

    def test_collection_commands(self):
        """Test collection-specific commands"""
        # Add a collection first
        self.interface.execute_command("library add TestCollection local")

        # Navigate to collection
        collections = self.interface.library_viewmodel.get_collections()
        if collections:
            collection_id = collections[0].get('id')
            result = self.interface.execute_command(f"nav collection {collection_id}")
            self.assertTrue(result)

            # Test collection commands
            result = self.interface.execute_command("collection list")
            self.assertTrue(result)

            result = self.interface.execute_command("collection info")
            self.assertTrue(result)

            result = self.interface.execute_command("collection refresh")
            self.assertTrue(result)

    def test_status_command(self):
        """Test status command"""
        result = self.interface.execute_command("status")
        self.assertTrue(result)

    def test_help_command(self):
        """Test help command"""
        result = self.interface.execute_command("help")
        self.assertTrue(result)

    def test_test_commands(self):
        """Test the test command functionality"""
        result = self.interface.execute_command("test navigation")
        self.assertTrue(result)

        result = self.interface.execute_command("test library")
        self.assertTrue(result)

        result = self.interface.execute_command("test all")
        self.assertTrue(result)

    def test_invalid_commands(self):
        """Test handling of invalid commands"""
        result = self.interface.execute_command("invalid_command")
        self.assertFalse(result)

        result = self.interface.execute_command("nav invalid_nav_command")
        self.assertFalse(result)

        result = self.interface.execute_command("library invalid_library_command")
        self.assertFalse(result)

    def test_batch_command_execution(self):
        """Test executing multiple commands in batch"""
        commands = [
            "library add Collection1 local",
            "library add Collection2 local",
            "library list",
            "nav library",
            "status"
        ]

        results = self.interface.run_commands(commands)
        self.assertEqual(len(results), len(commands))

        # All commands should succeed
        for result in results:
            self.assertTrue(result)

    def test_navigation_workflow(self):
        """Test a complete navigation workflow"""
        # Add collection
        result = self.interface.execute_command("library add TestWorkflow local")
        self.assertTrue(result)

        # Navigate to collection
        collections = self.interface.library_viewmodel.get_collections()
        self.assertTrue(len(collections) > 0)

        collection_id = collections[0].get('id')
        result = self.interface.execute_command(f"nav collection {collection_id}")
        self.assertTrue(result)

        # Check we're in collection context
        nav_state = self.interface.navigation_controller.get_current_state()
        self.assertEqual(nav_state.context.value, "collection")
        self.assertEqual(nav_state.collection_id, collection_id)

        # Navigate back to library
        result = self.interface.execute_command("nav back")
        self.assertTrue(result)

        # Check we're back in library context
        nav_state = self.interface.navigation_controller.get_current_state()
        self.assertEqual(nav_state.context.value, "library")

    def test_error_scenarios(self):
        """Test error handling scenarios"""
        # Try to navigate to non-existent collection
        result = self.interface.execute_command("nav collection nonexistent")
        self.assertFalse(result)

        # Try to navigate to path without being in collection
        result = self.interface.execute_command("nav path some/path")
        self.assertFalse(result)

        # Try to get info for non-existent collection
        result = self.interface.execute_command("library info nonexistent")
        self.assertFalse(result)

    def test_context_manager(self):
        """Test using console interface as context manager"""
        db_path = tempfile.NamedTemporaryFile(delete=False, suffix='.db').name

        with ConsoleLibraryInterface(db_path) as interface:
            result = interface.execute_command("library list")
            self.assertTrue(result)

        # File should be cleaned up
        self.assertFalse(os.path.exists(db_path))


if __name__ == '__main__':
    unittest.main()