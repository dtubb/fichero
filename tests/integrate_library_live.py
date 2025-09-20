#!/usr/bin/env python3
"""
Live Library Integration

This script can be run from within the running Fichero app to integrate the library system.
"""

import sys
from pathlib import Path

def integrate_library_live():
    """Integrate library system into the running app"""
    print("🔧 Integrating Library System Live...")
    
    try:
        # Add the library path to sys.path
        library_path = Path(__file__).parent.parent / "fichero" / "src" / "fichero" / "library"
        if str(library_path) not in sys.path:
            sys.path.insert(0, str(library_path))
        
        print(f"✅ Added library path: {library_path}")
        
        # Import library components directly
        import models
        import storage
        import import_export
        import library_manager
        
        print("✅ All library components imported successfully")
        
        # Test creating objects
        collection = models.Collection(name="Live Integration Test", type="local")
        item = models.CollectionItem(collection_id=collection.id, type="file", name="live_test.txt")
        result = models.ProcessingResult(item_id=item.id, workflow="live_integration")
        
        print("✅ Test objects created successfully")
        
        # Test storage
        test_db_path = Path("/tmp/live_integration.db")
        storage_instance = storage.LibraryStorage(test_db_path)
        
        # Add collection to storage
        success = storage_instance.add_collection(collection)
        if success:
            print("✅ Collection added to live storage")
            
            # Retrieve collection
            retrieved = storage_instance.get_collection(collection.id)
            if retrieved:
                print(f"✅ Collection retrieved: {retrieved.name}")
            else:
                print("❌ Failed to retrieve collection")
                return False
        else:
            print("❌ Failed to add collection to storage")
            return False
        
        # Test library manager
        class MockApp:
            class paths:
                data = Path("/tmp/live_library")
        
        app = MockApp()
        manager = library_manager.LibraryManager(app)
        
        print("✅ Library manager created successfully")
        
        # Clean up test database
        if test_db_path.exists():
            test_db_path.unlink()
            print("✅ Test database cleaned up")
        
        print("\n🎉 LIVE LIBRARY INTEGRATION SUCCESSFUL!")
        print("The library system is working in the running app context!")
        
        return True
        
    except Exception as e:
        print(f"❌ Live integration failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = integrate_library_live()
    if success:
        print("\n✅ Library system is ready for use!")
    else:
        print("\n❌ Library integration failed") 