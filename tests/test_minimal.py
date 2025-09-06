"""
Minimal test to debug ProcessingNavigator issue
"""

import pytest
import tempfile
from pathlib import Path

from fichero.library.processing_navigator import ProcessingNavigator

def test_processing_navigator_creation():
    """Test basic ProcessingNavigator creation"""
    temp_dir = Path(tempfile.mkdtemp())
    try:
        # Create test directory
        test_path = temp_dir / "test_collection"
        test_path.mkdir()
        
        # Create documents subdirectory
        docs_dir = test_path / "documents"
        docs_dir.mkdir()
        (docs_dir / "test1.jpg").write_text("fake content")
        
        # Test ProcessingNavigator creation
        navigator = ProcessingNavigator(test_path)
        assert navigator.collection_path == test_path
        
        # Test basic functionality
        available_steps = navigator.get_available_steps()
        assert len(available_steps) >= 1  # Should at least have documents
        
        print(f"✅ ProcessingNavigator created successfully with {len(available_steps)} steps")
        
    finally:
        import shutil
        shutil.rmtree(temp_dir)

if __name__ == "__main__":
    test_processing_navigator_creation()
