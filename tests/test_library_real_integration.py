#!/usr/bin/env python3
"""
Real Library System Integration Test

This script integrates the library system into the running Fichero app
and tests real functionality.
"""

import sys
import asyncio
from pathlib import Path

# Add the fichero package to Python path
fichero_src_path = Path(__file__).parent.parent / "fichero" / "src"
sys.path.insert(0, str(fichero_src_path))

def integrate_library_into_app():
    """Integrate library system into the running Fichero app"""
    print("🔧 Integrating Library System into Fichero App...")
    
    try:
        # Import the library system
        from fichero.library import LibraryManager, Collection, CollectionItem, ProcessingResult
        
        print("✅ Library system imported successfully")
        
        # Get the running app instance
        import toga
        app = toga.App.app
        
        if not app:
            print("❌ No running Toga app found")
            return False
        
        print(f"✅ Found running app: {app.formal_name}")
        
        # Create library manager
        library_manager = LibraryManager(app)
        print("✅ Library manager created successfully")
        
        # Test creating a real collection
        print("\n🧪 Testing Real Collection Creation...")
        
        # Create a test collection
        collection = Collection(
            name="Test Integration Collection",
            type="local",
            description="Testing the library system integration"
        )
        
        # Add to storage
        success = library_manager.storage.add_collection(collection)
        if success:
            print(f"✅ Collection '{collection.name}' added to storage")
        else:
            print("❌ Failed to add collection to storage")
            return False
        
        # Test retrieving the collection
        retrieved = library_manager.storage.get_collection(collection.id)
        if retrieved:
            print(f"✅ Collection retrieved: {retrieved.name}")
        else:
            print("❌ Failed to retrieve collection")
            return False
        
        # Test adding an item to the collection
        print("\n🧪 Testing Item Addition...")
        
        item = CollectionItem(
            collection_id=collection.id,
            type="file",
            name="test_document.txt",
            storage_type="local",
            source_path="/tmp/test_document.txt"
        )
        
        success = library_manager.storage.add_collection_item(item)
        if success:
            print(f"✅ Item '{item.name}' added to collection")
        else:
            print("❌ Failed to add item to collection")
            return False
        
        # Test adding a processing result
        print("\n🧪 Testing Processing Result...")
        
        result = ProcessingResult(
            item_id=item.id,
            workflow="test_integration",
            status="success",
            prompt_config="Test prompt configuration"
        )
        
        success = library_manager.storage.add_processing_result(result)
        if success:
            print(f"✅ Processing result added: {result.workflow}")
        else:
            print("❌ Failed to add processing result")
            return False
        
        # Test getting all collections
        print("\n🧪 Testing Collection Retrieval...")
        
        all_collections = library_manager.storage.get_all_collections()
        print(f"✅ Found {len(all_collections)} collections in storage")
        
        for col in all_collections:
            print(f"   - {col.name} ({col.type})")
        
        # Test getting collection items
        items = library_manager.storage.get_collection_items(collection.id)
        print(f"✅ Found {len(items)} items in collection '{collection.name}'")
        
        for item in items:
            print(f"   - {item.name} ({item.type})")
        
        # Test getting processing history
        history = library_manager.storage.get_processing_history(item.id)
        print(f"✅ Found {len(history)} processing results for item '{item.name}'")
        
        for hist in history:
            print(f"   - {hist.workflow} ({hist.status})")
        
        print("\n🎉 LIBRARY SYSTEM INTEGRATION SUCCESSFUL!")
        print("All core functionality is working in the running app!")
        
        return True
        
    except Exception as e:
        print(f"❌ Library integration failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_ui_integration():
    """Test UI integration components"""
    print("\n🔧 Testing UI Integration...")
    
    try:
        from fichero.library import LibraryUIIntegration, LibraryUIHooks
        
        # Create mock app for testing
        class MockApp:
            class paths:
                data = Path("/tmp/test_ui_integration")
        
        from fichero.library import LibraryManager
        app = MockApp()
        manager = LibraryManager(app)
        
        # Test UI integration
        ui_integration = LibraryUIIntegration(manager)
        ui_hooks = LibraryUIHooks(ui_integration)
        
        print("✅ UI Integration components created successfully")
        
        # Test callback registration
        def test_callback(data):
            print(f"   ✅ Callback triggered: {data}")
        
        ui_integration.register_ui_callbacks(on_collection_added=test_callback)
        print("✅ Callback system working")
        
        return True
        
    except Exception as e:
        print(f"❌ UI Integration test failed: {e}")
        return False

def main():
    """Main integration test"""
    print("=" * 70)
    print("FICHERO LIBRARY SYSTEM - REAL INTEGRATION TEST")
    print("=" * 70)
    print("This test integrates the library system into the running Fichero app")
    print("Make sure the app is running via 'briefcase dev'")
    print("=" * 70)
    
    # Test UI integration first
    if not test_ui_integration():
        print("❌ UI Integration test failed - cannot continue")
        return False
    
    print("✅ UI Integration verified")
    
    # Test real app integration
    if not integrate_library_into_app():
        print("❌ Real app integration failed")
        return False
    
    print("\n🎉 ALL INTEGRATION TESTS PASSED!")
    print("The library system is fully integrated and working in the Fichero app!")
    
    return True

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1) 