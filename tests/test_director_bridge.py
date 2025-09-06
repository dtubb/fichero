"""
Unit tests for LibraryDirectorBridge
"""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock, AsyncMock

from fichero.library.director_bridge import LibraryDirectorBridge
from fichero.library.processing_navigator import ProcessingNavigator

class TestLibraryDirectorBridge:
    """Test cases for LibraryDirectorBridge"""
    
    def setup_method(self):
        """Set up test environment"""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.collection_path = self.temp_dir / "test_collection"
        self.collection_path.mkdir()
        
        # Create mock director
        self.mock_director = Mock()
        self.mock_director.process_with_auto_detection = AsyncMock()
        
        # Create bridge
        self.bridge = LibraryDirectorBridge(self.mock_director)
        
        # Create test structure
        self._create_test_structure()
    
    def teardown_method(self):
        """Clean up test environment"""
        import shutil
        shutil.rmtree(self.temp_dir)
    
    def _create_test_structure(self):
        """Create test directory structure"""
        # Create documents directory
        docs_dir = self.collection_path / "documents"
        docs_dir.mkdir()
        (docs_dir / "test1.jpg").write_text("fake jpg content")
        
        # Create assets directory structure
        assets_dir = self.collection_path / "assets"
        assets_dir.mkdir()
        
        # Create rotated step
        rotated_dir = assets_dir / "rotated" / "documents"
        rotated_dir.mkdir(parents=True)
        (rotated_dir / "test1_rotated.jpg").write_text("fake rotated jpg")
        
        # Create transcriptions step
        trans_dir = assets_dir / "transcriptions" / "documents"
        trans_dir.mkdir(parents=True)
        (trans_dir / "test1.txt").write_text("This is a test transcription")
    
    @pytest.mark.asyncio
    async def test_get_collection_processing_status(self):
        """Test getting collection processing status"""
        status = await self.bridge.get_collection_processing_status(self.collection_path)
        
        assert "collection_path" in status
        assert "processing_summary" in status
        assert "available_steps" in status
        assert "total_files" in status
        assert "steps_status" in status
        
        # Check that we have some available steps
        assert len(status["available_steps"]) > 0
        assert "documents" in status["available_steps"]
        assert "rotated" in status["available_steps"]
        assert "transcriptions" in status["available_steps"]
        
        # Check steps status
        assert "documents" in status["steps_status"]
        assert "rotated" in status["steps_status"]
        assert "transcriptions" in status["steps_status"]
        
        # Check that completed steps have file counts
        assert status["steps_status"]["documents"]["status"] == "completed"
        assert status["steps_status"]["documents"]["file_count"] > 0
    
    @pytest.mark.asyncio
    async def test_process_collection(self):
        """Test processing a collection"""
        # Mock the director response
        self.mock_director.process_with_auto_detection.return_value = {
            "success": True,
            "processed_files": 1
        }
        
        result = await self.bridge.process_collection(self.collection_path)
        
        assert result["success"] is True
        assert "collection_path" in result
        assert "processed_steps" in result
        assert "results" in result
        
        # Check that we processed available steps
        assert len(result["processed_steps"]) > 0
    
    @pytest.mark.asyncio
    async def test_process_collection_with_specific_steps(self):
        """Test processing a collection with specific steps"""
        # Mock the director response
        self.mock_director.process_with_auto_detection.return_value = {
            "success": True,
            "processed_files": 1
        }
        
        result = await self.bridge.process_collection(
            self.collection_path, 
            steps=["documents", "rotated"]
        )
        
        assert result["success"] is True
        assert "documents" in result["processed_steps"]
        assert "rotated" in result["processed_steps"]
    
    @pytest.mark.asyncio
    async def test_process_collection_level(self):
        """Test processing a collection at a specific level"""
        # Create subdirectories for level testing
        subdir1 = self.collection_path / "subdir1"
        subdir1.mkdir()
        (subdir1 / "test2.jpg").write_text("fake jpg content")
        
        subdir2 = self.collection_path / "subdir2"
        subdir2.mkdir()
        (subdir2 / "test3.jpg").write_text("fake jpg content")
        
        # Mock the director response
        self.mock_director.process_with_auto_detection.return_value = {
            "success": True,
            "processed_files": 1
        }
        
        result = await self.bridge.process_collection_level(self.collection_path, level=1)
        
        assert result["success"] is True
        assert result["level"] == 1
        assert result["processed_paths"] == 2  # subdir1 and subdir2
        assert "results" in result
    
    @pytest.mark.asyncio
    async def test_preview_collection_structure(self):
        """Test previewing collection structure"""
        structure = await self.bridge.preview_collection_structure(self.collection_path, max_depth=2)
        
        assert "collection_path" in structure
        assert "max_depth" in structure
        assert "structure" in structure
        
        # Check structure tree
        tree = structure["structure"]
        assert tree["type"] == "directory"
        assert tree["name"] == self.collection_path.name
        assert "children" in tree
    
    def test_get_level_paths(self):
        """Test getting paths at specific levels"""
        # Create subdirectories
        subdir1 = self.collection_path / "subdir1"
        subdir1.mkdir()
        
        subdir2 = self.collection_path / "subdir2"
        subdir2.mkdir()
        
        # Test level 0 (root)
        level0_paths = self.bridge._get_level_paths(self.collection_path, 0)
        assert len(level0_paths) == 1
        assert level0_paths[0] == self.collection_path
        
        # Test level 1 (subdirectories)
        level1_paths = self.bridge._get_level_paths(self.collection_path, 1)
        assert len(level1_paths) == 2
        assert subdir1 in level1_paths
        assert subdir2 in level1_paths
        
        # Test level 2 (should be empty)
        level2_paths = self.bridge._get_level_paths(self.collection_path, 2)
        assert len(level2_paths) == 0
    
    def test_build_structure_tree(self):
        """Test building structure tree"""
        tree = self.bridge._build_structure_tree(self.collection_path, max_depth=2)
        
        assert tree["type"] == "directory"
        assert tree["name"] == self.collection_path.name
        assert "children" in tree
        
        # Check that we have some children
        assert len(tree["children"]) > 0
    
    @pytest.mark.asyncio
    async def test_process_collection_nonexistent_path(self):
        """Test processing a collection with nonexistent path"""
        nonexistent_path = self.temp_dir / "nonexistent"
        
        result = await self.bridge.process_collection(nonexistent_path)
        
        assert result["success"] is False
        assert "error" in result
        assert "No processing steps found" in result["error"]
    
    @pytest.mark.asyncio
    async def test_process_collection_with_invalid_steps(self):
        """Test processing a collection with invalid step names"""
        result = await self.bridge.process_collection(
            self.collection_path, 
            steps=["invalid_step1", "invalid_step2"]
        )
        
        assert result["success"] is False
        assert "error" in result
        assert "not found in available steps" in result["error"]
    
    @pytest.mark.asyncio
    async def test_director_error_handling(self):
        """Test error handling when director fails"""
        # Mock director to raise an exception
        self.mock_director.process_with_auto_detection.side_effect = Exception("Director error")
        
        result = await self.bridge.process_collection(self.collection_path)
        
        assert result["success"] is False
        assert "error" in result
        assert "Director error" in result["error"]
