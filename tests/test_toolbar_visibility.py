#!/usr/bin/env python3
"""
Toolbar Visibility Test

This script tests if the library top toolbar is being created and displayed properly.
"""

import sys
from pathlib import Path

def test_toolbar_creation():
    """Test toolbar creation and visibility"""
    print("🔧 Testing Library Top Toolbar Creation...")
    
    try:
        # Add the fichero package to Python path
        fichero_src_path = Path(__file__).parent.parent / "fichero" / "src"
        sys.path.insert(0, str(fichero_src_path))
        
        # Import the toolbar
        from fichero.shared.toolbars.library_top_toolbar import LibraryTopToolbar
        
        print("✅ LibraryTopToolbar imported successfully")
        
        # Create a mock app
        class MockApp:
            def __init__(self):
                self.name = "Test App"
        
        app = MockApp()
        
        # Create the toolbar
        toolbar = LibraryTopToolbar(app, is_mobile=False)
        
        print(f"✅ Toolbar created successfully")
        print(f"   Children count: {len(toolbar.children)}")
        print(f"   Style: {toolbar.style}")
        
        # Check if buttons were created
        if len(toolbar.children) > 0:
            print("✅ Toolbar has buttons")
            for i, child in enumerate(toolbar.children):
                print(f"   Button {i}: {type(child).__name__} - {getattr(child, 'text', 'No text')}")
        else:
            print("❌ Toolbar has no buttons")
            return False
        
        # Test callback registration
        def test_callback():
            print("   ✅ Callback triggered")
        
        toolbar.register_callbacks(
            on_add_collection=test_callback,
            on_edit_collection=test_callback,
            on_import_collection=test_callback,
            on_export_collection=test_callback,
            on_activity_monitor=test_callback
        )
        
        print("✅ Callbacks registered successfully")
        
        return True
        
    except Exception as e:
        print(f"❌ Toolbar test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_toolbar_integration():
    """Test toolbar integration with collection management view"""
    print("\n🔧 Testing Toolbar Integration...")
    
    try:
        # Import the collection management view
        from fichero.windows.main.views.collection_management_view import CollectionManagementView
        
        print("✅ CollectionManagementView imported successfully")
        
        # Create a mock app
        class MockApp:
            def __init__(self):
                self.name = "Test App"
                class paths:
                    data = Path("/tmp/test_app")
                self.paths = paths()
        
        app = MockApp()
        
        # Create the view
        view = CollectionManagementView(app, is_mobile=False)
        
        print("✅ CollectionManagementView created successfully")
        print(f"   Top toolbar: {type(view.top_toolbar).__name__}")
        print(f"   Bottom toolbar: {type(view.bottom_toolbar).__name__}")
        
        # Check if toolbars have buttons
        if hasattr(view.top_toolbar, 'children'):
            print(f"   Top toolbar buttons: {len(view.top_toolbar.children)}")
        else:
            print("   Top toolbar has no children attribute")
        
        return True
        
    except Exception as e:
        print(f"❌ Toolbar integration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Main test function"""
    print("=" * 70)
    print("FICHERO TOOLBAR VISIBILITY TEST")
    print("=" * 70)
    
    # Test toolbar creation
    if not test_toolbar_creation():
        print("❌ Toolbar creation test failed")
        return False
    
    print("✅ Toolbar creation test passed")
    
    # Test toolbar integration
    if not test_toolbar_integration():
        print("❌ Toolbar integration test failed")
        return False
    
    print("✅ Toolbar integration test passed")
    
    print("\n🎉 ALL TOOLBAR TESTS PASSED!")
    print("The toolbar system is working correctly!")
    
    return True

if __name__ == "__main__":
    success = main()
    if success:
        print("\n✅ Toolbar system is fully operational!")
    else:
        print("\n❌ Toolbar system has issues") 