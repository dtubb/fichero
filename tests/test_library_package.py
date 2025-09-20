#!/usr/bin/env python3
"""
Package Library System Tests

Tests that properly set up the Python path to test the library system as a package.
"""

import unittest
import tempfile
import shutil
from pathlib import Path
import sys
import os

# Add the fichero package to Python path
fichero_src_path = Path(__file__).parent.parent / "fichero" / "src"
sys.path.insert(0, str(fichero_src_path))

class TestLibraryPackage(unittest.TestCase):
    """Test library components as a proper package"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.test_dir = Path(tempfile.mkdtemp())
    
    def tearDown(self):
        """Clean up test fixtures"""
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)
    
    def test_models_package_import(self):
        """Test importing models from the package"""
        try:
            from fichero.library.models import Collection, CollectionItem, ProcessingResult
            print("✓ Models imported from package")
            
            # Test creating objects
            collection = Collection(name="Test", type="local")
            item = CollectionItem(collection_id=collection.id, type="file", name="test.txt")
            result = ProcessingResult(item_id=item.id, workflow="test")
            
            self.assertEqual(collection.name, "Test")
            self.assertEqual(item.name, "test.txt")
            self.assertEqual(result.workflow, "test")
            
            print("✓ Models work correctly")
            
        except Exception as e:
            self.fail(f"Failed to import models from package: {e}")
    
    def test_storage_package_import(self):
        """Test importing storage from the package"""
        try:
            from fichero.library.storage import LibraryStorage
            print("✓ Storage imported from package")
            
            # Test creating storage instance
            db_path = self.test_dir / "test.db"
            storage = LibraryStorage(db_path)
            
            self.assertIsNotNone(storage)
            self.assertTrue(db_path.exists())
            
            print("✓ Storage works correctly")
            
        except Exception as e:
            self.fail(f"Failed to import storage from package: {e}")
    
    def test_import_export_package_import(self):
        """Test importing import/export from the package"""
        try:
            from fichero.library.import_export import CollectionExporter, CollectionImporter
            print("✓ Import/Export imported from package")
            
            # Test creating instances
            from fichero.library.storage import LibraryStorage
            db_path = self.test_dir / "test_export.db"
            storage = LibraryStorage(db_path)
            
            exporter = CollectionExporter(storage)
            importer = CollectionImporter(storage)
            
            self.assertIsNotNone(exporter)
            self.assertIsNotNone(importer)
            
            print("✓ Import/Export works correctly")
            
        except Exception as e:
            self.fail(f"Failed to import import/export from package: {e}")
    
    def test_library_manager_package_import(self):
        """Test importing library manager from the package"""
        try:
            from fichero.library.library_manager import LibraryManager
            print("✓ Library Manager imported from package")
            
            # Test creating mock app and manager
            class MockApp:
                class paths:
                    data = self.test_dir
            
            app = MockApp()
            manager = LibraryManager(app)
            
            self.assertIsNotNone(manager)
            self.assertIsNotNone(manager.storage)
            
            print("✓ Library Manager works correctly")
            
        except Exception as e:
            self.fail(f"Failed to import library manager from package: {e}")
    
    def test_ui_integration_package_import(self):
        """Test importing UI integration from the package"""
        try:
            from fichero.library.ui_integration import LibraryUIIntegration
            print("✓ UI Integration imported from package")
            
            # Test creating instance
            from fichero.library.library_manager import LibraryManager
            
            class MockApp:
                class paths:
                    data = self.test_dir
            
            app = MockApp()
            manager = LibraryManager(app)
            ui_integration = LibraryUIIntegration(manager)
            
            self.assertIsNotNone(ui_integration)
            self.assertEqual(ui_integration.library_manager, manager)
            
            print("✓ UI Integration works correctly")
            
        except Exception as e:
            self.fail(f"Failed to import UI integration from package: {e}")
    
    def test_package_init(self):
        """Test that the package __init__.py works correctly"""
        try:
            from fichero.library import LibraryManager, Collection, CollectionItem, ProcessingResult
            print("✓ Package __init__.py imports work")
            
            # Test that we can create objects from the package imports
            collection = Collection(name="Package Test", type="external")
            self.assertEqual(collection.name, "Package Test")
            
            print("✓ Package initialization works correctly")
            
        except Exception as e:
            self.fail(f"Failed to import from package __init__.py: {e}")


def run_package_tests():
    """Run package library tests"""
    print("=" * 50)
    print("FICHERO LIBRARY SYSTEM - PACKAGE TESTS")
    print("=" * 50)
    
    # Create test suite
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestLibraryPackage)
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_package_tests()
    
    print("\n" + "=" * 50)
    if success:
        print("🎉 ALL PACKAGE TESTS PASSED!")
        print("The library system works correctly as a package.")
    else:
        print("💥 SOME PACKAGE TESTS FAILED!")
        print("Check the test output above for issues.")
    print("=" * 50)
    
    exit(0 if success else 1) 