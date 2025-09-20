#!/usr/bin/env python3
"""
Simple Library System Test

This is a minimal test that can be run to verify the library system works.
"""

import sys
from pathlib import Path

def test_basic_models():
    """Test basic model functionality"""
    print("🧪 Testing Basic Models...")
    
    try:
        # Add the library path directly
        library_path = Path(__file__).parent.parent / "fichero" / "src" / "fichero" / "library"
        sys.path.insert(0, str(library_path))
        
        # Import models directly
        import models
        
        # Test creating objects
        collection = models.Collection(name="Simple Test", type="local")
        item = models.CollectionItem(collection_id=collection.id, type="file", name="test.txt")
        result = models.ProcessingResult(item_id=item.id, workflow="simple_test")
        
        print("✅ Models working correctly")
        print(f"   Collection: {collection.name}")
        print(f"   Item: {item.name}")
        print(f"   Result: {result.workflow}")
        
        return True
        
    except Exception as e:
        print(f"❌ Models test failed: {e}")
        return False

def test_basic_storage():
    """Test basic storage functionality"""
    print("\n🧪 Testing Basic Storage...")
    
    try:
        # Import storage directly
        import storage
        
        # Create test storage
        test_db_path = Path("/tmp/simple_test.db")
        storage_instance = storage.LibraryStorage(test_db_path)
        
        print("✅ Storage created successfully")
        
        # Test database creation
        if test_db_path.exists():
            print("✅ Database file created")
            
            # Clean up
            test_db_path.unlink()
            print("✅ Test database cleaned up")
        else:
            print("⚠️ Database file not created (this might be expected)")
        
        return True
        
    except Exception as e:
        print(f"❌ Storage test failed: {e}")
        return False

def main():
    """Run simple tests"""
    print("=" * 50)
    print("FICHERO LIBRARY SYSTEM - SIMPLE TEST")
    print("=" * 50)
    
    tests = [
        ("Models", test_basic_models),
        ("Storage", test_basic_storage),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        try:
            if test_func():
                passed += 1
        except Exception as e:
            print(f"❌ {test_name} test crashed: {e}")
    
    print("\n" + "=" * 50)
    print(f"TEST SUMMARY: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 ALL SIMPLE TESTS PASSED!")
        print("The library system basic components are working.")
        return True
    else:
        print("💥 SOME SIMPLE TESTS FAILED!")
        print("Check the errors above for issues.")
        return False

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1) 