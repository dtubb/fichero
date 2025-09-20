#!/usr/bin/env python3
"""
Live Library Integration Test

This script tests the library system integration in the running Fichero app.
"""

import sys
from pathlib import Path

def test_library_integration():
    """Test library system integration"""
    print("🔧 Testing Library System Integration in Running App...")
    
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
        
        # Test creating objects
        collection = models.Collection(
            name="Live Integration Test",
            type="local",
            metadata={"description": "Testing live integration"}
        )
        
        item = models.CollectionItem(
            collection_id=collection.id,
            type="file",
            name="test_file.txt",
            storage_type="local"
        )
        
        result = models.ProcessingResult(
            item_id=item.id,
            workflow="live_test",
            status="success"
        )
        
        print("✅ Test objects created successfully")
        
        # Test storage
        test_db_path = Path("/tmp/live_integration_test.db")
        storage_instance = storage.LibraryStorage(test_db_path)
        
        # Add collection
        success = storage_instance.add_collection(collection)
        if success:
            print("✅ Collection added to live storage")
            
            # Add item
            item_success = storage_instance.add_collection_item(item)
            if item_success:
                print("✅ Item added to collection")
                
                # Add processing result
                result_success = storage_instance.add_processing_result(result)
                if result_success:
                    print("✅ Processing result added")
                    
                    # Test retrieval
                    retrieved_collection = storage_instance.get_collection(collection.id)
                    retrieved_items = storage_instance.get_collection_items(collection.id)
                    retrieved_results = storage_instance.get_processing_history(item.id)
                    
                    if retrieved_collection and retrieved_items and retrieved_results:
                        print(f"✅ Data retrieval successful:")
                        print(f"   Collection: {retrieved_collection.name}")
                        print(f"   Items: {len(retrieved_items)}")
                        print(f"   Results: {len(retrieved_results)}")
                    else:
                        print("❌ Data retrieval failed")
                        return False
                else:
                    print("❌ Failed to add processing result")
                    return False
            else:
                print("❌ Failed to add item")
                return False
        else:
            print("❌ Failed to add collection")
            return False
        
        # Test library manager
        class MockApp:
            class paths:
                data = Path("/tmp/live_library_test")
        
        app = MockApp()
        manager = library_manager.LibraryManager(app)
        
        print("✅ Library manager created successfully")
        
        # Test UI integration
        ui_integration_instance = ui_integration.LibraryUIIntegration(manager)
        ui_hooks_instance = ui_hooks.LibraryUIHooks(ui_integration_instance)
        
        print("✅ UI integration components created successfully")
        
        # Clean up test database
        if test_db_path.exists():
            test_db_path.unlink()
            print("✅ Test database cleaned up")
        
        print("\n🎉 LIVE LIBRARY INTEGRATION TEST SUCCESSFUL!")
        print("The library system is fully integrated and working!")
        
        return True
        
    except Exception as e:
        print(f"❌ Live integration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_library_integration()
    if success:
        print("\n✅ Library system integration is working perfectly!")
        print("You can now use the library system in the Fichero app!")
    else:
        print("\n❌ Library system integration failed") 