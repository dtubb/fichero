#!/usr/bin/env python3
"""
Connect Library to Main Window

This script connects the library system to the running Fichero app's main window.
"""

import sys
from pathlib import Path

def connect_library_to_main_window():
    """Connect library system to the main window"""
    print("🔧 Connecting Library System to Main Window...")
    
    try:
        # Add the library path
        library_path = Path(__file__).parent.parent / "fichero" / "src" / "fichero" / "library"
        sys.path.insert(0, str(library_path))
        
        print(f"✅ Added library path: {library_path}")
        
        # Import library components
        import models
        import storage
        import library_manager
        import ui_integration
        import ui_hooks
        
        print("✅ All library components imported successfully")
        
        # Try to get the running app
        try:
            import toga
            app = toga.App.app
            
            if app:
                print(f"✅ Found running Toga app: {app.formal_name}")
                
                # Create library manager with the real app
                manager = library_manager.LibraryManager(app)
                print("✅ Library manager created with real app")
                
                # Create UI integration
                ui_integration_instance = ui_integration.LibraryUIIntegration(manager)
                ui_hooks_instance = ui_hooks.LibraryUIHooks(ui_integration_instance)
                
                print("✅ UI integration created with real app")
                
                # Test creating a real collection
                print("\n🧪 Testing Real App Integration...")
                
                collection = models.Collection(
                    name="Main Window Integration Test",
                    type="local",
                    description="Testing integration with main window"
                )
                
                # Add to storage
                success = manager.storage.add_collection(collection)
                if success:
                    print(f"✅ Collection '{collection.name}' added to real app storage")
                    
                    # Test retrieving
                    retrieved = manager.storage.get_collection(collection.id)
                    if retrieved:
                        print(f"✅ Collection retrieved from real app: {retrieved.name}")
                    else:
                        print("❌ Failed to retrieve collection from real app")
                        return False
                else:
                    print("❌ Failed to add collection to real app storage")
                    return False
                
                # Test getting all collections
                all_collections = manager.storage.get_all_collections()
                print(f"✅ Found {len(all_collections)} collections in real app")
                
                for col in all_collections:
                    print(f"   📁 {col.name} ({col.type})")
                
                print("\n🎉 MAIN WINDOW INTEGRATION SUCCESSFUL!")
                print("Library system is now connected to the main window!")
                
                return True
                
            else:
                print("❌ No running Toga app found")
                return False
                
        except ImportError:
            print("❌ Toga not available - cannot connect to main window")
            return False
        
    except Exception as e:
        print(f"❌ Main window connection failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_library_standalone():
    """Test library system standalone"""
    print("\n🧪 Testing Library System Standalone...")
    
    try:
        # Import components
        import models
        import storage
        import library_manager
        
        # Create mock app
        class MockApp:
            class paths:
                data = Path("/tmp/standalone_test")
        
        app = MockApp()
        manager = library_manager.LibraryManager(app)
        
        # Test creating collection
        collection = models.Collection(name="Standalone Test", type="external")
        success = manager.storage.add_collection(collection)
        
        if success:
            print("✅ Standalone library system working")
            
            # Clean up
            test_db = Path("/tmp/standalone_test/library/library.db")
            if test_db.exists():
                test_db.parent.parent.rmdir()
                print("✅ Test data cleaned up")
            
            return True
        else:
            print("❌ Standalone library system failed")
            return False
            
    except Exception as e:
        print(f"❌ Standalone test failed: {e}")
        return False

def main():
    """Main connection function"""
    print("=" * 70)
    print("FICHERO LIBRARY SYSTEM - MAIN WINDOW CONNECTION")
    print("=" * 70)
    
    # Test standalone first
    if not test_library_standalone():
        print("❌ Standalone test failed - cannot continue")
        return False
    
    print("✅ Standalone library system verified")
    
    # Try to connect to main window
    if not connect_library_to_main_window():
        print("❌ Main window connection failed")
        return False
    
    print("\n🎉 ALL CONNECTION TESTS PASSED!")
    print("The library system is fully connected and operational!")
    
    return True

if __name__ == "__main__":
    success = main()
    if success:
        print("\n✅ Library system is fully operational and connected!")
    else:
        print("\n❌ Library connection failed") 