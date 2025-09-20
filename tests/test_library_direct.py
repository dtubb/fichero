#!/usr/bin/env python3
"""
Direct Library System Tests

Tests that import library components directly without going through the main package.
"""

import unittest
import tempfile
import shutil
from pathlib import Path
import sys
import os

# Add the library directory directly to Python path
library_path = Path(__file__).parent.parent / "fichero" / "src" / "fichero" / "library"
sys.path.insert(0, str(library_path))

class TestLibraryDirect(unittest.TestCase):
    """Test library components with direct imports"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.test_dir = Path(tempfile.mkdtemp())
    
    def tearDown(self):
        """Clean up test fixtures"""
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)
    
    def test_models_direct_import(self):
        """Test importing models directly"""
        try:
            import models
            print("✓ Models imported directly")
            
            # Test creating objects
            collection = models.Collection(name="Test", type="local")
            item = models.CollectionItem(collection_id=collection.id, type="file", name="test.txt")
            result = models.ProcessingResult(item_id=item.id, workflow="test")
            
            self.assertEqual(collection.name, "Test")
            self.assertEqual(item.name, "test.txt")
            self.assertEqual(result.workflow, "test")
            
            print("✓ Models work correctly")
            
        except Exception as e:
            self.fail(f"Failed to import models directly: {e}")
    
    def test_storage_direct_import(self):
        """Test importing storage directly"""
        try:
            import storage
            print("✓ Storage imported directly")
            
            # Test creating storage instance
            db_path = self.test_dir / "test.db"
            storage_instance = storage.LibraryStorage(db_path)
            
            self.assertIsNotNone(storage_instance)
            self.assertTrue(db_path.exists())
            
            print("✓ Storage works correctly")
            
        except Exception as e:
            self.fail(f"Failed to import storage directly: {e}")
    
    def test_import_export_direct_import(self):
        """Test importing import/export directly"""
        try:
            import import_export
            print("✓ Import/Export imported directly")
            
            # Test creating instances
            import storage
            db_path = self.test_dir / "test_export.db"
            storage_instance = storage.LibraryStorage(db_path)
            
            exporter = import_export.CollectionExporter(storage_instance)
            importer = import_export.CollectionImporter(storage_instance)
            
            self.assertIsNotNone(exporter)
            self.assertIsNotNone(importer)
            
            print("✓ Import/Export works correctly")
            
        except Exception as e:
            self.fail(f"Failed to import import/export directly: {e}")
    
    def test_library_manager_direct_import(self):
        """Test importing library manager directly"""
        try:
            import library_manager
            print("✓ Library Manager imported directly")
            
            # Test creating mock app and manager
            class MockApp:
                class paths:
                    data = self.test_dir
            
            app = MockApp()
            manager = library_manager.LibraryManager(app)
            
            self.assertIsNotNone(manager)
            self.assertIsNotNone(manager.storage)
            
            print("✓ Library Manager works correctly")
            
        except Exception as e:
            self.fail(f"Failed to import library manager directly: {e}")
    
    def test_ui_integration_direct_import(self):
        """Test importing UI integration directly"""
        try:
            import ui_integration
            print("✓ UI Integration imported directly")
            
            # Test creating instance
            import library_manager
            
            class MockApp:
                class paths:
                    data = self.test_dir
            
            app = MockApp()
            manager = library_manager.LibraryManager(app)
            ui_integration_instance = ui_integration.LibraryUIIntegration(manager)
            
            self.assertIsNotNone(ui_integration_instance)
            self.assertEqual(ui_integration_instance.library_manager, manager)
            
            print("✓ UI Integration works correctly")
            
        except Exception as e:
            self.fail(f"Failed to import UI integration directly: {e}")


def run_direct_tests():
    """Run direct library tests"""
    print("=" * 50)
    print("FICHERO LIBRARY SYSTEM - DIRECT TESTS")
    print("=" * 50)
    
    # Create test suite
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestLibraryDirect)
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_direct_tests()
    
    print("\n" + "=" * 50)
    if success:
        print("🎉 ALL DIRECT TESTS PASSED!")
        print("The library system components work with direct imports.")
    else:
        print("💥 SOME DIRECT TESTS FAILED!")
        print("Check the test output above for issues.")
    print("=" * 50)
    
    exit(0 if success else 1) 