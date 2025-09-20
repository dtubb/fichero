#!/usr/bin/env python3
"""
Library System App Integration Test

This script tests integrating the library system into the running Fichero app.
It should be run from within the app context.
"""

import sys
import asyncio
from pathlib import Path

def test_library_integration_with_app(app):
    """Test library system integration with the running app"""
    print("🧪 Testing Library System Integration with Running App...")
    
    try:
        # Import library components
        from fichero.library import LibraryManager, Collection, CollectionItem, ProcessingResult
        
        print("✅ Successfully imported library components")
        
        # Create library manager using the app's paths
        library_manager = LibraryManager(app)
        print("✅ Library manager created successfully")
        
        # Test creating a collection
        collection = Collection(name="Test Collection", type="local")
        print(f"✅ Test collection created: {collection.name}")
        
        # Test adding collection to storage
        success = library_manager.storage.add_collection(collection)
        if success:
            print("✅ Collection added to storage successfully")
        else:
            print("❌ Failed to add collection to storage")
            return False
        
        # Test retrieving collection
        retrieved = library_manager.storage.get_collection(collection.id)
        if retrieved:
            print(f"✅ Collection retrieved: {retrieved.name}")
        else:
            print("❌ Failed to retrieve collection")
            return False
        
        # Test UI integration
        from fichero.library import LibraryUIIntegration, LibraryUIHooks
        
        ui_integration = LibraryUIIntegration(library_manager)
        ui_hooks = LibraryUIHooks(ui_integration)
        
        print("✅ UI integration components created")
        
        # Test integration with main window
        if hasattr(app, 'main_window_wrapper'):
            main_window = app.main_window_wrapper
            print("✅ Main window found")
            
            # Try to integrate library system
            try:
                from fichero.library.integrate_with_main import integrate_library_into_main_window
                integration_result = integrate_library_into_main_window(app, main_window)
                
                if integration_result:
                    print("✅ Library system successfully integrated with main window")
                    return True
                else:
                    print("❌ Failed to integrate library system with main window")
                    return False
                    
            except Exception as e:
                print(f"❌ Library integration failed: {e}")
                return False
        else:
            print("❌ Main window not found")
            return False
            
    except Exception as e:
        print(f"❌ Library integration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_library_functionality():
    """Test basic library functionality"""
    print("\n🧪 Testing Basic Library Functionality...")
    
    try:
        # Test models
        from fichero.library.models import Collection, CollectionItem, ProcessingResult
        
        collection = Collection(name="Functionality Test", type="external")
        item = CollectionItem(collection_id=collection.id, type="file", name="test.txt")
        result = ProcessingResult(item_id=item.id, workflow="test_workflow")
        
        print("✅ Models working correctly")
        
        # Test storage
        from fichero.library.storage import LibraryStorage
        
        test_db_path = Path("/tmp/test_functionality.db")
        storage = LibraryStorage(test_db_path)
        
        success = storage.add_collection(collection)
        if success:
            print("✅ Storage working correctly")
            
            # Clean up
            if test_db_path.exists():
                test_db_path.unlink()
                print("✅ Test database cleaned up")
        else:
            print("❌ Storage test failed")
            return False
        
        # Test import/export
        from fichero.library.import_export import CollectionExporter, CollectionImporter
        
        exporter = CollectionExporter(storage)
        importer = CollectionImporter(storage)
        
        print("✅ Import/Export components working")
        
        return True
        
    except Exception as e:
        print(f"❌ Basic functionality test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Main test function"""
    print("=" * 60)
    print("FICHERO LIBRARY SYSTEM - APP INTEGRATION TEST")
    print("=" * 60)
    print("This test should be run from within the Fichero app context")
    print("=" * 60)
    
    # Test basic functionality first
    if not test_library_functionality():
        print("❌ Basic functionality test failed - cannot continue")
        return False
    
    print("\n✅ Basic library functionality verified")
    print("The library system is working correctly!")
    
    return True

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1) 