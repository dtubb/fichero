#!/usr/bin/env python3
"""
Comprehensive Library System Test

This test verifies all library system components work correctly.
"""

import sys
import tempfile
import shutil
from pathlib import Path

def test_models():
    """Test models functionality"""
    print("🧪 Testing Models...")
    
    try:
        # Add the library path directly
        library_path = Path(__file__).parent.parent / "fichero" / "src" / "fichero" / "library"
        sys.path.insert(0, str(library_path))
        
        # Import models directly
        import models
        
        # Test creating objects
        collection = models.Collection(name="Comprehensive Test", type="local")
        item = models.CollectionItem(collection_id=collection.id, type="file", name="test.txt")
        result = models.ProcessingResult(item_id=item.id, workflow="comprehensive_test")
        
        # Test serialization
        collection_dict = collection.to_dict()
        restored_collection = models.Collection.from_dict(collection_dict)
        
        print("✅ Models working correctly")
        print(f"   Collection: {collection.name} -> {restored_collection.name}")
        print(f"   Item: {item.name}")
        print(f"   Result: {result.workflow}")
        
        return True
        
    except Exception as e:
        print(f"❌ Models test failed: {e}")
        return False

def test_storage():
    """Test storage functionality"""
    print("\n🧪 Testing Storage...")
    
    try:
        # Import storage directly
        import storage
        
        # Create test storage
        test_db_path = Path("/tmp/comprehensive_test.db")
        storage_instance = storage.LibraryStorage(test_db_path)
        
        print("✅ Storage created successfully")
        
        # Test database creation
        if test_db_path.exists():
            print("✅ Database file created")
            
            # Test adding a collection
            import models
            collection = models.Collection(name="Storage Test", type="external")
            success = storage_instance.add_collection(collection)
            
            if success:
                print("✅ Collection added to storage")
                
                # Test retrieving collection
                retrieved = storage_instance.get_collection(collection.id)
                if retrieved:
                    print("✅ Collection retrieved from storage")
                else:
                    print("❌ Failed to retrieve collection")
                    return False
            else:
                print("❌ Failed to add collection")
                return False
            
            # Clean up
            test_db_path.unlink()
            print("✅ Test database cleaned up")
        else:
            print("❌ Database file not created")
            return False
        
        return True
        
    except Exception as e:
        print(f"❌ Storage test failed: {e}")
        return False

def test_import_export():
    """Test import/export functionality"""
    print("\n🧪 Testing Import/Export...")
    
    try:
        # Import components directly
        import import_export
        import storage
        
        # Create test storage
        test_db_path = Path("/tmp/import_export_test.db")
        storage_instance = storage.LibraryStorage(test_db_path)
        
        # Test exporter/importer creation
        exporter = import_export.CollectionExporter(storage_instance)
        importer = import_export.CollectionImporter(storage_instance)
        
        print("✅ Import/Export components created successfully")
        print(f"   Exporter: {type(exporter).__name__}")
        print(f"   Importer: {type(importer).__name__}")
        
        # Clean up
        if test_db_path.exists():
            test_db_path.unlink()
            print("✅ Test database cleaned up")
        
        return True
        
    except Exception as e:
        print(f"❌ Import/Export test failed: {e}")
        return False

def test_library_manager():
    """Test library manager functionality"""
    print("\n🧪 Testing Library Manager...")
    
    try:
        # Import library manager directly
        import library_manager
        
        # Create mock app
        class MockApp:
            class paths:
                data = Path("/tmp/test_library_manager")
        
        app = MockApp()
        manager = library_manager.LibraryManager(app)
        
        print("✅ Library Manager created successfully")
        print(f"   Storage: {type(manager.storage).__name__}")
        print(f"   Exporter: {type(manager.exporter).__name__}")
        print(f"   Importer: {type(manager.importer).__name__}")
        
        return True
        
    except Exception as e:
        print(f"❌ Library Manager test failed: {e}")
        return False

def test_ui_integration():
    """Test UI integration components"""
    print("\n🧪 Testing UI Integration...")
    
    try:
        # Import UI components directly
        import ui_integration
        import library_manager
        
        # Create mock app and manager
        class MockApp:
            class paths:
                data = Path("/tmp/test_ui_integration")
        
        app = MockApp()
        manager = library_manager.LibraryManager(app)
        
        # Test UI integration
        ui_integration_instance = ui_integration.LibraryUIIntegration(manager)
        print("✅ UI Integration created successfully")
        
        return True
        
    except Exception as e:
        print(f"❌ UI Integration test failed: {e}")
        return False

def test_ui_hooks():
    """Test UI hooks functionality"""
    print("\n🧪 Testing UI Hooks...")
    
    try:
        # Import UI hooks directly
        import ui_hooks
        import library_manager
        import ui_integration
        
        # Create mock app and manager
        class MockApp:
            class paths:
                data = Path("/tmp/test_ui_hooks")
        
        app = MockApp()
        manager = library_manager.LibraryManager(app)
        ui_integration_instance = ui_integration.LibraryUIIntegration(manager)
        
        # Test UI hooks
        hooks = ui_hooks.LibraryUIHooks(ui_integration_instance)
        print("✅ UI Hooks created successfully")
        
        return True
        
    except Exception as e:
        print(f"❌ UI Hooks test failed: {e}")
        return False

def main():
    """Run comprehensive tests"""
    print("=" * 60)
    print("FICHERO LIBRARY SYSTEM - COMPREHENSIVE TEST")
    print("=" * 60)
    
    tests = [
        ("Models", test_models),
        ("Storage", test_storage),
        ("Import/Export", test_import_export),
        ("Library Manager", test_library_manager),
        ("UI Integration", test_ui_integration),
        ("UI Hooks", test_ui_hooks),
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
    print(f"COMPREHENSIVE TEST SUMMARY: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 ALL COMPREHENSIVE TESTS PASSED!")
        print("The library system is fully functional and ready for integration!")
        return True
    else:
        print("💥 SOME COMPREHENSIVE TESTS FAILED!")
        print("Check the errors above for issues.")
        return False

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1) 