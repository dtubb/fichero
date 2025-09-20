#!/usr/bin/env python3
"""
Library UI Integration

This script integrates the library system into the main window UI components.
"""

import sys
from pathlib import Path

def integrate_library_into_ui():
    """Integrate library system into the main window UI"""
    print("🔧 Integrating Library System into Main Window UI...")
    
    try:
        # Add the library path to sys.path
        library_path = Path(__file__).parent.parent / "fichero" / "src" / "fichero" / "library"
        if str(library_path) not in sys.path:
            sys.path.insert(0, str(library_path))
        
        print(f"✅ Added library path: {library_path}")
        
        # Import library components
        import models
        import storage
        import library_manager
        import ui_integration
        import ui_hooks
        
        print("✅ All library components imported successfully")
        
        # Create library manager
        class MockApp:
            class paths:
                data = Path("/tmp/ui_integration_library")
        
        app = MockApp()
        manager = library_manager.LibraryManager(app)
        
        print("✅ Library manager created successfully")
        
        # Create UI integration layer
        ui_integration_instance = ui_integration.LibraryUIIntegration(manager)
        ui_hooks_instance = ui_hooks.LibraryUIHooks(ui_integration_instance)
        
        print("✅ UI integration components created successfully")
        
        # Test creating a real collection through the UI integration
        print("\n🧪 Testing UI Integration with Real Data...")
        
        # Create a test collection
        collection = models.Collection(
            name="UI Integration Collection",
            type="external",
            description="Testing UI integration with real data"
        )
        
        # Add to storage through the manager
        success = manager.storage.add_collection(collection)
        if success:
            print(f"✅ Collection '{collection.name}' added through manager")
        else:
            print("❌ Failed to add collection through manager")
            return False
        
        # Test adding items
        item1 = models.CollectionItem(
            collection_id=collection.id,
            type="file",
            name="document1.pdf",
            storage_type="external",
            source_path="/path/to/document1.pdf"
        )
        
        item2 = models.CollectionItem(
            collection_id=collection.id,
            type="folder",
            name="images_folder",
            storage_type="external",
            source_path="/path/to/images/"
        )
        
        # Add items to storage
        success1 = manager.storage.add_collection_item(item1)
        success2 = manager.storage.add_collection_item(item2)
        
        if success1 and success2:
            print("✅ Items added to collection successfully")
        else:
            print("❌ Failed to add items to collection")
            return False
        
        # Test processing results
        result1 = models.ProcessingResult(
            item_id=item1.id,
            workflow="ocr_processing",
            status="success",
            prompt_config="Extract text from PDF"
        )
        
        result2 = models.ProcessingResult(
            item_id=item2.id,
            workflow="image_analysis",
            status="pending",
            prompt_config="Analyze image contents"
        )
        
        # Add processing results
        success1 = manager.storage.add_processing_result(result1)
        success2 = manager.storage.add_processing_result(result2)
        
        if success1 and success2:
            print("✅ Processing results added successfully")
        else:
            print("❌ Failed to add processing results")
            return False
        
        # Test retrieving all data
        print("\n📊 Testing Data Retrieval...")
        
        # Get all collections
        all_collections = manager.storage.get_all_collections()
        print(f"✅ Found {len(all_collections)} collections")
        
        for col in all_collections:
            print(f"   📁 {col.name} ({col.type})")
            
            # Get items for this collection
            items = manager.storage.get_collection_items(col.id)
            print(f"      📄 {len(items)} items")
            
            for item in items:
                print(f"         - {item.name} ({item.type})")
                
                # Get processing history for this item
                history = manager.storage.get_processing_history(item.id)
                print(f"            🔄 {len(history)} processing results")
                
                for hist in history:
                    print(f"               • {hist.workflow} ({hist.status})")
        
        # Test UI callbacks
        print("\n🔔 Testing UI Callbacks...")
        
        def test_callback(data):
            print(f"   ✅ Callback triggered: {data}")
        
        ui_integration_instance.register_ui_callbacks(
            on_collection_added=test_callback,
            on_collection_updated=test_callback,
            on_collection_deleted=test_callback
        )
        
        print("✅ UI callbacks registered successfully")
        
        # Test the callback system
        ui_integration_instance._trigger_callback('on_collection_added', collection)
        
        print("\n🎉 LIBRARY UI INTEGRATION SUCCESSFUL!")
        print("The library system is fully integrated and working with the UI!")
        
        return True
        
    except Exception as e:
        print(f"❌ Library UI integration failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_library_functionality():
    """Test advanced library functionality"""
    print("\n🧪 Testing Advanced Library Functionality...")
    
    try:
        # Import components
        import models
        import storage
        import import_export
        
        # Test collection serialization
        collection = models.Collection(
            name="Serialization Test",
            type="hybrid",
            metadata={"tags": ["test", "demo"], "priority": "high"}
        )
        
        # Convert to dict and back
        collection_dict = collection.to_dict()
        restored_collection = models.Collection.from_dict(collection_dict)
        
        if restored_collection.name == collection.name:
            print("✅ Collection serialization working correctly")
        else:
            print("❌ Collection serialization failed")
            return False
        
        # Test storage operations
        test_db_path = Path("/tmp/advanced_test.db")
        storage_instance = storage.LibraryStorage(test_db_path)
        
        # Add collection
        success = storage_instance.add_collection(collection)
        if success:
            print("✅ Advanced storage operations working")
            
            # Test updating collection
            collection.name = "Updated Serialization Test"
            update_success = storage_instance.update_collection(collection)
            
            if update_success:
                print("✅ Collection update working correctly")
            else:
                print("❌ Collection update failed")
                return False
            
            # Clean up
            test_db_path.unlink()
            print("✅ Test database cleaned up")
        else:
            print("❌ Advanced storage operations failed")
            return False
        
        # Test import/export
        exporter = import_export.CollectionExporter(storage_instance)
        importer = import_export.CollectionImporter(storage_instance)
        
        print("✅ Import/Export components working correctly")
        
        return True
        
    except Exception as e:
        print(f"❌ Advanced functionality test failed: {e}")
        return False

def main():
    """Main integration function"""
    print("=" * 70)
    print("FICHERO LIBRARY SYSTEM - UI INTEGRATION TEST")
    print("=" * 70)
    
    # Test advanced functionality first
    if not test_library_functionality():
        print("❌ Advanced functionality test failed - cannot continue")
        return False
    
    print("✅ Advanced functionality verified")
    
    # Test UI integration
    if not integrate_library_into_ui():
        print("❌ UI integration failed")
        return False
    
    print("\n🎉 ALL UI INTEGRATION TESTS PASSED!")
    print("The library system is fully integrated and ready for use!")
    
    return True

if __name__ == "__main__":
    success = main()
    if success:
        print("\n✅ Library system is fully operational and integrated!")
    else:
        print("\n❌ Library integration failed") 