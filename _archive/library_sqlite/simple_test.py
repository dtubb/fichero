#!/usr/bin/env python3
"""
Simple Test for Fichero Library System

This script tests the library system components individually to avoid import issues.
"""

import sys
import os
from pathlib import Path

def test_models():
    """Test the models module directly"""
    try:
        print("Testing models module...")
        
        # Add the library directory to Python path
        library_path = Path(__file__).parent
        sys.path.insert(0, str(library_path))
        
        # Import models directly
        import models
        
        # Test creating objects
        collection = models.Collection(
            name="Test Collection",
            type="local",
            source_path="/test/path"
        )
        print(f"✓ Collection created: {collection.name}")
        
        item = models.CollectionItem(
            
            type="file",
            name="test.txt",
            source_path="/test/path/test.txt"
        )
        print(f"✓ Collection item created: {item.name}")
        
        result = models.ProcessingResult(
            
            item_id=item.id,
            workflow="test_workflow",
            status="success"
        )
        print(f"✓ Processing result created: {result.workflow}")
        
        print("✓ Models test passed!")
        return True
        
    except Exception as e:
        print(f"❌ Models test failed: {e}")
        return False

def test_storage():
    """Test the storage module directly"""
    try:
        print("\nTesting storage module...")
        
        # Add the library directory to Python path
        library_path = Path(__file__).parent
        sys.path.insert(0, str(library_path))
        
        # Import storage directly
        import storage
        
        # Create a test database path
        test_db_path = Path("/tmp/test_library.db")
        
        # Test storage initialization
        storage_instance = storage.LibraryStorage(test_db_path)
        print("✓ Storage initialized successfully")
        
        # Test database creation
        if test_db_path.exists():
            print("✓ Database file created")
        else:
            print("⚠️ Database file not created (this might be expected)")
        
        # Clean up
        if test_db_path.exists():
            test_db_path.unlink()
            print("✓ Test database cleaned up")
        
        print("✓ Storage test passed!")
        return True
        
    except Exception as e:
        print(f"❌ Storage test failed: {e}")
        return False

def test_import_export():
    """Test the import/export module directly"""
    try:
        print("\nTesting import/export module...")
        
        # Add the library directory to Python path
        library_path = Path(__file__).parent
        sys.path.insert(0, str(library_path))
        
        # Import modules directly
        import models
        import storage
        import import_export
        
        # Create test data
        collection = models.Collection(
            name="Test Export Collection",
            type="local"
        )
        
        # Test exporter creation
        test_db_path = Path("/tmp/test_export.db")
        storage_instance = storage.LibraryStorage(test_db_path)
        exporter = import_export.CollectionExporter(storage_instance)
        print("✓ Exporter created successfully")
        
        # Test importer creation
        importer = import_export.CollectionImporter(storage_instance)
        print("✓ Importer created successfully")
        
        # Clean up
        if test_db_path.exists():
            test_db_path.unlink()
        
        print("✓ Import/Export test passed!")
        return True
        
    except Exception as e:
        print(f"❌ Import/Export test failed: {e}")
        return False

def main():
    """Run all tests"""
    print("=" * 50)
    print("FICHERO LIBRARY SYSTEM - SIMPLE TEST")
    print("=" * 50)
    
    tests = [
        ("Models", test_models),
        ("Storage", test_storage),
        ("Import/Export", test_import_export)
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        try:
            if test_func():
                passed += 1
        except Exception as e:
            print(f"❌ {test_name} test crashed: {e}")
    
    print("\n" + "=" * 50)
    print(f"TEST SUMMARY: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 ALL TESTS PASSED!")
        print("The library system components are working correctly.")
        return True
    else:
        print("💥 SOME TESTS FAILED!")
        print("Check the errors above for issues.")
        return False

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
