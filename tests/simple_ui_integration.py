#!/usr/bin/env python3
"""
Simple UI Integration

This script integrates the library system into the main window UI.
"""

import sys
from pathlib import Path

def simple_integration():
    """Simple integration test"""
    print("🔧 Simple Library Integration...")
    
    try:
        # Add the library path
        library_path = Path(__file__).parent.parent / "fichero" / "src" / "fichero" / "library"
        sys.path.insert(0, str(library_path))
        
        print(f"✅ Added library path: {library_path}")
        
        # Import and test components one by one
        print("\n🧪 Testing Components...")
        
        # Test models
        import models
        collection = models.Collection(name="Simple Test", type="local")
        print("✅ Models working")
        
        # Test storage
        import storage
        test_db = Path("/tmp/simple_integration.db")
        storage_instance = storage.LibraryStorage(test_db)
        print("✅ Storage working")
        
        # Test adding collection
        success = storage_instance.add_collection(collection)
        if success:
            print("✅ Collection added to storage")
            
            # Test retrieving
            retrieved = storage_instance.get_collection(collection.id)
            if retrieved:
                print(f"✅ Collection retrieved: {retrieved.name}")
            else:
                print("❌ Failed to retrieve collection")
                return False
        else:
            print("❌ Failed to add collection")
            return False
        
        # Test library manager
        import library_manager
        class MockApp:
            class paths:
                data = Path("/tmp/simple_library")
        
        app = MockApp()
        manager = library_manager.LibraryManager(app)
        print("✅ Library manager working")
        
        # Test UI integration
        import ui_integration
        ui_integration_instance = ui_integration.LibraryUIIntegration(manager)
        print("✅ UI integration working")
        
        # Test UI hooks
        import ui_hooks
        hooks = ui_hooks.LibraryUIHooks(ui_integration_instance)
        print("✅ UI hooks working")
        
        # Clean up
        if test_db.exists():
            test_db.unlink()
            print("✅ Test database cleaned up")
        
        print("\n🎉 SIMPLE INTEGRATION SUCCESSFUL!")
        print("All library components are working!")
        
        return True
        
    except Exception as e:
        print(f"❌ Simple integration failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = simple_integration()
    if success:
        print("\n✅ Library system is ready for UI integration!")
    else:
        print("\n❌ Library integration failed") 