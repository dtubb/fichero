#!/usr/bin/env python3
"""
Core Library System Tests

Simple tests to verify the basic library system components work.
"""

import unittest
import tempfile
import shutil
from pathlib import Path
import sys
import os

# Add the src directory to Python path
src_path = Path(__file__).parent.parent / "fichero" / "src"
sys.path.insert(0, str(src_path))

class TestLibraryCore(unittest.TestCase):
    """Test core library functionality"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.test_dir = Path(tempfile.mkdtemp())
    
    def tearDown(self):
        """Clean up test fixtures"""
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)
    
    def test_models_import(self):
        """Test that models can be imported"""
        try:
            from fichero.library.models import Collection, CollectionItem, ProcessingResult
            print("✓ Models imported successfully")
            
            # Test creating objects
            collection = Collection(name="Test", type="local")
            item = CollectionItem(collection_id=collection.id, type="file", name="test.txt")
            result = ProcessingResult(item_id=item.id, workflow="test")
            
            self.assertEqual(collection.name, "Test")
            self.assertEqual(item.name, "test.txt")
            self.assertEqual(result.workflow, "test")
            
            print("✓ Models work correctly")
            
        except Exception as e:
            self.fail(f"Failed to import models: {e}")
    
    def test_storage_import(self):
        """Test that storage can be imported"""
        try:
            from fichero.library.storage import LibraryStorage
            print("✓ Storage imported successfully")
            
            # Test creating storage instance
            db_path = self.test_dir / "test.db"
            storage = LibraryStorage(db_path)
            
            self.assertIsNotNone(storage)
            self.assertTrue(db_path.exists())
            
            print("✓ Storage works correctly")
            
        except Exception as e:
            self.fail(f"Failed to import storage: {e}")
    
    def test_import_export_import(self):
        """Test that import/export can be imported"""
        try:
            from fichero.library.import_export import CollectionExporter, CollectionImporter
            print("✓ Import/Export imported successfully")
            
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
            self.fail(f"Failed to import import/export: {e}")
    
    def test_library_manager_import(self):
        """Test that library manager can be imported"""
        try:
            from fichero.library.library_manager import LibraryManager
            print("✓ Library Manager imported successfully")
            
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
            self.fail(f"Failed to import library manager: {e}")
    
    def test_ui_integration_import(self):
        """Test that UI integration can be imported"""
        try:
            from fichero.library.ui_integration import LibraryUIIntegration
            print("✓ UI Integration imported successfully")
            
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
            self.fail(f"Failed to import UI integration: {e}")


def run_core_tests():
    """Run core library tests"""
    print("=" * 50)
    print("FICHERO LIBRARY SYSTEM - CORE TESTS")
    print("=" * 50)
    
    # Create test suite
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestLibraryCore)
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_core_tests()
    
    print("\n" + "=" * 50)
    if success:
        print("🎉 ALL CORE TESTS PASSED!")
        print("The library system core components are working.")
    else:
        print("💥 SOME CORE TESTS FAILED!")
        print("Check the test output above for issues.")
    print("=" * 50)
    
    exit(0 if success else 1) 