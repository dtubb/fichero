#!/usr/bin/env python3
"""
App Context Test for Fichero Library System

This script tests the library system by creating a mock app context.
"""

import sys
import os
import asyncio
from pathlib import Path

# Add the src directory to Python path
src_path = Path(__file__).parent.parent.parent
sys.path.insert(0, str(src_path))

def create_mock_app():
    """Create a mock Toga app for testing"""
    class MockApp:
        class paths:
            data = Path("/tmp/fichero_test_app")
        
        def __init__(self):
            self.paths.data.mkdir(parents=True, exist_ok=True)
    
    return MockApp()

async def test_library_manager():
    """Test the library manager with mock app"""
    try:
        print("Testing Library Manager...")
        
        # Create mock app
        app = create_mock_app()
        
        # Import and test library manager
        from fichero.library.library_manager import LibraryManager
        
        library_manager = LibraryManager(app)
        print("✓ Library manager created successfully")
        
        # Test adding a collection
        collection_id = await library_manager.add_collection(
            name="Test Collection",
            collection_type="external",
            source_path="/test/path",
            description="Test collection for library system"
        )
        
        if collection_id:
            print(f"✓ Collection added successfully: {collection_id}")
            
            # Test retrieving the collection
            collection = await library_manager.get_collection(collection_id)
            if collection:
                print(f"✓ Collection retrieved: {collection.name}")
            else:
                print("❌ Failed to retrieve collection")
                return False
        else:
            print("❌ Failed to add collection")
            return False
        
        # Test getting all collections
        collections = await library_manager.get_all_collections()
        print(f"✓ Retrieved {len(collections)} collections")
        
        # Test library stats
        stats = await library_manager.get_library_stats()
        print(f"✓ Library stats: {stats}")
        
        print("✓ Library Manager test passed!")
        return True
        
    except Exception as e:
        print(f"❌ Library Manager test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_ui_integration():
    """Test the UI integration layer"""
    try:
        print("\nTesting UI Integration...")
        
        # Create mock app
        app = create_mock_app()
        
        # Import and test UI integration
        from fichero.library.library_manager import LibraryManager
        from fichero.library.ui_integration import LibraryUIIntegration
        
        library_manager = LibraryManager(app)
        ui_integration = LibraryUIIntegration(library_manager)
        print("✓ UI Integration created successfully")
        
        # Test adding collection from UI
        collection_id = await ui_integration.add_collection_from_ui(
            name="UI Test Collection",
            collection_type="local",
            description="Test collection from UI"
        )
        
        if collection_id:
            print(f"✓ UI collection added: {collection_id}")
        else:
            print("❌ Failed to add UI collection")
            return False
        
        # Test getting collections for UI
        collections = await ui_integration.get_collections_for_ui()
        print(f"✓ UI collections retrieved: {len(collections)}")
        
        print("✓ UI Integration test passed!")
        return True
        
    except Exception as e:
        print(f"❌ UI Integration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """Run all tests"""
    print("=" * 50)
    print("FICHERO LIBRARY SYSTEM - APP CONTEXT TEST")
    print("=" * 50)
    
    tests = [
        ("Library Manager", test_library_manager),
        ("UI Integration", test_ui_integration)
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        try:
            if await test_func():
                passed += 1
        except Exception as e:
            print(f"❌ {test_name} test crashed: {e}")
    
    print("\n" + "=" * 50)
    print(f"TEST SUMMARY: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 ALL TESTS PASSED!")
        print("The library system is working correctly in app context.")
        return True
    else:
        print("💥 SOME TESTS FAILED!")
        print("Check the errors above for issues.")
        return False

if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
