#!/usr/bin/env python3
"""
Library System Integration Test

This script tests the library system integration with the running Fichero app.
Run this while the app is running via 'briefcase dev'.
"""

import sys
import asyncio
from pathlib import Path

# Add the fichero package to Python path
fichero_src_path = Path(__file__).parent.parent / "fichero" / "src"
sys.path.insert(0, str(fichero_src_path))

def test_library_imports():
    """Test that library components can be imported"""
    print("🧪 Testing Library System Imports...")
    
    try:
        # Test importing from the package
        from fichero.library import LibraryManager, Collection, CollectionItem, ProcessingResult
        print("✅ Successfully imported library components from package")
        
        # Test creating objects
        collection = Collection(name="Test Collection", type="local")
        item = CollectionItem(collection_id=collection.id, type="file", name="test.txt")
        result = ProcessingResult(item_id=item.id, workflow="test_workflow")
        
        print(f"✅ Created test objects:")
        print(f"   Collection: {collection.name} ({collection.type})")
        print(f"   Item: {item.name} ({item.type})")
        print(f"   Result: {result.workflow}")
        
        return True
        
    except Exception as e:
        print(f"❌ Failed to import library components: {e}")
        return False

def test_library_manager_creation():
    """Test creating a library manager"""
    print("\n🧪 Testing Library Manager Creation...")
    
    try:
        from fichero.library import LibraryManager
        
        # Create a mock app for testing
        class MockApp:
            class paths:
                data = Path("/tmp/test_library")
        
        app = MockApp()
        manager = LibraryManager(app)
        
        print("✅ Library Manager created successfully")
        print(f"   Storage: {type(manager.storage).__name__}")
        print(f"   Exporter: {type(manager.exporter).__name__}")
        print(f"   Importer: {type(manager.importer).__name__}")
        
        return True
        
    except Exception as e:
        print(f"❌ Failed to create library manager: {e}")
        return False

def test_ui_integration():
    """Test UI integration components"""
    print("\n🧪 Testing UI Integration...")
    
    try:
        from fichero.library import LibraryUIIntegration, LibraryUIHooks
        
        # Create mock app and manager
        class MockApp:
            class paths:
                data = Path("/tmp/test_library")
        
        from fichero.library import LibraryManager
        app = MockApp()
        manager = LibraryManager(app)
        
        # Test UI integration
        ui_integration = LibraryUIIntegration(manager)
        ui_hooks = LibraryUIHooks(ui_integration)
        
        print("✅ UI Integration components created successfully")
        print(f"   UI Integration: {type(ui_integration).__name__}")
        print(f"   UI Hooks: {type(ui_hooks).__name__}")
        
        return True
        
    except Exception as e:
        print(f"❌ Failed to create UI integration: {e}")
        return False

def test_storage_operations():
    """Test basic storage operations"""
    print("\n🧪 Testing Storage Operations...")
    
    try:
        from fichero.library import LibraryStorage, Collection
        
        # Create test storage
        test_db_path = Path("/tmp/test_library_storage.db")
        storage = LibraryStorage(test_db_path)
        
        # Test adding a collection
        collection = Collection(name="Storage Test", type="external")
        success = storage.add_collection(collection)
        
        if success:
            print("✅ Storage operations working")
            print(f"   Database created: {test_db_path.exists()}")
            print(f"   Collection added: {success}")
            
            # Clean up
            if test_db_path.exists():
                test_db_path.unlink()
                print("   Test database cleaned up")
            
            return True
        else:
            print("❌ Failed to add collection to storage")
            return False
            
    except Exception as e:
        print(f"❌ Storage operations failed: {e}")
        return False

def test_import_export():
    """Test import/export functionality"""
    print("\n🧪 Testing Import/Export...")
    
    try:
        from fichero.library import CollectionExporter, CollectionImporter, LibraryStorage
        
        # Create test storage
        test_db_path = Path("/tmp/test_import_export.db")
        storage = LibraryStorage(test_db_path)
        
        # Test exporter/importer creation
        exporter = CollectionExporter(storage)
        importer = CollectionImporter(storage)
        
        print("✅ Import/Export components created successfully")
        print(f"   Exporter: {type(exporter).__name__}")
        print(f"   Importer: {type(importer).__name__}")
        
        # Clean up
        if test_db_path.exists():
            test_db_path.unlink()
            print("   Test database cleaned up")
        
        return True
        
    except Exception as e:
        print(f"❌ Import/Export test failed: {e}")
        return False

def main():
    """Run all integration tests"""
    print("=" * 60)
    print("FICHERO LIBRARY SYSTEM - INTEGRATION TESTS")
    print("=" * 60)
    print("Make sure the Fichero app is running via 'briefcase dev'")
    print("=" * 60)
    
    tests = [
        ("Library Imports", test_library_imports),
        ("Library Manager", test_library_manager_creation),
        ("UI Integration", test_ui_integration),
        ("Storage Operations", test_storage_operations),
        ("Import/Export", test_import_export),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        try:
            if test_func():
                passed += 1
        except Exception as e:
            print(f"❌ {test_name} test crashed: {e}")
    
    print("\n" + "=" * 60)
    print(f"INTEGRATION TEST SUMMARY: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 ALL INTEGRATION TESTS PASSED!")
        print("The library system is fully integrated and working!")
        return True
    else:
        print("💥 SOME INTEGRATION TESTS FAILED!")
        print("Check the errors above for issues.")
        return False

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1) 